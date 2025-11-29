"""
Test Suite for Main Entry Point (Story 6.2)

Tests that main.py correctly starts server and handles lifecycle.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock
from main import open_browser, delayed_browser_open


class TestBrowserOpening:
    """Tests for browser opening functionality"""
    
    @patch('webbrowser.open')
    def test_open_browser_default_params(self, mock_open):
        """Test browser opens with default parameters"""
        open_browser()
        mock_open.assert_called_once_with('http://127.0.0.1:5000')
    
    @patch('webbrowser.open')
    def test_open_browser_custom_params(self, mock_open):
        """Test browser opens with custom host and port"""
        open_browser('localhost', 8080)
        mock_open.assert_called_once_with('http://localhost:8080')
    
    @pytest.mark.asyncio
    @patch('webbrowser.open')
    async def test_delayed_browser_open(self, mock_open):
        """Test browser opens after delay"""
        await delayed_browser_open('127.0.0.1', 5000, delay=0.1)
        mock_open.assert_called_once_with('http://127.0.0.1:5000')


class TestMainEntryPoint:
    """Tests for main entry point"""
    
    def test_main_py_is_executable(self):
        """Test that main.py can be imported"""
        import main
        assert hasattr(main, 'main')
        assert callable(main.main)
    
    def test_main_has_required_functions(self):
        """Test that required functions exist"""
        import main
        assert hasattr(main, 'run_server')
        assert hasattr(main, 'open_browser')
        assert hasattr(main, 'delayed_browser_open')


class TestWorkflowIntegration:
    """Integration tests for complete workflow"""
    
    @pytest.mark.asyncio
    async def test_quart_app_exists(self):
        """Test that Quart app can be imported"""
        from templates.web_server import app
        assert app is not None
    
    @pytest.mark.asyncio
    async def test_app_has_routes(self):
        """Test that app has expected routes"""
        from templates.web_server import app
        
        # Get routes
        routes = [rule.rule for rule in app.url_map.iter_rules()]
        
        assert '/' in routes
        assert '/api/load-and-tag' in routes
        assert '/api/submit' in routes


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
