"""Templates layer - Full workflow orchestration"""
from .tagging_workflow import (
    generate_recommendations,
    submit_approved_changes
)

__all__ = [
    'generate_recommendations',
    'submit_approved_changes'
]
