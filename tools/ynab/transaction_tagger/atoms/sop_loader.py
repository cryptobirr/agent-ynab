"""
SOP Loader Atom - Parse Categorization Rules from Markdown

Provides pure function to load and parse categorization rules from
the SOP markdown file (categorization_rules.md) into structured
Python dictionaries for pattern matching.

Part of Layer 1 Atoms - Single-purpose, pure functions.
"""

from typing import Dict, List, Any, Tuple, Optional
from pathlib import Path
import logging
import re

# Configure logging
logger = logging.getLogger(__name__)


def detect_pattern_type(pattern: str) -> str:
    """
    Detect pattern type from pattern string.
    
    Args:
        pattern: Pattern string to analyze
    
    Returns:
        Pattern type: 'regex', 'contains', 'prefix', or 'exact'
    
    Precedence:
        1. regex: contains regex metacharacters ^$[](){}|.+?\\
        2. contains: starts and ends with *
        3. prefix: ends with * only
        4. exact: plain string (default)
    
    Examples:
        >>> detect_pattern_type("Starbucks")
        'exact'
        >>> detect_pattern_type("Starbucks*")
        'prefix'
        >>> detect_pattern_type("*coffee*")
        'contains'
        >>> detect_pattern_type("^Starbucks.*$")
        'regex'
    """
    # Check for regex metacharacters (precedence 1)
    regex_chars = '^$[](){}|.+?\\'
    if any(c in pattern for c in regex_chars):
        return 'regex'
    
    # Check for contains: starts and ends with * (precedence 2)
    if pattern.startswith('*') and pattern.endswith('*') and len(pattern) > 2:
        return 'contains'
    
    # Check for prefix: ends with * only (precedence 3)
    if pattern.endswith('*') and not pattern.startswith('*'):
        return 'prefix'
    
    # Default: exact match
    return 'exact'


def parse_kv_pair(line: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse key-value pair from markdown bullet line.
    
    Expected format: - **Key**: Value
    
    Args:
        line: Markdown line to parse
    
    Returns:
        Tuple of (key, value) or (None, None) if no match
        Skips template entries containing {placeholder}
    
    Examples:
        >>> parse_kv_pair("- **Pattern**: Starbucks")
        ('pattern', 'Starbucks')
        >>> parse_kv_pair("- **Category**: Coffee Shops")
        ('category', 'Coffee Shops')
        >>> parse_kv_pair("- **Pattern**: {regex}")
        (None, None)
    """
    match = re.match(r'- \*\*([^*]+)\*\*:\s*(.+)', line.strip())
    if not match:
        return None, None
    
    key = match.group(1).strip().lower().replace(' ', '_')
    value = match.group(2).strip()
    
    # Skip template entries
    if '{' in value and '}' in value:
        return None, None
    
    return key, value


def parse_split_allocations(lines: List[str], start_idx: int) -> List[Dict[str, Any]]:
    """
    Parse nested allocation list for split transactions.
    
    Expected format:
      * Category: XX%
    
    Args:
        lines: All lines from the file
        start_idx: Index of "Default Allocation:" line
    
    Returns:
        List of allocation dicts: [{'category': 'Groceries', 'percentage': 60}]
    
    Example:
        Input lines:
          * Groceries: 60%
          * Household: 30%
          * Entertainment: 10%
        
        Output:
        [
            {'category': 'Groceries', 'percentage': 60},
            {'category': 'Household', 'percentage': 30},
            {'category': 'Entertainment', 'percentage': 10}
        ]
    """
    allocations = []
    i = start_idx + 1  # Start after "Default Allocation:" line
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Stop at next bullet or non-indented line
        if not line or (line.startswith('-') and line.startswith('- **')):
            break
        
        # Parse: "* Category: XX%"
        match = re.match(r'\*\s*([^:]+):\s*(\d+)%?', line)
        if match:
            allocations.append({
                'category': match.group(1).strip(),
                'percentage': int(match.group(2))
            })
        else:
            # Not a valid allocation line, might be end of section
            if not line.startswith('*'):
                break
        
        i += 1
    
    return allocations


def load_categorization_rules(sop_path: str = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Load and parse categorization rules from markdown SOP file.
    
    Reads categorization_rules.md and parses rule sections into
    structured dictionaries for pattern matching.
    
    Args:
        sop_path: Path to SOP file (default: categorization_rules.md in parent dir)
    
    Returns:
        Dictionary with categorization rules organized by type:
        {
            'core_patterns': [
                {
                    'pattern': str,         # Regex or keyword pattern
                    'category': str,        # YNAB category name
                    'confidence': str,      # High|Medium|Low
                    'source': str,          # Historical|User|Web
                    'date_added': str,      # YYYY-MM-DD
                    'pattern_type': str     # exact|prefix|contains|regex
                }
            ],
            'split_patterns': [
                {
                    'pattern': str,         # Payee name pattern
                    'type': str,            # Split Transaction
                    'allocations': [
                        {'category': str, 'percentage': int}
                    ],
                    'confidence': str,
                    'source': str,
                    'date_added': str,
                    'note': str
                }
            ],
            'user_corrections': [
                {
                    'payee': str,           # Exact payee name
                    'correct_category': str, # Correct category
                    'agent_initially_suggested': str,
                    'reasoning': str,
                    'confidence': str,
                    'date_learned': str
                }
            ],
            'web_research': [
                {
                    'unknown_payee': str,
                    'business_type': str,
                    'category': str,
                    'reasoning': str,
                    'confidence': str,
                    'date_added': str
                }
            ]
        }
        
        Empty lists for sections with no rules.
        Empty dict {} if file not found or parse error.
    
    Example:
        >>> rules = load_categorization_rules()
        >>> print(rules['core_patterns'][0])
        {
            'pattern': 'Starbucks',
            'category': 'Coffee Shops',
            'confidence': 'High',
            'source': 'Historical',
            'date_added': '2025-11-27',
            'pattern_type': 'exact'
        }
    """
    # 1. Resolve SOP file path
    if sop_path is None:
        # Default: categorization_rules.md in parent directory
        sop_path = Path(__file__).parent.parent / "categorization_rules.md"
    else:
        sop_path = Path(sop_path)
    
    if not sop_path.exists():
        logger.error(f"SOP file not found: {sop_path}")
        return {}
    
    # 2. Read file
    try:
        with open(sop_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Failed to read SOP file: {e}")
        return {}
    
    # 3. Initialize sections
    sections = {
        'core_patterns': [],
        'split_patterns': [],
        'user_corrections': [],
        'web_research': []
    }
    
    # 4. Split into lines
    lines = content.split('\n')
    
    # 5. Parse sections
    current_section = None
    current_entry = {}
    
    for i, line in enumerate(lines):
        # Detect section headers
        if line.startswith('## Core Patterns'):
            current_section = 'core_patterns'
            if current_entry:
                logger.warning(f"Incomplete entry before Core Patterns section: {current_entry}")
                current_entry = {}
            continue
        elif line.startswith('## Split Transaction Patterns'):
            current_section = 'split_patterns'
            if current_entry:
                logger.warning(f"Incomplete entry before Split Patterns section: {current_entry}")
                current_entry = {}
            continue
        elif line.startswith('## Learned from User Corrections'):
            current_section = 'user_corrections'
            if current_entry:
                logger.warning(f"Incomplete entry before User Corrections section: {current_entry}")
                current_entry = {}
            continue
        elif line.startswith('## Web Research Results'):
            current_section = 'web_research'
            if current_entry:
                logger.warning(f"Incomplete entry before Web Research section: {current_entry}")
                current_entry = {}
            continue
        
        # Skip if no section detected yet
        if current_section is None:
            continue
        
        # Parse bullet list entries
        if line.strip().startswith('- **'):
            key, value = parse_kv_pair(line)
            
            if key is None:
                continue  # Skip malformed or template entries
            
            # Handle special case: default_allocation for split patterns
            if key == 'default_allocation':
                current_entry['allocations'] = parse_split_allocations(lines, i)
            else:
                current_entry[key] = value
        
        # Detect entry completion (next bullet or section header or empty line after entries)
        elif line.strip() == '' and current_entry:
            # Entry complete
            if current_section == 'core_patterns' and 'pattern' in current_entry:
                # Add pattern_type for core_patterns
                current_entry['pattern_type'] = detect_pattern_type(current_entry['pattern'])
            
            # Add to section
            sections[current_section].append(current_entry)
            current_entry = {}
    
    # Add last entry if exists
    if current_entry and current_section:
        if current_section == 'core_patterns' and 'pattern' in current_entry:
            current_entry['pattern_type'] = detect_pattern_type(current_entry['pattern'])
        sections[current_section].append(current_entry)
    
    logger.info(f"Loaded {len(sections['core_patterns'])} core patterns, "
               f"{len(sections['split_patterns'])} split patterns, "
               f"{len(sections['user_corrections'])} user corrections, "
               f"{len(sections['web_research'])} web research entries")
    
    return sections
