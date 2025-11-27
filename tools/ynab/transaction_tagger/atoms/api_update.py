"""API update atom - Pure functions for YNAB API transaction updates"""
import logging
from typing import Dict, List, Any
from common.base_client import BaseYNABClient, YNABConflictError

logger = logging.getLogger(__name__)


def update_transaction_category(
    budget_id: str,
    transaction_id: str,
    category_id: str
) -> bool:
    """
    Update a single transaction's category via YNAB API.
    
    Uses YNAB PUT /budgets/{budget_id}/transactions/{transaction_id} endpoint.
    Updates only the category_id field, preserving all other transaction fields.
    
    Note: If the transaction is a split transaction, updating category_id will
    convert it to a regular transaction and clear all subtransactions.
    
    Args:
        budget_id: YNAB budget identifier (UUID format)
        transaction_id: YNAB transaction identifier (UUID format)
        category_id: YNAB category identifier (UUID format)
    
    Returns:
        bool: True if update succeeded, False if failed (conflict)
    
    Raises:
        YNABAPIError: On API errors (401, 404, 429, network errors)
    
    Example:
        >>> success = update_transaction_category(
        ...     budget_id='budget-abc-123',
        ...     transaction_id='txn-def-456',
        ...     category_id='cat-ghi-789'
        ... )
        >>> print(success)
        True
    """
    logger.info(f"Updating transaction {transaction_id} to category {category_id}")
    
    client = BaseYNABClient()
    endpoint = f'/budgets/{budget_id}/transactions/{transaction_id}'
    payload = {
        'transaction': {
            'category_id': category_id
        }
    }
    
    try:
        response = client.put(endpoint, payload)
        logger.info(f"Successfully updated transaction {transaction_id}")
        return True
    
    except YNABConflictError:
        logger.warning(f"Transaction {transaction_id} conflict (outdated version)")
        return False


def _validate_subtransaction_amounts(
    subtransactions: List[Dict[str, Any]],
    expected_total: int
) -> None:
    """
    Validate subtransaction amounts sum to expected total.
    
    Args:
        subtransactions: List of subtransaction dicts with 'amount' field
        expected_total: Expected sum in milliunits
    
    Raises:
        ValueError: If amounts don't sum to expected total or list is empty
    """
    if not subtransactions:
        raise ValueError("Subtransactions list cannot be empty")
    
    actual_sum = sum(st.get('amount', 0) for st in subtransactions)
    
    if actual_sum != expected_total:
        diff_milliunits = abs(actual_sum - expected_total)
        diff_dollars = diff_milliunits / 1000
        raise ValueError(
            f"Subtransaction amounts sum to {actual_sum} milliunits, "
            f"expected {expected_total} milliunits. "
            f"Difference: {diff_milliunits} milliunits (${diff_dollars:.2f})"
        )


def update_split_transaction(
    budget_id: str,
    transaction_id: str,
    subtransactions: List[Dict[str, Any]],
    expected_amount: int
) -> bool:
    """
    Update a split transaction's subtransaction categories via YNAB API.
    
    Uses YNAB PUT /budgets/{budget_id}/transactions/{transaction_id} endpoint.
    Replaces entire subtransactions array with new categorization.
    
    Args:
        budget_id: YNAB budget identifier (UUID format)
        transaction_id: YNAB transaction identifier (UUID format)
        subtransactions: List of subtransaction dicts with structure:
            {
                'amount': int (milliunits, e.g., -12340 for -$12.34),
                'category_id': str (UUID),
                'memo': str (optional)
            }
            Sum of amounts must equal expected_amount.
        expected_amount: Expected sum of amounts in milliunits (transaction total)
    
    Returns:
        bool: True if update succeeded, False if failed (conflict)
    
    Raises:
        YNABAPIError: On API errors (401, 404, 429, network errors)
        ValueError: If subtransaction amounts don't sum correctly or list is empty
    
    Example:
        >>> subtxns = [
        ...     {'amount': -10000, 'category_id': 'cat-groceries', 'memo': 'Food'},
        ...     {'amount': -5000, 'category_id': 'cat-supplies', 'memo': 'Paper'}
        ... ]
        >>> success = update_split_transaction(
        ...     budget_id='budget-abc-123',
        ...     transaction_id='txn-def-456',
        ...     subtransactions=subtxns,
        ...     expected_amount=-15000
        ... )
        >>> print(success)
        True
    """
    logger.info(f"Updating split transaction {transaction_id} with {len(subtransactions)} subtransactions")
    
    # Validate amounts before API call
    _validate_subtransaction_amounts(subtransactions, expected_amount)
    
    client = BaseYNABClient()
    endpoint = f'/budgets/{budget_id}/transactions/{transaction_id}'
    payload = {
        'transaction': {
            'subtransactions': subtransactions
        }
    }
    
    try:
        response = client.put(endpoint, payload)
        logger.info(f"Successfully updated split transaction {transaction_id}")
        return True
    
    except YNABConflictError:
        logger.warning(f"Split transaction {transaction_id} conflict (outdated version)")
        return False
