"""Tests for Web UI Organism"""
import pytest
from tools.ynab.transaction_tagger.organisms.web_ui import generate_approval_html


class TestGenerateApprovalHTML:
    """Tests for generate_approval_html() function"""
    
    def test_basic_html_generation(self):
        """Test basic HTML generation with minimal valid input"""
        transactions = [{
            'id': 'txn_123',
            'date': '2025-11-29',
            'payee_name': 'Test Payee',
            'memo': 'Test memo',
            'amount': -10000,  # -$10.00
            'category_id': 'cat_123',
            'category_name': 'Test Category',
            'type': 'single',
            'confidence': 0.95,
            'tier': 'sop'
        }]
        
        category_groups = [{
            'id': 'grp_123',
            'name': 'Test Group',
            'categories': [
                {'id': 'cat_123', 'name': 'Test Category'}
            ]
        }]
        
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        
        # Basic structure checks
        assert '<!DOCTYPE html>' in html
        assert '<html' in html
        assert '</html>' in html
        assert '<body>' in html
        assert '</body>' in html
        
        # Check transaction data appears
        assert 'Test Payee' in html
        assert 'Test memo' in html
        assert '$10.00' in html  # Amount formatted correctly
        assert 'Test Category' in html
        
        # Check modals present
        assert 'category-modal' in html
        assert 'split-modal' in html
        
        # Check styles and scripts embedded
        assert '<style>' in html
        assert '<script>' in html
    
    def test_multiple_transactions(self):
        """Test HTML generation with multiple transactions"""
        transactions = [
            {
                'id': f'txn_{i}',
                'date': '2025-11-29',
                'payee_name': f'Payee {i}',
                'memo': f'Memo {i}',
                'amount': -1000 * i,
                'category_id': 'cat_123',
                'category_name': 'Category',
                'type': 'single',
                'confidence': 0.9,
                'tier': 'sop'
            }
            for i in range(1, 11)
        ]
        
        category_groups = [{
            'id': 'grp_123',
            'name': 'Group',
            'categories': [{'id': 'cat_123', 'name': 'Category'}]
        }]
        
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        
        # All transactions should appear
        for i in range(1, 11):
            assert f'Payee {i}' in html
            assert f'txn_{i}' in html
    
    def test_split_transaction_display(self):
        """Test split transaction shows [Split Transaction] indicator"""
        transactions = [{
            'id': 'txn_split',
            'date': '2025-11-29',
            'payee_name': 'Split Payee',
            'memo': '',
            'amount': -20000,
            'category_id': 'split',
            'category_name': 'Split',
            'type': 'split',
            'confidence': 1.0,
            'tier': 'sop'
        }]
        
        category_groups = [{
            'id': 'grp_123',
            'name': 'Group',
            'categories': [{'id': 'cat_123', 'name': 'Category'}]
        }]
        
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        
        assert '[Split Transaction]' in html
        assert 'split-indicator' in html
        assert 'openSplitModal' in html
    
    def test_confidence_color_coding(self):
        """Test confidence levels get correct CSS classes"""
        transactions = [
            {
                'id': 'txn_high',
                'date': '2025-11-29',
                'payee_name': 'High Confidence',
                'memo': '',
                'amount': -1000,
                'category_id': 'cat_123',
                'category_name': 'Category',
                'type': 'single',
                'confidence': 0.95,  # High
                'tier': 'sop'
            },
            {
                'id': 'txn_medium',
                'date': '2025-11-29',
                'payee_name': 'Medium Confidence',
                'memo': '',
                'amount': -1000,
                'category_id': 'cat_123',
                'category_name': 'Category',
                'type': 'single',
                'confidence': 0.80,  # Medium
                'tier': 'historical'
            },
            {
                'id': 'txn_low',
                'date': '2025-11-29',
                'payee_name': 'Low Confidence',
                'memo': '',
                'amount': -1000,
                'category_id': 'cat_123',
                'category_name': 'Category',
                'type': 'single',
                'confidence': 0.60,  # Low
                'tier': 'research'
            }
        ]
        
        category_groups = [{
            'id': 'grp_123',
            'name': 'Group',
            'categories': [{'id': 'cat_123', 'name': 'Category'}]
        }]
        
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        
        # Check CSS classes present
        assert 'confidence-high' in html
        assert 'confidence-medium' in html
        assert 'confidence-low' in html
        
        # Check percentages
        assert '95%' in html
        assert '80%' in html
        assert '60%' in html
    
    def test_tier_badges(self):
        """Test tier badges rendered correctly"""
        transactions = [
            {
                'id': 'txn_sop',
                'date': '2025-11-29',
                'payee_name': 'SOP Match',
                'memo': '',
                'amount': -1000,
                'category_id': 'cat_123',
                'category_name': 'Category',
                'type': 'single',
                'confidence': 1.0,
                'tier': 'sop'
            },
            {
                'id': 'txn_hist',
                'date': '2025-11-29',
                'payee_name': 'Historical Match',
                'memo': '',
                'amount': -1000,
                'category_id': 'cat_123',
                'category_name': 'Category',
                'type': 'single',
                'confidence': 0.9,
                'tier': 'historical'
            },
            {
                'id': 'txn_research',
                'date': '2025-11-29',
                'payee_name': 'Research Match',
                'memo': '',
                'amount': -1000,
                'category_id': 'cat_123',
                'category_name': 'Category',
                'type': 'single',
                'confidence': 0.8,
                'tier': 'research'
            }
        ]
        
        category_groups = [{
            'id': 'grp_123',
            'name': 'Group',
            'categories': [{'id': 'cat_123', 'name': 'Category'}]
        }]
        
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        
        assert 'tier-sop' in html
        assert 'tier-historical' in html
        assert 'tier-research' in html
        assert '>SOP<' in html
        assert '>HISTORICAL<' in html
        assert '>RESEARCH<' in html
    
    def test_category_groups_structure(self):
        """Test category groups rendered with all categories"""
        transactions = [{
            'id': 'txn_123',
            'date': '2025-11-29',
            'payee_name': 'Payee',
            'memo': '',
            'amount': -1000,
            'category_id': 'cat_groceries',
            'category_name': 'Groceries',
            'type': 'single',
            'confidence': 1.0,
            'tier': 'sop'
        }]
        
        category_groups = [
            {
                'id': 'grp_everyday',
                'name': 'Everyday Expenses',
                'categories': [
                    {'id': 'cat_groceries', 'name': 'Groceries'},
                    {'id': 'cat_gas', 'name': 'Gas & Fuel'}
                ]
            },
            {
                'id': 'grp_monthly',
                'name': 'Monthly Bills',
                'categories': [
                    {'id': 'cat_rent', 'name': 'Rent'},
                    {'id': 'cat_internet', 'name': 'Internet'}
                ]
            }
        ]
        
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        
        # Check all groups appear
        assert 'Everyday Expenses' in html
        assert 'Monthly Bills' in html
        
        # Check all categories appear
        assert 'Groceries' in html
        assert 'Gas & Fuel' in html
        assert 'Rent' in html
        assert 'Internet' in html
        
        # Check category selection handlers
        assert 'selectCategory' in html
        assert 'cat_groceries' in html
        assert 'cat_rent' in html
    
    def test_amount_formatting(self):
        """Test amount formatting with positive and negative values"""
        transactions = [
            {
                'id': 'txn_outflow',
                'date': '2025-11-29',
                'payee_name': 'Outflow',
                'memo': '',
                'amount': -123456,  # -$123.46
                'category_id': 'cat_123',
                'category_name': 'Category',
                'type': 'single',
                'confidence': 1.0,
                'tier': 'sop'
            },
            {
                'id': 'txn_inflow',
                'date': '2025-11-29',
                'payee_name': 'Inflow',
                'memo': '',
                'amount': 789012,  # $789.01
                'category_id': 'cat_123',
                'category_name': 'Category',
                'type': 'single',
                'confidence': 1.0,
                'tier': 'sop'
            }
        ]
        
        category_groups = [{
            'id': 'grp_123',
            'name': 'Group',
            'categories': [{'id': 'cat_123', 'name': 'Category'}]
        }]
        
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        
        # Check formatted amounts
        assert '$123.46' in html
        assert '$789.01' in html
        
        # Check CSS classes
        assert 'outflow' in html
        assert 'inflow' in html
    
    def test_empty_transactions_raises_error(self):
        """Test that empty transactions list raises ValueError"""
        category_groups = [{
            'id': 'grp_123',
            'name': 'Group',
            'categories': [{'id': 'cat_123', 'name': 'Category'}]
        }]
        
        with pytest.raises(ValueError, match="transactions list cannot be empty"):
            generate_approval_html([], category_groups, 'budget_123')
    
    def test_empty_category_groups_raises_error(self):
        """Test that empty category_groups raises ValueError"""
        transactions = [{
            'id': 'txn_123',
            'date': '2025-11-29',
            'payee_name': 'Payee',
            'memo': '',
            'amount': -1000,
            'category_id': 'cat_123',
            'category_name': 'Category',
            'type': 'single',
            'confidence': 1.0,
            'tier': 'sop'
        }]
        
        with pytest.raises(ValueError, match="category_groups list cannot be empty"):
            generate_approval_html(transactions, [], 'budget_123')
    
    def test_empty_budget_id_raises_error(self):
        """Test that empty budget_id raises ValueError"""
        transactions = [{
            'id': 'txn_123',
            'date': '2025-11-29',
            'payee_name': 'Payee',
            'memo': '',
            'amount': -1000,
            'category_id': 'cat_123',
            'category_name': 'Category',
            'type': 'single',
            'confidence': 1.0,
            'tier': 'sop'
        }]
        
        category_groups = [{
            'id': 'grp_123',
            'name': 'Group',
            'categories': [{'id': 'cat_123', 'name': 'Category'}]
        }]
        
        with pytest.raises(ValueError, match="budget_id must be a non-empty string"):
            generate_approval_html(transactions, category_groups, '')
    
    def test_missing_transaction_fields_raises_error(self):
        """Test that missing required transaction fields raises ValueError"""
        transactions = [{
            'id': 'txn_123',
            'date': '2025-11-29',
            # Missing payee_name, amount, etc.
        }]
        
        category_groups = [{
            'id': 'grp_123',
            'name': 'Group',
            'categories': [{'id': 'cat_123', 'name': 'Category'}]
        }]
        
        with pytest.raises(ValueError, match="missing required field"):
            generate_approval_html(transactions, category_groups, 'budget_123')
    
    def test_missing_category_group_fields_raises_error(self):
        """Test that missing category group fields raises ValueError"""
        transactions = [{
            'id': 'txn_123',
            'date': '2025-11-29',
            'payee_name': 'Payee',
            'memo': '',
            'amount': -1000,
            'category_id': 'cat_123',
            'category_name': 'Category',
            'type': 'single',
            'confidence': 1.0,
            'tier': 'sop'
        }]
        
        category_groups = [{
            'id': 'grp_123',
            # Missing 'name' and 'categories'
        }]
        
        with pytest.raises(ValueError, match="missing required fields"):
            generate_approval_html(transactions, category_groups, 'budget_123')
    
    def test_javascript_state_initialization(self):
        """Test that JavaScript state object is initialized with data"""
        transactions = [{
            'id': 'txn_123',
            'date': '2025-11-29',
            'payee_name': 'Payee',
            'memo': '',
            'amount': -1000,
            'category_id': 'cat_123',
            'category_name': 'Category',
            'type': 'single',
            'confidence': 1.0,
            'tier': 'sop'
        }]
        
        category_groups = [{
            'id': 'grp_123',
            'name': 'Group',
            'categories': [{'id': 'cat_123', 'name': 'Category'}]
        }]
        
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        
        # Check state initialization
        assert 'const state = {' in html
        assert 'transactions:' in html
        assert 'categoryGroups:' in html
        assert '"budgetId": \'budget_123\'' in html or "budgetId: 'budget_123'" in html
        assert 'txn_123' in html  # Transaction ID in JSON
    
    def test_keyboard_shortcuts_present(self):
        """Test that keyboard shortcut handlers are in JavaScript"""
        transactions = [{
            'id': 'txn_123',
            'date': '2025-11-29',
            'payee_name': 'Payee',
            'memo': '',
            'amount': -1000,
            'category_id': 'cat_123',
            'category_name': 'Category',
            'type': 'single',
            'confidence': 1.0,
            'tier': 'sop'
        }]
        
        category_groups = [{
            'id': 'grp_123',
            'name': 'Group',
            'categories': [{'id': 'cat_123', 'name': 'Category'}]
        }]
        
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        
        # Check keyboard event listeners
        assert 'keydown' in html
        assert 'Escape' in html
        assert 'ctrlKey || e.metaKey' in html  # Ctrl/Cmd detection
    
    def test_split_modal_structure(self):
        """Test split modal has required elements"""
        transactions = [{
            'id': 'txn_123',
            'date': '2025-11-29',
            'payee_name': 'Payee',
            'memo': '',
            'amount': -1000,
            'category_id': 'cat_123',
            'category_name': 'Category',
            'type': 'single',
            'confidence': 1.0,
            'tier': 'sop'
        }]
        
        category_groups = [{
            'id': 'grp_123',
            'name': 'Group',
            'categories': [{'id': 'cat_123', 'name': 'Category'}]
        }]
        
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        
        # Check split modal elements
        assert 'split-modal' in html
        assert 'split-transaction-info' in html
        assert 'split-rows-container' in html
        assert 'addSplitRow' in html
        assert 'removeSplitRow' in html
        assert 'approveSplit' in html
        assert 'split-remaining' in html
        assert 'split-error' in html
    
    def test_large_transaction_list(self):
        """Test performance with 500+ transactions"""
        transactions = [
            {
                'id': f'txn_{i}',
                'date': '2025-11-29',
                'payee_name': f'Payee {i}',
                'memo': f'Memo {i}',
                'amount': -1000 * (i % 100 + 1),
                'category_id': 'cat_123',
                'category_name': 'Category',
                'type': 'single',
                'confidence': 0.85 + (i % 15) / 100,
                'tier': ['sop', 'historical', 'research'][i % 3]
            }
            for i in range(500)
        ]
        
        category_groups = [{
            'id': 'grp_123',
            'name': 'Group',
            'categories': [{'id': 'cat_123', 'name': 'Category'}]
        }]
        
        import time
        start = time.time()
        html = generate_approval_html(transactions, category_groups, 'budget_123')
        duration = time.time() - start
        
        # Should complete in under 2 seconds (NFR-1 requirement)
        assert duration < 2.0
        assert len(html) > 0
        assert 'Payee 499' in html  # Last transaction present

