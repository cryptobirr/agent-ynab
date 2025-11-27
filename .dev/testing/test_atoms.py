"""
Tests for YNAB Transaction Tagger Atoms (Layer 1).

Tests pure functions that form the atomic building blocks of the system.
"""

import pytest
import tempfile
import os
from pathlib import Path
import threading
import time

from tools.ynab.transaction_tagger.atoms.sop_updater import (
    append_rule_to_sop,
    _inject_timestamp_if_missing
)


class TestSOPUpdater:
    """Tests for SOP Updater atom."""
    
    def test_append_rule_success(self):
        """Test successful rule append."""
        # Create temp SOP file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md') as f:
            temp_sop = f.name
            f.write("# Categorization Rules\n\n")
        
        try:
            # Append rule
            rule = """## Learned from User Corrections
- **Payee**: Test Payee
  **Category**: Test Category
  **Category ID**: cat_123
  **Wrong Suggestion**: Wrong Cat
  **Reasoning**: Test reasoning
  **Confidence**: High
  **Date Learned**: 2025-11-27T20:00:00Z
"""
            
            result = append_rule_to_sop(rule, sop_path=temp_sop)
            
            # Verify
            assert result is True
            
            with open(temp_sop, 'r') as f:
                content = f.read()
                assert "Test Payee" in content
                assert "Test Category" in content
        
        finally:
            os.unlink(temp_sop)
    
    
    def test_timestamp_injection_missing(self):
        """Test timestamp injection when missing."""
        rule = """## Core Patterns
- **Pattern**: Starbucks
  **Category**: Coffee Shops
  **Confidence**: High
  **Source**: Historical
"""
        
        result = _inject_timestamp_if_missing(rule)
        
        assert "**Date Added**:" in result
        assert "T" in result  # ISO 8601 format
        assert "Z" in result
    
    
    def test_timestamp_preservation_existing(self):
        """Test timestamp preserved when already present."""
        rule = """## Learned from User Corrections
- **Payee**: Amazon
  **Category**: Shopping
  **Date Learned**: 2025-01-01T00:00:00Z
"""
        
        result = _inject_timestamp_if_missing(rule)
        
        assert result == rule  # Unchanged
        assert "2025-01-01T00:00:00Z" in result
    
    
    def test_file_not_found(self):
        """Test graceful failure when SOP file doesn't exist."""
        result = append_rule_to_sop(
            "## Test\n- **Test**: value\n",
            sop_path="/nonexistent/path/file.md"
        )
        
        assert result is False
    
    
    def test_blank_line_insertion(self):
        """Test blank line inserted between rules."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md') as f:
            temp_sop = f.name
            f.write("# Categorization Rules\n\n## Section 1\n- Rule 1")
        
        try:
            rule = "## Section 2\n- Rule 2\n"
            result = append_rule_to_sop(rule, sop_path=temp_sop)
            
            assert result is True
            
            with open(temp_sop, 'r') as f:
                content = f.read()
                # Should have blank line between sections
                assert "\n\n## Section 2" in content
        
        finally:
            os.unlink(temp_sop)
    
    
    def test_concurrent_writes_thread_safe(self):
        """Test thread-safe concurrent writes."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md') as f:
            temp_sop = f.name
            f.write("# Categorization Rules\n\n")
        
        try:
            results = []
            
            # Function to append rules concurrently
            def append_concurrent(rule_num):
                rule = f"""## Test Section
- **Rule**: Rule {rule_num}
  **Date Added**: 2025-11-27T20:00:00Z
"""
                result = append_rule_to_sop(rule, sop_path=temp_sop)
                results.append(result)
            
            # Launch 10 concurrent writes
            threads = []
            
            for i in range(10):
                t = threading.Thread(target=append_concurrent, args=(i,))
                threads.append(t)
                t.start()
            
            # Wait for all threads
            for t in threads:
                t.join()
            
            # Verify all succeeded (or failed gracefully)
            assert len(results) == 10
            assert all(isinstance(r, bool) for r in results)
            
            # Verify file integrity (should have all 10 rules)
            with open(temp_sop, 'r') as f:
                content = f.read()
                for i in range(10):
                    assert f"Rule {i}" in content
        
        finally:
            os.unlink(temp_sop)
