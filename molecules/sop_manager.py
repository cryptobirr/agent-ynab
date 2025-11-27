"""
SOP Manager Molecule

Provides intelligent pattern matching and management of Standard Operating Procedures (SOPs)
for YNAB transaction tagging. Implements multiple matching strategies (exact, prefix, contains,
regex) with confidence scoring and rule management capabilities.

This molecule serves as the intelligence layer for SOP-driven automation, bridging the gap
between raw transaction data (atoms) and high-level workflow orchestration (organisms).

Functions:
    get_sop_match: Find matching SOPs for a transaction description
    update_sop_with_rule: Update or create an SOP rule

Author: AI-assisted (code-plan agent)
Created: 2025-11-27T06:20:00Z
Version: 1.0.0
"""

import json
import logging
import os
import re
import tempfile
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field, model_validator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Type definitions
MatchStrategy = Literal["exact", "prefix", "contains", "regex"]


class PatternConfig(BaseModel):
    """Configuration for a pattern matching rule."""
    
    pattern: str = Field(..., min_length=1, description="Pattern string to match")
    strategy: MatchStrategy = Field(..., description="Matching strategy to use")
    priority: int = Field(default=0, ge=0, le=100, description="Match priority (0-100)")
    enabled: bool = Field(default=True, description="Whether pattern is active")
    
    @model_validator(mode='after')
    def validate_regex_pattern(self):
        """Validate regex patterns can be compiled."""
        if self.strategy == 'regex':
            try:
                re.compile(self.pattern)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e}")
        return self


class SOPRule(BaseModel):
    """Complete SOP rule definition."""
    
    id: str = Field(..., pattern=r'^[a-z0-9-]+$', description="Unique rule ID (lowercase, hyphens)")
    name: str = Field(..., min_length=1, description="Human-readable rule name")
    patterns: list[PatternConfig] = Field(..., min_length=1, description="List of pattern configs")
    actions: list[dict] = Field(default_factory=list, description="Actions to execute on match")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    version: int = Field(default=1, ge=1, description="Rule version number")


class SOPMatch(TypedDict):
    """Result of SOP pattern matching."""
    
    sop_id: str
    sop_name: str
    pattern: str
    strategy: MatchStrategy
    confidence: float
    matched_text: str
    rule: dict


class ConcurrentUpdateError(Exception):
    """Raised when optimistic locking detects concurrent update."""
    pass


# Constants
PROJECT_ROOT = Path(__file__).parent.parent
SOP_RULES_FILE = PROJECT_ROOT / "sop_rules.json"
STRATEGY_CONFIDENCE = {
    "exact": 1.0,
    "prefix": 0.9,
    "contains": 0.8,
    "regex": 0.7,
}


# Storage Layer Functions

def _load_sop_rules() -> list[SOPRule]:
    """
    Load SOP rules from JSON file.
    
    Returns:
        List of SOPRule objects. Returns empty list if file doesn't exist.
    
    Raises:
        RuntimeError: If JSON is corrupted or validation fails
    """
    if not SOP_RULES_FILE.exists():
        logger.info(f"SOP rules file not found: {SOP_RULES_FILE}. Returning empty list.")
        return []
    
    try:
        with open(SOP_RULES_FILE, 'r') as f:
            data = json.load(f)
        
        # Validate and parse rules
        rules = []
        for rule_data in data.get('sops', []):
            try:
                rules.append(SOPRule(**rule_data))
            except Exception as e:
                logger.error(f"Failed to parse SOP rule {rule_data.get('id', 'unknown')}: {e}")
                # Continue with other rules instead of failing completely
        
        return rules
    
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Corrupted JSON in SOP rules file: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to load SOP rules: {e}")


def _save_sop_rules(rules: list[SOPRule]) -> None:
    """
    Save SOP rules to JSON file atomically.
    
    Uses temp file + atomic rename to ensure no partial writes.
    
    Args:
        rules: List of SOPRule objects to save
    
    Raises:
        RuntimeError: If save operation fails
    """
    try:
        # Convert rules to dict format
        data = {
            "sops": [rule.model_dump(mode='json') for rule in rules],
            "version": "1.0.0",
            "updated_at": datetime.utcnow().isoformat() + "Z"
        }
        
        # Write to temp file in same directory (required for atomic rename)
        temp_fd, temp_path = tempfile.mkstemp(
            dir=SOP_RULES_FILE.parent,
            prefix='.sop_rules_',
            suffix='.json.tmp'
        )
        
        try:
            with os.fdopen(temp_fd, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Atomic rename (POSIX guarantee)
            os.rename(temp_path, SOP_RULES_FILE)
            logger.info(f"Saved {len(rules)} SOP rules to {SOP_RULES_FILE}")
        
        except Exception:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
    
    except Exception as e:
        raise RuntimeError(f"Failed to save SOP rules: {e}")


def _get_sop_by_id(sop_id: str) -> SOPRule | None:
    """
    Get SOP rule by ID.
    
    Args:
        sop_id: Unique SOP identifier
    
    Returns:
        SOPRule if found, None otherwise
    """
    rules = _load_sop_rules()
    for rule in rules:
        if rule.id == sop_id:
            return rule
    return None


# Pattern Matching Functions

def _normalize_description(text: str) -> str:
    """
    Normalize transaction description for matching.
    
    TODO: Replace with atoms.transaction_analyzer.normalize_description when Story 2.6 ready
    
    Args:
        text: Raw transaction description
    
    Returns:
        Normalized text (trimmed, single spaces)
    """
    # Basic normalization: strip whitespace, collapse multiple spaces
    normalized = ' '.join(text.strip().split())
    return normalized


@lru_cache(maxsize=1000)
def _compile_regex(pattern: str) -> re.Pattern | None:
    """
    Compile and cache regex pattern.
    
    Args:
        pattern: Regex pattern string
    
    Returns:
        Compiled regex Pattern object, or None if invalid
    """
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        logger.warning(f"Invalid regex pattern '{pattern}': {e}")
        return None


def _exact_match(pattern: str, text: str) -> bool:
    """Case-insensitive exact match."""
    return pattern.lower() == text.lower()


def _prefix_match(pattern: str, text: str) -> bool:
    """Case-insensitive prefix match."""
    return text.lower().startswith(pattern.lower())


def _contains_match(pattern: str, text: str) -> bool:
    """Case-insensitive substring match."""
    return pattern.lower() in text.lower()


def _regex_match(pattern: str, text: str) -> bool:
    """Case-insensitive regex match with error handling."""
    compiled = _compile_regex(pattern)
    if compiled is None:
        return False
    
    try:
        return bool(compiled.search(text))
    except Exception as e:
        logger.warning(f"Regex match failed for pattern '{pattern}': {e}")
        return False


def _apply_strategy(strategy: MatchStrategy, pattern: str, text: str) -> bool:
    """
    Apply matching strategy to pattern and text.
    
    Args:
        strategy: Matching strategy to use
        pattern: Pattern to match
        text: Text to match against
    
    Returns:
        True if match found, False otherwise
    """
    matchers = {
        "exact": _exact_match,
        "prefix": _prefix_match,
        "contains": _contains_match,
        "regex": _regex_match,
    }
    
    matcher = matchers.get(strategy)
    if matcher is None:
        logger.error(f"Unknown matching strategy: {strategy}")
        return False
    
    return matcher(pattern, text)


def _calculate_confidence(
    strategy: MatchStrategy,
    pattern: str,
    text: str
) -> float:
    """
    Calculate match confidence score.
    
    Base confidence from strategy, with bonus for longer pattern length.
    
    Args:
        strategy: Matching strategy used
        pattern: Matched pattern
        text: Matched text
    
    Returns:
        Confidence score (0.0-1.0)
    """
    base_confidence = STRATEGY_CONFIDENCE.get(strategy, 0.5)
    
    # Bonus for longer pattern length (relative to text)
    # Longer patterns are more specific, thus higher confidence
    if len(text) > 0:
        length_ratio = len(pattern) / len(text)
        # Add up to 10% bonus for patterns that are >50% of text length
        length_bonus = min(0.1, length_ratio * 0.2)
    else:
        length_bonus = 0.0
    
    return min(1.0, base_confidence + length_bonus)


# Main API Functions

def get_sop_match(
    description: str,
    strategies: list[MatchStrategy] | None = None,
    max_results: int = 5,
    min_confidence: float = 0.5
) -> list[SOPMatch]:
    """
    Find matching SOPs for a transaction description.
    
    Applies multiple pattern matching strategies and returns matches sorted by confidence.
    
    Args:
        description: Transaction description to match against
        strategies: List of matching strategies to use (default: all strategies)
        max_results: Maximum number of matches to return (default: 5)
        min_confidence: Minimum confidence threshold 0.0-1.0 (default: 0.5)
    
    Returns:
        List of SOPMatch objects, sorted by confidence (descending)
    
    Raises:
        ValueError: If description is empty or parameters are invalid
        RuntimeError: If SOP storage is unavailable
    
    Example:
        >>> matches = get_sop_match("WALMART GROCERY #123", max_results=3)
        >>> matches[0]["sop_name"]
        "Walmart Groceries Auto-tag"
        >>> matches[0]["confidence"]
        0.95
    """
    # Input validation
    if not description or not description.strip():
        raise ValueError("Description cannot be empty")
    
    if max_results <= 0:
        raise ValueError("max_results must be positive")
    
    if not (0.0 <= min_confidence <= 1.0):
        raise ValueError("min_confidence must be between 0.0 and 1.0")
    
    # Default to all strategies
    if strategies is None:
        strategies = ["exact", "prefix", "contains", "regex"]
    
    # Validate strategies
    valid_strategies = {"exact", "prefix", "contains", "regex"}
    for strategy in strategies:
        if strategy not in valid_strategies:
            raise ValueError(f"Invalid strategy: {strategy}")
    
    # Normalize description
    normalized_desc = _normalize_description(description)
    
    # Load SOP rules
    try:
        rules = _load_sop_rules()
    except Exception as e:
        raise RuntimeError(f"Failed to load SOP rules: {e}")
    
    # Collect matches
    matches: list[SOPMatch] = []
    
    for rule in rules:
        for pattern_config in rule.patterns:
            # Skip disabled patterns
            if not pattern_config.enabled:
                continue
            
            # Skip if strategy not requested
            if pattern_config.strategy not in strategies:
                continue
            
            # Apply matching strategy
            is_match = _apply_strategy(
                pattern_config.strategy,
                pattern_config.pattern,
                normalized_desc
            )
            
            if is_match:
                # Calculate confidence
                confidence = _calculate_confidence(
                    pattern_config.strategy,
                    pattern_config.pattern,
                    normalized_desc
                )
                
                # Apply pattern priority boost (up to 10% bonus)
                priority_boost = pattern_config.priority / 1000.0
                confidence = min(1.0, confidence + priority_boost)
                
                # Create match object
                match: SOPMatch = {
                    "sop_id": rule.id,
                    "sop_name": rule.name,
                    "pattern": pattern_config.pattern,
                    "strategy": pattern_config.strategy,
                    "confidence": confidence,
                    "matched_text": normalized_desc,
                    "rule": rule.model_dump(mode='json'),
                }
                
                matches.append(match)
    
    # Sort by confidence (descending), then by pattern length (descending)
    matches.sort(
        key=lambda m: (m["confidence"], len(m["pattern"])),
        reverse=True
    )
    
    # Filter by min_confidence
    matches = [m for m in matches if m["confidence"] >= min_confidence]
    
    # Limit to max_results
    matches = matches[:max_results]
    
    logger.info(
        f"Found {len(matches)} SOP matches for '{description[:50]}...' "
        f"(strategies: {strategies})"
    )
    
    return matches


def update_sop_with_rule(
    sop_id: str,
    rule: SOPRule | dict,
    validate: bool = True,
    create_if_missing: bool = False
) -> dict[str, Any]:
    """
    Update or create an SOP rule.
    
    Implements optimistic locking via version field to prevent concurrent update conflicts.
    
    Args:
        sop_id: Unique SOP identifier
        rule: Complete SOP rule definition (SOPRule or dict)
        validate: Whether to validate rule before persisting (default: True)
        create_if_missing: Create new SOP if ID doesn't exist (default: False)
    
    Returns:
        Dictionary containing:
        - success: bool
        - sop_id: str
        - version: int (new version number)
        - updated_at: datetime
    
    Raises:
        ValueError: If rule is invalid or sop_id is malformed
        RuntimeError: If update fails due to storage error
        KeyError: If sop_id doesn't exist and create_if_missing=False
        ConcurrentUpdateError: If version mismatch detected
    
    Example:
        >>> rule = SOPRule(
        ...     id="walmart-groceries",
        ...     name="Walmart Groceries Auto-tag",
        ...     patterns=[PatternConfig(pattern="WALMART", strategy="contains")],
        ...     actions=[{"type": "tag", "value": "Groceries"}]
        ... )
        >>> result = update_sop_with_rule("walmart-groceries", rule, create_if_missing=True)
        >>> result["success"]
        True
    """
    # Validate sop_id format
    if not re.match(r'^[a-z0-9-]+$', sop_id):
        raise ValueError(f"Invalid sop_id format: {sop_id}. Must be lowercase alphanumeric with hyphens.")
    
    # Convert dict to SOPRule if needed
    if isinstance(rule, dict):
        try:
            rule = SOPRule(**rule)
        except Exception as e:
            raise ValueError(f"Invalid rule structure: {e}")
    
    # Validate rule if requested
    if validate:
        try:
            # Pydantic validation happens on construction, but re-validate to be safe
            rule.model_validate(rule)
        except Exception as e:
            raise ValueError(f"Rule validation failed: {e}")
    
    # Load existing rules
    try:
        rules = _load_sop_rules()
    except Exception as e:
        raise RuntimeError(f"Failed to load SOP rules: {e}")
    
    # Find existing rule
    existing_rule = None
    existing_index = None
    for i, r in enumerate(rules):
        if r.id == sop_id:
            existing_rule = r
            existing_index = i
            break
    
    # Handle create vs update logic
    if existing_rule is None:
        # SOP doesn't exist
        if not create_if_missing:
            raise KeyError(f"SOP '{sop_id}' not found and create_if_missing=False")
        
        # Create new SOP
        rule.id = sop_id
        rule.version = 1
        rule.created_at = datetime.utcnow()
        rule.updated_at = datetime.utcnow()
        rules.append(rule)
        logger.info(f"Created new SOP rule: {sop_id}")
    
    else:
        # SOP exists - update it
        
        # Optimistic locking: check version match
        if rule.version != existing_rule.version:
            raise ConcurrentUpdateError(
                f"SOP '{sop_id}' was modified concurrently. "
                f"Expected version {rule.version}, found version {existing_rule.version}. "
                f"Reload and retry."
            )
        
        # Increment version and update timestamp
        rule.version = existing_rule.version + 1
        rule.updated_at = datetime.utcnow()
        rule.created_at = existing_rule.created_at  # Preserve creation time
        
        # Replace existing rule
        rules[existing_index] = rule
        logger.info(f"Updated SOP rule: {sop_id} (version {existing_rule.version} → {rule.version})")
    
    # Save atomically
    try:
        _save_sop_rules(rules)
    except Exception as e:
        raise RuntimeError(f"Failed to save SOP rules: {e}")
    
    # Return success result
    return {
        "success": True,
        "sop_id": sop_id,
        "version": rule.version,
        "updated_at": rule.updated_at.isoformat() + "Z",
    }
