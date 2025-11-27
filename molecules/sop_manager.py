"""
SOP Manager Molecule - High-level SOP Rule Management

Combines sop_loader and sop_updater atoms to provide high-level
functions for pattern matching and rule management. This molecule
orchestrates the atoms to implement the complete SOP management workflow.

Part of Layer 2: Molecules (2-3 atom combinations)

Public API:
    - get_sop_match(payee_name, rules_dict=None) -> Optional[Dict]
    - update_sop_with_rule(rule_type, rule_data) -> bool

Pattern Matching Support:
    - exact: "Starbucks" matches "Starbucks" (case-insensitive)
    - prefix: "Starbucks*" matches "Starbucks Pike Place"
    - contains: "*coffee*" matches "Local Coffee Shop"
    - regex: "^Star.*s$" matches "Starbucks"

Rule Types:
    - core_pattern: Core categorization patterns
    - split_pattern: Split transaction patterns with allocations
    - user_correction: Learned from user corrections
    - web_research: Web research categorization results
"""

import re
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

# Import atoms at module level for testability
from tools.ynab.transaction_tagger.atoms.sop_loader import load_categorization_rules
from tools.ynab.transaction_tagger.atoms.sop_updater import append_rule_to_sop

# Configure logger
logger = logging.getLogger(__name__)


def _match_pattern(payee: str, pattern: str, pattern_type: str) -> bool:
    """
    Check if payee matches pattern using specified pattern type.
    
    Implements pattern matching logic for all 4 pattern types:
    exact, prefix, contains, and regex. All matching is case-insensitive.
    
    Args:
        payee: Payee name to test
        pattern: Pattern string (may contain * wildcards or regex)
        pattern_type: 'exact' | 'prefix' | 'contains' | 'regex'
    
    Returns:
        bool: True if match, False otherwise
    
    Examples:
        >>> _match_pattern("Starbucks", "starbucks", "exact")
        True
        >>> _match_pattern("Starbucks Pike Place", "Starbucks*", "prefix")
        True
        >>> _match_pattern("Local Coffee Shop", "*coffee*", "contains")
        True
        >>> _match_pattern("Starbucks", "^Star.*s$", "regex")
        True
    """
    # Input validation
    if not payee or not pattern:
        logger.debug(f"Empty input: payee='{payee}', pattern='{pattern}'")
        return False
    
    # Case-insensitive comparison
    payee_lower = payee.lower()
    pattern_lower = pattern.lower()
    
    # Pattern type logic
    if pattern_type == 'exact':
        result = payee_lower == pattern_lower
        logger.debug(f"Exact match: '{payee}' == '{pattern}' → {result}")
        return result
    
    elif pattern_type == 'prefix':
        # Strip trailing * from pattern
        clean_pattern = pattern_lower.rstrip('*')
        result = payee_lower.startswith(clean_pattern)
        logger.debug(f"Prefix match: '{payee}' starts with '{clean_pattern}' → {result}")
        return result
    
    elif pattern_type == 'contains':
        # Strip * from both ends
        clean_pattern = pattern_lower.strip('*')
        result = clean_pattern in payee_lower
        logger.debug(f"Contains match: '{clean_pattern}' in '{payee}' → {result}")
        return result
    
    elif pattern_type == 'regex':
        # Compile and match with case-insensitive flag
        try:
            regex = re.compile(pattern, re.IGNORECASE)
            result = bool(regex.match(payee))
            logger.debug(f"Regex match: '{pattern}' matches '{payee}' → {result}")
            return result
        except re.error as e:
            logger.warning(f"Invalid regex pattern '{pattern}': {e}")
            return False
    
    else:
        logger.warning(f"Unknown pattern_type '{pattern_type}'")
        return False


def get_sop_match(
    payee_name: str,
    rules_dict: Optional[Dict[str, List[Dict[str, Any]]]] = None
) -> Optional[Dict[str, Any]]:
    """
    Find matching SOP rule for given payee name.
    
    Searches through core_patterns, split_patterns, user_corrections,
    and web_research sections for pattern matches. Returns first match
    found (priority order: core > split > user > web).
    
    Args:
        payee_name: Transaction payee name to match against patterns
        rules_dict: Optional pre-loaded rules dict (if None, loads from file)
    
    Returns:
        Matching rule dict with all fields from SOP section, or None if no match
        
    Pattern Matching Logic:
        - exact: payee_name == pattern (case-insensitive)
        - prefix: payee_name.startswith(pattern without *)
        - contains: pattern (without *) in payee_name
        - regex: re.match(pattern, payee_name, re.IGNORECASE)
    
    Example:
        >>> rules = load_categorization_rules()
        >>> match = get_sop_match("Starbucks Pike Place", rules)
        >>> print(match)
        {
            'pattern': 'Starbucks*',
            'category': 'Coffee Shops',
            'confidence': 'High',
            'source': 'Historical',
            'date_added': '2025-11-27T20:00:00Z',
            'pattern_type': 'prefix'
        }
    """
    # Validate input
    if not payee_name:
        logger.warning("Empty payee_name provided to get_sop_match")
        return None
    
    # Load rules if not provided
    if rules_dict is None:
        rules_dict = load_categorization_rules()
        
        if not rules_dict:
            logger.error("Failed to load categorization rules")
            return None
    
    # Search sections in priority order
    sections = ['core_patterns', 'split_patterns', 'user_corrections', 'web_research']
    
    for section_name in sections:
        section = rules_dict.get(section_name, [])
        
        for rule in section:
            # Get pattern and pattern_type based on section
            if section_name == 'user_corrections':
                pattern = rule.get('payee', '')
                pattern_type = 'exact'  # User corrections are exact matches
            elif section_name == 'web_research':
                pattern = rule.get('unknown_payee', '')
                pattern_type = 'exact'  # Web research is exact matches
            else:
                pattern = rule.get('pattern', '')
                pattern_type = rule.get('pattern_type', 'exact')
            
            # Check if pattern matches
            if _match_pattern(payee_name, pattern, pattern_type):
                logger.info(f"Found SOP match for '{payee_name}' in {section_name}: {pattern}")
                return rule
    
    logger.debug(f"No SOP match found for '{payee_name}'")
    return None


def _format_rule_to_markdown(
    section_header: str,
    rule_data: Dict[str, Any]
) -> str:
    """
    Format rule data into markdown bullet list format.
    
    Converts rule dict into properly formatted markdown with section
    header and bullet list. Uses bullet format (not indented) to match
    sop_loader expectations.
    
    CRITICAL: sop_loader only parses lines starting with "- **Field**:",
    NOT indented lines. All fields must use bullet format.
    
    Args:
        section_header: Markdown section header (e.g., "## Core Patterns")
        rule_data: Dict with rule fields
    
    Returns:
        Formatted markdown string ready for appending to SOP file
    
    Format (ALL BULLETS):
        ## {section_header}
        - **Field1**: {value1}
        - **Field2**: {value2}
        ...
    
    Special handling:
        - Split allocations: nested bullet list with * markers
        - Optional fields: skip if None/empty
        - Timestamps: NOT added here (sop_updater injects automatically)
    
    Example:
        >>> formatted = _format_rule_to_markdown(
        ...     "## Core Patterns",
        ...     {'pattern': 'Trader Joe*', 'category': 'Groceries', 'confidence': 'High'}
        ... )
        >>> print(formatted)
        ## Core Patterns
        - **Pattern**: Trader Joe*
        - **Category**: Groceries
        - **Confidence**: High
    """
    # Start with section header
    lines = [f"{section_header}"]
    
    # Determine field order based on section type
    if 'split' in section_header.lower():
        # Split pattern fields - handle allocations specially
        field_order = ['pattern', 'allocations', 'confidence', 'source', 'note']
    elif 'core' in section_header.lower() or 'patterns' in section_header.lower():
        # Core pattern fields
        field_order = ['pattern', 'category', 'category_id', 'confidence', 'source']
    elif 'correction' in section_header.lower():
        # User correction fields
        field_order = ['payee', 'correct_category', 'category_id', 'agent_initially_suggested', 'reasoning', 'confidence']
    elif 'research' in section_header.lower():
        # Web research fields
        field_order = ['unknown_payee', 'business_type', 'category', 'category_id', 'reasoning', 'confidence']
    else:
        # Generic fallback: all fields
        field_order = list(rule_data.keys())
    
    # Format ALL fields as bullets (not indented - sop_loader requirement)
    for field in field_order:
        if field not in rule_data or rule_data[field] is None:
            continue  # Skip missing/None fields
        
        value = rule_data[field]
        
        # Skip empty strings
        if isinstance(value, str) and not value.strip():
            continue
        
        # Special handling for allocations
        if field == 'allocations':
            lines.append(f"- **Default Allocation**:")
            for alloc in value:
                lines.append(f"  * {alloc['category']}: {alloc['percentage']}%")
        else:
            # Capitalize field name for display
            display_name = field.replace('_', ' ').title()
            lines.append(f"- **{display_name}**: {value}")
    
    # Join with newlines and add final newline
    return '\n'.join(lines) + '\n'


def update_sop_with_rule(
    rule_type: str,
    rule_data: Dict[str, Any]
) -> bool:
    """
    Update SOP file with new categorization rule.
    
    Formats rule_data into markdown bullet list format and appends
    to appropriate section in categorization_rules.md using thread-safe
    append_rule_to_sop() atom.
    
    Args:
        rule_type: Section to append to:
            - 'core_pattern' → Core Patterns
            - 'split_pattern' → Split Transaction Patterns
            - 'user_correction' → Learned from User Corrections
            - 'web_research' → Web Research Results
        
        rule_data: Dict with rule fields (varies by type)
            
            core_pattern:
                - pattern: str (required)
                - category: str (required)
                - category_id: str (optional)
                - confidence: str (default: "Medium")
                - source: str (default: "Agent")
                - date_added: str (auto-injected by sop_updater if missing)
            
            split_pattern:
                - pattern: str (required)
                - allocations: List[Dict] (required)
                    - Each: {'category': str, 'percentage': int}
                - confidence: str (default: "Medium")
                - source: str (default: "Agent")
                - note: str (optional)
                - date_added: str (auto-injected)
            
            user_correction:
                - payee: str (required)
                - correct_category: str (required)
                - category_id: str (optional)
                - agent_initially_suggested: str (optional)
                - reasoning: str (optional)
                - confidence: str (default: "High")
                - date_learned: str (auto-injected)
            
            web_research:
                - unknown_payee: str (required)
                - business_type: str (required)
                - category: str (required)
                - category_id: str (optional)
                - reasoning: str (optional)
                - confidence: str (default: "Medium")
                - date_added: str (auto-injected)
    
    Returns:
        bool: True if rule appended successfully, False if failed
    
    Example:
        >>> success = update_sop_with_rule(
        ...     rule_type='core_pattern',
        ...     rule_data={
        ...         'pattern': 'Trader Joe*',
        ...         'category': 'Groceries',
        ...         'category_id': 'cat_groceries_123',
        ...         'confidence': 'High',
        ...         'source': 'Historical'
        ...     }
        ... )
        >>> print(success)
        True
    """
    # Validate rule_type
    valid_types = ['core_pattern', 'split_pattern', 'user_correction', 'web_research']
    if rule_type not in valid_types:
        logger.error(f"Invalid rule_type '{rule_type}'. Must be one of: {valid_types}")
        return False
    
    # Map rule_type to section header
    section_headers = {
        'core_pattern': '## Core Patterns',
        'split_pattern': '## Split Transaction Patterns',
        'user_correction': '## Learned from User Corrections',
        'web_research': '## Web Research Results'
    }
    section_header = section_headers[rule_type]
    
    # Validate required fields for each type
    required_fields = {
        'core_pattern': ['pattern', 'category'],
        'split_pattern': ['pattern', 'allocations'],
        'user_correction': ['payee', 'correct_category'],
        'web_research': ['unknown_payee', 'business_type', 'category']
    }
    
    missing_fields = [f for f in required_fields[rule_type] if f not in rule_data]
    if missing_fields:
        logger.error(f"Missing required fields for {rule_type}: {missing_fields}")
        return False
    
    # Add default values for optional fields (create copy to avoid modifying input)
    rule_data_copy = rule_data.copy()
    
    if 'confidence' not in rule_data_copy:
        rule_data_copy['confidence'] = 'High' if rule_type == 'user_correction' else 'Medium'
    
    if 'source' not in rule_data_copy and rule_type in ['core_pattern', 'split_pattern']:
        rule_data_copy['source'] = 'Agent'
    
    # Format to markdown
    formatted_content = _format_rule_to_markdown(section_header, rule_data_copy)
    
    # Append to SOP file
    try:
        success = append_rule_to_sop(formatted_content)
        
        if success:
            logger.info(f"Successfully added {rule_type} rule to SOP")
        else:
            logger.error(f"Failed to add {rule_type} rule to SOP")
        
        return success
    
    except Exception as e:
        logger.error(f"Unexpected error updating SOP: {e}")
        return False
