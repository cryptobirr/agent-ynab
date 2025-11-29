"""
Recommendation Engine Organism - Layer 3 Facade for Transaction Categorization

Simple orchestrator that provides a clean interface for getting category
recommendations using the Categorization Agent Organism.

Part of Layer 3: Organisms (Complex business logic composition)
"""

from typing import Dict, Any
from datetime import datetime, timezone
import logging

# Internal imports
from organisms.categorization_agent import CategorizationAgent

# Configure logging
logger = logging.getLogger(__name__)


class RecommendationEngine:
    """
    Facade for transaction categorization using CategorizationAgent.
    
    Provides simple interface for getting category recommendations with
    automatic 3-tier fallback logic (SOP → Historical → AI Research).
    """
    
    def __init__(self, budget_id: str):
        """
        Initialize recommendation engine with YNAB budget context.
        
        Args:
            budget_id: YNAB budget UUID
        
        Raises:
            ValueError: If budget_id invalid
        """
        if not budget_id or not isinstance(budget_id, str):
            raise ValueError("budget_id must be non-empty string")
        
        self.budget_id = budget_id
        
        # Initialize categorization agent (does heavy lifting)
        self.categorization_agent = CategorizationAgent(budget_id)
        
        logger.info(f"RecommendationEngine initialized for budget {budget_id}")
    
    def get_recommendation(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get category recommendation for transaction.
        
        Delegates to CategorizationAgent with error handling and logging.
        
        Args:
            transaction: Transaction dict with keys:
                - id: str (YNAB transaction ID)
                - payee_name: str
                - amount: int (milliunits)
                - date: str (ISO 8601)
                - memo: str (optional)
        
        Returns:
            Recommendation result dict:
            {
                'transaction_id': str,
                'type': 'single' | 'split',
                'category_id': str | None,
                'category_name': str,
                'confidence': float (0.0-1.0),
                'tier': 'sop' | 'historical' | 'research',
                'method': str,
                'reasoning': str,
                'timestamp': str (ISO 8601)
            }
        
        Raises:
            ValueError: If transaction invalid
        """
        txn_id = transaction.get('id', 'unknown')
        payee = transaction.get('payee_name', 'unknown')
        
        logger.info(f"Getting recommendation for transaction {txn_id} (payee: {payee})")
        
        try:
            # Delegate to categorization agent
            result = self.categorization_agent.categorize_transaction(transaction)
            
            # Log result
            logger.info(
                f"Recommendation complete: {txn_id} → "
                f"{result['category_name']} "
                f"(tier: {result['tier']}, confidence: {result['confidence']:.2%})"
            )
            
            return result
        
        except ValueError as e:
            # Validation errors should bubble up
            logger.error(f"Invalid transaction: {e}")
            raise
        
        except Exception as e:
            # All other errors → manual review result
            logger.error(f"Recommendation failed for {txn_id}: {e}", exc_info=True)
            
            return {
                'transaction_id': txn_id,
                'type': 'single',
                'category_id': None,
                'category_name': 'Uncategorized',
                'confidence': 0.0,
                'tier': 'research',
                'method': 'failed',
                'reasoning': f"Recommendation failed: {str(e)}",
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'requires_manual_review': True
            }
