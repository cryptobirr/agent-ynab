"""
Amazon Transaction Categorizer Molecule

Handles Amazon transaction categorization with split support.
Matches YNAB Amazon transactions to invoice line items and generates
split transactions when items span multiple categories.

Part of Layer 2: Molecules (2-3 atom combinations)

Public API:
    - categorize_amazon_transaction(txn_data, invoice_data) -> dict
    - generate_split_transaction(order_id) -> dict
    - learn_amazon_item_category(item_name, category_id, category_name, asin) -> bool

Example:
    >>> from tools.ynab.transaction_tagger.molecules.amazon_categorizer import (
    ...     categorize_amazon_transaction
    ... )
    >>> txn = {'id': 'txn_123', 'payee_name': 'Amazon', 'amount': -19900000}
    >>> invoice = parse_amazon_invoice('invoice.pdf')
    >>> result = categorize_amazon_transaction(txn, invoice)
    >>> print(result['type'])
    'split'
    >>> print(len(result['subtransactions']))
    3
"""

import logging
from typing import Dict, List, Any, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


def categorize_amazon_transaction(txn_data: Dict[str, Any],
                                  invoice_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Categorize Amazon transaction using invoice line items.

    Analyzes invoice items and generates:
    - Single category if all items in same category
    - Split transaction if items span multiple categories

    Args:
        txn_data: YNAB transaction dict with:
            - id: transaction ID
            - payee_name: should be 'Amazon' or similar
            - amount: transaction amount in milliunits
            - date: transaction date

        invoice_data: Parsed invoice from amazon_parser.parse_amazon_invoice():
            - order_id: Amazon order ID
            - items: List of line items
            - total: Order total

    Returns:
        Dict with categorization result:
        {
            'type': 'single' | 'split',
            'category_id': str (if single),
            'category_name': str (if single),
            'subtransactions': [  # if split
                {
                    'category_id': str,
                    'category_name': str,
                    'amount': int (milliunits),
                    'memo': str (item description)
                }
            ],
            'confidence': float,
            'method': 'amazon_invoice',
            'reasoning': str,
            'source': 'amazon_categorizer'
        }

        None if categorization fails

    Example - Split Transaction:
        >>> txn = {'id': 'txn_123', 'amount': -29970000}
        >>> invoice = {
        ...     'order_id': '113-1234567-8901234',
        ...     'items': [
        ...         {'name': 'USB Cable', 'total_price': Decimal('12.99')},
        ...         {'name': 'Coffee Beans', 'total_price': Decimal('16.98')}
        ...     ]
        ... }
        >>> result = categorize_amazon_transaction(txn, invoice)
        >>> print(result['type'])
        'split'
        >>> print(result['subtransactions'][0]['category_name'])
        'Electronics'
        >>> print(result['subtransactions'][1]['category_name'])
        'Groceries'
    """
    try:
        # 1. Validate inputs
        if not txn_data or 'id' not in txn_data:
            logger.error("Invalid transaction data")
            return None

        if not invoice_data or 'items' not in invoice_data:
            logger.error("Invalid invoice data")
            return None

        order_id = invoice_data['order_id']
        items = invoice_data['items']

        if not items:
            logger.warning(f"No items in invoice {order_id}")
            return None

        logger.info(f"Categorizing Amazon transaction {txn_data['id']} "
                   f"with {len(items)} items from order {order_id}")

        # 2. Get category for each item
        categorized_items = []
        uncategorized_items = []

        for item in items:
            category = _get_item_category(
                item_name=item['name'],
                asin=item.get('asin')
            )

            if category:
                categorized_items.append({
                    'item_name': item['name'],
                    'category_id': category['category_id'],
                    'category_name': category['category_name'],
                    'amount_milliunits': int(item['total_price'] * 1000000),
                    'confidence': category['confidence']
                })
            else:
                uncategorized_items.append({
                    'item_name': item['name'],
                    'amount_milliunits': int(item['total_price'] * 1000000)
                })

        # 3. Handle uncategorized items
        if uncategorized_items:
            logger.warning(f"{len(uncategorized_items)} items need categorization:")
            for item in uncategorized_items:
                logger.warning(f"  - {item['item_name']}")

            # Return partial result for user review
            return {
                'type': 'needs_review',
                'category_id': None,
                'category_name': 'Amazon - Needs Review',
                'confidence': 0.0,
                'method': 'amazon_invoice',
                'reasoning': f'{len(uncategorized_items)} items need category assignment',
                'source': 'amazon_categorizer',
                'uncategorized_items': uncategorized_items,
                'categorized_items': categorized_items
            }

        # 4. Check if all items are same category
        unique_categories = {item['category_id'] for item in categorized_items}

        if len(unique_categories) == 1:
            # Single category
            first_item = categorized_items[0]
            total_amount = sum(item['amount_milliunits'] for item in categorized_items)

            return {
                'type': 'single',
                'category_id': first_item['category_id'],
                'category_name': first_item['category_name'],
                'confidence': min(item['confidence'] for item in categorized_items),
                'method': 'amazon_invoice',
                'reasoning': f'All {len(items)} items categorized as {first_item["category_name"]}',
                'source': 'amazon_categorizer',
                'memo': f'Amazon order {order_id}: {", ".join(item["item_name"] for item in categorized_items[:2])}' +
                       (f' +{len(categorized_items)-2} more' if len(categorized_items) > 2 else '')
            }

        # 5. Split transaction
        return {
            'type': 'split',
            'subtransactions': [
                {
                    'category_id': item['category_id'],
                    'category_name': item['category_name'],
                    'amount': -abs(item['amount_milliunits']),  # Negative for expense
                    'memo': item['item_name']
                }
                for item in categorized_items
            ],
            'confidence': min(item['confidence'] for item in categorized_items),
            'method': 'amazon_invoice',
            'reasoning': f'Split across {len(unique_categories)} categories: ' +
                        ', '.join(sorted(unique_categories)),
            'source': 'amazon_categorizer'
        }

    except Exception as e:
        logger.error(f"Failed to categorize Amazon transaction: {e}")
        return None


def _get_item_category(item_name: str, asin: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get category for Amazon item using database lookup.

    Uses PostgreSQL get_amazon_item_category() function for multi-tier matching:
    1. Exact ASIN match (highest confidence)
    2. Exact item name match (user verified)
    3. Fuzzy item name match (learned patterns)

    Args:
        item_name: Product name/description
        asin: Amazon ASIN (optional)

    Returns:
        Dict with category info or None:
        {
            'category_id': str,
            'category_name': str,
            'confidence': float,
            'method': str
        }
    """
    try:
        from common.db_connection import DatabaseConnection

        db = DatabaseConnection()
        conn = db.get_connection()

        if not conn:
            logger.error("Failed to connect to database")
            return None

        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT category_id, category_name, confidence, method
                FROM get_amazon_item_category(%s, %s)
            """, (item_name, asin))

            row = cursor.fetchone()

            if row:
                return {
                    'category_id': row[0],
                    'category_name': row[1],
                    'confidence': float(row[2]),
                    'method': row[3]
                }

        return None

    except Exception as e:
        logger.error(f"Failed to get category for '{item_name}': {e}")
        return None

    finally:
        if 'conn' in locals() and conn:
            conn.close()


def learn_amazon_item_category(item_name: str,
                               category_id: str,
                               category_name: str,
                               asin: Optional[str] = None,
                               user_verified: bool = False) -> bool:
    """
    Record category mapping for Amazon item.

    Stores item-category mapping for future automatic categorization.
    User-verified mappings have highest priority.

    Args:
        item_name: Product name/description
        category_id: YNAB category ID
        category_name: YNAB category name
        asin: Amazon ASIN (optional, enables exact product matching)
        user_verified: True if user manually set this category

    Returns:
        bool: True if stored successfully, False otherwise

    Example:
        >>> success = learn_amazon_item_category(
        ...     item_name='USB-C Cable, 6ft',
        ...     category_id='cat_electronics_123',
        ...     category_name='Electronics',
        ...     asin='B07ABCD1234',
        ...     user_verified=True
        ... )
        >>> print(success)
        True
    """
    try:
        from common.db_connection import DatabaseConnection

        db = DatabaseConnection()
        conn = db.get_connection()

        if not conn:
            logger.error("Failed to connect to database")
            return False

        confidence = 1.0 if user_verified else 0.8
        method = 'manual' if user_verified else 'learned'

        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE amazon_items
                SET category_id = %s,
                    category_name = %s,
                    categorization_method = %s,
                    confidence_score = %s,
                    user_verified = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE item_name = %s
                  AND (item_asin = %s OR item_asin IS NULL)
            """, (
                category_id,
                category_name,
                method,
                confidence,
                user_verified,
                item_name,
                asin
            ))

            rows_updated = cursor.rowcount
            conn.commit()

        if rows_updated > 0:
            logger.info(f"Learned category for '{item_name}': {category_name} "
                       f"({rows_updated} items updated, verified={user_verified})")
            return True
        else:
            logger.warning(f"No items found to update for '{item_name}'")
            return False

    except Exception as e:
        logger.error(f"Failed to learn category for '{item_name}': {e}")
        if 'conn' in locals():
            conn.rollback()
        return False

    finally:
        if 'conn' in locals() and conn:
            conn.close()


def generate_split_transaction(order_id: str) -> Optional[Dict[str, Any]]:
    """
    Generate split transaction breakdown for Amazon order.

    Uses PostgreSQL categorize_amazon_order() function to get
    category breakdown for existing order in database.

    Args:
        order_id: Amazon order ID

    Returns:
        Dict with split transaction data or None:
        {
            'type': 'split',
            'subtransactions': [
                {
                    'category_id': str,
                    'category_name': str,
                    'amount': int (milliunits, negative),
                    'memo': str
                }
            ]
        }

    Example:
        >>> split = generate_split_transaction('113-1234567-8901234')
        >>> print(len(split['subtransactions']))
        3
    """
    try:
        from common.db_connection import DatabaseConnection

        db = DatabaseConnection()
        conn = db.get_connection()

        if not conn:
            logger.error("Failed to connect to database")
            return None

        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT category_id, category_name, amount_milliunits, memo
                FROM categorize_amazon_order(%s)
            """, (order_id,))

            rows = cursor.fetchall()

            if not rows:
                logger.warning(f"No categorized items for order {order_id}")
                return None

            return {
                'type': 'split',
                'subtransactions': [
                    {
                        'category_id': row[0],
                        'category_name': row[1],
                        'amount': -abs(row[2]),  # Negative for expense
                        'memo': row[3]
                    }
                    for row in rows
                ]
            }

    except Exception as e:
        logger.error(f"Failed to generate split for order {order_id}: {e}")
        return None

    finally:
        if 'conn' in locals() and conn:
            conn.close()
