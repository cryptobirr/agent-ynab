"""
Amazon Database Initialization Atom

Creates Amazon-specific tables for scalable item-level categorization:
- amazon_items: Individual line items with category mappings
- amazon_order_totals: Order-level totals for reconciliation
- Helper functions for category lookup and split transactions

Part of Layer 1: Atoms (single operations)
"""

import logging
from pathlib import Path
from common.db_connection import DatabaseConnection

logger = logging.getLogger(__name__)


def initialize_amazon_tables() -> bool:
    """
    Initialize Amazon categorization tables in PostgreSQL.

    Creates:
    - amazon_items table with indexes
    - amazon_order_totals table with indexes
    - get_amazon_item_category() function
    - categorize_amazon_order() function

    Returns:
        bool: True if successful, False otherwise

    Example:
        >>> from tools.ynab.transaction_tagger.atoms.amazon_db_init import initialize_amazon_tables
        >>> success = initialize_amazon_tables()
        >>> print(success)
        True
    """
    try:
        # 1. Load SQL schema
        schema_path = Path(__file__).parent / "amazon_schema.sql"

        if not schema_path.exists():
            logger.error(f"Amazon schema file not found: {schema_path}")
            return False

        with open(schema_path, 'r') as f:
            schema_sql = f.read()

        logger.info("Loaded Amazon schema SQL")

        # 2. Connect to database
        db = DatabaseConnection()
        conn = db.get_connection()

        if not conn:
            logger.error("Failed to connect to database")
            return False

        # 3. Execute schema
        with conn.cursor() as cursor:
            cursor.execute(schema_sql)
            conn.commit()

        logger.info("✓ Amazon tables initialized successfully")
        logger.info("  - amazon_items table created")
        logger.info("  - amazon_order_totals table created")
        logger.info("  - get_amazon_item_category() function created")
        logger.info("  - categorize_amazon_order() function created")

        return True

    except Exception as e:
        logger.error(f"Failed to initialize Amazon tables: {e}")
        return False

    finally:
        if 'conn' in locals() and conn:
            conn.close()


if __name__ == '__main__':
    # Allow direct execution for setup
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    success = initialize_amazon_tables()

    if success:
        print("\n✓ Amazon categorization tables initialized successfully")
        print("\nTables created:")
        print("  • amazon_items - Individual line items with category mappings")
        print("  • amazon_order_totals - Order-level totals for reconciliation")
        print("\nFunctions created:")
        print("  • get_amazon_item_category() - Find category for an item")
        print("  • categorize_amazon_order() - Generate split transaction breakdown")
    else:
        print("\n✗ Failed to initialize Amazon tables")
        exit(1)
