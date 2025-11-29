"""
Pattern Analyzer Molecule - Tier 2 Historical Pattern Matching

Analyzes transactions using historical data patterns to recommend categories.
Part of the 3-tier categorization decision logic:
- Tier 1: SOP Rules (explicit rules)
- Tier 2: Pattern Analyzer (historical patterns) ← THIS MODULE
- Tier 3: Research + Reasoning (Claude AI with WebSearch)

Composes the historical_match atom to provide pattern-based recommendations
with ≥80% confidence threshold.
"""

from typing import Dict, Any, Optional
import logging
from tools.ynab.transaction_tagger.atoms.historical_match import find_historical_category

# Configure logging
logger = logging.getLogger(__name__)


def _validate_transaction(txn: Dict[str, Any]) -> bool:
    """
    Validate transaction has required fields.
    
    Args:
        txn: Transaction dict to validate
    
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(txn, dict):
        logger.error("Transaction must be dict")
        return False
    
    if 'payee_name' not in txn or not txn['payee_name']:
        logger.error("Transaction missing payee_name")
        return False
    
    if not isinstance(txn['payee_name'], str):
        logger.error("payee_name must be string")
        return False
    
    return True


def _build_reasoning(payee_name: str, match: Dict[str, Any]) -> str:
    """
    Generate human-readable reasoning for pattern match.
    
    Args:
        payee_name: Payee name that was matched
        match: Match result from historical_match atom
    
    Returns:
        Formatted reasoning string
    
    Example:
        >>> _build_reasoning("Starbucks", {
        ...     'confidence': 0.95,
        ...     'match_count': 47,
        ...     'category_name': 'Coffee Shops'
        ... })
        'Based on 47 previous transactions with "Starbucks", 95% were categorized as "Coffee Shops".'
    """
    confidence_pct = int(match['confidence'] * 100)
    match_count = match['match_count']
    category_name = match['category_name']
    
    return (
        f'Based on {match_count} previous transactions with "{payee_name}", '
        f'{confidence_pct}% were categorized as "{category_name}".'
    )


def analyze_transaction(txn: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Analyze transaction using historical patterns (Tier 2).
    
    Uses PostgreSQL find_historical_category() to find category based on
    historical payee patterns with ≥80% confidence threshold.
    
    Args:
        txn: Transaction dict with required keys:
            - payee_name: str (required, must be non-empty)
            - amount: int (optional, milliunits for amount-based matching)
            - id: str (transaction ID for logging)
    
    Returns:
        Dict with category recommendation if match found:
        {
            'type': 'single',
            'category_id': str,
            'category_name': str,
            'confidence': float,       # 0.0-1.0 (will be ≥0.80)
            'method': 'historical',
            'reasoning': str,          # Explanation of match
            'match_count': int,        # Number of historical matches
            'source': 'pattern_analyzer'
        }
        
        None if no match found or error occurs.
    
    Example - Match Found:
        >>> txn = {
        ...     'id': 'txn_123',
        ...     'payee_name': 'Starbucks Coffee',
        ...     'amount': -450000  # -$45.00 in milliunits
        ... }
        >>> result = analyze_transaction(txn)
        >>> result
        {
            'type': 'single',
            'category_id': 'cat_coffee_xyz',
            'category_name': 'Coffee Shops',
            'confidence': 0.95,
            'method': 'historical',
            'reasoning': 'Based on 47 previous transactions with "Starbucks Coffee", 95% were categorized as "Coffee Shops".',
            'match_count': 47,
            'source': 'pattern_analyzer'
        }
    
    Example - No Match:
        >>> txn = {
        ...     'id': 'txn_456',
        ...     'payee_name': 'Unknown New Merchant'
        ... }
        >>> result = analyze_transaction(txn)
        >>> result
        None  # No historical pattern found
    """
    # 1. Validate input
    if not _validate_transaction(txn):
        return None
    
    # 2. Extract fields
    payee_name = txn['payee_name']
    amount = txn.get('amount')  # Optional
    txn_id = txn.get('id', 'unknown')
    
    logger.info(f"Analyzing transaction {txn_id} for payee: {payee_name}")
    
    # 3. Query historical patterns
    match = find_historical_category(
        payee_name=payee_name,
        amount=amount,
        min_confidence=0.0  # Return top match regardless of confidence percentage
    )
    
    # 4. No match found
    if not match:
        logger.info(f"No historical pattern found for {payee_name}")
        return None
    
    # 5. Format result
    result = {
        'type': 'single',
        'category_id': match['category_id'],
        'category_name': match['category_name'],
        'confidence': match['confidence'],
        'method': 'historical',
        'reasoning': _build_reasoning(payee_name, match),
        'match_count': match['match_count'],
        'source': 'pattern_analyzer'
    }
    
    logger.info(f"Historical match found: {match['category_name']} "
               f"(confidence: {match['confidence']:.2%})")
    
    return result
