"""
Historical Match Atom - Find Category from Historical Patterns

Provides pure function to query PostgreSQL for category based on
payee name history. Returns category if confidence ≥80% (default).

Part of Layer 1 Atoms - Single-purpose, pure functions.
"""

from typing import Dict, Any, Optional
import logging
from common.db_connection import DatabaseConnection

# Configure logging
logger = logging.getLogger(__name__)


def find_historical_category(
    payee_name: str,
    amount: int = None,
    min_confidence: float = 0.80
) -> Optional[Dict[str, Any]]:
    """
    Find category for payee based on historical transaction patterns.
    
    Queries PostgreSQL function find_historical_category() which returns
    category if confidence ≥80% (default threshold).
    
    Args:
        payee_name: Payee name to search (required, must be non-empty)
        amount: Transaction amount in milliunits (optional, for amount-based matching)
        min_confidence: Minimum confidence threshold 0.0-1.0 (default 0.80)
    
    Returns:
        Dictionary with category details if match found:
        {
            'category_id': str,
            'category_name': str,
            'confidence': float,  # 0.0-1.0
            'match_count': int    # Number of historical matches
        }
        
        None if no match found or error occurs.
    
    Example:
        >>> result = find_historical_category("Starbucks")
        >>> print(result)
        {
            'category_id': 'cat_xyz',
            'category_name': 'Coffee Shops',
            'confidence': 0.95,
            'match_count': 47
        }
    """
    # 1. Input validation
    if not payee_name or not isinstance(payee_name, str):
        logger.error("Invalid payee_name: must be non-empty string")
        return None
    
    if amount is not None and not isinstance(amount, int):
        logger.error(f"Invalid amount: {amount}. Must be integer or None")
        return None
    
    if not isinstance(min_confidence, (int, float)) or min_confidence < 0.0 or min_confidence > 1.0:
        logger.error(f"Invalid min_confidence: {min_confidence}. Must be float between 0.0-1.0")
        return None
    
    # 2. Database connection
    try:
        db = DatabaseConnection()
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None
    
    cursor = None
    try:
        # 3. Execute SQL function call
        cursor = db.get_connection().cursor()
        query = "SELECT * FROM find_historical_category(%s, %s, %s);"
        cursor.execute(query, (payee_name, amount, float(min_confidence)))
        row = cursor.fetchone()
        
        # 4. Parse result
        if not row:
            logger.info(f"No historical match found for payee: {payee_name}")
            return None
        
        columns = [desc[0] for desc in cursor.description]
        result = dict(zip(columns, row))
        
        logger.info(f"Historical match found for {payee_name}: {result['category_name']} "
                   f"(confidence: {result['confidence']:.2%})")
        return result
        
    except Exception as e:
        logger.error(f"Query execution failed: {e}")
        return None
    
    finally:
        # 5. Cleanup
        if cursor:
            cursor.close()
        if db and db.get_connection():
            db.close()
