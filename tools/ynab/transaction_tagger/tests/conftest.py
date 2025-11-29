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


# ============================================================================
# Fixtures for Template Layer Tests
# ============================================================================

@pytest.fixture
def mock_vault(monkeypatch):
    """Mock VaultClient for testing"""
    class MockVault:
        def is_connected(self):
            return True
        
        def kv_get(self, path):
            if path == 'secret/ynab/credentials':
                return {
                    'personal_budget_id': 'personal-budget-123',
                    'business_budget_id': 'business-budget-456',
                    'api_token': 'test-token-xyz'
                }
            return None
    
    from unittest.mock import Mock
    mock_vault_instance = MockVault()
    
    def mock_vault_init(*args, **kwargs):
        return mock_vault_instance
    
    monkeypatch.setattr('tools.ynab.transaction_tagger.templates.tagging_workflow.VaultClient', mock_vault_init)
    yield mock_vault_instance


@pytest.fixture
def mock_sop_rules():
    """Mock SOP rules for testing"""
    return {
        'core_patterns': [
            {
                'pattern': 'Starbucks',
                'category': 'Coffee Shops',
                'confidence': 'High',
                'pattern_type': 'exact',
                'source': 'Historical'
            },
            {
                'pattern': 'Amazon*',
                'category': 'Online Shopping',
                'confidence': 'Medium',
                'pattern_type': 'prefix',
                'source': 'Pattern'
            }
        ],
        'user_corrections': [
            {
                'payee': 'Amazon',
                'correct_category': 'Business Expenses',
                'reasoning': 'User preference'
            }
        ],
        'split_patterns': [],
        'web_research': []
    }


@pytest.fixture
def mock_api_fetch(monkeypatch):
    """Mock API fetch functions"""
    def mock_fetch_transactions(budget_id, since_date=None):
        return [
            {
                'id': 'txn-1',
                'date': '2025-11-28',
                'payee_name': 'Test Merchant 1',
                'amount': -500,
                'category_id': None,
                'memo': ''
            },
            {
                'id': 'txn-2',
                'date': '2025-11-27',
                'payee_name': 'Test Merchant 2',
                'amount': -2500,
                'category_id': None,
                'memo': ''
            }
        ]
    
    def mock_fetch_categories(budget_id):
        return [
            {
                'id': 'cat-1',
                'name': 'Coffee Shops',
                'category_group_id': 'group-1'
            },
            {
                'id': 'cat-2',
                'name': 'Online Shopping',
                'category_group_id': 'group-2'
            }
        ]
    
    monkeypatch.setattr(
        'tools.ynab.transaction_tagger.templates.tagging_workflow.fetch_transactions',
        mock_fetch_transactions
    )
    monkeypatch.setattr(
        'tools.ynab.transaction_tagger.templates.tagging_workflow.fetch_categories',
        mock_fetch_categories
    )
    yield


@pytest.fixture
def mock_sop_loader(monkeypatch):
    """Mock SOP loader"""
    def mock_load_rules():
        return {
            'core_patterns': [
                {
                    'pattern': 'Starbucks',
                    'category': 'Coffee Shops',
                    'confidence': 'High',
                    'pattern_type': 'exact',
                    'source': 'Historical'
                }
            ],
            'user_corrections': [],
            'split_patterns': [],
            'web_research': []
        }
    
    monkeypatch.setattr(
        'tools.ynab.transaction_tagger.templates.tagging_workflow.load_categorization_rules',
        mock_load_rules
    )
    yield
