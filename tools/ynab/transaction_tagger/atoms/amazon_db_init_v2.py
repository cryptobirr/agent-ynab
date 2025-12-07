"""
Amazon Database V2 Initialization

Creates Amazon shipment-based matching schema:
- amazon_orders: Order-level data
- amazon_items: Line items with categorization
- amazon_shipments: Shipment tracking for YNAB matching
- amazon_match_attempts: Audit trail

Part of Layer 1: Atoms (single operations)
"""

import logging
from pathlib import Path
from common.db_connection import DatabaseConnection

logger = logging.getLogger(__name__)


def initialize_amazon_v2_tables() -> bool:
    """
    Initialize Amazon V2 categorization schema in PostgreSQL.

    Creates:
    - amazon_orders table with indexes
    - amazon_items table with FTS indexes
    - amazon_shipments table with matching indexes
    - amazon_match_attempts table for audit trail
    - find_shipment_matches() function for fuzzy matching
    - get_shipment_items() function for split generation
    - get_unmatched_shipments_summary() function for dashboards

    Returns:
        bool: True if successful, False otherwise

    Example:
        >>> from tools.ynab.transaction_tagger.atoms.amazon_db_init_v2 import initialize_amazon_v2_tables
        >>> success = initialize_amazon_v2_tables()
        >>> print(success)
        True
    """
    try:
        # 1. Load SQL schema
        schema_path = Path(__file__).parent / "amazon_schema_v2.sql"

        if not schema_path.exists():
            logger.error(f"Amazon V2 schema file not found: {schema_path}")
            return False

        with open(schema_path, 'r') as f:
            schema_sql = f.read()

        logger.info("Loaded Amazon V2 schema SQL")

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

        logger.info("✓ Amazon V2 tables initialized successfully")
        logger.info("  - amazon_orders table created")
        logger.info("  - amazon_items table created")
        logger.info("  - amazon_shipments table created")
        logger.info("  - amazon_match_attempts table created")
        logger.info("  - find_shipment_matches() function created")
        logger.info("  - get_shipment_items() function created")
        logger.info("  - get_unmatched_shipments_summary() function created")

        return True

    except Exception as e:
        logger.error(f"Failed to initialize Amazon V2 tables: {e}")
        import traceback
        traceback.print_exc()
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

    success = initialize_amazon_v2_tables()

    if success:
        print("\n✓ Amazon V2 categorization schema initialized successfully")
        print("\nTables created:")
        print("  • amazon_orders - Order-level data from invoices")
        print("  • amazon_items - Line items with learned categorization")
        print("  • amazon_shipments - Shipment tracking for YNAB matching")
        print("  • amazon_match_attempts - Audit trail for matches")
        print("\nFunctions created:")
        print("  • find_shipment_matches() - Fuzzy matching with confidence scoring")
        print("  • get_shipment_items() - Get items for split generation")
        print("  • get_unmatched_shipments_summary() - Dashboard summary")
        print("\nReady for invoice pre-processing!")
    else:
        print("\n✗ Failed to initialize Amazon V2 tables")
        exit(1)
