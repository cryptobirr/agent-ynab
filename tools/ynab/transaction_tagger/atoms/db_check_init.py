"""Database initialization check atom - Check if historical data has been loaded"""
from typing import Dict, Any
import logging
from common.db_connection import DatabaseConnection, DatabaseExecutionError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_init_budget_loaded() -> bool:
    """
    Check if historical data from INIT_BUDGET_ID has been loaded.

    Returns:
        bool: True if init_budget_loaded flag is set, False otherwise

    Example:
        >>> check_init_budget_loaded()
        False  # First run
        >>> # After loading INIT_BUDGET data...
        >>> check_init_budget_loaded()
        True
    """
    db = None
    try:
        db = DatabaseConnection()

        result = db.query(
            "SELECT value FROM agent_metadata WHERE key = 'init_budget_loaded'"
        )

        if result and len(result) > 0:
            value = result[0]['value']
            if isinstance(value, dict):
                return value.get('loaded', False)

        return False

    except DatabaseExecutionError:
        # Table doesn't exist yet
        return False
    finally:
        if db:
            db.close()


def mark_init_budget_loaded(budget_id: str, transaction_count: int) -> None:
    """
    Mark that historical data from INIT_BUDGET_ID has been loaded.

    Args:
        budget_id: The INIT_BUDGET_ID that was loaded
        transaction_count: Number of transactions loaded
    """
    db = None
    try:
        db = DatabaseConnection()

        from datetime import datetime
        timestamp = datetime.utcnow().isoformat() + 'Z'

        db.execute(f"""
            INSERT INTO agent_metadata (key, value, created_at, updated_at)
            VALUES (
                'init_budget_loaded',
                '{{"loaded": true, "budget_id": "{budget_id}", "transaction_count": {transaction_count}, "timestamp": "{timestamp}"}}'::jsonb,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (key)
            DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = CURRENT_TIMESTAMP
        """)

        logger.info(f"Marked init_budget_loaded: {transaction_count} transactions from {budget_id}")

    finally:
        if db:
            db.close()
