"""
Test suite for Learning Tracker Molecule.

Tests the continuous learning system that records agent decisions
and user corrections in the database and SOP file.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from tools.ynab.transaction_tagger.molecules.learning_tracker import (
    record_agent_decision,
    record_user_correction
)


class TestLearningTrackerAgentDecision:
    """Test suite for record_agent_decision function."""
    
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.upsert_transaction')
    def test_record_agent_decision_valid(self, mock_upsert):
        """Test recording valid agent decision with all required fields."""
        mock_upsert.return_value = {'status': 'success'}
        
        result = record_agent_decision(
            transaction_id='txn_abc123',
            category_id='cat_groceries_xyz',
            category_name='Groceries',
            categorization_tier=2,
            confidence_score=0.95,
            method='historical'
        )
        
        assert result is True
        mock_upsert.assert_called_once()
        
        # Verify txn_data structure
        call_args = mock_upsert.call_args[0][0]
        assert call_args['id'] == 'txn_abc123'
        assert call_args['category_id'] == 'cat_groceries_xyz'
        assert call_args['category_name'] == 'Groceries'
        assert call_args['confidence_score'] == 0.95
        assert call_args['categorization_tier'] == 2
        assert 'categorization_timestamp' in call_args
    
    def test_record_agent_decision_invalid_transaction_id_empty(self):
        """Test validation when transaction_id is empty."""
        result = record_agent_decision(
            transaction_id='',
            category_id='cat_xyz',
            category_name='Test',
            categorization_tier=1,
            confidence_score=0.9,
            method='sop'
        )
        
        assert result is False
    
    def test_record_agent_decision_invalid_transaction_id_none(self):
        """Test validation when transaction_id is None."""
        result = record_agent_decision(
            transaction_id=None,
            category_id='cat_xyz',
            category_name='Test',
            categorization_tier=1,
            confidence_score=0.9,
            method='sop'
        )
        
        assert result is False
    
    @pytest.mark.parametrize("invalid_tier", [0, 4, -1, 999])
    def test_record_agent_decision_invalid_tier(self, invalid_tier):
        """Test validation when categorization_tier is not 1, 2, or 3."""
        result = record_agent_decision(
            transaction_id='txn_123',
            category_id='cat_xyz',
            category_name='Test',
            categorization_tier=invalid_tier,
            confidence_score=0.9,
            method='sop'
        )
        
        assert result is False
    
    @pytest.mark.parametrize("invalid_score", [-0.1, 1.1, None, "high"])
    def test_record_agent_decision_invalid_confidence_score(self, invalid_score):
        """Test validation when confidence_score is invalid."""
        result = record_agent_decision(
            transaction_id='txn_123',
            category_id='cat_xyz',
            category_name='Test',
            categorization_tier=1,
            confidence_score=invalid_score,
            method='sop'
        )
        
        assert result is False
    
    def test_record_agent_decision_invalid_method(self):
        """Test validation when method is not in allowed list."""
        result = record_agent_decision(
            transaction_id='txn_123',
            category_id='cat_xyz',
            category_name='Test',
            categorization_tier=1,
            confidence_score=0.9,
            method='invalid_method'
        )
        
        assert result is False
    
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.upsert_transaction')
    def test_record_agent_decision_upsert_success(self, mock_upsert):
        """Verify database upsert is called and returns success."""
        mock_upsert.return_value = {'status': 'success'}
        
        result = record_agent_decision(
            transaction_id='txn_123',
            category_id='cat_xyz',
            category_name='Test',
            categorization_tier=1,
            confidence_score=0.9,
            method='sop'
        )
        
        assert result is True
        assert mock_upsert.call_count == 1
    
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.upsert_transaction')
    def test_record_agent_decision_upsert_failure(self, mock_upsert):
        """Test handling when database upsert fails."""
        mock_upsert.return_value = {'status': 'failed', 'error': 'Database error'}
        
        result = record_agent_decision(
            transaction_id='txn_123',
            category_id='cat_xyz',
            category_name='Test',
            categorization_tier=1,
            confidence_score=0.9,
            method='sop'
        )
        
        assert result is False
    
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.upsert_transaction')
    def test_record_agent_decision_timestamp(self, mock_upsert):
        """Verify categorization_timestamp is set correctly."""
        mock_upsert.return_value = {'status': 'success'}
        
        before = datetime.now(timezone.utc).isoformat()
        result = record_agent_decision(
            transaction_id='txn_123',
            category_id='cat_xyz',
            category_name='Test',
            categorization_tier=1,
            confidence_score=0.9,
            method='sop'
        )
        after = datetime.now(timezone.utc).isoformat()
        
        assert result is True
        
        call_args = mock_upsert.call_args[0][0]
        timestamp = call_args['categorization_timestamp']
        
        # Verify timestamp is between before and after (rough check)
        assert before <= timestamp <= after
    
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.upsert_transaction')
    def test_record_agent_decision_performance(self, mock_upsert):
        """Test record_agent_decision performance is under 50ms."""
        import time
        
        mock_upsert.return_value = {'status': 'success'}
        
        start = time.time()
        result = record_agent_decision(
            transaction_id='txn_123',
            category_id='cat_xyz',
            category_name='Test',
            categorization_tier=1,
            confidence_score=0.9,
            method='sop'
        )
        duration = (time.time() - start) * 1000
        
        assert result is True
        assert duration < 50, f"record_agent_decision took {duration:.2f}ms (expected <50ms)"


class TestLearningTrackerUserCorrection:
    """Test suite for record_user_correction function."""
    
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.update_sop_with_rule')
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.upsert_transaction')
    def test_record_user_correction_valid_with_reasoning(self, mock_upsert, mock_update_sop):
        """Test recording valid user correction with all required fields."""
        mock_upsert.return_value = {'status': 'success'}
        mock_update_sop.return_value = True
        
        result = record_user_correction(
            transaction_id='txn_def456',
            agent_suggested_category='Dining Out',
            user_correct_category='Coffee Shops',
            user_correct_category_id='cat_coffee_123',
            payee_name='Starbucks Pike Place',
            reasoning='Starbucks is coffee shop, not restaurant'
        )
        
        assert result is True
        
        # Verify upsert was called correctly
        mock_upsert.assert_called_once()
        call_args = mock_upsert.call_args[0][0]
        assert call_args['id'] == 'txn_def456'
        assert call_args['category_id'] == 'cat_coffee_123'
        assert call_args['category_name'] == 'Coffee Shops'
        assert call_args['user_corrected'] is True
        
        # Verify SOP update was called
        mock_update_sop.assert_called_once()
        sop_args = mock_update_sop.call_args[1]
        assert sop_args['rule_type'] == 'user_correction'
        assert sop_args['rule_data']['payee'] == 'Starbucks Pike Place'
    
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.update_sop_with_rule')
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.upsert_transaction')
    def test_record_user_correction_without_reasoning(self, mock_upsert, mock_update_sop):
        """Test correction without reasoning (optional parameter)."""
        mock_upsert.return_value = {'status': 'success'}
        mock_update_sop.return_value = True
        
        result = record_user_correction(
            transaction_id='txn_123',
            agent_suggested_category='Category A',
            user_correct_category='Category B',
            user_correct_category_id='cat_b',
            payee_name='Test Merchant'
        )
        
        assert result is True
        
        # Verify default reasoning was used
        sop_args = mock_update_sop.call_args[1]
        assert sop_args['rule_data']['reasoning'] == 'User correction'
    
    @pytest.mark.parametrize("invalid_field", [
        {'transaction_id': ''},
        {'transaction_id': None},
        {'agent_suggested_category': ''},
        {'user_correct_category': ''},
        {'user_correct_category_id': ''},
        {'payee_name': ''}
    ])
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.upsert_transaction')
    def test_record_user_correction_invalid_inputs(self, mock_upsert, invalid_field):
        """Test validation of all required fields."""
        valid_params = {
            'transaction_id': 'txn_123',
            'agent_suggested_category': 'Cat A',
            'user_correct_category': 'Cat B',
            'user_correct_category_id': 'cat_b',
            'payee_name': 'Merchant'
        }
        
        # Override one field with invalid value
        params = {**valid_params, **invalid_field}
        
        result = record_user_correction(**params)
        
        assert result is False
        mock_upsert.assert_not_called()
    
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.update_sop_with_rule')
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.upsert_transaction')
    def test_record_user_correction_database_update(self, mock_upsert, mock_update_sop):
        """Verify database is updated with user_corrected flag."""
        mock_upsert.return_value = {'status': 'success'}
        mock_update_sop.return_value = True
        
        record_user_correction(
            transaction_id='txn_123',
            agent_suggested_category='Cat A',
            user_correct_category='Cat B',
            user_correct_category_id='cat_b',
            payee_name='Merchant'
        )
        
        call_args = mock_upsert.call_args[0][0]
        assert call_args['user_corrected'] is True
    
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.update_sop_with_rule')
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.upsert_transaction')
    def test_record_user_correction_sop_update(self, mock_upsert, mock_update_sop):
        """Verify SOP file is updated with correction rule."""
        mock_upsert.return_value = {'status': 'success'}
        mock_update_sop.return_value = True
        
        record_user_correction(
            transaction_id='txn_123',
            agent_suggested_category='Cat A',
            user_correct_category='Cat B',
            user_correct_category_id='cat_b',
            payee_name='Merchant',
            reasoning='Test reasoning'
        )
        
        mock_update_sop.assert_called_once_with(
            rule_type='user_correction',
            rule_data={
                'payee': 'Merchant',
                'correct_category': 'Cat B',
                'category_id': 'cat_b',
                'agent_initially_suggested': 'Cat A',
                'reasoning': 'Test reasoning',
                'confidence': 'High'
            }
        )
    
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.update_sop_with_rule')
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.upsert_transaction')
    def test_record_user_correction_sop_update_fails(self, mock_upsert, mock_update_sop):
        """Test that transaction update succeeds even if SOP update fails."""
        mock_upsert.return_value = {'status': 'success'}
        mock_update_sop.return_value = False  # SOP update fails
        
        result = record_user_correction(
            transaction_id='txn_123',
            agent_suggested_category='Cat A',
            user_correct_category='Cat B',
            user_correct_category_id='cat_b',
            payee_name='Merchant'
        )
        
        # Should still return True (transaction is most critical)
        assert result is True
        mock_upsert.assert_called_once()
    
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.update_sop_with_rule')
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.upsert_transaction')
    def test_record_user_correction_composition(self, mock_upsert, mock_update_sop):
        """Verify record_user_correction composes db_upsert and sop_updater atoms."""
        mock_upsert.return_value = {'status': 'success'}
        mock_update_sop.return_value = True
        
        record_user_correction(
            transaction_id='txn_123',
            agent_suggested_category='Cat A',
            user_correct_category='Cat B',
            user_correct_category_id='cat_b',
            payee_name='Merchant'
        )
        
        # Both atoms should be called
        assert mock_upsert.call_count == 1
        assert mock_update_sop.call_count == 1
    
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.upsert_transaction')
    def test_record_user_correction_database_failure(self, mock_upsert):
        """Test handling when database update fails."""
        mock_upsert.return_value = {'status': 'failed', 'error': 'DB error'}
        
        result = record_user_correction(
            transaction_id='txn_123',
            agent_suggested_category='Cat A',
            user_correct_category='Cat B',
            user_correct_category_id='cat_b',
            payee_name='Merchant'
        )
        
        assert result is False
    
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.update_sop_with_rule')
    @patch('tools.ynab.transaction_tagger.molecules.learning_tracker.upsert_transaction')
    def test_record_user_correction_sop_exception(self, mock_upsert, mock_update_sop):
        """Test that SOP update exception is caught and logged."""
        mock_upsert.return_value = {'status': 'success'}
        mock_update_sop.side_effect = Exception("SOP file locked")
        
        result = record_user_correction(
            transaction_id='txn_123',
            agent_suggested_category='Cat A',
            user_correct_category='Cat B',
            user_correct_category_id='cat_b',
            payee_name='Merchant'
        )
        
        # Should still return True (non-critical failure)
        assert result is True
