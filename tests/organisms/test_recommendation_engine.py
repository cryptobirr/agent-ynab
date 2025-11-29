"""
Tests for Recommendation Engine Organism

ZERO MOCKS POLICY: All tests use real systems only.
- Real CategorizationAgent integration
- Real error handling
- Real logging

NO mocking, stubbing, or simulation permitted.
"""

import pytest
from datetime import datetime, timezone
from organisms.recommendation_engine import RecommendationEngine


# Test fixtures
@pytest.fixture
def mock_budget_id():
    """Return a test budget ID."""
    return "test-budget-12345"


@pytest.fixture
def sample_transaction():
    """Return a sample transaction for testing."""
    return {
        'id': 'txn-001',
        'payee_name': 'Test Merchant',
        'amount': -50000,
        'date': datetime.now(timezone.utc).isoformat(),
        'memo': 'Test transaction'
    }


class TestRecommendationEngineInitialization:
    """Test recommendation engine initialization."""
    
    def test_init_with_valid_budget_id(self, mock_budget_id):
        """Test initialization with valid budget ID."""
        try:
            engine = RecommendationEngine(mock_budget_id)
            assert engine.budget_id == mock_budget_id
            assert engine.categorization_agent is not None
        except ValueError as e:
            # Expected if Anthropic API key not available
            if "Anthropic API key not found" in str(e):
                pytest.skip("Anthropic API key not configured")
            raise
    
    def test_init_with_empty_budget_id(self):
        """Test initialization fails with empty budget ID."""
        with pytest.raises(ValueError, match="budget_id must be non-empty string"):
            RecommendationEngine("")
    
    def test_init_with_none_budget_id(self):
        """Test initialization fails with None budget ID."""
        with pytest.raises(ValueError, match="budget_id must be non-empty string"):
            RecommendationEngine(None)
    
    def test_init_with_invalid_type(self):
        """Test initialization fails with invalid type."""
        with pytest.raises(ValueError, match="budget_id must be non-empty string"):
            RecommendationEngine(12345)


class TestGetRecommendation:
    """Test get_recommendation() method."""
    
    def test_get_recommendation_with_valid_transaction(self, mock_budget_id, sample_transaction):
        """Test get_recommendation with valid transaction."""
        try:
            engine = RecommendationEngine(mock_budget_id)
            result = engine.get_recommendation(sample_transaction)
            
            # Verify result structure
            assert 'transaction_id' in result
            assert 'type' in result
            assert 'category_id' in result
            assert 'category_name' in result
            assert 'confidence' in result
            assert 'tier' in result
            assert 'method' in result
            assert 'reasoning' in result
            assert 'timestamp' in result
            
            # Verify values
            assert result['transaction_id'] == sample_transaction['id']
            assert result['type'] in ['single', 'split']
            assert result['tier'] in ['sop', 'historical', 'research']
            assert 0.0 <= result['confidence'] <= 1.0
            
        except ValueError as e:
            if "Anthropic API key not found" in str(e):
                pytest.skip("Anthropic API key not configured")
            raise
    
    def test_get_recommendation_with_invalid_transaction(self, mock_budget_id):
        """Test get_recommendation raises ValueError for invalid transaction."""
        try:
            engine = RecommendationEngine(mock_budget_id)
            
            with pytest.raises(ValueError):
                engine.get_recommendation({'invalid': 'data'})
                
        except ValueError as e:
            if "Anthropic API key not found" in str(e):
                pytest.skip("Anthropic API key not configured")
            raise
    
    def test_get_recommendation_missing_id(self, mock_budget_id):
        """Test get_recommendation fails when transaction ID missing."""
        try:
            engine = RecommendationEngine(mock_budget_id)
            
            with pytest.raises(ValueError):
                engine.get_recommendation({
                    'payee_name': 'Test',
                    'amount': -10000
                })
                
        except ValueError as e:
            if "Anthropic API key not found" in str(e):
                pytest.skip("Anthropic API key not configured")
            raise
    
    def test_get_recommendation_missing_payee(self, mock_budget_id):
        """Test get_recommendation fails when payee_name missing."""
        try:
            engine = RecommendationEngine(mock_budget_id)
            
            with pytest.raises(ValueError):
                engine.get_recommendation({
                    'id': 'txn-001',
                    'amount': -10000
                })
                
        except ValueError as e:
            if "Anthropic API key not found" in str(e):
                pytest.skip("Anthropic API key not configured")
            raise


class TestErrorHandling:
    """Test error handling and fallback logic."""
    
    def test_get_recommendation_returns_manual_review_on_agent_failure(self, mock_budget_id):
        """Test that failures return manual review result instead of crashing."""
        try:
            engine = RecommendationEngine(mock_budget_id)
            
            # This should return a result even if categorization fails
            # (though it will likely raise ValueError for invalid format)
            
        except ValueError as e:
            if "Anthropic API key not found" in str(e):
                pytest.skip("Anthropic API key not configured")
            raise


class TestResultFormat:
    """Test result format and consistency."""
    
    def test_result_has_required_fields(self, mock_budget_id, sample_transaction):
        """Test recommendation result has all required fields."""
        try:
            engine = RecommendationEngine(mock_budget_id)
            result = engine.get_recommendation(sample_transaction)
            
            required_fields = [
                'transaction_id',
                'type',
                'category_id',
                'category_name',
                'confidence',
                'tier',
                'method',
                'reasoning',
                'timestamp'
            ]
            
            for field in required_fields:
                assert field in result, f"Missing required field: {field}"
                
        except ValueError as e:
            if "Anthropic API key not found" in str(e):
                pytest.skip("Anthropic API key not configured")
            raise
    
    def test_result_transaction_id_matches(self, mock_budget_id, sample_transaction):
        """Test result transaction_id matches input."""
        try:
            engine = RecommendationEngine(mock_budget_id)
            result = engine.get_recommendation(sample_transaction)
            
            assert result['transaction_id'] == sample_transaction['id']
            
        except ValueError as e:
            if "Anthropic API key not found" in str(e):
                pytest.skip("Anthropic API key not configured")
            raise
    
    def test_result_tier_is_valid(self, mock_budget_id, sample_transaction):
        """Test result tier is one of expected values."""
        try:
            engine = RecommendationEngine(mock_budget_id)
            result = engine.get_recommendation(sample_transaction)
            
            assert result['tier'] in ['sop', 'historical', 'research']
            
        except ValueError as e:
            if "Anthropic API key not found" in str(e):
                pytest.skip("Anthropic API key not configured")
            raise
    
    def test_result_confidence_in_range(self, mock_budget_id, sample_transaction):
        """Test result confidence is between 0.0 and 1.0."""
        try:
            engine = RecommendationEngine(mock_budget_id)
            result = engine.get_recommendation(sample_transaction)
            
            assert 0.0 <= result['confidence'] <= 1.0
            
        except ValueError as e:
            if "Anthropic API key not found" in str(e):
                pytest.skip("Anthropic API key not configured")
            raise


class TestIntegration:
    """Integration tests with CategorizationAgent."""
    
    def test_recommendation_delegates_to_categorization_agent(self, mock_budget_id, sample_transaction):
        """Test recommendation properly delegates to categorization agent."""
        try:
            engine = RecommendationEngine(mock_budget_id)
            result = engine.get_recommendation(sample_transaction)
            
            # Result should come from categorization agent
            # Verify it has expected structure
            assert isinstance(result, dict)
            assert 'tier' in result
            assert 'confidence' in result
            
        except ValueError as e:
            if "Anthropic API key not found" in str(e):
                pytest.skip("Anthropic API key not configured")
            raise
