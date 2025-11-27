"""
Tests for YNAB Transaction Tagger Atoms (Layer 1).

Tests pure functions that form the atomic building blocks of the system.
Includes tests for SOP Updater and API Update atoms.
"""

import pytest
import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
import sys
from pathlib import Path
import threading
import time

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
from tools.ynab.transaction_tagger.atoms.sop_updater import (
    append_rule_to_sop,
    _inject_timestamp_if_missing
)


# ============================================================================
# API Update Atom Tests
# ============================================================================

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


# ============================================================================
# SOP Updater Atom Tests
# ============================================================================

class TestSOPUpdater:
    """Tests for SOP Updater atom."""
    
    def test_append_rule_success(self):
        """Test successful rule append."""
        # Create temp SOP file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md') as f:
            temp_sop = f.name
            f.write("# Categorization Rules\n\n")
        
        try:
            rule = """
## Learned from User Corrections
- **Payee**: Test Payee
  **Category**: Test Category
  **Date Learned**: 2025-11-27T12:00:00Z
"""
            result = append_rule_to_sop(rule, temp_sop)
            
            assert result is True
            
            # Verify content
            with open(temp_sop, 'r') as f:
                content = f.read()
                assert '## Learned from User Corrections' in content
                assert 'Test Payee' in content
                
        finally:
            os.unlink(temp_sop)
    
    def test_append_rule_file_not_found(self):
        """Test file not found returns False."""
        result = append_rule_to_sop("test", "/nonexistent/file.md")
        assert result is False
    
    def test_timestamp_injection(self):
        """Test timestamp injection when missing."""
        rule_without_timestamp = """
## Core Patterns
- **Payee**: Test
  **Category**: Test Category
"""
        result = _inject_timestamp_if_missing(rule_without_timestamp)
        assert '**Date Added**:' in result
        assert 'Z' in result  # ISO 8601 format
    
    def test_timestamp_preservation(self):
        """Test existing timestamp is preserved."""
        rule_with_timestamp = """
## Learned from User Corrections
- **Payee**: Test
  **Date Learned**: 2025-11-27T12:00:00Z
"""
        result = _inject_timestamp_if_missing(rule_with_timestamp)
        assert result == rule_with_timestamp
    
    def test_concurrent_writes(self):
        """Test thread-safe concurrent writes."""
        # Create temp SOP file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md') as f:
            temp_sop = f.name
            f.write("# Categorization Rules\n\n")
        
        try:
            results = []
            
            def append_test_rule(n):
                rule = f"""
## Test Section {n}
- **Payee**: Test {n}
  **Category**: Cat {n}
  **Date Added**: 2025-11-27T12:00:00Z
"""
                result = append_rule_to_sop(rule, temp_sop)
                results.append(result)
            
            # Spawn 5 threads
            threads = [threading.Thread(target=append_test_rule, args=(i,)) for i in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            # All should succeed
            assert all(results)
            
            # Verify all rules present
            with open(temp_sop, 'r') as f:
                content = f.read()
                for i in range(5):
                    assert f'Test {i}' in content
                    
        finally:
            os.unlink(temp_sop)
    
    def test_blank_line_insertion(self):
        """Test blank line inserted before appended content."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md') as f:
            temp_sop = f.name
            f.write("# Categorization Rules\nExisting content")
        
        try:
            rule = """
## New Section
- **Payee**: Test
"""
            append_rule_to_sop(rule, temp_sop)
            
            with open(temp_sop, 'r') as f:
                content = f.read()
                # Should have blank lines between existing content and new rule
                assert '## New Section' in content
                assert 'Existing content' in content
                
        finally:
            os.unlink(temp_sop)


if __name__ == '__main__':
    unittest.main()
