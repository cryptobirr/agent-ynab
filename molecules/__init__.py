"""
Layer 2: Molecules

Molecules combine 2-3 atomic operations to create higher-level business logic.
Each molecule represents a cohesive unit of functionality.
"""

__version__ = "1.0.0"

from .sop_manager import get_sop_match, update_sop_with_rule

__all__ = ["get_sop_match", "update_sop_with_rule"]
