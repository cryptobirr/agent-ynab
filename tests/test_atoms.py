"""Test suite for API fetch atom"""
import pytest
import json
from unittest.mock import patch, Mock
from pathlib import Path

from tools.ynab.transaction_tagger.atoms.api_fetch import fetch_transactions, fetch_categories
from common.base_client import YNABUnauthorizedError, YNABNotFoundError


# Load fixtures
FIXTURES_PATH = Path(__file__).parent / 'fixtures' / 'ynab_responses.json'
with open(FIXTURES_PATH) as f:
    FIXTURES = json.load(f)


@patch('tools.ynab.transaction_tagger.atoms.api_fetch.BaseYNABClient')
def test_fetch_transactions_success(mock_client_class):
    """Test successful transaction fetch"""
    mock_client = Mock()
    # Return data once, then empty batch to stop pagination
    mock_client.get.side_effect = [
        FIXTURES['transactions_page2'],
        {'data': {'transactions': [], 'server_knowledge': 100}}
    ]
    mock_client_class.return_value = mock_client
    
    result = fetch_transactions('budget-123')
    
    assert len(result) == 1
    assert result[0]['id'] == 'txn-003'


@patch('tools.ynab.transaction_tagger.atoms.api_fetch.BaseYNABClient')
def test_fetch_transactions_with_since_date(mock_client_class):
    """Test transaction fetch with since_date parameter"""
    mock_client = Mock()
    # Return data once, then empty batch to stop
    mock_client.get.side_effect = [
        FIXTURES['transactions_page1'],
        {'data': {'transactions': [], 'server_knowledge': 100}}
    ]
    mock_client_class.return_value = mock_client
    
    result = fetch_transactions('budget-123', since_date='2025-01-01')
    
    assert len(result) == 2
    # Verify since_date was passed
    assert mock_client.get.call_args_list[0][0][1]['since_date'] == '2025-01-01'


@patch('tools.ynab.transaction_tagger.atoms.api_fetch.BaseYNABClient')
def test_fetch_transactions_pagination(mock_client_class):
    """Test transaction fetch handles pagination"""
    mock_client = Mock()
    # Modify page1 to have different server_knowledge to trigger pagination
    page1 = FIXTURES['transactions_page1'].copy()
    page1_data = page1['data'].copy()
    page1_data['server_knowledge'] = 50
    page1['data'] = page1_data
    
    # First call returns page1 (knowledge=50), second call returns page2 (knowledge=100), third empty
    mock_client.get.side_effect = [
        page1,
        FIXTURES['transactions_page2'],
        {'data': {'transactions': [], 'server_knowledge': 100}}
    ]
    mock_client_class.return_value = mock_client
    
    result = fetch_transactions('budget-123')
    
    assert len(result) == 3  # 2 from page1 + 1 from page2
    assert mock_client.get.call_count == 3


@patch('tools.ynab.transaction_tagger.atoms.api_fetch.BaseYNABClient')
def test_fetch_transactions_filters_deleted(mock_client_class):
    """Test deleted transactions are filtered out"""
    mock_client = Mock()
    mock_client.get.side_effect = [
        FIXTURES['transactions_with_deleted'],
        {'data': {'transactions': [], 'server_knowledge': 100}}
    ]
    mock_client_class.return_value = mock_client
    
    result = fetch_transactions('budget-123')
    
    assert len(result) == 1
    assert result[0]['id'] == 'txn-004'


@patch('tools.ynab.transaction_tagger.atoms.api_fetch.BaseYNABClient')
def test_fetch_categories_success(mock_client_class):
    """Test successful category fetch"""
    mock_client = Mock()
    mock_client.get.return_value = FIXTURES['categories']
    mock_client_class.return_value = mock_client
    
    result = fetch_categories('budget-123')
    
    assert len(result) == 3
    assert result[0]['name'] == 'Rent/Mortgage'
    assert result[1]['name'] == 'Electric'
    assert result[2]['name'] == 'Groceries'


@patch('tools.ynab.transaction_tagger.atoms.api_fetch.BaseYNABClient')
def test_fetch_categories_filters_hidden_deleted(mock_client_class):
    """Test hidden and deleted categories are filtered out"""
    mock_client = Mock()
    
    # Create fixture with hidden/deleted items
    categories_with_hidden = {
        "data": {
            "category_groups": [
                {
                    "id": "grp-001",
                    "name": "Active Group",
                    "hidden": False,
                    "deleted": False,
                    "categories": [
                        {
                            "id": "cat-001",
                            "name": "Active Category",
                            "hidden": False,
                            "deleted": False
                        },
                        {
                            "id": "cat-002",
                            "name": "Hidden Category",
                            "hidden": True,
                            "deleted": False
                        }
                    ]
                },
                {
                    "id": "grp-002",
                    "name": "Deleted Group",
                    "hidden": False,
                    "deleted": True,
                    "categories": [
                        {
                            "id": "cat-003",
                            "name": "Should Not Appear",
                            "hidden": False,
                            "deleted": False
                        }
                    ]
                }
            ]
        }
    }
    
    mock_client.get.return_value = categories_with_hidden
    mock_client_class.return_value = mock_client
    
    result = fetch_categories('budget-123')
    
    assert len(result) == 1
    assert result[0]['name'] == 'Active Category'


@patch('tools.ynab.transaction_tagger.atoms.api_fetch.BaseYNABClient')
def test_api_unauthorized_error(mock_client_class):
    """Test 401 unauthorized error handling"""
    mock_client = Mock()
    mock_client.get.side_effect = YNABUnauthorizedError("Invalid token")
    mock_client_class.return_value = mock_client
    
    with pytest.raises(YNABUnauthorizedError):
        fetch_transactions('budget-123')


@patch('tools.ynab.transaction_tagger.atoms.api_fetch.BaseYNABClient')
def test_api_not_found_error(mock_client_class):
    """Test 404 not found error handling"""
    mock_client = Mock()
    mock_client.get.side_effect = YNABNotFoundError("Budget not found")
    mock_client_class.return_value = mock_client
    
    with pytest.raises(YNABNotFoundError):
        fetch_categories('budget-999')


# ============================================================================
# Database Initialization Atom Tests (Issue #8)
# ============================================================================

from tools.ynab.transaction_tagger.atoms.db_init import initialize_database
from common.db_connection import DatabaseConnectionError, DatabaseExecutionError


@patch('tools.ynab.transaction_tagger.atoms.db_init.DatabaseConnection')
def test_initialize_database_first_run(mock_db_class):
    """Test successful database initialization on first run"""
    mock_db = Mock()
    
    # Simulate agent_metadata table doesn't exist yet (first run)
    mock_db.query.side_effect = DatabaseExecutionError("relation \"agent_metadata\" does not exist")
    mock_db.execute.return_value = True
    mock_db_class.return_value = mock_db
    
    result = initialize_database()
    
    # Verify result structure
    assert result['status'] == 'initialized'
    assert result['version'] == '1.0.0'
    assert len(result['tables_created']) == 4
    assert 'ynab_transactions' in result['tables_created']
    assert 'ynab_split_transactions' in result['tables_created']
    assert 'sop_rules' in result['tables_created']
    assert 'agent_metadata' in result['tables_created']
    assert result['error'] is None
    assert 'T' in result['timestamp']  # ISO 8601 format
    
    # Verify SQL was executed (2 calls: schema + flag)
    assert mock_db.execute.call_count == 2
    
    # Verify connection was closed
    mock_db.close.assert_called_once()


@patch('tools.ynab.transaction_tagger.atoms.db_init.DatabaseConnection')
def test_initialize_database_already_initialized(mock_db_class):
    """Test idempotency - second run detects existing initialization"""
    mock_db = Mock()
    
    # Simulate agent_metadata exists with initialization flag
    mock_db.query.return_value = [{
        'value': {
            'initialized': True,
            'version': '1.0.0',
            'timestamp': '2025-11-27T19:00:00Z'
        }
    }]
    mock_db_class.return_value = mock_db
    
    result = initialize_database()
    
    # Verify result structure
    assert result['status'] == 'already_initialized'
    assert result['version'] == '1.0.0'
    assert result['timestamp'] == '2025-11-27T19:00:00Z'
    assert len(result['tables_created']) == 0
    assert result['error'] is None
    
    # Verify SQL was NOT executed (only query, no execute)
    mock_db.execute.assert_not_called()
    
    # Verify connection was closed
    mock_db.close.assert_called_once()


@patch('tools.ynab.transaction_tagger.atoms.db_init.DatabaseConnection')
def test_initialize_database_connection_error(mock_db_class):
    """Test error handling when database connection fails"""
    # Simulate connection error
    mock_db_class.side_effect = DatabaseConnectionError("Connection refused")
    
    result = initialize_database()
    
    # Verify error result
    assert result['status'] == 'error'
    assert 'Connection refused' in result['error']
    assert result['version'] is None
    assert len(result['tables_created']) == 0


@patch('tools.ynab.transaction_tagger.atoms.db_init.DatabaseConnection')
def test_initialize_database_sql_execution_error(mock_db_class):
    """Test error handling when SQL execution fails"""
    mock_db = Mock()
    
    # Simulate agent_metadata doesn't exist (first run)
    mock_db.query.side_effect = DatabaseExecutionError("table not found")
    
    # Simulate SQL execution error
    mock_db.execute.side_effect = DatabaseExecutionError("syntax error at or near 'CREATE'")
    mock_db_class.return_value = mock_db
    
    result = initialize_database()
    
    # Verify error result
    assert result['status'] == 'error'
    assert 'syntax error' in result['error']
    assert result['version'] is None
    assert len(result['tables_created']) == 0
    
    # Verify connection was closed even on error
    mock_db.close.assert_called_once()


# ============================================================================
# Database Upsert Atom Tests (Issue #9)
# ============================================================================

from tools.ynab.transaction_tagger.atoms.db_upsert import (
    upsert_transaction,
    _detect_split_transaction,
    _validate_transaction_data
)
import uuid


def test_detect_split_transaction_with_splits():
    """Test split detection with subtransactions"""
    txn_data = {
        'subtransactions': [
            {'id': 'sub_1', 'amount': -30000},
            {'id': 'sub_2', 'amount': -20000}
        ]
    }
    
    is_split, count = _detect_split_transaction(txn_data)
    
    assert is_split is True
    assert count == 2


def test_detect_split_transaction_no_splits():
    """Test split detection without subtransactions"""
    txn_data = {'subtransactions': []}
    
    is_split, count = _detect_split_transaction(txn_data)
    
    assert is_split is False
    assert count == 0


def test_detect_split_transaction_missing_key():
    """Test split detection when subtransactions key is missing"""
    txn_data = {}
    
    is_split, count = _detect_split_transaction(txn_data)
    
    assert is_split is False
    assert count == 0


def test_validate_transaction_data_valid():
    """Test validation with valid transaction data"""
    txn_data = {
        'id': 'txn_123',
        'account_id': 'acc_xyz',
        'date': '2025-11-27',
        'amount': -45000,
        'budget_id': 'budget_learning',
        'cleared': 'cleared'
    }
    
    result = _validate_transaction_data(txn_data)
    
    assert result is None  # Valid


def test_validate_transaction_data_missing_id():
    """Test validation fails when id is missing"""
    txn_data = {
        'account_id': 'acc_xyz',
        'date': '2025-11-27',
        'amount': -45000,
        'budget_id': 'budget_learning'
    }
    
    result = _validate_transaction_data(txn_data)
    
    assert result is not None
    assert result['status'] == 'error'
    assert 'Missing required field: id' in result['error']


def test_validate_transaction_data_invalid_cleared():
    """Test validation fails with invalid cleared status"""
    txn_data = {
        'id': 'txn_123',
        'account_id': 'acc_xyz',
        'date': '2025-11-27',
        'amount': -45000,
        'budget_id': 'budget_learning',
        'cleared': 'invalid_status'
    }
    
    result = _validate_transaction_data(txn_data)
    
    assert result is not None
    assert result['status'] == 'error'
    assert 'Invalid cleared status' in result['error']


@patch('tools.ynab.transaction_tagger.atoms.db_upsert.DatabaseConnection')
def test_upsert_transaction_insert(mock_db_class):
    """Test first upsert inserts new transaction"""
    mock_db = Mock()
    
    # Simulate INSERT (sync_version = 1)
    mock_db.query.return_value = [{
        'sync_version': 1,
        'updated_at': '2025-11-27T19:30:00'
    }]
    mock_db_class.return_value = mock_db
    
    txn_data = {
        'id': 'test_txn_insert_' + uuid.uuid4().hex[:8],
        'account_id': 'test_account',
        'date': '2025-11-27',
        'amount': -45000,
        'budget_id': 'test_budget',
        'cleared': 'cleared',
        'approved': True
    }
    
    result = upsert_transaction(txn_data)
    
    # Verify result
    assert result['status'] == 'inserted'
    assert result['transaction_id'] == txn_data['id']
    assert result['sync_version'] == 1
    assert result['error'] is None
    assert 'T' in result['timestamp']
    
    # Verify database was called
    assert mock_db.query.call_count == 1
    mock_db.close.assert_called_once()


@patch('tools.ynab.transaction_tagger.atoms.db_upsert.DatabaseConnection')
def test_upsert_transaction_update(mock_db_class):
    """Test second upsert updates existing transaction"""
    mock_db = Mock()
    
    # Simulate UPDATE (sync_version = 2)
    mock_db.query.return_value = [{
        'sync_version': 2,
        'updated_at': '2025-11-27T19:31:00'
    }]
    mock_db_class.return_value = mock_db
    
    txn_data = {
        'id': 'test_txn_update',
        'account_id': 'test_account',
        'date': '2025-11-27',
        'amount': -50000,
        'budget_id': 'test_budget',
        'payee_name': 'Starbucks',
        'category_name': 'Coffee Shops'
    }
    
    result = upsert_transaction(txn_data)
    
    # Verify result
    assert result['status'] == 'updated'
    assert result['transaction_id'] == txn_data['id']
    assert result['sync_version'] == 2
    assert result['error'] is None


@patch('tools.ynab.transaction_tagger.atoms.db_upsert.DatabaseConnection')
def test_upsert_transaction_idempotency(mock_db_class):
    """Test multiple upserts increment sync_version"""
    mock_db = Mock()
    
    # Simulate third UPDATE (sync_version = 3)
    mock_db.query.return_value = [{
        'sync_version': 3,
        'updated_at': '2025-11-27T19:32:00'
    }]
    mock_db_class.return_value = mock_db
    
    txn_data = {
        'id': 'test_txn_idempotent',
        'account_id': 'test_account',
        'date': '2025-11-27',
        'amount': -45000,
        'budget_id': 'test_budget'
    }
    
    result = upsert_transaction(txn_data)
    
    # Even with same data, should update and increment version
    assert result['status'] == 'updated'
    assert result['sync_version'] == 3


@patch('tools.ynab.transaction_tagger.atoms.db_upsert.DatabaseConnection')
def test_upsert_transaction_split_detection(mock_db_class):
    """Test split transaction flags are set correctly"""
    mock_db = Mock()
    
    mock_db.query.return_value = [{
        'sync_version': 1,
        'updated_at': '2025-11-27T19:33:00'
    }]
    mock_db_class.return_value = mock_db
    
    txn_data = {
        'id': 'test_txn_split_' + uuid.uuid4().hex[:8],
        'account_id': 'test_account',
        'date': '2025-11-27',
        'amount': -50000,
        'budget_id': 'test_budget',
        'subtransactions': [
            {'id': 'sub_1', 'amount': -30000},
            {'id': 'sub_2', 'amount': -20000}
        ]
    }
    
    result = upsert_transaction(txn_data)
    
    assert result['status'] == 'inserted'
    assert result['error'] is None
    
    # Verify SQL was called with is_split=True and subtransaction_count=2
    call_args = mock_db.query.call_args
    values_tuple = call_args[0][1]
    
    # is_split is the 14th value (index 13)
    # subtransaction_count is the 15th value (index 14)
    assert values_tuple[13] is True  # is_split
    assert values_tuple[14] == 2  # subtransaction_count


def test_upsert_transaction_missing_required_field():
    """Test error handling for missing required field"""
    txn_data = {
        'id': 'test_txn_missing',
        'account_id': 'test_account',
        # Missing: date, amount, budget_id
    }
    
    result = upsert_transaction(txn_data)
    
    assert result['status'] == 'error'
    assert 'Missing required field' in result['error']
    assert result['sync_version'] is None


@patch('tools.ynab.transaction_tagger.atoms.db_upsert.DatabaseConnection')
def test_upsert_transaction_connection_error(mock_db_class):
    """Test error handling for database connection failure"""
    # Simulate connection error
    mock_db_class.side_effect = DatabaseConnectionError("Connection refused")
    
    txn_data = {
        'id': 'test_txn_conn_error',
        'account_id': 'test_account',
        'date': '2025-11-27',
        'amount': -45000,
        'budget_id': 'test_budget'
    }
    
    result = upsert_transaction(txn_data)
    
    assert result['status'] == 'error'
    assert 'Database connection error' in result['error']
    assert result['sync_version'] is None


@patch('tools.ynab.transaction_tagger.atoms.db_upsert.DatabaseConnection')
def test_upsert_transaction_execution_error(mock_db_class):
    """Test error handling for SQL execution failure"""
    mock_db = Mock()
    
    # Simulate SQL execution error (e.g., constraint violation)
    mock_db.query.side_effect = DatabaseExecutionError("CHECK constraint violated")
    mock_db_class.return_value = mock_db
    
    txn_data = {
        'id': 'test_txn_exec_error',
        'account_id': 'test_account',
        'date': '2025-11-27',
        'amount': -45000,
        'budget_id': 'test_budget'
    }
    
    result = upsert_transaction(txn_data)
    
    assert result['status'] == 'error'
    assert 'SQL execution error' in result['error']
    assert result['sync_version'] is None
    
    # Verify connection was closed even on error
    mock_db.close.assert_called_once()
