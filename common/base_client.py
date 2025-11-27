"""Base API client utilities"""
import os
import requests
from typing import Dict, Optional
from common.vault_client import VaultClient


class YNABAPIError(Exception):
    """Base exception for YNAB API errors"""
    pass


class YNABUnauthorizedError(YNABAPIError):
    """401 - Invalid API token"""
    pass


class YNABNotFoundError(YNABAPIError):
    """404 - Resource not found"""
    pass


class YNABRateLimitError(YNABAPIError):
    """429 - Rate limit exceeded"""
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s")


class BaseYNABClient:
    """YNAB API client with authentication and error handling"""
    
    def __init__(self):
        """Initialize client with API token from Vault or environment"""
        self.base_url = "https://api.youneedabudget.com/v1"
        self.api_token = self._load_api_token()
        
    def _load_api_token(self) -> str:
        """
        Load API token from Vault or environment variable.
        
        Priority order:
        1. HashiCorp Vault: secret/ynab/api_token
        2. Environment variable: YNAB_API_TOKEN
        
        Returns:
            API token string
            
        Raises:
            YNABAPIError: If no token found in Vault or environment
        """
        # Try Vault first
        try:
            vault = VaultClient()
            if vault.is_connected():
                data = vault.kv_get('secret/data/ynab/api_token')
                if data and 'data' in data and 'token' in data['data']:
                    return data['data']['token']
        except Exception:
            # Vault connection failed, fall through to env var
            pass
        
        # Fall back to environment variable
        token = os.getenv('YNAB_API_TOKEN')
        if token:
            return token
        
        raise YNABAPIError(
            "No YNAB API token found. Set YNAB_API_TOKEN env var or "
            "store in Vault at secret/ynab/api_token"
        )
    
    def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Make authenticated GET request to YNAB API.
        
        Args:
            endpoint: API endpoint path (e.g., '/budgets/{id}/transactions')
            params: Optional query parameters
            
        Returns:
            JSON response as dictionary
            
        Raises:
            YNABUnauthorizedError: Invalid API token (401)
            YNABNotFoundError: Resource not found (404)
            YNABRateLimitError: Rate limit exceeded (429)
            YNABAPIError: Other API or network errors
        """
        headers = {'Authorization': f'Bearer {self.api_token}'}
        url = f'{self.base_url}{endpoint}'
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                raise YNABUnauthorizedError("Invalid YNAB API token")
            elif response.status_code == 404:
                raise YNABNotFoundError(f"Resource not found: {endpoint}")
            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                raise YNABRateLimitError(retry_after)
            else:
                raise YNABAPIError(
                    f"YNAB API error {response.status_code}: {response.text}"
                )
        
        except requests.RequestException as e:
            raise YNABAPIError(f"Network error: {str(e)}")
