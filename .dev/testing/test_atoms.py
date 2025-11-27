"""Unit tests for YNAB Transaction Tagger atoms"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from common.base_client import (
    BaseYNABClient, YNABConflictError, YNABNotFoundError,
    YNABUnauthorizedError, YNABRateLimitError, YNABAPIError
)
from tools.ynab.transaction_tagger.atoms.api_update import (
    update_transaction_category,
    update_split_transaction,
    _validate_subtransaction_amounts
)


class TestBaseYNABClientPut(unittest.TestCase):
    """Test BaseYNABClient.put() method"""
    
    @patch('common.base_client.os.getenv')
    @patch('common.base_client.requests.put')
    def test_put_success(self, mock_put, mock_getenv):
        """Test successful PUT request (200 OK)"""
        mock_getenv.return_value = 'test-token'
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': {'transaction': {'id': 'txn-123'}}}
        mock_put.return_value = mock_response
        
        client = BaseYNABClient()
        result = client.put('/budgets/b1/transactions/t1', {'transaction': {'category_id': 'c1'}})
        
        self.assertEqual(result, {'data': {'transaction': {'id': 'txn-123'}}})
        mock_put.assert_called_once()
    
    @patch('common.base_client.os.getenv')
    @patch('common.base_client.requests.put')
    def test_put_conflict(self, mock_put, mock_getenv):
        """Test 409 Conflict error"""
        mock_getenv.return_value = 'test-token'
        mock_response = Mock()
        mock_response.status_code = 409
        mock_put.return_value = mock_response
        
        client = BaseYNABClient()
        with self.assertRaises(YNABConflictError):
            client.put('/budgets/b1/transactions/t1', {})
    
    @patch('common.base_client.os.getenv')
    @patch('common.base_client.requests.put')
    def test_put_unauthorized(self, mock_put, mock_getenv):
        """Test 401 Unauthorized error"""
        mock_getenv.return_value = 'test-token'
        mock_response = Mock()
        mock_response.status_code = 401
        mock_put.return_value = mock_response
        
        client = BaseYNABClient()
        with self.assertRaises(YNABUnauthorizedError):
            client.put('/budgets/b1/transactions/t1', {})
    
    @patch('common.base_client.os.getenv')
    @patch('common.base_client.requests.put')
    def test_put_not_found(self, mock_put, mock_getenv):
        """Test 404 Not Found error"""
        mock_getenv.return_value = 'test-token'
        mock_response = Mock()
        mock_response.status_code = 404
        mock_put.return_value = mock_response
        
        client = BaseYNABClient()
        with self.assertRaises(YNABNotFoundError):
            client.put('/budgets/b1/transactions/t1', {})
    
    @patch('common.base_client.os.getenv')
    @patch('common.base_client.requests.put')
    def test_put_rate_limit(self, mock_put, mock_getenv):
        """Test 429 Rate Limit error"""
        mock_getenv.return_value = 'test-token'
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {'Retry-After': '60'}
        mock_put.return_value = mock_response
        
        client = BaseYNABClient()
        with self.assertRaises(YNABRateLimitError) as ctx:
            client.put('/budgets/b1/transactions/t1', {})
        
        self.assertEqual(ctx.exception.retry_after, 60)


class TestUpdateTransactionCategory(unittest.TestCase):
    """Test update_transaction_category() function"""
    
    @patch('tools.ynab.transaction_tagger.atoms.api_update.BaseYNABClient')
    def test_update_success(self, mock_client_class):
        """Test successful transaction update"""
        mock_client = Mock()
        mock_client.put.return_value = {'data': {'transaction': {'id': 'txn-123'}}}
        mock_client_class.return_value = mock_client
        
        result = update_transaction_category('b1', 'txn-123', 'cat-456')
        
        self.assertTrue(result)
        mock_client.put.assert_called_once_with(
            '/budgets/b1/transactions/txn-123',
            {'transaction': {'category_id': 'cat-456'}}
        )
    
    @patch('tools.ynab.transaction_tagger.atoms.api_update.BaseYNABClient')
    def test_update_conflict(self, mock_client_class):
        """Test conflict returns False"""
        mock_client = Mock()
        mock_client.put.side_effect = YNABConflictError()
        mock_client_class.return_value = mock_client
        
        result = update_transaction_category('b1', 'txn-123', 'cat-456')
        
        self.assertFalse(result)
    
    @patch('tools.ynab.transaction_tagger.atoms.api_update.BaseYNABClient')
    def test_update_api_error_propagates(self, mock_client_class):
        """Test other API errors propagate"""
        mock_client = Mock()
        mock_client.put.side_effect = YNABNotFoundError("Not found")
        mock_client_class.return_value = mock_client
        
        with self.assertRaises(YNABNotFoundError):
            update_transaction_category('b1', 'txn-123', 'cat-456')


class TestValidateSubtransactionAmounts(unittest.TestCase):
    """Test _validate_subtransaction_amounts() helper"""
    
    def test_validation_success(self):
        """Test valid subtransaction amounts"""
        subtxns = [
            {'amount': -10000},
            {'amount': -5000}
        ]
        
        # Should not raise
        _validate_subtransaction_amounts(subtxns, -15000)
    
    def test_validation_failure(self):
        """Test invalid subtransaction amounts"""
        subtxns = [
            {'amount': -10000},
            {'amount': -6000}  # Off by 1000
        ]
        
        with self.assertRaises(ValueError) as ctx:
            _validate_subtransaction_amounts(subtxns, -15000)
        
        error_msg = str(ctx.exception)
        self.assertIn('milliunits', error_msg)
        self.assertIn('-16000', error_msg)
        self.assertIn('-15000', error_msg)
    
    def test_validation_empty_list(self):
        """Test empty subtransactions list"""
        with self.assertRaises(ValueError) as ctx:
            _validate_subtransaction_amounts([], -15000)
        
        self.assertIn('empty', str(ctx.exception))
    
    def test_validation_zero_amounts(self):
        """Test zero amounts (valid if sum is zero)"""
        subtxns = [
            {'amount': 0},
            {'amount': 0}
        ]
        
        # Should not raise
        _validate_subtransaction_amounts(subtxns, 0)


class TestUpdateSplitTransaction(unittest.TestCase):
    """Test update_split_transaction() function"""
    
    @patch('tools.ynab.transaction_tagger.atoms.api_update.BaseYNABClient')
    def test_split_update_success(self, mock_client_class):
        """Test successful split transaction update"""
        mock_client = Mock()
        mock_client.put.return_value = {'data': {'transaction': {'id': 'txn-123'}}}
        mock_client_class.return_value = mock_client
        
        subtxns = [
            {'amount': -10000, 'category_id': 'cat-1'},
            {'amount': -5000, 'category_id': 'cat-2'}
        ]
        
        result = update_split_transaction('b1', 'txn-123', subtxns, -15000)
        
        self.assertTrue(result)
        mock_client.put.assert_called_once_with(
            '/budgets/b1/transactions/txn-123',
            {'transaction': {'subtransactions': subtxns}}
        )
    
    @patch('tools.ynab.transaction_tagger.atoms.api_update.BaseYNABClient')
    def test_split_update_conflict(self, mock_client_class):
        """Test split conflict returns False"""
        mock_client = Mock()
        mock_client.put.side_effect = YNABConflictError()
        mock_client_class.return_value = mock_client
        
        subtxns = [
            {'amount': -10000, 'category_id': 'cat-1'},
            {'amount': -5000, 'category_id': 'cat-2'}
        ]
        
        result = update_split_transaction('b1', 'txn-123', subtxns, -15000)
        
        self.assertFalse(result)
    
    def test_split_update_amount_validation_failure(self):
        """Test amount validation prevents API call"""
        subtxns = [
            {'amount': -10000, 'category_id': 'cat-1'},
            {'amount': -6000, 'category_id': 'cat-2'}  # Wrong total
        ]
        
        with self.assertRaises(ValueError):
            update_split_transaction('b1', 'txn-123', subtxns, -15000)
    
    def test_split_update_empty_subtransactions(self):
        """Test empty subtransactions raises ValueError"""
        with self.assertRaises(ValueError):
            update_split_transaction('b1', 'txn-123', [], -15000)


if __name__ == '__main__':
    unittest.main()
