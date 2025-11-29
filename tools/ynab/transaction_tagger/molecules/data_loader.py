"""
Data Loader Molecule - Transaction synchronization workflow

Composes atoms:
- db_init.initialize_database()
- api_fetch.fetch_transactions()
- db_upsert.upsert_transaction()

Implements two-budget architecture:
- First run: INIT_BUDGET_ID (all historical transactions)
- Subsequent runs: TARGET_BUDGET_ID (incremental sync)
"""
from typing import Dict, Any
from datetime import datetime, timezone
import logging
import json

from tools.ynab.transaction_tagger.atoms import (
    initialize_database,
    fetch_transactions,
    upsert_transaction
)
from common.db_connection import DatabaseConnection, DatabaseConnectionError, DatabaseExecutionError
from common.base_client import YNABAPIError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Two-budget architecture constants
INIT_BUDGET_ID = "75f63aa3-9f8f-4dcc-9350-d22535494657"      # One-time init
TARGET_BUDGET_ID = "eaf7c5cb-e008-4b62-9733-e7d0ca96cbf1"    # Ongoing ops


def _determine_sync_strategy(db: DatabaseConnection) -> Dict[str, Any]:
    """
    Determine which budget to sync and how.
    
    Args:
        db: Database connection instance
    
    Returns:
        Dict with keys:
            - budget_id: Budget ID to sync from
            - since_date: Date filter for API (YYYY-MM-DD) or None
            - run_type: 'first_run' or 'incremental'
            - last_sync: Previous sync timestamp or None
    
    Raises:
        DatabaseExecutionError: On query failure
    """
    try:
        # Query agent_metadata for last sync
        result = db.query("SELECT value FROM agent_metadata WHERE key = 'last_sync'")
        
        if not result or len(result) == 0:
            # First run: Fetch ALL transactions from INIT_BUDGET_ID
            logger.info("First run detected - will sync all history from INIT_BUDGET_ID")
            return {
                'budget_id': INIT_BUDGET_ID,
                'since_date': None,  # No filter - get all history
                'run_type': 'first_run',
                'last_sync': None
            }
        else:
            # Incremental run: Fetch NEW transactions from TARGET_BUDGET_ID
            last_sync_data = result[0]['value']
            last_sync_timestamp = last_sync_data['timestamp']
            
            # Extract date from timestamp (first 10 chars: YYYY-MM-DD)
            since_date = last_sync_timestamp[:10]
            
            logger.info(f"Incremental run detected - will sync since {since_date} from TARGET_BUDGET_ID")
            return {
                'budget_id': TARGET_BUDGET_ID,
                'since_date': since_date,
                'run_type': 'incremental',
                'last_sync': last_sync_timestamp
            }
    
    except DatabaseExecutionError as e:
        # If table doesn't exist yet, this is first run
        if "does not exist" in str(e):
            logger.info("agent_metadata table not found - treating as first run")
            return {
                'budget_id': INIT_BUDGET_ID,
                'since_date': None,
                'run_type': 'first_run',
                'last_sync': None
            }
        else:
            raise


def _update_sync_state(
    db: DatabaseConnection,
    strategy: Dict[str, Any],
    transaction_count: int
) -> None:
    """
    Update agent_metadata.last_sync after successful sync.
    
    Args:
        db: Database connection instance
        strategy: Sync strategy dict (from _determine_sync_strategy)
        transaction_count: Number of transactions synced
    
    Raises:
        DatabaseExecutionError: On query failure
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Ensure timestamp ends with 'Z'
    if not timestamp.endswith('Z'):
        timestamp = timestamp.replace('+00:00', 'Z')
    
    # Build state JSONB
    state = {
        'timestamp': timestamp,
        'budget_id': strategy['budget_id'],
        'transaction_count': transaction_count,
        'run_type': strategy['run_type']
    }
    
    # Convert to JSON string for SQL
    state_json = json.dumps(state)
    
    # UPSERT last_sync state
    sql = f"""
        INSERT INTO agent_metadata (key, value, created_at, updated_at)
        VALUES (
            'last_sync',
            '{state_json}'::jsonb,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT (key) DO UPDATE SET
            value = EXCLUDED.value,
            updated_at = CURRENT_TIMESTAMP
    """
    
    db.execute(sql)
    logger.info(f"Updated last_sync state: {timestamp}")


def sync_transactions(budget_id: str) -> Dict[str, Any]:
    """
    Sync YNAB transactions to local database.
    
    Implements two-budget architecture:
    - First run: Uses INIT_BUDGET_ID, fetches ALL transactions
    - Subsequent runs: Uses TARGET_BUDGET_ID, fetches NEW transactions
    
    Args:
        budget_id: Budget ID (ignored - determined automatically)
    
    Returns:
        Dict with keys:
            - status: 'success' or 'error'
            - run_type: 'first_run' or 'incremental'
            - budget_used: Budget ID that was actually used
            - transactions_synced: Number of transactions processed
            - inserted: Number of new transactions
            - updated: Number of updated transactions
            - errors: Number of failed transactions
            - timestamp: ISO-8601 timestamp of sync
            - last_sync_before: Previous sync timestamp (or None)
            - last_sync_after: New sync timestamp
            - error: Error message (or None)
    
    Example - First Run:
        >>> result = sync_transactions('ignored')
        >>> result['run_type']
        'first_run'
        >>> result['budget_used']
        '75f63aa3-9f8f-4dcc-9350-d22535494657'
    
    Example - Incremental Run:
        >>> result = sync_transactions('ignored')
        >>> result['run_type']
        'incremental'
        >>> result['budget_used']
        'eaf7c5cb-e008-4b62-9733-e7d0ca96cbf1'
    """
    db = None
    start_time = datetime.now(timezone.utc)
    
    try:
        # Step 1: Initialize database (idempotent)
        logger.info("Step 1: Initializing database...")
        init_result = initialize_database()
        
        if init_result['status'] == 'error':
            return {
                'status': 'error',
                'run_type': None,
                'budget_used': None,
                'transactions_synced': 0,
                'inserted': 0,
                'updated': 0,
                'errors': 0,
                'timestamp': start_time.isoformat(),
                'last_sync_before': None,
                'last_sync_after': None,
                'error': f"Database initialization failed: {init_result['error']}"
            }
        
        logger.info(f"Database status: {init_result['status']}")
        
        # Step 2: Determine sync strategy
        logger.info("Step 2: Determining sync strategy...")
        db = DatabaseConnection()
        strategy = _determine_sync_strategy(db)
        
        logger.info(f"Sync strategy: {strategy['run_type']} using budget {strategy['budget_id']}")
        
        # Step 3: Fetch transactions from API
        logger.info(f"Step 3: Fetching transactions (since_date={strategy['since_date']})...")
        
        try:
            transactions = fetch_transactions(
                budget_id=strategy['budget_id'],
                since_date=strategy['since_date']
            )
            logger.info(f"Fetched {len(transactions)} transactions from API")
        
        except YNABAPIError as e:
            logger.error(f"API fetch failed: {e}")
            return {
                'status': 'error',
                'run_type': strategy['run_type'],
                'budget_used': strategy['budget_id'],
                'transactions_synced': 0,
                'inserted': 0,
                'updated': 0,
                'errors': 0,
                'timestamp': start_time.isoformat(),
                'last_sync_before': strategy['last_sync'],
                'last_sync_after': None,
                'error': f"YNAB API error: {str(e)}"
            }
        
        # Step 4: Upsert each transaction
        logger.info("Step 4: Upserting transactions to database...")
        inserted = 0
        updated = 0
        errors = 0
        
        for txn in transactions:
            # Add budget_id context (CRITICAL - API doesn't return this)
            txn['budget_id'] = strategy['budget_id']
            
            # Upsert transaction
            result = upsert_transaction(txn)
            
            if result['status'] == 'inserted':
                inserted += 1
            elif result['status'] == 'updated':
                updated += 1
            else:
                errors += 1
                logger.error(f"Failed to upsert {txn['id']}: {result['error']}")
        
        logger.info(f"Upsert complete: {inserted} inserted, {updated} updated, {errors} errors")
        
        # Step 5: Update sync state
        logger.info("Step 5: Updating sync state...")
        _update_sync_state(db, strategy, len(transactions))
        
        # Success
        end_time = datetime.now(timezone.utc)
        new_timestamp = end_time.isoformat()
        
        return {
            'status': 'success',
            'run_type': strategy['run_type'],
            'budget_used': strategy['budget_id'],
            'transactions_synced': len(transactions),
            'inserted': inserted,
            'updated': updated,
            'errors': errors,
            'timestamp': new_timestamp,
            'last_sync_before': strategy['last_sync'],
            'last_sync_after': new_timestamp,
            'error': None
        }
    
    except DatabaseConnectionError as e:
        logger.error(f"Database connection error: {e}")
        return {
            'status': 'error',
            'run_type': None,
            'budget_used': None,
            'transactions_synced': 0,
            'inserted': 0,
            'updated': 0,
            'errors': 0,
            'timestamp': start_time.isoformat(),
            'last_sync_before': None,
            'last_sync_after': None,
            'error': f"Database connection error: {str(e)}"
        }
    
    except Exception as e:
        logger.error(f"Unexpected error during sync: {e}")
        return {
            'status': 'error',
            'run_type': None,
            'budget_used': None,
            'transactions_synced': 0,
            'inserted': 0,
            'updated': 0,
            'errors': 0,
            'timestamp': start_time.isoformat(),
            'last_sync_before': None,
            'last_sync_after': None,
            'error': f"Unexpected error: {str(e)}"
        }
    
    finally:
        # Always close connection
        if db is not None:
            db.close()
            logger.debug("Database connection closed")
