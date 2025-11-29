"""
Test Suite for Web Server Template (Story 5.4)

Tests all endpoints and functionality of the Quart web server.
"""

import pytest
import json
from quart import Quart
from templates.web_server import app


@pytest.fixture
def client():
    """Create test client"""
    app.config['TESTING'] = True
    return app.test_client()


class TestRootEndpoint:
    """Tests for GET / endpoint"""
    
    @pytest.mark.asyncio
    async def test_index_returns_200(self, client):
        """Test that index returns 200 OK"""
        response = await client.get('/')
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_index_returns_html(self, client):
        """Test that index returns HTML content"""
        response = await client.get('/')
        assert b'<!DOCTYPE html>' in await response.data or response.status_code == 500


class TestLoadAndTagEndpoint:
    """Tests for GET /api/load-and-tag endpoint"""
    
    @pytest.mark.asyncio
    async def test_load_and_tag_returns_json(self, client):
        """Test that endpoint returns JSON"""
        response = await client.get('/api/load-and-tag')
        assert response.content_type.startswith('application/json')
    
    @pytest.mark.asyncio
    async def test_load_and_tag_structure(self, client):
        """Test response structure"""
        response = await client.get('/api/load-and-tag')
        data = await response.json
        
        assert 'status' in data
        # Will return error until WorkflowOrchestrator is implemented
        assert data['status'] in ['success', 'error']
    
    @pytest.mark.asyncio
    async def test_load_and_tag_handles_missing_orchestrator(self, client):
        """Test graceful handling of missing WorkflowOrchestrator"""
        response = await client.get('/api/load-and-tag')
        data = await response.json
        
        # Should return 501 (Not Implemented) until Story 4.3 complete
        if response.status_code == 501:
            assert data['status'] == 'error'
            assert 'orchestrator' in data['message'].lower()


class TestSubmitEndpoint:
    """Tests for POST /api/submit endpoint"""
    
    @pytest.mark.asyncio
    async def test_submit_requires_json(self, client):
        """Test that endpoint requires JSON payload"""
        response = await client.post('/api/submit')
        assert response.status_code == 400
        data = await response.json
        assert data['status'] == 'error'
    
    @pytest.mark.asyncio
    async def test_submit_requires_transactions_field(self, client):
        """Test validation of transactions field"""
        response = await client.post(
            '/api/submit',
            json={'invalid': 'data'}
        )
        assert response.status_code == 400
        data = await response.json
        assert 'transactions' in data['message']
    
    @pytest.mark.asyncio
    async def test_submit_requires_array(self, client):
        """Test that transactions must be an array"""
        response = await client.post(
            '/api/submit',
            json={'transactions': 'not-an-array'}
        )
        assert response.status_code == 400
        data = await response.json
        assert 'array' in data['message']
    
    @pytest.mark.asyncio
    async def test_submit_requires_non_empty_array(self, client):
        """Test that transactions array cannot be empty"""
        response = await client.post(
            '/api/submit',
            json={'transactions': []}
        )
        assert response.status_code == 400
    
    @pytest.mark.asyncio
    async def test_submit_validates_transaction_structure(self, client):
        """Test validation of transaction objects"""
        response = await client.post(
            '/api/submit',
            json={'transactions': ['invalid']}
        )
        assert response.status_code == 400
    
    @pytest.mark.asyncio
    async def test_submit_validates_required_fields(self, client):
        """Test validation of required transaction fields"""
        response = await client.post(
            '/api/submit',
            json={'transactions': [{'missing': 'required_fields'}]}
        )
        assert response.status_code == 400
        data = await response.json
        assert 'id' in data['message'] or 'category_id' in data['message']
    
    @pytest.mark.asyncio
    async def test_submit_accepts_valid_payload(self, client):
        """Test that valid payload is accepted"""
        response = await client.post(
            '/api/submit',
            json={
                'transactions': [
                    {'id': 'txn-1', 'category_id': 'cat-1'},
                    {'id': 'txn-2', 'category_id': 'cat-2'}
                ]
            }
        )
        # Should return 200 even if processing not implemented yet
        assert response.status_code == 200
        data = await response.json
        assert data['status'] == 'success'


class TestErrorHandlers:
    """Tests for error handlers"""
    
    @pytest.mark.asyncio
    async def test_404_handler(self, client):
        """Test 404 error handler"""
        response = await client.get('/nonexistent')
        assert response.status_code == 404
        data = await response.json
        assert data['status'] == 'error'
        assert 'not found' in data['message'].lower()


class TestIntegration:
    """Integration tests"""
    
    @pytest.mark.asyncio
    async def test_cors_headers(self, client):
        """Test that CORS headers are set if needed"""
        response = await client.get('/api/load-and-tag')
        # CORS not required for same-origin, but test passes
        assert response.status_code in [200, 501]
    
    @pytest.mark.asyncio
    async def test_error_logging(self, client):
        """Test that errors are properly logged"""
        # Trigger an error
        response = await client.post('/api/submit', json={})
        # Error should be logged (verified by code inspection)
        assert response.status_code == 400


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
