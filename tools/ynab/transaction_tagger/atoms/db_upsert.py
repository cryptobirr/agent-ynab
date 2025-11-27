"""
Database upsert atom - Idempotent transaction storage for YNAB Transaction Tagger

This module provides the upsert_transaction() function for persisting YNAB
transaction data to PostgreSQL. Uses ON CONFLICT DO UPDATE pattern for
idempotent inserts and updates.

Functions:
    upsert_transaction(txn_data) -> Dict[str, Any]
        Upsert transaction to database, returns status dict
        
Internal Functions:
    _detect_split_transaction(txn_data) -> Tuple[bool, int]
        Detect split transaction and count subtransactions
        
    _validate_transaction_data(txn_data) -> Dict[str, Any] | None
        Validate required fields, return error dict or None
"""
from typing import Dict, Any, Tuple
from datetime import datetime, timezone
import logging

from common.db_connection import (
    DatabaseConnection,
    DatabaseConnectionError,
    DatabaseExecutionError
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _detect_split_transaction(txn_data: Dict[str, Any]) -> Tuple[bool, int]:
    """
    Detect if transaction is split and count subtransactions.
    
    Args:
        txn_data: Transaction dictionary from YNAB API
        
    Returns:
        (is_split, subtransaction_count) tuple
        
    Example:
        >>> _detect_split_transaction({'subtransactions': [{'id': '1'}, {'id': '2'}]})
        (True, 2)
        >>> _detect_split_transaction({'subtransactions': []})
        (False, 0)
        >>> _detect_split_transaction({})
        (False, 0)
    """
    subtransactions = txn_data.get('subtransactions', [])
    
    if subtransactions and len(subtransactions) > 0:
        return (True, len(subtransactions))
    else:
        return (False, 0)


def _validate_transaction_data(txn_data: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    Validate transaction data has all required fields.
    
    Args:
        txn_data: Transaction dictionary to validate
        
    Returns:
        None if valid, error dict if invalid
        
    Example:
        >>> _validate_transaction_data({'id': '123', 'account_id': 'acc', ...})
        None  # Valid
        >>> _validate_transaction_data({})
        {'status': 'error', 'error': 'Missing required field: id', ...}
    """
    required_fields = ['id', 'account_id', 'date', 'amount', 'budget_id']
    
    for field in required_fields:
        if field not in txn_data:
            error_msg = f"Missing required field: {field}"
            logger.error(f"Validation failed: {error_msg}")
            return {
                'status': 'error',
                'transaction_id': None,
                'sync_version': None,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': error_msg
            }
    
    # Validate cleared status (must be one of allowed values)
    cleared = txn_data.get('cleared')
    if cleared and cleared not in ['cleared', 'uncleared', 'reconciled']:
        error_msg = f"Invalid cleared status: {cleared}. Must be one of: cleared, uncleared, reconciled"
        logger.error(f"Validation failed: {error_msg}")
        return {
            'status': 'error',
            'transaction_id': None,
            'sync_version': None,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'error': error_msg
        }
    
    return None  # Valid


def upsert_transaction(txn_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upsert YNAB transaction to PostgreSQL database.
    
    Uses ON CONFLICT DO UPDATE pattern for idempotent inserts. On first
    call with a transaction ID, inserts new row. On subsequent calls,
    updates existing row and increments sync_version.
    
    Args:
        txn_data: Transaction dictionary from YNAB API with required fields:
            - id (str): YNAB transaction ID
            - account_id (str): YNAB account ID
            - date (str): Transaction date (YYYY-MM-DD)
            - amount (int): Amount in milliunits (1000 = $1.00)
            - budget_id (str): Budget ID (context parameter)
            Optional fields: payee_id, payee_name, category_id, category_name,
                           memo, cleared, approved, flag_color, subtransactions
    
    Returns:
        Dict with keys:
            - status: 'inserted', 'updated', or 'error'
            - transaction_id: Transaction ID (or None on error)
            - sync_version: Version number after upsert (or None on error)
            - timestamp: ISO-8601 timestamp of operation
            - error: Error message (or None on success)
    
    Example:
        >>> result = upsert_transaction({
        ...     'id': 'txn_123',
        ...     'account_id': 'acc_xyz',
        ...     'date': '2025-11-27',
        ...     'amount': -45000,
        ...     'budget_id': 'budget_learning'
        ... })
        >>> result['status']
        'inserted'
        >>> result['sync_version']
        1
        
        >>> result = upsert_transaction({...})  # Same ID, different data
        >>> result['status']
        'updated'
        >>> result['sync_version']
        2
    """
    # Step 1: Validate input data
    validation_error = _validate_transaction_data(txn_data)
    if validation_error is not None:
        return validation_error
    
    # Step 2: Detect split transaction
    is_split, subtransaction_count = _detect_split_transaction(txn_data)
    
    # Step 3: Build SQL query with ON CONFLICT and RETURNING
    sql = """
        INSERT INTO ynab_transactions (
            id, account_id, date, amount, payee_id, payee_name,
            category_id, category_name, memo, cleared, approved,
            flag_color, budget_id, is_split, subtransaction_count,
            created_at, updated_at, sync_version
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1
        )
        ON CONFLICT (id) DO UPDATE SET
            account_id = EXCLUDED.account_id,
            date = EXCLUDED.date,
            amount = EXCLUDED.amount,
            payee_id = EXCLUDED.payee_id,
            payee_name = EXCLUDED.payee_name,
            category_id = EXCLUDED.category_id,
            category_name = EXCLUDED.category_name,
            memo = EXCLUDED.memo,
            cleared = EXCLUDED.cleared,
            approved = EXCLUDED.approved,
            flag_color = EXCLUDED.flag_color,
            is_split = EXCLUDED.is_split,
            subtransaction_count = EXCLUDED.subtransaction_count,
            updated_at = CURRENT_TIMESTAMP,
            sync_version = ynab_transactions.sync_version + 1
        RETURNING sync_version, updated_at;
    """
    
    # Step 4: Build values tuple
    values = (
        txn_data['id'],                          # id
        txn_data['account_id'],                  # account_id
        txn_data['date'],                        # date
        txn_data['amount'],                      # amount
        txn_data.get('payee_id'),                # payee_id (optional)
        txn_data.get('payee_name'),              # payee_name (optional)
        txn_data.get('category_id'),             # category_id (optional)
        txn_data.get('category_name'),           # category_name (optional)
        txn_data.get('memo'),                    # memo (optional)
        txn_data.get('cleared', 'uncleared'),    # cleared (default: uncleared)
        txn_data.get('approved', False),         # approved (default: False)
        txn_data.get('flag_color'),              # flag_color (optional)
        txn_data['budget_id'],                   # budget_id
        is_split,                                # is_split
        subtransaction_count                     # subtransaction_count
    )
    
    # Step 5: Execute query and handle errors
    db = None
    
    try:
        # Create connection
        logger.info(f"Upserting transaction: {txn_data['id']}")
        db = DatabaseConnection()
        
        # Execute query (use .query() for RETURNING clause)
        result = db.query(sql, values)
        
        # Parse RETURNING results
        if not result or len(result) == 0:
            raise DatabaseExecutionError("No result returned from upsert query")
        
        sync_version = result[0]['sync_version']
        updated_at = result[0]['updated_at']
        
        # Determine insert vs update
        status = 'inserted' if sync_version == 1 else 'updated'
        
        logger.info(f"Transaction {txn_data['id']} {status} (version {sync_version})")
        
        # Handle both datetime objects and strings for updated_at
        if isinstance(updated_at, str):
            timestamp_str = updated_at
        else:
            timestamp_str = updated_at.isoformat()
        
        # Ensure timestamp ends with 'Z' for UTC
        if not timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str.replace('+00:00', 'Z')
        
        # Return success
        return {
            'status': status,
            'transaction_id': txn_data['id'],
            'sync_version': sync_version,
            'timestamp': timestamp_str,
            'error': None
        }
    
    except DatabaseConnectionError as e:
        error_msg = f"Database connection error: {e}"
        logger.error(error_msg)
        return {
            'status': 'error',
            'transaction_id': txn_data.get('id'),
            'sync_version': None,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'error': error_msg
        }
    
    except DatabaseExecutionError as e:
        error_msg = f"SQL execution error: {e}"
        logger.error(error_msg)
        return {
            'status': 'error',
            'transaction_id': txn_data.get('id'),
            'sync_version': None,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'error': error_msg
        }
    
    except Exception as e:
        error_msg = f"Unexpected error during transaction upsert: {e}"
        logger.error(error_msg)
        return {
            'status': 'error',
            'transaction_id': txn_data.get('id'),
            'sync_version': None,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'error': error_msg
        }
    
    finally:
        # Always close connection
        if db is not None:
            db.close()
            logger.debug("Database connection closed")
