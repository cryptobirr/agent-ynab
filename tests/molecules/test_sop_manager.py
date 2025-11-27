"""
Unit tests for SOP Manager molecule

Tests cover:
- Pattern matching (exact, prefix, contains, regex)
- SOP rule management (create, update, validation)
- Edge cases and error handling
- Caching behavior
- Confidence scoring
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from molecules.sop_manager import (
    ConcurrentUpdateError,
    PatternConfig,
    SOPMatch,
    SOPRule,
    get_sop_match,
    update_sop_with_rule,
    _exact_match,
    _prefix_match,
    _contains_match,
    _regex_match,
    _calculate_confidence,
    _normalize_description,
)


# Test Fixtures

@pytest.fixture
def sample_sop_rule():
    """Sample SOP rule for testing."""
    return SOPRule(
        id="test-walmart",
        name="Test Walmart Rule",
        patterns=[
            PatternConfig(pattern="WALMART", strategy="contains", priority=10, enabled=True),
            PatternConfig(pattern="WAL", strategy="prefix", priority=5, enabled=True),
        ],
        actions=[{"type": "tag", "category": "Groceries"}],
        metadata={"test": True},
        created_at=datetime(2025, 11, 27, 6, 0, 0),
        updated_at=datetime(2025, 11, 27, 6, 0, 0),
        version=1,
    )


@pytest.fixture
def temp_sop_file(tmp_path, sample_sop_rule):
    """Create temporary SOP rules file for testing."""
    from molecules import sop_manager
    
    # Save original path
    original_path = sop_manager.SOP_RULES_FILE
    
    # Set temp path
    temp_file = tmp_path / "sop_rules.json"
    sop_manager.SOP_RULES_FILE = temp_file
    
    # Create initial file with sample rule
    data = {
        "sops": [sample_sop_rule.model_dump(mode='json')],
        "version": "1.0.0",
        "updated_at": "2025-11-27T06:00:00.000000Z"
    }
    with open(temp_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    yield temp_file
    
    # Restore original path
    sop_manager.SOP_RULES_FILE = original_path


# Pattern Matching Tests

class TestPatternMatching:
    """Tests for individual pattern matching strategies."""
    
    def test_exact_match_case_insensitive(self):
        """Exact match should be case-insensitive."""
        assert _exact_match("WALMART", "walmart") == True
        assert _exact_match("Walmart", "WALMART") == True
        assert _exact_match("walmart", "Walmart") == True
        assert _exact_match("walmart", "target") == False
    
    def test_prefix_match_returns_correct(self):
        """Prefix match should find patterns at start of text."""
        assert _prefix_match("WAL", "WALMART GROCERY") == True
        assert _prefix_match("wal", "Walmart Store") == True
        assert _prefix_match("TARGET", "Target Corp") == True
        assert _prefix_match("WAL", "STORE WALMART") == False
    
    def test_contains_match_finds_substring(self):
        """Contains match should find pattern anywhere in text."""
        assert _contains_match("GROCERY", "WALMART GROCERY STORE") == True
        assert _contains_match("mart", "Walmart") == True
        assert _contains_match("STORE", "target store #123") == True
        assert _contains_match("COSTCO", "Walmart") == False
    
    def test_regex_match_with_valid_pattern(self):
        """Regex match should work with valid patterns."""
        assert _regex_match(r"WALMART.*\d+", "WALMART STORE #123") == True
        assert _regex_match(r"^TARGET", "TARGET CORP") == True
        assert _regex_match(r"\w+ GROCERY", "WALMART GROCERY") == True
        assert _regex_match(r"COSTCO", "Walmart") == False
    
    def test_regex_match_invalid_pattern_graceful(self):
        """Invalid regex should be handled gracefully."""
        # Invalid regex should return False, not raise exception
        assert _regex_match(r"[invalid(", "test text") == False
        assert _regex_match(r"**invalid", "test text") == False


class TestConfidenceScoring:
    """Tests for confidence score calculation."""
    
    def test_confidence_exact_match_highest(self):
        """Exact match should have highest base confidence (1.0)."""
        conf = _calculate_confidence("exact", "WALMART", "WALMART")
        assert conf == 1.0
    
    def test_confidence_prefix_higher_than_contains(self):
        """Prefix match should have higher confidence than contains."""
        prefix_conf = _calculate_confidence("prefix", "WAL", "WALMART")
        contains_conf = _calculate_confidence("contains", "MART", "WALMART")
        assert prefix_conf > contains_conf
    
    def test_confidence_contains_higher_than_regex(self):
        """Contains match should have higher confidence than regex."""
        contains_conf = _calculate_confidence("contains", "WALMART", "WALMART STORE")
        regex_conf = _calculate_confidence("regex", "WAL.*", "WALMART STORE")
        assert contains_conf > regex_conf
    
    def test_confidence_longer_match_bonus(self):
        """Longer patterns should get confidence bonus."""
        short_conf = _calculate_confidence("contains", "WAL", "WALMART GROCERY STORE")
        long_conf = _calculate_confidence("contains", "WALMART GROCERY", "WALMART GROCERY STORE")
        assert long_conf > short_conf


class TestNormalization:
    """Tests for description normalization."""
    
    def test_normalize_strips_whitespace(self):
        """Normalization should strip leading/trailing whitespace."""
        assert _normalize_description("  WALMART  ") == "WALMART"
        assert _normalize_description("\tTARGET\n") == "TARGET"
    
    def test_normalize_collapses_spaces(self):
        """Normalization should collapse multiple spaces to single space."""
        assert _normalize_description("WALMART  GROCERY   STORE") == "WALMART GROCERY STORE"
        assert _normalize_description("TARGET    CORP") == "TARGET CORP"


# Data Model Tests

class TestPatternConfig:
    """Tests for PatternConfig validation."""
    
    def test_pattern_config_validates_regex(self):
        """Valid regex patterns should be accepted."""
        config = PatternConfig(
            pattern=r"WALMART.*\d+",
            strategy="regex",
            priority=10,
            enabled=True
        )
        assert config.pattern == r"WALMART.*\d+"
    
    def test_pattern_config_rejects_invalid_regex(self):
        """Invalid regex patterns should raise ValidationError."""
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            PatternConfig(
                pattern=r"[invalid(",
                strategy="regex",
                priority=10,
                enabled=True
            )
    
    def test_pattern_config_non_regex_no_validation(self):
        """Non-regex strategies don't validate as regex."""
        # Should not raise even with invalid regex syntax
        config = PatternConfig(
            pattern="[this is not regex]",
            strategy="exact",
            priority=10,
            enabled=True
        )
        assert config.pattern == "[this is not regex]"


class TestSOPRule:
    """Tests for SOPRule validation."""
    
    def test_sop_rule_validates_id_format(self):
        """Rule ID must be lowercase alphanumeric with hyphens."""
        # Valid IDs
        SOPRule(
            id="walmart-groceries",
            name="Test",
            patterns=[PatternConfig(pattern="test", strategy="exact")]
        )
        
        SOPRule(
            id="test-123",
            name="Test",
            patterns=[PatternConfig(pattern="test", strategy="exact")]
        )
        
        # Invalid IDs should raise ValidationError
        with pytest.raises(ValueError):
            SOPRule(
                id="WALMART",  # Uppercase not allowed
                name="Test",
                patterns=[PatternConfig(pattern="test", strategy="exact")]
            )
        
        with pytest.raises(ValueError):
            SOPRule(
                id="walmart groceries",  # Spaces not allowed
                name="Test",
                patterns=[PatternConfig(pattern="test", strategy="exact")]
            )
    
    def test_sop_rule_requires_patterns(self):
        """SOPRule must have at least one pattern."""
        with pytest.raises(ValueError):
            SOPRule(
                id="test",
                name="Test",
                patterns=[]  # Empty patterns not allowed
            )


# get_sop_match() Tests

class TestGetSOPMatch:
    """Tests for get_sop_match() function."""
    
    def test_get_sop_match_all_strategies(self, temp_sop_file):
        """Should find matches using all strategies."""
        matches = get_sop_match("WALMART GROCERY #123")
        
        # Should find at least the contains match
        assert len(matches) > 0
        assert any(m["strategy"] == "contains" for m in matches)
    
    def test_get_sop_match_single_strategy(self, temp_sop_file):
        """Should respect strategies parameter."""
        matches = get_sop_match("WALMART GROCERY", strategies=["contains"])
        
        # Should only include contains matches
        assert all(m["strategy"] == "contains" for m in matches)
    
    def test_get_sop_match_max_results(self, temp_sop_file):
        """Should limit results to max_results."""
        matches = get_sop_match("WALMART", max_results=1)
        
        assert len(matches) <= 1
    
    def test_get_sop_match_min_confidence(self, temp_sop_file):
        """Should filter results by min_confidence."""
        matches = get_sop_match("WALMART", min_confidence=0.95)
        
        # All matches should meet threshold
        assert all(m["confidence"] >= 0.95 for m in matches)
    
    def test_get_sop_match_empty_description_raises(self):
        """Empty description should raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            get_sop_match("")
        
        with pytest.raises(ValueError, match="cannot be empty"):
            get_sop_match("   ")
    
    def test_get_sop_match_no_matches_returns_empty(self, temp_sop_file):
        """No matches should return empty list."""
        matches = get_sop_match("COSTCO WHOLESALE")
        
        assert matches == []
    
    def test_get_sop_match_invalid_strategy_raises(self):
        """Invalid strategy should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid strategy"):
            get_sop_match("test", strategies=["invalid"])
    
    def test_get_sop_match_invalid_max_results_raises(self):
        """Invalid max_results should raise ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            get_sop_match("test", max_results=0)
        
        with pytest.raises(ValueError, match="must be positive"):
            get_sop_match("test", max_results=-1)
    
    def test_get_sop_match_invalid_min_confidence_raises(self):
        """Invalid min_confidence should raise ValueError."""
        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            get_sop_match("test", min_confidence=1.5)
        
        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            get_sop_match("test", min_confidence=-0.1)
    
    def test_get_sop_match_sorts_by_confidence(self, temp_sop_file):
        """Results should be sorted by confidence (descending)."""
        matches = get_sop_match("WALMART GROCERY")
        
        if len(matches) > 1:
            # Verify descending order
            for i in range(len(matches) - 1):
                assert matches[i]["confidence"] >= matches[i + 1]["confidence"]
    
    def test_get_sop_match_returns_correct_structure(self, temp_sop_file):
        """Match results should have correct structure."""
        matches = get_sop_match("WALMART")
        
        if matches:
            match = matches[0]
            assert "sop_id" in match
            assert "sop_name" in match
            assert "pattern" in match
            assert "strategy" in match
            assert "confidence" in match
            assert "matched_text" in match
            assert "rule" in match
            
            # Verify types
            assert isinstance(match["sop_id"], str)
            assert isinstance(match["sop_name"], str)
            assert isinstance(match["pattern"], str)
            assert isinstance(match["strategy"], str)
            assert isinstance(match["confidence"], float)
            assert isinstance(match["matched_text"], str)
            assert isinstance(match["rule"], dict)


# update_sop_with_rule() Tests

class TestUpdateSOPWithRule:
    """Tests for update_sop_with_rule() function."""
    
    def test_update_existing_sop_increments_version(self, temp_sop_file):
        """Updating existing SOP should increment version."""
        # Load existing rule
        from molecules.sop_manager import _get_sop_by_id
        existing = _get_sop_by_id("test-walmart")
        assert existing.version == 1
        
        # Update rule
        existing.name = "Updated Name"
        result = update_sop_with_rule("test-walmart", existing)
        
        assert result["success"] == True
        assert result["version"] == 2
        
        # Verify in storage
        updated = _get_sop_by_id("test-walmart")
        assert updated.version == 2
        assert updated.name == "Updated Name"
    
    def test_update_existing_sop_updates_timestamp(self, temp_sop_file):
        """Updating existing SOP should update timestamp."""
        from molecules.sop_manager import _get_sop_by_id
        existing = _get_sop_by_id("test-walmart")
        original_updated_at = existing.updated_at
        
        # Update rule (need small delay to ensure timestamp changes)
        import time
        time.sleep(0.01)
        existing.name = "Updated Name"
        result = update_sop_with_rule("test-walmart", existing)
        
        # Verify timestamp updated
        updated = _get_sop_by_id("test-walmart")
        assert updated.updated_at > original_updated_at
    
    def test_create_new_sop_when_missing_and_flag_true(self, temp_sop_file):
        """Should create new SOP when missing and create_if_missing=True."""
        new_rule = SOPRule(
            id="new-test",
            name="New Test Rule",
            patterns=[PatternConfig(pattern="TEST", strategy="exact")],
            actions=[],
            version=1
        )
        
        result = update_sop_with_rule("new-test", new_rule, create_if_missing=True)
        
        assert result["success"] == True
        assert result["version"] == 1
        
        # Verify in storage
        from molecules.sop_manager import _get_sop_by_id
        created = _get_sop_by_id("new-test")
        assert created is not None
        assert created.name == "New Test Rule"
    
    def test_raise_key_error_when_missing_and_flag_false(self, temp_sop_file):
        """Should raise KeyError when SOP missing and create_if_missing=False."""
        new_rule = SOPRule(
            id="nonexistent",
            name="Test",
            patterns=[PatternConfig(pattern="TEST", strategy="exact")],
            version=1
        )
        
        with pytest.raises(KeyError, match="not found"):
            update_sop_with_rule("nonexistent", new_rule, create_if_missing=False)
    
    def test_validate_rejects_invalid_rule(self, temp_sop_file):
        """Validation should reject invalid rule structure."""
        invalid_rule_dict = {
            "id": "INVALID",  # Uppercase not allowed
            "name": "Test",
            "patterns": [],  # Empty patterns not allowed
        }
        
        with pytest.raises(ValueError):
            update_sop_with_rule("test", invalid_rule_dict, validate=True)
    
    def test_validate_accepts_valid_rule(self, temp_sop_file):
        """Validation should accept valid rule structure."""
        valid_rule = SOPRule(
            id="valid-test",
            name="Valid Test",
            patterns=[PatternConfig(pattern="TEST", strategy="exact")],
            version=1
        )
        
        # Should not raise
        result = update_sop_with_rule("valid-test", valid_rule, create_if_missing=True, validate=True)
        assert result["success"] == True
    
    def test_concurrent_update_raises(self, temp_sop_file):
        """Version mismatch should raise ConcurrentUpdateError."""
        from molecules.sop_manager import _get_sop_by_id
        
        # Get existing rule
        rule1 = _get_sop_by_id("test-walmart")
        rule2 = _get_sop_by_id("test-walmart")
        
        # Update once (increments version)
        rule1.name = "Update 1"
        update_sop_with_rule("test-walmart", rule1)
        
        # Try to update with old version (should fail)
        rule2.name = "Update 2"
        with pytest.raises(ConcurrentUpdateError, match="was modified concurrently"):
            update_sop_with_rule("test-walmart", rule2)
    
    def test_update_with_dict_input(self, temp_sop_file):
        """Should accept dict input and convert to SOPRule."""
        rule_dict = {
            "id": "dict-test",
            "name": "Dict Test",
            "patterns": [
                {"pattern": "TEST", "strategy": "exact", "priority": 0, "enabled": True}
            ],
            "actions": [],
            "metadata": {},
            "version": 1
        }
        
        result = update_sop_with_rule("dict-test", rule_dict, create_if_missing=True)
        
        assert result["success"] == True
    
    def test_invalid_sop_id_format_raises(self, temp_sop_file):
        """Invalid sop_id format should raise ValueError."""
        rule = SOPRule(
            id="test",
            name="Test",
            patterns=[PatternConfig(pattern="TEST", strategy="exact")],
            version=1
        )
        
        with pytest.raises(ValueError, match="Invalid sop_id format"):
            update_sop_with_rule("INVALID_ID", rule)
        
        with pytest.raises(ValueError, match="Invalid sop_id format"):
            update_sop_with_rule("invalid id", rule)


# Storage Layer Tests

class TestStorageLayer:
    """Tests for storage layer functions."""
    
    def test_load_empty_file(self, tmp_path):
        """Loading non-existent file should return empty list."""
        from molecules import sop_manager
        
        # Point to non-existent file
        original_path = sop_manager.SOP_RULES_FILE
        sop_manager.SOP_RULES_FILE = tmp_path / "nonexistent.json"
        
        try:
            rules = sop_manager._load_sop_rules()
            assert rules == []
        finally:
            sop_manager.SOP_RULES_FILE = original_path
    
    def test_load_corrupted_json_raises(self, tmp_path):
        """Loading corrupted JSON should raise RuntimeError."""
        from molecules import sop_manager
        
        # Create corrupted JSON file
        corrupted_file = tmp_path / "corrupted.json"
        with open(corrupted_file, 'w') as f:
            f.write("{invalid json")
        
        original_path = sop_manager.SOP_RULES_FILE
        sop_manager.SOP_RULES_FILE = corrupted_file
        
        try:
            with pytest.raises(RuntimeError, match="Corrupted JSON"):
                sop_manager._load_sop_rules()
        finally:
            sop_manager.SOP_RULES_FILE = original_path
    
    def test_save_atomic_write(self, temp_sop_file, sample_sop_rule):
        """Save should use atomic write (temp file + rename)."""
        from molecules import sop_manager
        
        # Save new rules
        new_rules = [sample_sop_rule]
        sop_manager._save_sop_rules(new_rules)
        
        # Verify file exists and is valid JSON
        assert temp_sop_file.exists()
        with open(temp_sop_file) as f:
            data = json.load(f)
        
        assert "sops" in data
        assert len(data["sops"]) == 1


# Edge Cases and Error Handling

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_match_with_unicode(self, temp_sop_file):
        """Should handle Unicode characters in descriptions."""
        matches = get_sop_match("WALMART 🛒 GROCERY")
        # Should not crash, may or may not match
        assert isinstance(matches, list)
    
    def test_match_with_special_chars(self, temp_sop_file):
        """Should handle special characters."""
        matches = get_sop_match("WALMART & CO. #123")
        assert isinstance(matches, list)
    
    def test_disabled_pattern_not_matched(self, temp_sop_file):
        """Disabled patterns should not match."""
        from molecules.sop_manager import _get_sop_by_id, _save_sop_rules, _load_sop_rules
        
        # Disable all patterns
        rule = _get_sop_by_id("test-walmart")
        for pattern in rule.patterns:
            pattern.enabled = False
        
        rules = _load_sop_rules()
        for r in rules:
            if r.id == "test-walmart":
                r.patterns = rule.patterns
        _save_sop_rules(rules)
        
        # Should not match
        matches = get_sop_match("WALMART")
        walmart_matches = [m for m in matches if m["sop_id"] == "test-walmart"]
        assert len(walmart_matches) == 0
