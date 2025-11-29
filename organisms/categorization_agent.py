"""
Categorization Agent Organism - Layer 3 Intelligent Transaction Categorization

Composes molecules and atoms to provide 3-tier categorization:
- Tier 1: SOP Rules (highest confidence, fastest)
- Tier 2: Historical Patterns (high confidence, database-backed)
- Tier 3: Research + AI Reasoning (medium confidence, Claude + WebSearch)

Part of Layer 3: Organisms (Complex business logic composition)
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import logging
import os
import json
import re
import time

# Anthropic SDK
import anthropic

# Internal imports
from common.vault_client import VaultClient
from tools.ynab.transaction_tagger.atoms.sop_loader import load_categorization_rules
from tools.ynab.transaction_tagger.atoms.sop_updater import append_rule_to_sop
from tools.ynab.transaction_tagger.atoms.api_fetch import fetch_categories
from tools.ynab.transaction_tagger.molecules.pattern_analyzer import analyze_transaction

# Configure logging
logger = logging.getLogger(__name__)


class CategorizationAgent:
    """
    Layer 3 Organism - Intelligent transaction categorization using 3-tier logic.
    
    Composes molecules and atoms to provide Claude-powered categorization with
    fallback tiers for resilience.
    """
    
    def __init__(self, budget_id: str):
        """
        Initialize agent with YNAB budget context.
        
        Args:
            budget_id: YNAB budget UUID
        
        Raises:
            ValueError: If budget_id invalid or Anthropic API key missing
        """
        if not budget_id or not isinstance(budget_id, str):
            raise ValueError("budget_id must be non-empty string")
        
        self.budget_id = budget_id
        
        # Initialize Anthropic client
        self.anthropic_client = self._init_anthropic()
        
        # Lazy-loaded caches
        self.sop_rules = None  # Loaded on first use
        self.ynab_categories = None  # Loaded on first use
        self.categories_cached_at = None  # Timestamp for cache TTL
        
        logger.info(f"CategorizationAgent initialized for budget {budget_id}")
    
    def _init_anthropic(self) -> anthropic.Anthropic:
        """
        Initialize Anthropic client with API key from Vault or environment.
        
        Returns:
            Anthropic client instance
        
        Raises:
            ValueError: If API key not found
        """
        vault = VaultClient()
        api_key = None
        
        # Try Vault first
        if vault.is_connected():
            try:
                secret = vault.kv_get('secret/claude/api_key')
                if secret:
                    api_key = secret.get('api_key')
                    logger.info("Loaded Claude API key from Vault")
            except Exception as e:
                logger.warning(f"Failed to load from Vault: {e}")
        
        # Fallback to environment variable
        if not api_key:
            api_key = os.getenv('ANTHROPIC_API_KEY')
            if api_key:
                logger.info("Loaded Claude API key from environment")
        
        if not api_key:
            raise ValueError(
                "Anthropic API key not found. Set in Vault (secret/claude/api_key) "
                "or environment variable (ANTHROPIC_API_KEY)"
            )
        
        return anthropic.Anthropic(api_key=api_key)
    
    def categorize_transaction(
        self, 
        transaction: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Categorize single transaction using 3-tier decision logic.
        
        Args:
            transaction: Transaction dict with keys:
                - id: str (YNAB transaction ID)
                - payee_name: str
                - amount: int (milliunits)
                - date: str (ISO 8601)
                - memo: str (optional)
        
        Returns:
            Categorization result dict:
            {
                'transaction_id': str,
                'type': 'single' | 'split',
                'category_id': str,
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
        # Validate input
        if not self._validate_transaction(transaction):
            raise ValueError("Invalid transaction format")
        
        txn_id = transaction['id']
        logger.info(f"Categorizing transaction {txn_id}")
        
        # Tier 1: SOP Rules
        result = self._tier1_sop_match(transaction)
        if result:
            logger.info(f"Tier 1 match: {result['category_name']} (confidence: {result['confidence']:.2%})")
            return result
        
        # Tier 2: Historical Patterns
        result = self._tier2_historical_match(transaction)
        if result:
            logger.info(f"Tier 2 match: {result['category_name']} (confidence: {result['confidence']:.2%})")
            return result
        
        # Tier 3: Research + Reasoning
        result = self._tier3_research_and_reasoning(transaction)
        logger.info(f"Tier 3 result: {result['category_name']} (confidence: {result['confidence']:.2%})")
        return result
    
    def learn_from_correction(
        self,
        transaction_id: str,
        payee_name: str,
        correct_category_id: str,
        correct_category_name: str,
        agent_suggested_category: str,
        reasoning: str
    ) -> bool:
        """
        Learn from user correction by updating SOP rules.
        
        Creates new SOP entry in categorization_rules.md under
        "Learned from User Corrections" section.
        
        Args:
            transaction_id: Transaction that was corrected
            payee_name: Payee name from transaction
            correct_category_id: Correct category UUID
            correct_category_name: Correct category name
            agent_suggested_category: What agent initially suggested
            reasoning: Why user corrected it
        
        Returns:
            True if SOP updated successfully, False otherwise
        """
        logger.info(f"Learning from correction for transaction {transaction_id}")
        
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        
        rule_content = f"""
## Learned from User Corrections

- **Payee**: {payee_name}
  **Correct Category**: {correct_category_name} (ID: {correct_category_id})
  **Agent Initially Suggested**: {agent_suggested_category}
  **Reasoning**: {reasoning}
  **Confidence**: High (user-validated)
  **Date Learned**: {timestamp}
"""
        
        try:
            success = append_rule_to_sop(rule_content)
            
            if success:
                logger.info(f"Learned correction: {payee_name} → {correct_category_name}")
                # Invalidate SOP cache to force reload
                self.sop_rules = None
            else:
                logger.error("Failed to append correction to SOP")
            
            return success
        
        except Exception as e:
            logger.error(f"Failed to learn correction: {e}")
            return False
    
    def _validate_transaction(self, txn: Dict[str, Any]) -> bool:
        """
        Validate transaction has required fields.
        
        Args:
            txn: Transaction dict to validate
        
        Returns:
            True if valid, False otherwise
        """
        if not isinstance(txn, dict):
            logger.error("Transaction must be dict")
            return False
        
        required = ['id', 'payee_name']
        for field in required:
            if field not in txn or not txn[field]:
                logger.error(f"Transaction missing required field: {field}")
                return False
        
        return True
    
    def _load_sop_rules(self) -> Dict:
        """
        Lazy-load SOP rules from markdown file with caching.
        
        Returns:
            Dict with core_patterns, split_patterns, user_corrections, web_research
        """
        if self.sop_rules is not None:
            logger.debug("Using cached SOP rules")
            return self.sop_rules
        
        logger.info("Loading SOP rules from file")
        self.sop_rules = load_categorization_rules()
        
        if not self.sop_rules:
            logger.warning("No SOP rules loaded, empty dict")
            self.sop_rules = {
                'core_patterns': [],
                'split_patterns': [],
                'user_corrections': [],
                'web_research': []
            }
        
        logger.info(f"Loaded {len(self.sop_rules.get('core_patterns', []))} core patterns")
        return self.sop_rules
    
    def _tier1_sop_match(self, transaction: Dict) -> Optional[Dict]:
        """
        Tier 1: Match transaction against SOP rules.
        
        Implements pattern matching with precedence:
        1. exact (confidence: 1.0)
        2. prefix (confidence: 0.95)
        3. contains (confidence: 0.92)
        4. regex (confidence: 0.90)
        
        Args:
            transaction: Transaction dict
        
        Returns:
            Match result dict or None if no match
        """
        # Load SOP rules (cached)
        rules = self._load_sop_rules()
        
        payee = transaction['payee_name'].lower()
        txn_id = transaction['id']
        
        # Check core_patterns section
        for rule in rules.get('core_patterns', []):
            pattern = rule.get('pattern', '').lower()
            pattern_type = rule.get('pattern_type', 'exact')
            
            matched = False
            confidence = 1.0
            
            if pattern_type == 'exact':
                matched = (payee == pattern)
                confidence = 1.0
            elif pattern_type == 'prefix':
                matched = payee.startswith(pattern.rstrip('*'))
                confidence = 0.95
            elif pattern_type == 'contains':
                matched = pattern.strip('*') in payee
                confidence = 0.92
            elif pattern_type == 'regex':
                try:
                    matched = bool(re.search(pattern, payee))
                    confidence = 0.90
                except re.error as e:
                    logger.error(f"Invalid regex pattern: {pattern} - {e}")
                    continue
            
            if matched:
                logger.debug(f"SOP match: {pattern} ({pattern_type}) for {payee}")
                return {
                    'transaction_id': txn_id,
                    'type': 'single',
                    'category_id': rule.get('category_id', 'unknown'),
                    'category_name': rule.get('category', 'Uncategorized'),
                    'confidence': confidence,
                    'tier': 'sop',
                    'method': pattern_type,
                    'reasoning': f"SOP rule match: '{pattern}' ({pattern_type})",
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
        
        logger.debug(f"No SOP match for {payee}")
        return None
    
    def _load_ynab_categories(self) -> List[Dict]:
        """
        Lazy-load YNAB categories with 1-hour TTL cache.
        
        Returns:
            List of category dicts: [{'id': str, 'name': str}]
        """
        now = datetime.now(timezone.utc)
        
        # Check cache TTL (1 hour)
        if (self.ynab_categories and self.categories_cached_at and
            now - self.categories_cached_at < timedelta(hours=1)):
            logger.debug("Using cached YNAB categories")
            return self.ynab_categories
        
        logger.info("Fetching YNAB categories from API")
        try:
            self.ynab_categories = fetch_categories(self.budget_id)
            self.categories_cached_at = now
            logger.info(f"Loaded {len(self.ynab_categories)} categories")
            return self.ynab_categories
        except Exception as e:
            logger.error(f"Failed to fetch categories: {e}")
            # Return cached if available, empty list otherwise
            if self.ynab_categories:
                logger.warning("Using stale category cache due to fetch failure")
                return self.ynab_categories
            return []
    
    def _tier2_historical_match(self, transaction: Dict) -> Optional[Dict]:
        """
        Tier 2: Match transaction using historical patterns.
        
        Delegates to pattern_analyzer molecule, requires ≥80% confidence.
        
        Args:
            transaction: Transaction dict
        
        Returns:
            Match result dict or None if no match or confidence too low
        """
        txn_id = transaction['id']
        
        try:
            # Delegate to pattern_analyzer molecule
            result = analyze_transaction(transaction)
            
            if not result:
                logger.debug(f"No historical pattern for transaction {txn_id}")
                return None
            
            # Verify confidence threshold (pattern_analyzer already filters ≥80%)
            if result['confidence'] < 0.80:
                logger.debug(f"Historical match confidence too low: {result['confidence']:.2%}")
                return None
            
            # Add transaction_id and timestamp
            result['transaction_id'] = txn_id
            result['tier'] = 'historical'
            result['timestamp'] = datetime.now(timezone.utc).isoformat()
            
            logger.debug(f"Historical match: {result['category_name']} ({result['confidence']:.2%})")
            return result
        
        except Exception as e:
            logger.error(f"Tier 2 historical match failed: {e}")
            return None
    
    def _mock_web_search(self, payee_name: str) -> str:
        """
        Mock web search results for testing (Phase 1 implementation).
        
        Args:
            payee_name: Payee name to search
        
        Returns:
            Mock search results as text
        
        Note:
            Real WebSearch via MCP server will be added in Phase 2.
        """
        payee_lower = payee_name.lower()
        
        # Mock responses for common patterns
        if 'starbucks' in payee_lower or 'coffee' in payee_lower:
            return "Starbucks is a multinational coffee shop chain."
        elif 'whole foods' in payee_lower or 'grocery' in payee_lower:
            return "Whole Foods is a grocery store chain specializing in organic products."
        elif 'amazon' in payee_lower:
            return "Amazon is an online retail platform selling various products."
        elif 'shell' in payee_lower or 'chevron' in payee_lower or 'gas' in payee_lower:
            return "Gas station for vehicle fuel."
        else:
            return f"No specific information found for {payee_name}."
    
    def _call_claude_with_retry(
        self,
        prompt: str,
        max_retries: int = 3
    ) -> str:
        """
        Call Claude API with exponential backoff retry.
        
        Args:
            prompt: Prompt text for Claude
            max_retries: Maximum retry attempts (default: 3)
        
        Returns:
            Response text from Claude
        
        Raises:
            Exception: If all retries exhausted or non-retryable error
        """
        for attempt in range(max_retries):
            try:
                logger.debug(f"Calling Claude API (attempt {attempt + 1}/{max_retries})")
                
                response = self.anthropic_client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=1024,
                    messages=[{
                        "role": "user",
                        "content": prompt
                    }]
                )
                
                result_text = response.content[0].text
                logger.debug(f"Claude API call successful ({len(result_text)} chars)")
                return result_text
            
            except Exception as e:
                error_str = str(e)
                
                # Check if rate limit error (429)
                if '429' in error_str and attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"Rate limit hit, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    # Non-retryable error or max retries reached
                    logger.error(f"Claude API call failed: {error_str}")
                    raise
        
        raise Exception(f"Claude API call failed after {max_retries} retries")
    
    def _tier3_research_and_reasoning(self, transaction: Dict) -> Dict:
        """
        Tier 3: Claude-powered research and reasoning.
        
        Uses Claude Sonnet 4.5 to:
        1. Perform mock web search for unknown payee
        2. Analyze business type
        3. Recommend appropriate YNAB category
        
        Args:
            transaction: Transaction dict
        
        Returns:
            Categorization result dict (always returns, never None)
        """
        payee = transaction['payee_name']
        amount = transaction.get('amount', 0)
        memo = transaction.get('memo', '')
        txn_id = transaction['id']
        
        logger.info(f"Tier 3: Researching payee '{payee}'")
        
        # Load categories
        categories = self._load_ynab_categories()
        
        if not categories:
            logger.error("No YNAB categories available for Tier 3")
            return self._manual_review_response(txn_id, "Categories unavailable")
        
        # Build category list for prompt
        category_list = "\n".join([
            f"- {cat['name']} (ID: {cat['id']})"
            for cat in categories
        ])
        
        # Mock web search
        search_results = self._mock_web_search(payee)
        
        # Build prompt
        prompt = f"""Analyze this transaction and recommend the most appropriate YNAB category.

Transaction Details:
- Payee: {payee}
- Amount: ${abs(amount)/1000:.2f}
- Memo: {memo or 'N/A'}

Web Search Results:
{search_results}

Available Categories:
{category_list}

Instructions:
1. Based on the web search results, identify the business type
2. Determine the most appropriate category from the list
3. Provide confidence score between 0.60-0.79 (research-based categorization)
4. Explain your reasoning

Respond ONLY with valid JSON (no markdown, no code blocks):
{{
    "category_id": "UUID from list",
    "category_name": "Exact category name from list",
    "confidence": 0.75,
    "business_type": "identified business type",
    "reasoning": "brief explanation"
}}"""
        
        try:
            # Call Claude
            response_text = self._call_claude_with_retry(prompt)
            
            # Parse JSON (strip any markdown code blocks if present)
            response_text = response_text.strip()
            if response_text.startswith('```'):
                # Strip markdown code blocks
                response_text = re.sub(r'^```(?:json)?\n', '', response_text)
                response_text = re.sub(r'\n```$', '', response_text)
            
            result = json.loads(response_text)
            
            # Validate required fields
            required = ['category_id', 'category_name', 'confidence', 'reasoning']
            if not all(k in result for k in required):
                raise ValueError(f"Missing required fields in Claude response: {result}")
            
            # Add transaction metadata
            result['transaction_id'] = txn_id
            result['type'] = 'single'
            result['tier'] = 'research'
            result['method'] = 'claude'
            result['timestamp'] = datetime.now(timezone.utc).isoformat()
            
            # Update SOP with learned rule (Web Research section)
            self._update_sop_web_research(
                payee=payee,
                business_type=result.get('business_type', 'Unknown'),
                category=result['category_name'],
                reasoning=result['reasoning']
            )
            
            logger.info(f"Tier 3 success: {result['category_name']} (confidence: {result['confidence']:.2%})")
            return result
        
        except Exception as e:
            logger.error(f"Tier 3 research failed: {e}")
            return self._manual_review_response(txn_id, f"Research failed: {str(e)}")
    
    def _manual_review_response(
        self,
        transaction_id: str,
        error_message: str
    ) -> Dict:
        """
        Generate manual review response when all tiers fail.
        
        Args:
            transaction_id: Transaction ID
            error_message: Error description
        
        Returns:
            Response dict with confidence=0.0 and manual review flag
        """
        return {
            'transaction_id': transaction_id,
            'type': 'single',
            'category_id': None,
            'category_name': 'Uncategorized',
            'confidence': 0.0,
            'tier': 'research',
            'method': 'failed',
            'reasoning': error_message,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'requires_manual_review': True
        }
    
    def _update_sop_web_research(
        self,
        payee: str,
        business_type: str,
        category: str,
        reasoning: str
    ) -> bool:
        """
        Add web research result to SOP file.
        
        Args:
            payee: Payee name
            business_type: Identified business type
            category: Recommended category
            reasoning: Explanation
        
        Returns:
            True if updated, False otherwise
        """
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        
        rule_content = f"""
## Web Research Results

- **Unknown Payee**: {payee}
  **Business Type**: {business_type}
  **Category**: {category}
  **Reasoning**: {reasoning}
  **Confidence**: Medium (web-sourced)
  **Date Added**: {timestamp}
"""
        
        try:
            success = append_rule_to_sop(rule_content)
            if success:
                logger.info(f"Added web research result for {payee} to SOP")
                # Invalidate SOP cache
                self.sop_rules = None
            return success
        except Exception as e:
            logger.error(f"Failed to update SOP with web research: {e}")
            return False
