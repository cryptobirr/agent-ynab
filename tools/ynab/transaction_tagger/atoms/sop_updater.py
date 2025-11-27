"""
SOP Updater Atom - Thread-safe appending of categorization rules to SOP file.

This module provides a pure function to append categorization rules to the
markdown SOP file (categorization_rules.md) with proper formatting, timestamps,
and thread-safe file locking.

Part of Layer 1: Atoms (pure functions)
"""

import logging
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
import platform
import time

# Platform-specific file locking
if platform.system() == 'Windows':
    import msvcrt
else:
    import fcntl

# Configure logger for SOP updater
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _inject_timestamp_if_missing(rule_content: str) -> str:
    """
    Inject ISO 8601 timestamp if not present in rule content.
    
    Args:
        rule_content: Markdown rule entry
    
    Returns:
        Rule content with timestamp field
    """
    # Check if timestamp already exists
    if '**Date Learned**:' in rule_content or '**Date Added**:' in rule_content:
        logger.debug("Timestamp already present in rule content")
        return rule_content
    
    # Generate ISO 8601 timestamp
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    
    # Determine field name based on section
    if 'Learned from User Corrections' in rule_content:
        field_name = "Date Learned"
    else:
        field_name = "Date Added"
    
    # Insert timestamp before final newline
    lines = rule_content.rstrip('\n').split('\n')
    lines.append(f"  **{field_name}**: {timestamp}")
    
    result = '\n'.join(lines) + '\n'
    logger.debug(f"Injected timestamp field: {field_name}")
    return result


def _acquire_lock(file_handle, timeout: int = 5) -> bool:
    """
    Acquire exclusive lock on file with timeout.
    
    Args:
        file_handle: Open file handle
        timeout: Timeout in seconds (default: 5)
    
    Returns:
        True if lock acquired, False if timeout
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            if platform.system() == 'Windows':
                # Windows: msvcrt locking
                msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                # POSIX: fcntl locking (non-blocking)
                fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            logger.debug("Lock acquired successfully")
            return True
        
        except (IOError, OSError):
            # Lock not available, retry after short delay
            time.sleep(0.1)
    
    logger.error(f"Lock timeout after {timeout}s")
    return False


def _release_lock(file_handle):
    """
    Release exclusive lock on file.
    
    Args:
        file_handle: Open file handle
    """
    try:
        if platform.system() == 'Windows':
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
        
        logger.debug("Lock released successfully")
    except Exception as e:
        logger.warning(f"Failed to release lock: {e}")


def append_rule_to_sop(
    rule_content: str,
    sop_path: Optional[str] = None
) -> bool:
    """
    Append a categorization rule to the SOP file with thread-safe locking.
    
    Appends formatted rule content to categorization_rules.md with
    proper markdown formatting and ISO 8601 timestamp. Uses file
    locking to prevent concurrent write corruption.
    
    Args:
        rule_content: Formatted markdown rule entry (must include section header)
            Example for user correction:
            "## Learned from User Corrections\n- **Payee**: Amazon\n  **Category**: Shopping..."
            
        sop_path: Path to SOP file (default: categorization_rules.md in same dir)
    
    Returns:
        bool: True if rule appended successfully, False if failed
    
    Example:
        >>> rule = '''
        ... ## Learned from User Corrections
        ... - **Payee**: Starbucks Pike Place
        ...   **Category**: Coffee Shops
        ...   **Category ID**: cat_12345
        ...   **Wrong Suggestion**: Restaurants
        ...   **Reasoning**: User correction - coffee shop, not restaurant
        ...   **Confidence**: High
        ...   **Date Learned**: 2025-11-27T20:42:00Z
        ... '''
        >>> success = append_rule_to_sop(rule)
        >>> print(success)
        True
    """
    # Resolve SOP file path
    if sop_path is None:
        # Default: categorization_rules.md in same directory as this module
        module_dir = Path(__file__).parent.parent
        sop_file = module_dir / 'categorization_rules.md'
    else:
        sop_file = Path(sop_path)
    
    logger.info(f"Appending rule to SOP file: {sop_file}")
    
    # Verify file exists
    if not sop_file.exists():
        logger.error(f"SOP file not found: {sop_file}")
        return False
    
    # Inject timestamp if missing
    rule_with_timestamp = _inject_timestamp_if_missing(rule_content)
    
    try:
        # Open file in read-append mode
        with open(sop_file, 'r+') as f:
            # Acquire exclusive lock with timeout
            if not _acquire_lock(f, timeout=5):
                logger.error("Failed to acquire lock within timeout")
                return False
            
            try:
                # Read last character to check if we need blank line
                f.seek(0, 2)  # Seek to end
                current_pos = f.tell()
                
                if current_pos > 0:
                    f.seek(current_pos - 1)
                    last_char = f.read(1)
                    
                    # Add blank line if file doesn't end with double newline
                    if last_char != '\n':
                        f.write('\n\n')
                    else:
                        # Check if second-to-last is also newline
                        if current_pos > 1:
                            f.seek(current_pos - 2)
                            second_last = f.read(1)
                            if second_last != '\n':
                                f.seek(0, 2)  # Back to end
                                f.write('\n')
                        
                    f.seek(0, 2)  # Back to end
                
                # Write rule content
                f.write(rule_with_timestamp)
                
                # Ensure single newline at end
                if not rule_with_timestamp.endswith('\n'):
                    f.write('\n')
                
                logger.info("Successfully appended rule to SOP")
                return True
            
            finally:
                # Always release lock
                _release_lock(f)
    
    except IOError as e:
        logger.error(f"Failed to write to SOP file: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error appending rule: {e}")
        return False
