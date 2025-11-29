"""Unit tests for molecules layer"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from tools.ynab.transaction_tagger.molecules import sync_transactions


def test_sync_first_run(mocker):
    """Test first run uses INIT_BUDGET_ID and fetches all transactions."""
    # Mock initialize_database
    mock_init = mocker.patch('tools.ynab.transaction_tagger.molecules.data_loader.initialize_database')
    mock_init.return_value = {'status': 'initialized', 'error': None}
    
    # Mock DatabaseConnection to return no last_sync
    mock_db = MagicMock()
    mock_db.query.return_value = []  # No last_sync found
    mocker.patch('tools.ynab.transaction_tagger.molecules.data_loader.DatabaseConnection', return_value=mock_db)
    
    # Mock fetch_transactions
    mock_fetch = mocker.patch('tools.ynab.transaction_tagger.molecules.data_loader.fetch_transactions')
    mock_fetch.return_value = [
        {'id': 'txn1', 'account_id': 'acc1', 'date': '2025-11-27', 'amount': -10000},
        {'id': 'txn2', 'account_id': 'acc1', 'date': '2025-11-26', 'amount': -20000}
    ]
    
    # Mock upsert_transaction
    mock_upsert = mocker.patch('tools.ynab.transaction_tagger.molecules.data_loader.upsert_transaction')
    mock_upsert.side_effect = [
        {'status': 'inserted', 'transaction_id': 'txn1', 'sync_version': 1, 'error': None},
        {'status': 'inserted', 'transaction_id': 'txn2', 'sync_version': 1, 'error': None}
    ]
    
    # Run sync
    result = sync_transactions('ignored')
    
    # Assertions
    assert result['status'] == 'success'
    assert result['run_type'] == 'first_run'
    assert result['budget_used'] == '75f63aa3-9f8f-4dcc-9350-d22535494657'  # INIT_BUDGET_ID
    assert result['transactions_synced'] == 2
    assert result['inserted'] == 2
    assert result['updated'] == 0
    assert result['errors'] == 0
    
    # Verify fetch called with INIT_BUDGET_ID and no since_date
    mock_fetch.assert_called_once_with(
        budget_id='75f63aa3-9f8f-4dcc-9350-d22535494657',
        since_date=None
    )


def test_sync_incremental(mocker):
    """Test incremental run uses TARGET_BUDGET_ID and since_date."""
    # Mock initialize_database
    mock_init = mocker.patch('tools.ynab.transaction_tagger.molecules.data_loader.initialize_database')
    mock_init.return_value = {'status': 'already_initialized', 'error': None}
    
    # Mock DatabaseConnection to return last_sync
    mock_db = MagicMock()
    mock_db.query.return_value = [{
        'value': {
            'timestamp': '2025-11-20T00:00:00Z',
            'budget_id': 'eaf7c5cb-e008-4b62-9733-e7d0ca96cbf1',
            'transaction_count': 100
        }
    }]
    mocker.patch('tools.ynab.transaction_tagger.molecules.data_loader.DatabaseConnection', return_value=mock_db)
    
    # Mock fetch_transactions
    mock_fetch = mocker.patch('tools.ynab.transaction_tagger.molecules.data_loader.fetch_transactions')
    mock_fetch.return_value = [
        {'id': 'txn3', 'account_id': 'acc1', 'date': '2025-11-27', 'amount': -5000}
    ]
    
    # Mock upsert_transaction
    mock_upsert = mocker.patch('tools.ynab.transaction_tagger.molecules.data_loader.upsert_transaction')
    mock_upsert.return_value = {'status': 'inserted', 'transaction_id': 'txn3', 'sync_version': 1, 'error': None}
    
    # Run sync
    result = sync_transactions('ignored')
    
    # Assertions
    assert result['status'] == 'success'
    assert result['run_type'] == 'incremental'
    assert result['budget_used'] == 'eaf7c5cb-e008-4b62-9733-e7d0ca96cbf1'  # TARGET_BUDGET_ID
    assert result['transactions_synced'] == 1
    assert result['last_sync_before'] == '2025-11-20T00:00:00Z'
    
    # Verify fetch called with TARGET_BUDGET_ID and since_date
    mock_fetch.assert_called_once_with(
        budget_id='eaf7c5cb-e008-4b62-9733-e7d0ca96cbf1',
        since_date='2025-11-20'  # Date extracted from timestamp
    )


def test_sync_updates_state(mocker):
    """Test last_sync state updated after successful sync."""
    # Mock all dependencies
    mocker.patch('tools.ynab.transaction_tagger.molecules.data_loader.initialize_database', 
                 return_value={'status': 'already_initialized', 'error': None})
    
    mock_db = MagicMock()
    mock_db.query.return_value = []  # First run
    mocker.patch('tools.ynab.transaction_tagger.molecules.data_loader.DatabaseConnection', return_value=mock_db)
    
    mocker.patch('tools.ynab.transaction_tagger.molecules.data_loader.fetch_transactions', return_value=[])
    
    # Run sync
    result = sync_transactions('ignored')
    
    # Verify execute called to update state
    assert mock_db.execute.called
    execute_call_args = mock_db.execute.call_args[0][0]
    assert 'agent_metadata' in execute_call_args
    assert 'last_sync' in execute_call_args


def test_sync_handles_api_error(mocker):
    """Test API error handled gracefully."""
    # Mock initialize_database
    mocker.patch('tools.ynab.transaction_tagger.molecules.data_loader.initialize_database',
                 return_value={'status': 'already_initialized', 'error': None})
    
    # Mock DatabaseConnection
    mock_db = MagicMock()
    mock_db.query.return_value = []  # First run
    mocker.patch('tools.ynab.transaction_tagger.molecules.data_loader.DatabaseConnection', return_value=mock_db)
    
    # Mock fetch_transactions to raise YNABAPIError
    from common.base_client import YNABAPIError
    mocker.patch('tools.ynab.transaction_tagger.molecules.data_loader.fetch_transactions',
                 side_effect=YNABAPIError("API rate limit exceeded"))
    
    # Run sync
    result = sync_transactions('ignored')
    
    # Assertions
    assert result['status'] == 'error'
    assert 'API' in result['error']
    assert 'rate limit' in result['error']
    assert result['transactions_synced'] == 0
