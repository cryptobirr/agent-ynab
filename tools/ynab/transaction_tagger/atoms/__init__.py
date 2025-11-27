"""YNAB Transaction Tagger - Atoms Package

Layer 1: Pure, single-purpose functions for YNAB data operations.
"""

from .api_fetch import fetch_transactions, fetch_categories
from .api_update import update_transaction_category, update_split_transaction
from .db_init import initialize_database
from .db_upsert import upsert_transaction
from .db_query import get_untagged_transactions
from .historical_match import find_historical_category
from .sop_loader import load_categorization_rules

__all__ = [
    'fetch_transactions',
    'fetch_categories',
    'update_transaction_category',
    'update_split_transaction',
    'initialize_database',
    'upsert_transaction',
    'get_untagged_transactions',
    'find_historical_category',
    'load_categorization_rules',
]
