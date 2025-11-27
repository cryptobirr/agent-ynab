"""
YNAB Syncer Molecule - Batch sync approved categorizations to YNAB API

Orchestrates api_update atom to handle both single-category and split
transactions, with learning_tracker integration for continuous improvement.

Part of Layer 2: Molecules (2-3 atom combinations)

Public API:
    - sync_approved_changes(budget_id, approved_changes) -> Dict

Example - Single Transaction:
    >>> changes = [{
    ...     'transaction_id': 'txn_abc',
    ...     'category_id': 'cat_groceries',
    ...     'category_name': 'Groceries',
    ...     'categorization_tier': 2,
    ...     'confidence_score': 0.95,
    ...     'method': 'historical'
    ... }]
    >>> result = sync_approved_changes('budget_xyz', changes)
    >>> print(result)
    {'status': 'success', 'total': 1, 'succeeded': 1, 'failed': 0, 'conflicts': 0, 'errors': []}

Example - Split Transaction:
    >>> changes = [{
    ...     'transaction_id': 'txn_def',
    ...     'is_split': True,
    ...     'amount': -15000,
    ...     'subtransactions': [
    ...         {'amount': -10000, 'category_id': 'cat_groceries', 'memo': 'Food'},
    ...         {'amount': -5000, 'category_id': 'cat_supplies', 'memo': 'Paper'}
    ...     ],
    ...     'categorization_tier': 1,
    ...     'confidence_score': 0.98,
    ...     'method': 'sop'
    ... }]
    >>> result = sync_approved_changes('budget_xyz', changes)
    >>> print(result)
    {'status': 'success', 'total': 1, 'succeeded': 1, 'failed': 0, 'conflicts': 0, 'errors': []}
"""

import logging
from typing import Dict, List, Any

# Import atoms
from tools.ynab.transaction_tagger.atoms.api_update import (
    update_transaction_category,
    update_split_transaction
)
from common.base_client import YNABAPIError, YNABConflictError

# Import molecules
from tools.ynab.transaction_tagger.molecules.learning_tracker import (
    record_agent_decision
)

# Configure logger
logger = logging.getLogger(__name__)


def _validate_inputs(
    budget_id: str,
    approved_changes: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Validate sync_approved_changes inputs.
    
    Returns error dict if validation fails, None if valid.
    """
    # Validate budget_id
    if not budget_id or not isinstance(budget_id, str):
        return {
            'status': 'failed',
            'total': 0,
            'succeeded': 0,
            'failed': 0,
            'conflicts': 0,
            'errors': [{
                'transaction_id': None,
                'error': 'Invalid budget_id: must be non-empty string',
                'type': 'validation_error'
            }]
        }
    
    # Validate approved_changes
    if not isinstance(approved_changes, list) or len(approved_changes) == 0:
        return {
            'status': 'failed',
            'total': 0,
            'succeeded': 0,
            'failed': 0,
            'conflicts': 0,
            'errors': [{
                'transaction_id': None,
                'error': 'Invalid approved_changes: must be non-empty list',
                'type': 'validation_error'
            }]
        }
    
    # Validate each change has required fields
    for idx, change in enumerate(approved_changes):
        if 'transaction_id' not in change:
            return {
                'status': 'failed',
                'total': 0,
                'succeeded': 0,
                'failed': 0,
                'conflicts': 0,
                'errors': [{
                    'transaction_id': None,
                    'error': f'Change at index {idx} missing transaction_id',
                    'type': 'validation_error'
                }]
            }
        
        # Check for single transaction required fields
        if not change.get('is_split', False):
            required = ['category_id', 'category_name', 'categorization_tier', 
                       'confidence_score', 'method']
            missing = [f for f in required if f not in change]
            if missing:
                return {
                    'status': 'failed',
                    'total': 0,
                    'succeeded': 0,
                    'failed': 0,
                    'conflicts': 0,
                    'errors': [{
                        'transaction_id': change['transaction_id'],
                        'error': f'Missing required fields: {missing}',
                        'type': 'validation_error'
                    }]
                }
        
        # Check for split transaction required fields
        else:
            required = ['amount', 'subtransactions', 'categorization_tier',
                       'confidence_score', 'method']
            missing = [f for f in required if f not in change]
            if missing:
                return {
                    'status': 'failed',
                    'total': 0,
                    'succeeded': 0,
                    'failed': 0,
                    'conflicts': 0,
                    'errors': [{
                        'transaction_id': change['transaction_id'],
                        'error': f'Split transaction missing required fields: {missing}',
                        'type': 'validation_error'
                    }]
                }
    
    # All valid
    return None


def sync_approved_changes(
    budget_id: str,
    approved_changes: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Sync approved transaction categorizations to YNAB API.
    
    Processes list of approved changes, updating YNAB via API and
    recording successful syncs in learning database. Handles both
    single-category and split transactions transparently.
    
    Args:
        budget_id: YNAB budget ID (UUID format)
        approved_changes: List of approved transaction dicts with structure:
            
            Single transaction:
            {
                'transaction_id': str (required),
                'category_id': str (required),
                'category_name': str (required),
                'categorization_tier': int (1-3, required),
                'confidence_score': float (0.0-1.0, required),
                'method': str ('sop' | 'historical' | 'research' | 'reasoning', required),
                'is_split': False (or omitted)
            }
            
            Split transaction:
            {
                'transaction_id': str (required),
                'is_split': True (required),
                'amount': int (milliunits, required - for validation),
                'subtransactions': List[Dict] (required):
                    [
                        {
                            'amount': int (milliunits),
                            'category_id': str (UUID),
                            'memo': str (optional)
                        },
                        ...
                    ],
                'categorization_tier': int (1-3, required),
                'confidence_score': float (0.0-1.0, required),
                'method': str (required)
            }
    
    Returns:
        Dict with structure:
        {
            'status': 'success' | 'partial' | 'failed',
            'total': int (total transactions processed),
            'succeeded': int (successful updates),
            'failed': int (failed updates),
            'conflicts': int (version conflicts),
            'errors': List[Dict] (details of failures):
                [
                    {
                        'transaction_id': str,
                        'error': str,
                        'type': 'conflict' | 'api_error' | 'validation_error'
                    },
                    ...
                ]
        }
    
    Processing Logic:
        1. Validate inputs (budget_id, approved_changes array)
        2. For each approved change:
           a. Determine transaction type (single vs split)
           b. Call appropriate api_update function
           c. If successful: record_agent_decision() for learning
           d. If conflict/error: log and continue to next
        3. Return summary with success/failure counts
    
    Error Handling:
        - Invalid inputs → Return {'status': 'failed', 'errors': [...]}
        - API conflicts (409) → Log, increment conflicts, continue
        - API errors → Log, increment failed, continue
        - Learning tracker failures → Log warning, continue (non-critical)
    """
    # 1. Validate inputs
    validation_error = _validate_inputs(budget_id, approved_changes)
    if validation_error:
        logger.error(f"Input validation failed: {validation_error['errors'][0]['error']}")
        return validation_error
    
    # 2. Initialize counters
    total = len(approved_changes)
    succeeded = 0
    failed = 0
    conflicts = 0
    errors = []
    
    logger.info(f"Starting sync of {total} approved changes to budget {budget_id}")
    
    # 3. Process each change
    for idx, change in enumerate(approved_changes):
        txn_id = change['transaction_id']
        is_split = change.get('is_split', False)
        
        logger.debug(f"Processing {idx+1}/{total}: {txn_id} (split={is_split})")
        
        try:
            # Determine transaction type and call appropriate atom
            if is_split:
                # Split transaction
                success = update_split_transaction(
                    budget_id=budget_id,
                    transaction_id=txn_id,
                    subtransactions=change['subtransactions'],
                    expected_amount=change['amount']
                )
            else:
                # Single transaction
                success = update_transaction_category(
                    budget_id=budget_id,
                    transaction_id=txn_id,
                    category_id=change['category_id']
                )
            
            # Handle result
            if success:
                succeeded += 1
                logger.info(f"✅ Successfully synced {txn_id}")
                
                # Record in learning database
                try:
                    if is_split:
                        # Use first subtransaction category as primary
                        primary_cat_id = change['subtransactions'][0]['category_id']
                        cat_name = 'Split Transaction'
                    else:
                        primary_cat_id = change['category_id']
                        cat_name = change['category_name']
                    
                    record_agent_decision(
                        transaction_id=txn_id,
                        category_id=primary_cat_id,
                        category_name=cat_name,
                        categorization_tier=change['categorization_tier'],
                        confidence_score=change['confidence_score'],
                        method=change['method']
                    )
                    logger.debug(f"Recorded decision for {txn_id} in learning database")
                
                except Exception as e:
                    logger.warning(
                        f"Failed to record decision for {txn_id} in learning database: {e}. "
                        f"Transaction was synced successfully."
                    )
            
            else:
                # Conflict (409)
                conflicts += 1
                error_msg = 'Version conflict - transaction modified externally'
                errors.append({
                    'transaction_id': txn_id,
                    'error': error_msg,
                    'type': 'conflict'
                })
                logger.warning(f"⚠️  Conflict for {txn_id}: {error_msg}")
        
        except ValueError as e:
            # Validation error (split amounts, etc.)
            failed += 1
            errors.append({
                'transaction_id': txn_id,
                'error': str(e),
                'type': 'validation_error'
            })
            logger.error(f"❌ Validation error for {txn_id}: {e}")
        
        except YNABAPIError as e:
            # API error (401, 404, 429, network)
            failed += 1
            errors.append({
                'transaction_id': txn_id,
                'error': str(e),
                'type': 'api_error'
            })
            logger.error(f"❌ API error for {txn_id}: {e}")
        
        except Exception as e:
            # Unexpected error
            failed += 1
            errors.append({
                'transaction_id': txn_id,
                'error': f'Unexpected error: {str(e)}',
                'type': 'unexpected_error'
            })
            logger.error(f"❌ Unexpected error for {txn_id}: {e}")
    
    # 4. Determine final status
    if failed > 0 or (succeeded == 0 and total > 0):
        status = 'failed'
    elif conflicts > 0 or len(errors) > 0:
        status = 'partial'
    else:
        status = 'success'
    
    # 5. Build result
    result = {
        'status': status,
        'total': total,
        'succeeded': succeeded,
        'failed': failed,
        'conflicts': conflicts,
        'errors': errors
    }
    
    logger.info(
        f"Sync complete: {status.upper()} - "
        f"{succeeded}/{total} succeeded, {failed} failed, {conflicts} conflicts"
    )
    
    return result
