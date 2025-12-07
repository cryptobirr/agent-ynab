"""
Amazon Invoice Parser Molecule

Parses Amazon PDF invoices to extract line items for categorization.
Supports split transactions across multiple YNAB categories.

Part of Layer 2: Molecules (2-3 atom combinations)

Public API:
    - parse_amazon_invoice(pdf_path) -> dict
    - extract_order_items(invoice_data) -> list
    - store_amazon_items(order_id, items) -> bool

Example:
    >>> from tools.ynab.transaction_tagger.molecules.amazon_parser import parse_amazon_invoice
    >>> invoice_data = parse_amazon_invoice('/path/to/invoice.pdf')
    >>> print(invoice_data['order_id'])
    '113-7901042-5085031'
    >>> print(len(invoice_data['items']))
    3
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from decimal import Decimal
from datetime import datetime

logger = logging.getLogger(__name__)


def parse_amazon_invoice(pdf_path: str) -> Optional[Dict[str, Any]]:
    """
    Parse Amazon PDF invoice to extract order details and line items.

    Args:
        pdf_path: Path to Amazon invoice PDF

    Returns:
        Dict with invoice data:
        {
            'order_id': str,
            'order_date': str (YYYY-MM-DD),
            'items': [
                {
                    'name': str,
                    'asin': str (optional),
                    'quantity': int,
                    'unit_price': Decimal,
                    'total_price': Decimal
                }
            ],
            'subtotal': Decimal,
            'tax': Decimal,
            'shipping': Decimal,
            'total': Decimal,
            'invoice_path': str
        }

        None if parsing fails

    Example:
        >>> invoice = parse_amazon_invoice('amazon/20251128-19.90.pdf')
        >>> print(invoice['order_id'])
        '113-9566812-5085031'
        >>> print(invoice['items'][0]['name'])
        'USB-C Cable, 6ft'
    """
    try:
        # Import PDF library (try pdfplumber first, fallback to PyPDF2)
        try:
            import pdfplumber
            use_pdfplumber = True
        except ImportError:
            try:
                import PyPDF2
                use_pdfplumber = False
                logger.warning("pdfplumber not available, using PyPDF2 (less accurate)")
            except ImportError:
                logger.error("No PDF library available. Install: pip install pdfplumber")
                return None

        # 1. Extract text from PDF
        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            logger.error(f"PDF not found: {pdf_path}")
            return None

        text = ""
        if use_pdfplumber:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() + "\n"
        else:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages:
                    text += page.extract_text() + "\n"

        if not text.strip():
            logger.error(f"No text extracted from PDF: {pdf_path}")
            return None

        # 2. Parse invoice structure
        invoice_data = {
            'order_id': _extract_order_id(text),
            'order_date': _extract_order_date(text),
            'items': _extract_line_items(text),
            'subtotal': _extract_amount(text, r'Subtotal:?\s*\$?([\d,]+\.\d{2})'),
            'tax': _extract_amount(text, r'(?:Sales )?Tax:?\s*\$?([\d,]+\.\d{2})'),
            'shipping': _extract_amount(text, r'Shipping:?\s*\$?([\d,]+\.\d{2})'),
            'total': _extract_amount(text, r'(?:Order )?Total:?\s*\$?([\d,]+\.\d{2})'),
            'invoice_path': str(pdf_path_obj.absolute())
        }

        # 3. Validate required fields
        if not invoice_data['order_id']:
            logger.error(f"Could not extract order ID from: {pdf_path}")
            return None

        if not invoice_data['items']:
            logger.warning(f"No line items found in: {pdf_path}")

        logger.info(f"Parsed Amazon invoice {invoice_data['order_id']}: "
                   f"{len(invoice_data['items'])} items, total ${invoice_data['total']}")

        return invoice_data

    except Exception as e:
        logger.error(f"Failed to parse Amazon invoice {pdf_path}: {e}")
        return None


def _extract_order_id(text: str) -> Optional[str]:
    """Extract Amazon order ID from invoice text."""
    patterns = [
        r'Order #?\s*([0-9]{3}-[0-9]{7}-[0-9]{7})',
        r'Order ID:?\s*([0-9]{3}-[0-9]{7}-[0-9]{7})',
        r'([0-9]{3}-[0-9]{7}-[0-9]{7})',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    return None


def _extract_order_date(text: str) -> Optional[str]:
    """Extract order date and convert to YYYY-MM-DD format."""
    patterns = [
        r'Order Date:?\s*(\w+ \d{1,2},?\s*\d{4})',
        r'Ordered on:?\s*(\w+ \d{1,2},?\s*\d{4})',
        r'(\w+ \d{1,2},?\s*\d{4})',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(1)
            try:
                # Parse "November 28, 2025" format
                dt = datetime.strptime(date_str, "%B %d, %Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                try:
                    # Try without comma
                    dt = datetime.strptime(date_str, "%B %d %Y")
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue

    return None


def _extract_line_items(text: str) -> List[Dict[str, Any]]:
    """
    Extract individual line items from invoice.

    Amazon invoice format:
    - Product name on multiple lines
    - "Sold by: ..." line
    - "Return or replace items: ..." line
    - Price on its own line: $XX.XX
    """
    items = []
    lines = text.split('\n')

    # Keywords to skip
    skip_keywords = [
        'subtotal', 'tax', 'shipping', 'total', 'order date', 'invoice',
        'order summary', 'ship to', 'payment method', 'grand total',
        'sold by:', 'return or replace', 'eligible through', 'conditions of use',
        'privacy notice', 'amazon.com', 'your package', 'delivered'
    ]

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Look for standalone price line (just $XX.XX, possibly with whitespace)
        price_only_match = re.match(r'^\s*\$(\d+\.\d{2})\s*$', line)

        if price_only_match:
            price = Decimal(price_only_match.group(1))

            # Work backward to find product name
            product_lines = []
            j = i - 1

            # Skip intermediate lines like "Sold by:" and "Return or replace items:"
            intermediate_keywords = ['sold by:', 'return or replace', 'eligible through']
            stop_keywords = [
                'subtotal', 'tax', 'shipping', 'total', 'order date', 'invoice',
                'order summary', 'ship to', 'payment method', 'grand total',
                'conditions of use', 'privacy notice', 'amazon.com',
                'your package', 'delivered'
            ]

            while j >= 0:
                prev_line = lines[j].strip()

                # Stop if we hit a hard stop keyword or another price
                if any(kw in prev_line.lower() for kw in stop_keywords):
                    break
                if re.search(r'\$\d+\.\d{2}', prev_line):
                    break

                # Skip intermediate lines (Sold by, Return policy, etc.)
                if any(kw in prev_line.lower() for kw in intermediate_keywords):
                    j -= 1
                    continue

                # Skip empty lines
                if not prev_line:
                    j -= 1
                    continue

                # Add non-empty line to product name (we'll reverse later)
                product_lines.insert(0, prev_line)
                j -= 1

                # Stop after collecting reasonable amount of text
                if len(' '.join(product_lines)) > 200:
                    break

            # Construct product name from collected lines
            if product_lines:
                name = ' '.join(product_lines).strip()

                # Clean up name (remove extra whitespace)
                name = re.sub(r'\s+', ' ', name)

                if len(name) > 3:  # Reasonable name length
                    items.append({
                        'name': name,
                        'asin': None,
                        'quantity': 1,  # Amazon invoices typically don't show quantity explicitly
                        'unit_price': price,
                        'total_price': price
                    })

        i += 1

    return items


def _extract_amount(text: str, pattern: str) -> Optional[Decimal]:
    """Extract dollar amount from text using regex pattern."""
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        amount_str = match.group(1).replace(',', '')
        try:
            return Decimal(amount_str)
        except:
            pass

    return None


def store_amazon_items(order_id: str, items: List[Dict[str, Any]],
                      order_date: str) -> bool:
    """
    Store Amazon line items in database for categorization.

    Args:
        order_id: Amazon order ID
        items: List of item dicts from parse_amazon_invoice()
        order_date: Order date in YYYY-MM-DD format

    Returns:
        bool: True if stored successfully, False otherwise

    Example:
        >>> items = [
        ...     {'name': 'USB Cable', 'quantity': 1, 'total_price': Decimal('12.99')},
        ...     {'name': 'Phone Case', 'quantity': 2, 'total_price': Decimal('15.98')}
        ... ]
        >>> success = store_amazon_items('113-1234567-8901234', items, '2025-11-28')
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

        with conn.cursor() as cursor:
            for item in items:
                # Convert prices to milliunits (YNAB format)
                unit_price_milliunits = int(item['unit_price'] * 1000000)
                total_price_milliunits = int(item['total_price'] * 1000000)

                cursor.execute("""
                    INSERT INTO amazon_items (
                        order_id, order_date, item_name, item_asin,
                        quantity, unit_price_milliunits, total_price_milliunits,
                        categorization_method, confidence_score
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (order_id, item_name, unit_price_milliunits)
                    DO UPDATE SET
                        order_date = EXCLUDED.order_date,
                        quantity = EXCLUDED.quantity,
                        total_price_milliunits = EXCLUDED.total_price_milliunits,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    order_id,
                    order_date,
                    item['name'],
                    item.get('asin'),
                    item['quantity'],
                    unit_price_milliunits,
                    total_price_milliunits,
                    'pending',  # Initial state
                    0.0  # No confidence until categorized
                ))

            conn.commit()

        logger.info(f"Stored {len(items)} items for order {order_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to store Amazon items for {order_id}: {e}")
        if 'conn' in locals():
            conn.rollback()
        return False

    finally:
        if 'conn' in locals() and conn:
            conn.close()
