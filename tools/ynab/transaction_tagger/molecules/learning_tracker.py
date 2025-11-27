"""
Learning Tracker Molecule - Record Agent Decisions and User Corrections

Enables continuous learning by recording categorization decisions and user
corrections in the persistent PostgreSQL database. Integrates with sop_manager
to automatically update SOP rules when user corrections occur.

Part of Layer 2: Molecules (2-3 atom combinations)

Public API:
    - record_agent_decision(transaction_id, category_id, category_name, 
                           categorization_tier, confidence_score, method) -> bool
    - record_user_correction(transaction_id, agent_suggested_category, 
                            user_correct_category, user_correct_category_id,
                            payee_name, reasoning=None) -> bool

Example - Record Agent Decision:
    >>> from tools.ynab.transaction_tagger.molecules.learning_tracker import record_agent_decision
    >>> success = record_agent_decision(
    ...     transaction_id='txn_abc123',
    ...     category_id='cat_groceries_xyz',
    ...     category_name='Groceries',
    ...     categorization_tier=2,
    ...     confidence_score=0.95,
    ...     method='historical'
    ... )
    >>> print(success)
    True

Example - Record User Correction:
    >>> from tools.ynab.transaction_tagger.molecules.learning_tracker import record_user_correction
    >>> success = record_user_correction(
    ...     transaction_id='txn_def456',
    ...     agent_suggested_category='Dining Out',
    ...     user_correct_category='Coffee Shops',
    ...     user_correct_category_id='cat_coffee_123',
    ...     payee_name='Starbucks Pike Place',
    ...     reasoning='Starbucks is coffee shop, not restaurant'
    ... )
    >>> print(success)
    True
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

# Import atoms
from tools.ynab.transaction_tagger.atoms.db_upsert import upsert_transaction
from molecules.sop_manager import update_sop_with_rule

# Configure logger
logger = logging.getLogger(__name__)


def record_agent_decision(
    transaction_id: str,
    category_id: str,
    category_name: str,
    categorization_tier: int,
    confidence_score: float,
    method: str
) -> bool:
    """
    Record agent categorization decision in database.
    
    Updates ynab_transactions with learning metadata fields to track:
    - Which tier was used (1=SOP, 2=Historical, 3=Research)
    - Confidence score (0.0-1.0)
    - When decision was made
    
    Args:
        transaction_id: YNAB transaction ID (required)
        category_id: YNAB category ID assigned (required)
        category_name: Category name for logging (required)
        categorization_tier: 1=SOP, 2=Historical, 3=Research (required)
        confidence_score: 0.0-1.0 confidence (required)
        method: 'sop' | 'historical' | 'research' | 'reasoning' (required)
    
    Returns:
        bool: True if recorded successfully, False if failed
    
    Database Updates:
        - category_id = category_id
        - category_name = category_name
        - confidence_score = confidence_score
        - categorization_tier = categorization_tier
        - categorization_timestamp = CURRENT_TIMESTAMP
        - updated_at = CURRENT_TIMESTAMP (auto-trigger)
        - sync_version += 1 (auto-increment)
    
    Example:
        >>> success = record_agent_decision(
        ...     transaction_id='txn_abc123',
        ...     category_id='cat_groceries_xyz',
        ...     category_name='Groceries',
        ...     categorization_tier=2,
        ...     confidence_score=0.95,
        ...     method='historical'
        ... )
        >>> print(success)
        True
    """
    # 1. Validate inputs
    if not transaction_id or not isinstance(transaction_id, str):
        logger.error("Invalid transaction_id: must be non-empty string")
        return False
    
    if not category_id or not isinstance(category_id, str):
        logger.error("Invalid category_id: must be non-empty string")
        return False
    
    if not category_name or not isinstance(category_name, str):
        logger.error("Invalid category_name: must be non-empty string")
        return False
    
    if categorization_tier not in [1, 2, 3]:
        logger.error(f"Invalid categorization_tier: {categorization_tier}. Must be 1, 2, or 3")
        return False
    
    if not isinstance(confidence_score, (int, float)) or not (0.0 <= confidence_score <= 1.0):
        logger.error(f"Invalid confidence_score: {confidence_score}. Must be 0.0-1.0")
        return False
    
    valid_methods = ['sop', 'historical', 'research', 'reasoning']
    if method not in valid_methods:
        logger.error(f"Invalid method: {method}. Must be one of: {valid_methods}")
        return False
    
    # 2. Build txn_data
    txn_data = {
        'id': transaction_id,
        'category_id': category_id,
        'category_name': category_name,
        'confidence_score': float(confidence_score),
        'categorization_tier': categorization_tier,
        'categorization_timestamp': datetime.now(timezone.utc).isoformat()
    }
    
    # 3. Update database
    try:
        result = upsert_transaction(txn_data)
        
        if result['status'] != 'success':
            logger.error(f"Failed to record decision for {transaction_id}: {result.get('error')}")
            return False
        
        logger.info(
            f"Recorded decision for {transaction_id}: {category_name} "
            f"(tier {categorization_tier}, confidence {confidence_score:.2f}, method {method})"
        )
        return True
    
    except Exception as e:
        logger.error(f"Unexpected error recording decision for {transaction_id}: {e}")
        return False


def record_user_correction(
    transaction_id: str,
    agent_suggested_category: str,
    user_correct_category: str,
    user_correct_category_id: str,
    payee_name: str,
    reasoning: Optional[str] = None
) -> bool:
    """
    Record user correction to agent categorization.
    
    When user corrects agent's categorization:
    1. Updates transaction with user_corrected=True flag
    2. Appends learned rule to categorization_rules.md via sop_manager
    3. Future transactions with same payee will use this correction
    
    Args:
        transaction_id: YNAB transaction ID (required)
        agent_suggested_category: What agent originally suggested (required)
        user_correct_category: User's correct category name (required)
        user_correct_category_id: YNAB category ID (required)
        payee_name: Transaction payee for SOP pattern (required)
        reasoning: Optional explanation for correction
    
    Returns:
        bool: True if recorded successfully, False if failed
    
    Database Updates:
        1. ynab_transactions:
           - category_id = user_correct_category_id
           - category_name = user_correct_category
           - user_corrected = True
           - updated_at = CURRENT_TIMESTAMP
           - sync_version += 1
        
        2. categorization_rules.md (via sop_manager):
           Appends to "## Learned from User Corrections" section:
           - Payee: {payee_name}
           - Correct Category: {user_correct_category}
           - Category ID: {user_correct_category_id}
           - Agent Initially Suggested: {agent_suggested_category}
           - Reasoning: {reasoning}
           - Confidence: High
           - Date Learned: {timestamp}
    
    Example:
        >>> success = record_user_correction(
        ...     transaction_id='txn_def456',
        ...     agent_suggested_category='Dining Out',
        ...     user_correct_category='Coffee Shops',
        ...     user_correct_category_id='cat_coffee_123',
        ...     payee_name='Starbucks Pike Place',
        ...     reasoning='Starbucks is coffee shop, not restaurant'
        ... )
        >>> print(success)
        True
    """
    # 1. Validate inputs
    if not transaction_id or not isinstance(transaction_id, str):
        logger.error("Invalid transaction_id: must be non-empty string")
        return False
    
    if not agent_suggested_category or not isinstance(agent_suggested_category, str):
        logger.error("Invalid agent_suggested_category: must be non-empty string")
        return False
    
    if not user_correct_category or not isinstance(user_correct_category, str):
        logger.error("Invalid user_correct_category: must be non-empty string")
        return False
    
    if not user_correct_category_id or not isinstance(user_correct_category_id, str):
        logger.error("Invalid user_correct_category_id: must be non-empty string")
        return False
    
    if not payee_name or not isinstance(payee_name, str):
        logger.error("Invalid payee_name: must be non-empty string")
        return False
    
    # reasoning is optional, can be None or empty
    
    # 2. Update transaction
    txn_data = {
        'id': transaction_id,
        'category_id': user_correct_category_id,
        'category_name': user_correct_category,
        'user_corrected': True
    }
    
    try:
        result = upsert_transaction(txn_data)
        
        if result['status'] != 'success':
            logger.error(f"Failed to update transaction {transaction_id}: {result.get('error')}")
            return False
        
        logger.info(
            f"Recorded correction for {transaction_id}: {user_correct_category} "
            f"(was: {agent_suggested_category})"
        )
    
    except Exception as e:
        logger.error(f"Unexpected error updating transaction {transaction_id}: {e}")
        return False
    
    # 3. Update SOP rules
    rule_data = {
        'payee': payee_name,
        'correct_category': user_correct_category,
        'category_id': user_correct_category_id,
        'agent_initially_suggested': agent_suggested_category,
        'reasoning': reasoning or 'User correction',
        'confidence': 'High'
    }
    
    try:
        sop_success = update_sop_with_rule(
            rule_type='user_correction',
            rule_data=rule_data
        )
        
        if not sop_success:
            logger.warning(
                f"Transaction updated but SOP update failed for {payee_name}. "
                f"Manual SOP update may be required."
            )
        else:
            logger.info(f"SOP updated with correction rule for {payee_name}")
    
    except Exception as e:
        logger.warning(
            f"Transaction updated but SOP update raised exception for {payee_name}: {e}"
        )
    
    # Return True even if SOP update failed (transaction is most critical)
    return True
