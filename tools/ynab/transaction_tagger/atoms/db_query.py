"""
Database Query Atom - Get Untagged Transactions

Provides pure function to query PostgreSQL for transactions
requiring categorization (category_id IS NULL).

Part of Layer 1 Atoms - Single-purpose, pure functions.
"""

from typing import List, Dict, Any
import logging
from common.db_connection import DatabaseConnection

# Configure logging
logger = logging.getLogger(__name__)


def get_untagged_transactions(
    budget_id: str,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Query untagged transactions from PostgreSQL database.
    
    A transaction is "untagged" if category_id IS NULL.
    Results ordered by date DESC, created_at DESC.
    
    Args:
        budget_id: Budget ID to filter transactions (required)
        limit: Maximum number of transactions to return (default 100, max 1000)
    
    Returns:
        List of transaction dictionaries with 18 fields.
        Empty list if error or no results.
    
    Example:
        >>> txns = get_untagged_transactions("budget_123", limit=50)
        >>> print(len(txns))
        50
        >>> print(txns[0]['payee_name'])
        'Starbucks'
    """
    # 1. Input validation
    if not budget_id or not isinstance(budget_id, str):
        logger.error("Invalid budget_id: must be non-empty string")
        return []
    
    if not isinstance(limit, int) or limit < 1 or limit > 1000:
        logger.error(f"Invalid limit: {limit}. Must be integer between 1-1000")
        return []
    
    # 2. Database connection
    try:
        db = DatabaseConnection()
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return []
    
    cursor = None
    try:
        # 3. Build and execute query
        cursor = db.connection.cursor()
        query = """
            SELECT 
                id, account_id, date, amount, payee_id, payee_name,
                category_id, category_name, memo, cleared, approved, flag_color,
                budget_id, is_split, subtransaction_count,
                created_at, updated_at, sync_version
            FROM ynab_transactions
            WHERE 
                budget_id = %s
                AND category_id IS NULL
            ORDER BY 
                date DESC,
                created_at DESC
            LIMIT %s;
        """
        cursor.execute(query, (budget_id, limit))
        rows = cursor.fetchall()
        
        # 4. Convert to dictionaries
        if not rows:
            logger.info(f"No untagged transactions found for budget {budget_id}")
            return []
        
        columns = [desc[0] for desc in cursor.description]
        result = [dict(zip(columns, row)) for row in rows]
        
        logger.info(f"Retrieved {len(result)} untagged transactions for budget {budget_id}")
        return result
        
    except Exception as e:
        logger.error(f"Query execution failed: {e}")
        return []
    
    finally:
        # 5. Cleanup
        if cursor:
            cursor.close()
        if db and db.connection:
            db.connection.close()
