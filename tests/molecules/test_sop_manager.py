"""
Tests for SOP Manager molecule - Pattern matching and rule management.

Note: This is a minimal test suite for basic functionality verification.
Implementation verified through manual testing and integration with atoms.
"""

import pytest
from pathlib import Path
from molecules.sop_manager import get_sop_match, update_sop_with_rule


class TestBasicFunctionality:
    """Basic smoke tests for SOP Manager functions."""
    
    def test_get_sop_match_finds_pattern(self):
        """Test get_sop_match() finds matching pattern."""
        rules = {
            'core_patterns': [
                {'pattern': 'Starbucks*', 'category': 'Coffee', 'pattern_type': 'prefix'}
            ],
            'split_patterns': [],
            'user_corrections': [],
            'web_research': []
        }
        match = get_sop_match("Starbucks Pike Place", rules)
        assert match is not None
        assert match['category'] == 'Coffee'
    
    def test_get_sop_match_returns_none_when_no_match(self):
        """Test get_sop_match() returns None when no pattern matches."""
        rules = {
            'core_patterns': [
                {'pattern': 'Starbucks*', 'category': 'Coffee', 'pattern_type': 'prefix'}
            ],
            'split_patterns': [],
            'user_corrections': [],
            'web_research': []
        }
        match = get_sop_match("Walmart", rules)
        assert match is None
    
    def test_update_sop_with_rule_validates_rule_type(self):
        """Test update_sop_with_rule() validates rule_type."""
        result = update_sop_with_rule('invalid_type', {'pattern': 'Test'})
        assert result is False
    
    def test_update_sop_with_rule_validates_required_fields(self):
        """Test update_sop_with_rule() validates required fields."""
        # Missing 'category' for core_pattern
        result = update_sop_with_rule('core_pattern', {'pattern': 'Test*'})
        assert result is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
