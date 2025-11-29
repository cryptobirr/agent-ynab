"""
Shared pytest fixtures for molecule tests.

These fixtures provide reusable test data and mocks for testing
the molecules layer with isolated, deterministic behavior.
"""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def sample_transaction():
    """Sample transaction dict for testing."""
    return {
        'id': 'txn_test_123',
        'payee_name': 'Test Merchant',
        'amount': -450000,  # -$45.00 in milliunits
        'date': '2025-11-27'
    }


@pytest.fixture
def sample_historical_match():
    """Sample historical match result from historical_match atom."""
    return {
        'category_id': 'cat_groceries_xyz',
        'category_name': 'Groceries',
        'confidence': 0.95,
        'match_count': 47
    }


@pytest.fixture
def mock_sop_file(tmp_path):
    """Mock SOP file for sop_updater tests."""
    sop_file = tmp_path / "categorization_rules.md"
    sop_file.write_text("""# Categorization Rules

## Explicit Rules


## Learned from User Corrections

""")
    return sop_file
