"""
Test suite for Pattern Analyzer Molecule.

Tests the Tier 2 categorization logic that uses historical patterns
to recommend categories with ≥80% confidence threshold.
"""

import pytest
from unittest.mock import patch, MagicMock
from tools.ynab.transaction_tagger.molecules.pattern_analyzer import analyze_transaction


class TestPatternAnalyzer:
    """Test suite for Pattern Analyzer molecule."""
    
    @patch('tools.ynab.transaction_tagger.molecules.pattern_analyzer.find_historical_category')
    def test_analyze_transaction_with_match_above_threshold(
        self, mock_find_historical, sample_transaction, sample_historical_match
    ):
        """Test transaction analysis when historical match found above 80% threshold."""
        mock_find_historical.return_value = sample_historical_match
        
        result = analyze_transaction(sample_transaction)
        
        assert result is not None
        assert result['type'] == 'single'
        assert result['category_id'] == 'cat_groceries_xyz'
        assert result['category_name'] == 'Groceries'
        assert result['confidence'] == 0.95
        assert result['method'] == 'historical'
        assert result['source'] == 'pattern_analyzer'
        assert 'reasoning' in result
        assert result['match_count'] == 47
        
        # Verify atom was called with correct parameters
        mock_find_historical.assert_called_once_with(
            payee_name='Test Merchant',
            amount=-450000,
            min_confidence=0.80
        )
    
    @patch('tools.ynab.transaction_tagger.molecules.pattern_analyzer.find_historical_category')
    def test_analyze_transaction_no_match(
        self, mock_find_historical, sample_transaction
    ):
        """Test transaction analysis when no historical match found."""
        mock_find_historical.return_value = None
        
        result = analyze_transaction(sample_transaction)
        
        assert result is None
        mock_find_historical.assert_called_once()
    
    def test_analyze_transaction_missing_payee_name(self):
        """Test validation when payee_name is missing."""
        txn = {'id': 'txn_123', 'amount': -1000}
        
        result = analyze_transaction(txn)
        
        assert result is None
    
    @pytest.mark.parametrize("invalid_payee", [None, "", "   "])
    def test_analyze_transaction_invalid_payee_name(self, invalid_payee):
        """Test validation when payee_name is None or empty string."""
        txn = {'id': 'txn_123', 'payee_name': invalid_payee, 'amount': -1000}
        
        result = analyze_transaction(txn)
        
        assert result is None
    
    @patch('tools.ynab.transaction_tagger.molecules.pattern_analyzer.find_historical_category')
    def test_analyze_transaction_confidence_at_threshold(
        self, mock_find_historical, sample_transaction
    ):
        """Test transaction with confidence exactly at 80% threshold."""
        match = {
            'category_id': 'cat_xyz',
            'category_name': 'Test Category',
            'confidence': 0.80,
            'match_count': 10
        }
        mock_find_historical.return_value = match
        
        result = analyze_transaction(sample_transaction)
        
        assert result is not None
        assert result['confidence'] == 0.80
    
    @patch('tools.ynab.transaction_tagger.molecules.pattern_analyzer.find_historical_category')
    def test_analyze_transaction_confidence_below_threshold(
        self, mock_find_historical, sample_transaction
    ):
        """Test transaction with confidence below 80% threshold."""
        # find_historical_category returns None when below threshold (min_confidence=0.80)
        mock_find_historical.return_value = None
        
        result = analyze_transaction(sample_transaction)
        
        assert result is None
    
    @patch('tools.ynab.transaction_tagger.molecules.pattern_analyzer.find_historical_category')
    def test_analyze_transaction_atom_composition(
        self, mock_find_historical, sample_transaction
    ):
        """Verify Pattern Analyzer correctly composes historical_match atom."""
        mock_find_historical.return_value = None
        
        analyze_transaction(sample_transaction)
        
        # Verify atom was called with correct signature
        mock_find_historical.assert_called_once()
        call_args = mock_find_historical.call_args[1]
        assert 'payee_name' in call_args
        assert 'amount' in call_args
        assert 'min_confidence' in call_args
        assert call_args['min_confidence'] == 0.80
    
    @patch('tools.ynab.transaction_tagger.molecules.pattern_analyzer.find_historical_category')
    def test_analyze_transaction_database_error(
        self, mock_find_historical, sample_transaction
    ):
        """Test error handling when database connection fails."""
        mock_find_historical.side_effect = Exception("Database connection failed")
        
        with pytest.raises(Exception, match="Database connection failed"):
            analyze_transaction(sample_transaction)
    
    @patch('tools.ynab.transaction_tagger.molecules.pattern_analyzer.find_historical_category')
    def test_analyze_transaction_performance(
        self, mock_find_historical, sample_transaction, sample_historical_match
    ):
        """Test Pattern Analyzer performance is under 100ms."""
        import time
        
        mock_find_historical.return_value = sample_historical_match
        
        start = time.time()
        result = analyze_transaction(sample_transaction)
        duration = (time.time() - start) * 1000  # Convert to ms
        
        assert result is not None
        assert duration < 100, f"Pattern Analyzer took {duration:.2f}ms (expected <100ms)"
    
    @patch('tools.ynab.transaction_tagger.molecules.pattern_analyzer.find_historical_category')
    def test_analyze_transaction_reasoning_format(
        self, mock_find_historical, sample_transaction, sample_historical_match
    ):
        """Test that reasoning string is properly formatted."""
        mock_find_historical.return_value = sample_historical_match
        
        result = analyze_transaction(sample_transaction)
        
        assert result is not None
        reasoning = result['reasoning']
        assert 'Test Merchant' in reasoning
        assert '95%' in reasoning
        assert 'Groceries' in reasoning
        assert '47 previous transactions' in reasoning
