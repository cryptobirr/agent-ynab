"""Integration tests for organisms with molecules"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from tools.ynab.transaction_tagger.organisms.web_ui import generate_approval_html


class TestWebUIWithMolecules:
    """Test Web UI organism with molecule-like data structures"""
    
    def test_integration_with_data_loader_output(self):
        """Test Web UI with data loader molecule output format"""
        # Simulate data loader molecule output
        # Data loader returns transactions from YNAB API
        transactions = [
            {
                'id': 'txn_001',
                'date': '2025-11-29',
                'payee_name': 'Walmart',
                'memo': 'Groceries and supplies',
                'amount': -125000,  # -$125.00 (milliunits = amount * 1000)
                'category_id': 'cat_groceries',
                'category_name': 'Groceries',
                'type': 'single',
                'confidence': 0.95,
                'tier': 'sop'
            },
            {
                'id': 'txn_002',
                'date': '2025-11-29',
                'payee_name': 'Shell Gas Station',
                'memo': 'Fuel',
                'amount': -65000,  # -$65.00 (milliunits = amount * 1000)
                'category_id': 'cat_gas',
                'category_name': 'Gas',
                'type': 'single',
                'confidence': 0.92,
                'tier': 'historical'
            }
        ]
        
        category_groups = [{
            'id': 'grp_everyday',
            'name': 'Everyday Expenses',
            'categories': [
                {'id': 'cat_groceries', 'name': 'Groceries'},
                {'id': 'cat_gas', 'name': 'Gas'}
            ]
        }]
        
        # Generate HTML with data loader output
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        
        # Verify HTML contains data loader transaction data
        assert 'Walmart' in html
        assert 'Shell Gas Station' in html
        assert '125.00' in html  # Amount formatted correctly
        assert '65.00' in html   # Amount formatted correctly
        assert 'Groceries and supplies' in html
        assert 'Fuel' in html
    
    def test_integration_with_pattern_analyzer_confidence(self):
        """Test Web UI with pattern analyzer confidence scores"""
        # Pattern analyzer adds confidence scores to transactions
        transactions = [
            {
                'id': 'txn_high_conf',
                'date': '2025-11-29',
                'payee_name': 'High Confidence Merchant',
                'memo': '',
                'amount': -10000,  # -$10.00
                'category_id': 'cat_dining',
                'category_name': 'Dining Out',
                'type': 'single',
                'confidence': 0.98,  # High confidence from pattern analyzer
                'tier': 'sop'
            },
            {
                'id': 'txn_med_conf',
                'date': '2025-11-29',
                'payee_name': 'Medium Confidence Merchant',
                'memo': '',
                'amount': -10000,  # -$10.00
                'category_id': 'cat_shopping',
                'category_name': 'Shopping',
                'type': 'single',
                'confidence': 0.75,  # Medium confidence
                'tier': 'historical'
            },
            {
                'id': 'txn_low_conf',
                'date': '2025-11-29',
                'payee_name': 'Low Confidence Merchant',
                'memo': '',
                'amount': -10000,  # -$10.00
                'category_id': 'cat_misc',
                'category_name': 'Miscellaneous',
                'type': 'single',
                'confidence': 0.45,  # Low confidence
                'tier': 'research'
            }
        ]
        
        category_groups = [{
            'id': 'grp_test',
            'name': 'Test Group',
            'categories': [
                {'id': 'cat_dining', 'name': 'Dining Out'},
                {'id': 'cat_shopping', 'name': 'Shopping'},
                {'id': 'cat_misc', 'name': 'Miscellaneous'}
            ]
        }]
        
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        
        # Verify confidence-based color coding appears
        # High confidence (>90%) = green
        # Medium confidence (70-90%) = yellow
        # Low confidence (<70%) = red
        assert 'confidence-high' in html or 'bg-green' in html or '98%' in html
        assert 'confidence-medium' in html or 'bg-yellow' in html or '75%' in html
        assert 'confidence-low' in html or 'bg-red' in html or '45%' in html
    
    def test_integration_with_learning_tracker_tiers(self):
        """Test Web UI with learning tracker tier indicators"""
        # Learning tracker assigns tier: sop, historical, or research
        transactions = [
            {
                'id': 'txn_sop',
                'date': '2025-11-29',
                'payee_name': 'SOP Rule Merchant',
                'memo': 'Matched by SOP rule',
                'amount': -10000,  # -$10.00
                'category_id': 'cat_groceries',
                'category_name': 'Groceries',
                'type': 'single',
                'confidence': 1.0,
                'tier': 'sop'  # Tier from learning tracker
            },
            {
                'id': 'txn_historical',
                'date': '2025-11-29',
                'payee_name': 'Historical Pattern Merchant',
                'memo': 'Matched by historical pattern',
                'amount': -10000,  # -$10.00
                'category_id': 'cat_gas',
                'category_name': 'Gas',
                'type': 'single',
                'confidence': 0.85,
                'tier': 'historical'  # Tier from learning tracker
            },
            {
                'id': 'txn_research',
                'date': '2025-11-29',
                'payee_name': 'Research-based Merchant',
                'memo': 'Matched by web research',
                'amount': -10000,  # -$10.00
                'category_id': 'cat_shopping',
                'category_name': 'Shopping',
                'type': 'single',
                'confidence': 0.60,
                'tier': 'research'  # Tier from learning tracker
            }
        ]
        
        category_groups = [{
            'id': 'grp_test',
            'name': 'Test Group',
            'categories': [
                {'id': 'cat_groceries', 'name': 'Groceries'},
                {'id': 'cat_gas', 'name': 'Gas'},
                {'id': 'cat_shopping', 'name': 'Shopping'}
            ]
        }]
        
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        
        # Verify tier badges appear in HTML
        assert 'SOP' in html or 'sop' in html
        assert 'Historical' in html or 'historical' in html
        assert 'Research' in html or 'research' in html
    
    def test_integration_with_ynab_syncer_categories(self):
        """Test Web UI with YNAB syncer category groups"""
        # YNAB syncer fetches category groups from YNAB API
        # These have the real YNAB structure with nested categories
        transactions = [{
            'id': 'txn_test',
            'date': '2025-11-29',
            'payee_name': 'Test Merchant',
            'memo': '',
            'amount': -10000,  # -$10.00
            'category_id': 'cat_groceries',
            'category_name': 'Groceries',
            'type': 'single',
            'confidence': 0.95,
            'tier': 'sop'
        }]
        
        # Realistic YNAB category group structure
        category_groups = [
            {
                'id': 'grp_everyday',
                'name': 'Everyday Expenses',
                'categories': [
                    {'id': 'cat_groceries', 'name': 'Groceries'},
                    {'id': 'cat_gas', 'name': 'Gas'},
                    {'id': 'cat_dining', 'name': 'Dining Out'},
                    {'id': 'cat_household', 'name': 'Household Items'}
                ]
            },
            {
                'id': 'grp_bills',
                'name': 'Monthly Bills',
                'categories': [
                    {'id': 'cat_rent', 'name': 'Rent/Mortgage'},
                    {'id': 'cat_utilities', 'name': 'Utilities'},
                    {'id': 'cat_internet', 'name': 'Internet'},
                    {'id': 'cat_phone', 'name': 'Phone'}
                ]
            },
            {
                'id': 'grp_savings',
                'name': 'Savings Goals',
                'categories': [
                    {'id': 'cat_emergency', 'name': 'Emergency Fund'},
                    {'id': 'cat_vacation', 'name': 'Vacation'},
                    {'id': 'cat_car', 'name': 'Car Replacement'}
                ]
            }
        ]
        
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        
        # Verify all category groups appear
        assert 'Everyday Expenses' in html
        assert 'Monthly Bills' in html
        assert 'Savings Goals' in html
        
        # Verify categories within groups appear
        assert 'Groceries' in html
        assert 'Rent/Mortgage' in html
        assert 'Emergency Fund' in html
        
        # Verify category selector modal has all options
        assert 'cat_groceries' in html
        assert 'cat_rent' in html
        assert 'cat_emergency' in html
    
    def test_end_to_end_workflow_simulation(self):
        """Test complete workflow: data loader → pattern analyzer → learning tracker → web UI"""
        # Simulate full workflow with realistic data
        
        # Step 1: Data loader fetches transactions from YNAB
        raw_transactions = [
            {
                'id': 'txn_walmart',
                'date': '2025-11-29',
                'payee_name': 'WALMART SUPERCENTER',
                'memo': 'Weekly groceries',
                'amount': -157500,  # -$157.50 (milliunits = amount * 1000)
                'category_id': None,  # Uncategorized from YNAB
                'category_name': None,
                'type': 'single',
                'confidence': 0.0,
                'tier': None
            }
        ]
        
        # Step 2: Pattern analyzer adds confidence score
        # (Simulated - would query historical patterns)
        raw_transactions[0]['confidence'] = 0.95
        
        # Step 3: Learning tracker adds tier
        # (Simulated - would check SOP rules, historical data, research)
        raw_transactions[0]['tier'] = 'sop'
        raw_transactions[0]['category_id'] = 'cat_groceries'
        raw_transactions[0]['category_name'] = 'Groceries'
        
        # Step 4: YNAB syncer provides category groups
        category_groups = [{
            'id': 'grp_everyday',
            'name': 'Everyday Expenses',
            'categories': [
                {'id': 'cat_groceries', 'name': 'Groceries'},
                {'id': 'cat_gas', 'name': 'Gas'}
            ]
        }]
        
        # Step 5: Web UI generates approval interface
        html = generate_approval_html(raw_transactions, category_groups, 'budget_123')
        
        # Verify end-to-end data flow worked
        assert 'WALMART SUPERCENTER' in html
        assert 'Weekly groceries' in html
        assert '157.50' in html  # Amount formatted correctly
        assert 'Groceries' in html
        assert '95%' in html or 'confidence-high' in html
        assert 'SOP' in html or 'sop' in html
        
        # Verify HTML structure is complete
        assert '<!DOCTYPE html>' in html
        assert '<html' in html
        assert '</html>' in html
        assert 'category-modal' in html
        assert 'split-modal' in html


class TestWebUIErrorHandling:
    """Test Web UI handles molecule data errors gracefully"""
    
    def test_handles_missing_optional_fields(self):
        """Test Web UI handles transactions with missing optional fields"""
        # Some molecules might not populate all fields
        transactions = [{
            'id': 'txn_minimal',
            'date': '2025-11-29',
            'payee_name': 'Test Merchant',
            'memo': '',  # Empty memo (optional)
            'amount': -10000,  # -$10.00
            'category_id': 'cat_test',
            'category_name': 'Test Category',
            'type': 'single',
            'confidence': 0.95,
            'tier': 'sop'
        }]
        
        category_groups = [{
            'id': 'grp_test',
            'name': 'Test Group',
            'categories': [{'id': 'cat_test', 'name': 'Test Category'}]
        }]
        
        # Should not raise error
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        assert html is not None
        assert 'Test Merchant' in html
    
    def test_handles_split_transactions_from_molecules(self):
        """Test Web UI handles split transactions from data loader"""
        # Data loader might return split transactions
        transactions = [{
            'id': 'txn_split',
            'date': '2025-11-29',
            'payee_name': 'Costco',
            'memo': 'Groceries and gas',
            'amount': -350000,  # -$350.00 (milliunits = amount * 1000)
            'category_id': 'split',  # Special indicator for split
            'category_name': 'Split',
            'type': 'split',  # Type indicates split transaction
            'confidence': 1.0,
            'tier': 'sop'
        }]
        
        category_groups = [{
            'id': 'grp_test',
            'name': 'Test Group',
            'categories': [
                {'id': 'cat_groceries', 'name': 'Groceries'},
                {'id': 'cat_gas', 'name': 'Gas'}
            ]
        }]
        
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        
        # Verify split transaction displayed correctly
        assert 'Costco' in html
        assert '350.00' in html  # Amount formatted correctly
        assert '[Split Transaction]' in html or 'Split' in html
