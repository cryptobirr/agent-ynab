"""Tests for tagging workflow template"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from tools.ynab.transaction_tagger.templates.tagging_workflow import (
    generate_recommendations,
    submit_approved_changes,
    _load_budget_config,
    _load_budget_from_env,
    _check_sop_rules,
    _categorize_transaction,
    _build_summary
)


class TestBudgetConfiguration:
    """Test budget configuration loading"""
    
    def test_load_budget_config_personal_only(self, mock_vault):
        """Test loading personal budget only"""
        budgets = _load_budget_config('personal')
        assert 'personal' in budgets
        assert 'business' not in budgets
        assert budgets['personal']['budget_id'] == 'personal-budget-123'
        assert budgets['personal']['budget_name'] == 'Personal Budget'
    
    def test_load_budget_config_business_only(self, mock_vault):
        """Test loading business budget only"""
        budgets = _load_budget_config('business')
        assert 'business' in budgets
        assert 'personal' not in budgets
        assert budgets['business']['budget_id'] == 'business-budget-456'
    
    def test_load_budget_config_both(self, mock_vault):
        """Test loading both budgets"""
        budgets = _load_budget_config('both')
        assert 'personal' in budgets
        assert 'business' in budgets
        assert len(budgets) == 2
    
    def test_load_budget_config_invalid_type(self, mock_vault):
        """Test invalid budget_type raises ValueError"""
        with pytest.raises(ValueError, match="Invalid budget_type"):
            _load_budget_config('invalid')
    
    def test_load_budget_from_env_personal(self, monkeypatch):
        """Test loading from env vars - personal"""
        monkeypatch.setenv('YNAB_PERSONAL_BUDGET_ID', 'env-personal-123')
        budgets = _load_budget_from_env('personal')
        assert budgets['personal']['budget_id'] == 'env-personal-123'
    
    def test_load_budget_from_env_missing(self, monkeypatch):
        """Test missing env var raises ValueError"""
        monkeypatch.delenv('YNAB_PERSONAL_BUDGET_ID', raising=False)
        with pytest.raises(ValueError, match="Missing YNAB_PERSONAL_BUDGET_ID"):
            _load_budget_from_env('personal')


class TestSOPRuleMatching:
    """Test SOP rule matching (Tier 1)"""
    
    def test_check_sop_rules_exact_match(self):
        """Test exact pattern match"""
        txn = {'payee_name': 'Starbucks'}
        rules = {
            'core_patterns': [{
                'pattern': 'Starbucks',
                'category': 'Coffee Shops',
                'confidence': 'High',
                'pattern_type': 'exact',
                'source': 'Historical'
            }],
            'user_corrections': []
        }
        match = _check_sop_rules(txn, rules)
        assert match is not None
        assert match['category_name'] == 'Coffee Shops'
        assert match['confidence'] == 1.0
        assert 'Historical' in match['reasoning']
    
    def test_check_sop_rules_prefix_match(self):
        """Test prefix pattern match"""
        txn = {'payee_name': 'Amazon Prime Video'}
        rules = {
            'core_patterns': [{
                'pattern': 'Amazon*',
                'category': 'Online Shopping',
                'confidence': 'High',
                'pattern_type': 'prefix',
                'source': 'Pattern'
            }],
            'user_corrections': []
        }
        match = _check_sop_rules(txn, rules)
        assert match is not None
        assert match['category_name'] == 'Online Shopping'
    
    def test_check_sop_rules_contains_match(self):
        """Test contains pattern match"""
        txn = {'payee_name': 'Shell Gas Station'}
        rules = {
            'core_patterns': [{
                'pattern': '*Shell*',
                'category': 'Gas & Fuel',
                'confidence': 'High',
                'pattern_type': 'contains',
                'source': 'Pattern'
            }],
            'user_corrections': []
        }
        match = _check_sop_rules(txn, rules)
        assert match is not None
        assert match['category_name'] == 'Gas & Fuel'
    
    def test_check_sop_rules_user_correction_priority(self):
        """Test user correction takes priority over core patterns"""
        txn = {'payee_name': 'Amazon'}
        rules = {
            'user_corrections': [{
                'payee': 'Amazon',
                'correct_category': 'Business Expenses',
                'reasoning': 'User preference'
            }],
            'core_patterns': [{
                'pattern': 'Amazon',
                'category': 'Online Shopping',
                'confidence': 'High',
                'pattern_type': 'exact'
            }]
        }
        match = _check_sop_rules(txn, rules)
        assert match is not None
        assert match['category_name'] == 'Business Expenses'
        assert 'User correction' in match['reasoning']
    
    def test_check_sop_rules_confidence_threshold(self):
        """Test low confidence patterns are rejected"""
        txn = {'payee_name': 'Unknown Store'}
        rules = {
            'core_patterns': [{
                'pattern': 'Unknown Store',
                'category': 'Shopping',
                'confidence': 'Low',  # 0.70, below 0.95 threshold
                'pattern_type': 'exact'
            }],
            'user_corrections': []
        }
        match = _check_sop_rules(txn, rules)
        assert match is None  # Below threshold
    
    def test_check_sop_rules_no_payee(self):
        """Test empty payee_name returns None"""
        txn = {'payee_name': ''}
        rules = {'core_patterns': [], 'user_corrections': []}
        match = _check_sop_rules(txn, rules)
        assert match is None


class TestThreeTierCategorization:
    """Test 3-tier categorization logic"""
    
    def test_categorize_transaction_tier_1_sop(self, mock_sop_rules):
        """Test Tier 1 (SOP) categorization"""
        txn = {
            'id': 'txn-1',
            'payee_name': 'Starbucks',
            'amount': -500,
            'date': '2025-11-28'
        }
        result = _categorize_transaction(txn, mock_sop_rules)
        
        assert result['tier'] == 'sop'
        assert result['method'] == 'sop'
        assert result['confidence'] == 1.0
        assert result['category_name'] == 'Coffee Shops'
        assert result['type'] == 'single'
    
    @patch('tools.ynab.transaction_tagger.templates.tagging_workflow.analyze_transaction')
    def test_categorize_transaction_tier_2_historical(self, mock_analyze):
        """Test Tier 2 (Historical) categorization"""
        # Mock historical match
        mock_analyze.return_value = {
            'category_id': 'cat-123',
            'category_name': 'Groceries',
            'confidence': 0.85,
            'reasoning': 'Historical pattern',
            'type': 'single'
        }
        
        txn = {
            'id': 'txn-2',
            'payee_name': 'Unknown Grocery',
            'amount': -2500
        }
        rules = {'core_patterns': [], 'user_corrections': []}
        
        result = _categorize_transaction(txn, rules)
        
        assert result['tier'] == 'historical'
        assert result['method'] == 'historical'
        assert result['confidence'] == 0.85
        assert result['category_name'] == 'Groceries'
        mock_analyze.assert_called_once_with(txn)
    
    @patch('tools.ynab.transaction_tagger.templates.tagging_workflow.analyze_transaction')
    def test_categorize_transaction_tier_3_manual(self, mock_analyze):
        """Test Tier 3 (Manual Review) fallback"""
        # No historical match
        mock_analyze.return_value = None
        
        txn = {
            'id': 'txn-3',
            'payee_name': 'Unknown Merchant',
            'amount': -1000
        }
        rules = {'core_patterns': [], 'user_corrections': []}
        
        result = _categorize_transaction(txn, rules)
        
        assert result['tier'] == 'research'
        assert result['method'] == 'manual'
        assert result['confidence'] == 0.0
        assert result['category_name'] == 'Uncategorized'
        assert 'Requires manual categorization' in result['reasoning']
    
    def test_tier_precedence(self, mock_sop_rules):
        """Test SOP rules take precedence over historical"""
        with patch('tools.ynab.transaction_tagger.templates.tagging_workflow.analyze_transaction') as mock_analyze:
            # Mock historical match
            mock_analyze.return_value = {
                'category_id': 'cat-999',
                'category_name': 'Wrong Category',
                'confidence': 0.85
            }
            
            # Transaction matches SOP rule
            txn = {
                'id': 'txn-4',
                'payee_name': 'Starbucks'
            }
            
            result = _categorize_transaction(txn, mock_sop_rules)
            
            # Should use SOP, not historical
            assert result['tier'] == 'sop'
            assert result['category_name'] == 'Coffee Shops'
            # analyze_transaction should NOT be called
            mock_analyze.assert_not_called()


class TestSummaryGeneration:
    """Test summary statistics"""
    
    def test_build_summary_mixed_tiers(self):
        """Test summary with mixed categorization tiers"""
        transactions = [
            {'tier': 'sop'},
            {'tier': 'sop'},
            {'tier': 'historical'},
            {'tier': 'historical'},
            {'tier': 'historical'},
            {'tier': 'research'},
        ]
        
        summary = _build_summary(transactions)
        
        assert summary['total'] == 6
        assert summary['sop_matches'] == 2
        assert summary['historical_matches'] == 3
        assert summary['needs_review'] == 1
    
    def test_build_summary_empty(self):
        """Test summary with no transactions"""
        summary = _build_summary([])
        
        assert summary['total'] == 0
        assert summary['sop_matches'] == 0
        assert summary['historical_matches'] == 0
        assert summary['needs_review'] == 0


class TestGenerateRecommendations:
    """Test generate_recommendations function"""
    
    def test_generate_recommendations_success(
        self,
        mock_vault,
        mock_api_fetch,
        mock_sop_loader
    ):
        """Test successful recommendation generation"""
        with patch('tools.ynab.transaction_tagger.templates.tagging_workflow.analyze_transaction') as mock_analyze:
            mock_analyze.return_value = None  # Force tier 3
            
            result = generate_recommendations(budget_type='personal')
            
            assert result['status'] == 'success'
            assert 'personal' in result['budgets']
            assert 'timestamp' in result
            assert len(result['errors']) == 0
            
            budget_result = result['budgets']['personal']
            assert budget_result['budget_id'] == 'personal-budget-123'
            assert 'transactions' in budget_result
            assert 'summary' in budget_result
            assert len(budget_result['transactions']) > 0
    
    def test_generate_recommendations_invalid_budget_type(self):
        """Test invalid budget_type"""
        result = generate_recommendations(budget_type='invalid')
        
        assert result['status'] == 'failed'
        assert len(result['errors']) == 1
        assert result['errors'][0]['type'] == 'validation_error'
        assert 'Invalid budget_type' in result['errors'][0]['error']
    
    def test_generate_recommendations_vault_error(self):
        """Test Vault configuration error"""
        with patch('tools.ynab.transaction_tagger.templates.tagging_workflow.VaultClient') as mock_vault_cls:
            mock_vault = Mock()
            mock_vault.is_connected.return_value = True
            mock_vault.kv_get.return_value = None  # Missing credentials
            mock_vault_cls.return_value = mock_vault
            
            result = generate_recommendations(budget_type='personal')
            
            assert result['status'] == 'failed'
            assert len(result['errors']) == 1
            assert result['errors'][0]['type'] == 'config_error'
    
    def test_generate_recommendations_api_error(
        self,
        mock_vault,
        mock_sop_loader
    ):
        """Test API error handling"""
        with patch('tools.ynab.transaction_tagger.templates.tagging_workflow.fetch_transactions') as mock_fetch:
            from common.base_client import YNABAPIError
            mock_fetch.side_effect = YNABAPIError("API connection failed")
            
            result = generate_recommendations(budget_type='personal')
            
            assert result['status'] == 'failed'
            assert len(result['errors']) == 1
            assert result['errors'][0]['type'] == 'api_error'
            assert result['errors'][0]['budget'] == 'personal'
    
    def test_generate_recommendations_uncategorized_filter(
        self,
        mock_vault,
        mock_sop_loader
    ):
        """Test uncategorized_only filter"""
        with patch('tools.ynab.transaction_tagger.templates.tagging_workflow.fetch_transactions') as mock_fetch:
            mock_fetch.return_value = [
                {'id': 'txn-1', 'payee_name': 'Test', 'category_id': None, 'date': '2025-11-28'},
                {'id': 'txn-2', 'payee_name': 'Test2', 'category_id': 'cat-1', 'date': '2025-11-28'}
            ]
            
            with patch('tools.ynab.transaction_tagger.templates.tagging_workflow.fetch_categories') as mock_cat:
                mock_cat.return_value = []
                
                with patch('tools.ynab.transaction_tagger.templates.tagging_workflow.analyze_transaction') as mock_analyze:
                    mock_analyze.return_value = None
                    
                    result = generate_recommendations(budget_type='personal', uncategorized_only=True)
                    
                    # Should only process txn-1 (uncategorized)
                    assert len(result['budgets']['personal']['transactions']) == 1
                    assert result['budgets']['personal']['transactions'][0]['id'] == 'txn-1'


class TestSubmitApprovedChanges:
    """Test submit_approved_changes function"""
    
    def test_submit_approved_changes_success(self):
        """Test successful change submission"""
        with patch('tools.ynab.transaction_tagger.templates.tagging_workflow._sync_approved_changes') as mock_sync:
            mock_sync.return_value = {
                'status': 'success',
                'succeeded': 2,
                'failed': 0,
                'total': 2,
                'results': []
            }
            
            changes = [
                {
                    'transaction_id': 'txn-1',
                    'category_id': 'cat-1',
                    'category_name': 'Groceries',
                    'categorization_tier': 1,
                    'confidence_score': 1.0,
                    'method': 'sop'
                },
                {
                    'transaction_id': 'txn-2',
                    'category_id': 'cat-2',
                    'category_name': 'Gas & Fuel',
                    'categorization_tier': 2,
                    'confidence_score': 0.85,
                    'method': 'historical'
                }
            ]
            
            result = submit_approved_changes('budget-123', changes)
            
            assert result['status'] == 'success'
            assert result['succeeded'] == 2
            assert result['total'] == 2
            assert 'timestamp' in result
            
            mock_sync.assert_called_once_with('budget-123', changes)
    
    def test_submit_approved_changes_adds_timestamp(self):
        """Test timestamp is added to result"""
        with patch('tools.ynab.transaction_tagger.templates.tagging_workflow._sync_approved_changes') as mock_sync:
            mock_sync.return_value = {
                'status': 'success',
                'succeeded': 1,
                'failed': 0,
                'total': 1
            }
            
            result = submit_approved_changes('budget-123', [])
            
            assert 'timestamp' in result
            # Verify ISO 8601 format
            assert result['timestamp'].endswith('Z')
            datetime.fromisoformat(result['timestamp'].replace('Z', '+00:00'))
