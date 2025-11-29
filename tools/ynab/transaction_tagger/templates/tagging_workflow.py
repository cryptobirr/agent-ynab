"""
Tagging Workflow Template - Orchestrate 3-tier categorization workflow.

Layer 4: Templates (full workflow orchestration)
Composes organisms and molecules to generate recommendations and submit changes.

Public API:
    - generate_recommendations(budget_type, start_date, end_date, uncategorized_only)
    - submit_approved_changes(budget_id, approved_changes)

Example:
    >>> from tools.ynab.transaction_tagger.templates.tagging_workflow import (
    ...     generate_recommendations,
    ...     submit_approved_changes
    ... )
    >>> 
    >>> # Generate recommendations for both budgets
    >>> result = generate_recommendations(budget_type='both')
    >>> 
    >>> # Submit approved changes
    >>> sync_result = submit_approved_changes(
    ...     budget_id=result['budgets']['personal']['budget_id'],
    ...     approved_changes=result['budgets']['personal']['transactions'][:10]
    ... )
"""

import logging
import os
from typing import Dict, List, Any, Optional
from datetime import datetime

# Import atoms
from tools.ynab.transaction_tagger.atoms.api_fetch import (
    fetch_transactions,
    fetch_categories
)
from tools.ynab.transaction_tagger.atoms.sop_loader import (
    load_categorization_rules
)
from tools.ynab.transaction_tagger.atoms.db_init import initialize_database
from tools.ynab.transaction_tagger.atoms.db_check_init import (
    check_init_budget_loaded,
    mark_init_budget_loaded
)
from tools.ynab.transaction_tagger.atoms.db_upsert import upsert_transaction

# Import molecules
from tools.ynab.transaction_tagger.molecules.pattern_analyzer import (
    analyze_transaction
)
from tools.ynab.transaction_tagger.molecules.ynab_syncer import (
    sync_approved_changes as _sync_approved_changes
)

# Import common utilities
from common.vault_client import VaultClient
from common.base_client import YNABAPIError

# Configure logger
logger = logging.getLogger(__name__)

# Constants
TIER_1_CONFIDENCE_THRESHOLD = 0.95  # SOP rules
TIER_2_CONFIDENCE_THRESHOLD = 0.80  # Historical patterns

# Two-Budget Architecture (PRD v3.5)
INIT_BUDGET_ID = "75f63aa3-9f8f-4dcc-9350-d22535494657"  # One-time historical import
TARGET_BUDGET_ID = "eaf7c5cb-e008-4b62-9733-e7d0ca96cbf1"  # Ongoing operations


def _load_budget_config(budget_type: str) -> Dict[str, Any]:
    """
    Load budget configuration using TARGET_BUDGET_ID (two-budget architecture).

    Args:
        budget_type: 'personal' | 'business' | 'both'

    Returns:
        Dict with budget configurations using TARGET_BUDGET_ID:
        {
            'personal': {'budget_id': TARGET_BUDGET_ID, 'budget_name': 'Personal Budget'}
        }

    Note:
        Uses TARGET_BUDGET_ID for ongoing operations.
        INIT_BUDGET_ID is only used once to populate historical data.
    """
    # Validate budget_type
    if budget_type not in ['personal', 'business', 'both']:
        raise ValueError(f"Invalid budget_type: {budget_type}. Must be 'personal', 'business', or 'both'")

    # For two-budget architecture, always use TARGET_BUDGET_ID for ongoing operations
    budgets = {}

    if budget_type in ['personal', 'both']:
        budgets['personal'] = {
            'budget_id': TARGET_BUDGET_ID,
            'budget_name': 'Personal Budget'
        }

    # Business budget not used in current PRD implementation
    # if budget_type in ['business', 'both']:
    #     budgets['business'] = {
    #         'budget_id': 'future-business-budget-id',
    #         'budget_name': 'Business Budget'
    #     }

    logger.info(f"Loaded budget config for: {', '.join(budgets.keys())}")
    return budgets


def _load_budget_from_env(budget_type: str) -> Dict[str, Any]:
    """
    Load budget configuration from environment variables (fallback).
    
    Expected env vars:
        YNAB_PERSONAL_BUDGET_ID
        YNAB_BUSINESS_BUDGET_ID
    
    Args:
        budget_type: 'personal' | 'business' | 'both'
    
    Returns:
        Dict with budget configurations
    
    Raises:
        ValueError: If required env vars missing
    """
    budgets = {}
    
    if budget_type in ['personal', 'both']:
        personal_id = os.getenv('YNAB_PERSONAL_BUDGET_ID')
        if not personal_id:
            raise ValueError("Missing YNAB_PERSONAL_BUDGET_ID environment variable")
        budgets['personal'] = {
            'budget_id': personal_id,
            'budget_name': 'Personal Budget'
        }
    
    if budget_type in ['business', 'both']:
        business_id = os.getenv('YNAB_BUSINESS_BUDGET_ID')
        if not business_id:
            raise ValueError("Missing YNAB_BUSINESS_BUDGET_ID environment variable")
        budgets['business'] = {
            'budget_id': business_id,
            'budget_name': 'Business Budget'
        }
    
    logger.info(f"Loaded budget config from .env for: {', '.join(budgets.keys())}")
    return budgets


def _check_sop_rules(txn: Dict[str, Any], rules: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Check transaction against SOP rules (Tier 1).

    Checks core_patterns and user_corrections sections.
    Returns first match with confidence ≥ 0.95.

    Special handling for transfers: YNAB transfers between accounts should NOT
    be categorized (they remain without a category per YNAB standard).

    Args:
        txn: Transaction dict with 'payee_name'
        rules: SOP rules from load_categorization_rules()

    Returns:
        Match dict or None:
        {
            'category_id': None,  # ID not available from SOP
            'category_name': str or 'SKIP_TRANSFER',
            'confidence': 1.0,    # High confidence for SOP rules
            'reasoning': str
        }
    """
    payee_name = txn.get('payee_name', '')

    if not payee_name:
        return None

    # PRIORITY 1: Check for YNAB transfer pattern (highest priority)
    # Pattern: "Transfer : Account Name" or "Transfer: Account Name"
    import re
    if re.match(r'^Transfer\s*:', payee_name, re.IGNORECASE):
        return {
            'category_id': None,
            'category_name': 'SKIP_TRANSFER',  # Special marker to skip categorization
            'confidence': 1.0,
            'reasoning': 'YNAB transfer between accounts - transfers are not categorized per YNAB standard'
        }

    # PRIORITY 2: Check for inflows (positive amounts) - should be "Ready to Assign"
    # YNAB standard: All income goes to "Ready to Assign" unless it's a transfer
    amount = txn.get('amount', 0)
    if amount > 0:
        return {
            'category_id': None,
            'category_name': 'INFLOW_READY_TO_ASSIGN',  # Special marker for inflows
            'confidence': 1.0,
            'reasoning': 'YNAB standard: Inflows are categorized as "Ready to Assign"'
        }

    payee_name_lower = payee_name.lower()

    # Check user corrections first (highest priority after transfers)
    for correction in rules.get('user_corrections', []):
        if correction.get('payee', '').lower() == payee_name_lower:
            return {
                'category_id': None,  # Will need category lookup
                'category_name': correction.get('correct_category'),
                'confidence': 1.0,
                'reasoning': f"User correction: {correction.get('reasoning', 'Previously corrected by user')}"
            }
    
    # Check core patterns
    for pattern in rules.get('core_patterns', []):
        pattern_str = pattern.get('pattern', '')
        pattern_type = pattern.get('pattern_type', 'exact')
        
        matched = False
        
        if pattern_type == 'exact':
            matched = payee_name == pattern_str.lower()
        elif pattern_type == 'prefix':
            matched = payee_name.startswith(pattern_str.lower().rstrip('*'))
        elif pattern_type == 'contains':
            matched = pattern_str.lower().strip('*') in payee_name
        elif pattern_type == 'regex':
            import re
            matched = bool(re.search(pattern_str, payee_name, re.IGNORECASE))
        
        if matched:
            # Check confidence level
            confidence_str = pattern.get('confidence', 'Low')
            confidence = {
                'High': 1.0,
                'Medium': 0.85,
                'Low': 0.70
            }.get(confidence_str, 0.70)
            
            if confidence >= TIER_1_CONFIDENCE_THRESHOLD:
                return {
                    'category_id': None,
                    'category_name': pattern.get('category'),
                    'confidence': confidence,
                    'reasoning': f"SOP rule: {pattern.get('source', 'Unknown source')}"
                }
    
    return None


def _categorize_transaction(txn: Dict[str, Any], rules: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply 3-tier categorization logic to single transaction.
    
    Tier 1: SOP Rules (confidence ≥ 0.95)
    Tier 2: Historical Patterns (confidence ≥ 0.80)
    Tier 3: Manual Review (no match)
    
    Args:
        txn: Transaction dict
        rules: SOP rules from load_categorization_rules()
    
    Returns:
        Enriched transaction dict with categorization metadata
    """
    txn_id = txn.get('id', 'unknown')
    
    # Tier 1: SOP Rules
    sop_match = _check_sop_rules(txn, rules)
    if sop_match and sop_match['confidence'] >= TIER_1_CONFIDENCE_THRESHOLD:
        logger.debug(f"Tier 1 (SOP) match for {txn_id}: {sop_match['category_name']}")
        return {
            **txn,
            'category_id': sop_match.get('category_id') or txn.get('category_id'),
            'category_name': sop_match['category_name'],
            'type': 'single',
            'confidence': sop_match['confidence'],
            'tier': 'sop',
            'method': 'sop',
            'reasoning': sop_match['reasoning']
        }
    
    # Tier 2: Historical Patterns
    historical_match = analyze_transaction(txn)
    if historical_match:
        logger.debug(f"Tier 2 (Historical) match for {txn_id}: {historical_match['category_name']}")
        return {
            **txn,
            'category_id': historical_match['category_id'],
            'category_name': historical_match['category_name'],
            'type': historical_match.get('type', 'single'),
            'confidence': historical_match['confidence'],
            'tier': 'historical',
            'method': 'historical',
            'reasoning': historical_match['reasoning']
        }
    
    # Tier 3: Manual Review
    logger.debug(f"No tier match for {txn_id}, marking for manual review")
    return {
        **txn,
        'category_id': None,
        'category_name': 'Uncategorized',
        'type': 'single',
        'confidence': 0.0,
        'tier': 'research',
        'method': 'manual',
        'reasoning': 'No SOP rule or historical pattern found. Requires manual categorization.'
    }


def _build_summary(transactions: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Build summary statistics for categorized transactions.
    
    Args:
        transactions: List of categorized transactions
    
    Returns:
        Summary dict:
        {
            'total': 100,
            'sop_matches': 45,
            'historical_matches': 40,
            'needs_review': 15
        }
    """
    total = len(transactions)
    sop_matches = sum(1 for t in transactions if t.get('tier') == 'sop')
    historical_matches = sum(1 for t in transactions if t.get('tier') == 'historical')
    needs_review = sum(1 for t in transactions if t.get('tier') == 'research')
    
    return {
        'total': total,
        'sop_matches': sop_matches,
        'historical_matches': historical_matches,
        'needs_review': needs_review
    }


def generate_recommendations(
    budget_type: str = 'both',
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    uncategorized_only: bool = True
) -> Dict[str, Any]:
    """
    Generate categorization recommendations for transactions.
    
    Applies 3-tier categorization logic:
    - Tier 1: SOP Rules (confidence ≥ 0.95)
    - Tier 2: Historical Patterns (confidence ≥ 0.80)
    - Tier 3: Manual Review (no match)
    
    Args:
        budget_type: 'personal' | 'business' | 'both' (default: 'both')
        start_date: ISO date string (YYYY-MM-DD), None = 90 days ago
        end_date: ISO date string (YYYY-MM-DD), None = today
        uncategorized_only: Only fetch uncategorized transactions (default: True)
    
    Returns:
        Dict with recommendations:
        {
            'status': 'success' | 'partial' | 'failed',
            'budgets': {
                'personal': {
                    'budget_id': str,
                    'budget_name': str,
                    'transactions': List[Dict],  # Categorized transactions
                    'category_groups': List[Dict],
                    'summary': {
                        'total': int,
                        'sop_matches': int,
                        'historical_matches': int,
                        'needs_review': int
                    }
                },
                'business': {...}
            },
            'errors': List[Dict],
            'timestamp': str  # ISO 8601
        }
    """
    # Step 1: Initialize database (idempotent)
    logger.info("Initializing database...")
    db_result = initialize_database()
    if db_result['status'] == 'error':
        return {
            'status': 'failed',
            'errors': [{
                'type': 'database_init_error',
                'error': db_result['error']
            }],
            'budgets': {},
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
    logger.info(f"Database initialization: {db_result['status']}")

    # Step 2: Check if historical data has been loaded from INIT_BUDGET
    if not check_init_budget_loaded():
        logger.info("INIT_BUDGET data not loaded. Loading historical transactions...")
        try:
            # Fetch ALL transactions from INIT_BUDGET (historical data for learning)
            init_transactions = fetch_transactions(INIT_BUDGET_ID)
            logger.info(f"Fetched {len(init_transactions)} transactions from INIT_BUDGET")

            # Upsert all into database (with existing categories for learning)
            for txn in init_transactions:
                # Add budget_id to transaction data (required by upsert_transaction)
                txn['budget_id'] = INIT_BUDGET_ID
                upsert_transaction(txn)

            # Mark as loaded
            mark_init_budget_loaded(INIT_BUDGET_ID, len(init_transactions))
            logger.info(f"Historical data loaded successfully: {len(init_transactions)} transactions")

        except YNABAPIError as e:
            logger.error(f"Failed to load INIT_BUDGET data: {e}")
            return {
                'status': 'failed',
                'errors': [{
                    'type': 'init_budget_load_error',
                    'error': f"Failed to load historical data from INIT_BUDGET: {str(e)}"
                }],
                'budgets': {},
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
    else:
        logger.info("INIT_BUDGET data already loaded, skipping historical import")

    # Validate budget_type
    if budget_type not in ['personal', 'business', 'both']:
        return {
            'status': 'failed',
            'errors': [{
                'type': 'validation_error',
                'error': f"Invalid budget_type: {budget_type}"
            }],
            'budgets': {},
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    # Load budget configuration
    try:
        budgets = _load_budget_config(budget_type)
    except ValueError as e:
        return {
            'status': 'failed',
            'errors': [{
                'type': 'config_error',
                'error': str(e)
            }],
            'budgets': {},
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    # Load SOP rules (once)
    try:
        rules = load_categorization_rules()
    except Exception as e:
        logger.error(f"Failed to load SOP rules: {e}")
        rules = {
            'core_patterns': [],
            'split_patterns': [],
            'user_corrections': [],
            'web_research': []
        }
    
    # Process each budget
    result = {
        'status': 'success',
        'budgets': {},
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'errors': []
    }
    
    for budget_name, budget_config in budgets.items():
        budget_id = budget_config['budget_id']
        
        try:
            # Fetch transactions
            transactions = fetch_transactions(budget_id, since_date=start_date)
            
            # Filter by uncategorized if requested
            # Definition: unapproved OR uncleared OR no category
            if uncategorized_only:
                transactions = [
                    t for t in transactions
                    if not t.get('approved') or
                       t.get('cleared') == 'uncleared' or
                       not t.get('category_id')
                ]
            
            # Filter by date range
            if end_date:
                end = datetime.fromisoformat(end_date)
                transactions = [t for t in transactions 
                              if datetime.fromisoformat(t['date']) <= end]
            
            # Categorize each transaction
            categorized = []
            for txn in transactions:
                categorized.append(_categorize_transaction(txn, rules))
            
            # Fetch category groups
            try:
                from tools.ynab.transaction_tagger.atoms.api_fetch import fetch_category_groups
                category_groups = fetch_category_groups(budget_id)
            except YNABAPIError as e:
                logger.warning(f"Failed to fetch categories for {budget_name}: {e}")
                category_groups = []
            
            # Build summary
            summary = _build_summary(categorized)
            
            # Add to result
            result['budgets'][budget_name] = {
                'budget_id': budget_id,
                'budget_name': budget_config['budget_name'],
                'transactions': categorized,
                'category_groups': category_groups,
                'summary': summary
            }
        
        except YNABAPIError as e:
            result['errors'].append({
                'type': 'api_error',
                'budget': budget_name,
                'error': str(e)
            })
            result['status'] = 'partial' if len(result['budgets']) > 0 else 'failed'
    
    return result


def submit_approved_changes(
    budget_id: str,
    approved_changes: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Submit approved transaction categorizations to YNAB API.
    
    Delegates to ynab_syncer.sync_approved_changes().
    Adds timestamp to result.
    
    Args:
        budget_id: YNAB budget UUID
        approved_changes: List of approved categorizations
    
    Returns:
        Sync result dict from ynab_syncer with added timestamp
    """
    logger.info(f"Submitting {len(approved_changes)} approved changes to budget {budget_id}")
    
    # Delegate to ynab_syncer
    result = _sync_approved_changes(budget_id, approved_changes)
    
    # Add timestamp
    result['timestamp'] = datetime.utcnow().isoformat() + 'Z'
    
    logger.info(f"Sync complete: {result['status']} - "
               f"{result['succeeded']}/{result['total']} succeeded")
    
    return result
