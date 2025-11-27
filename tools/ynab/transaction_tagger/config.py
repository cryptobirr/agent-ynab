"""
YNAB Transaction Tagger - Configuration Management
"""
import os
from common.vault_client import VaultClient

class Config:
    """Application configuration"""
    
    def __init__(self):
        self.vault = VaultClient()
        
    def get_ynab_token(self):
        """Get YNAB API token from Vault"""
        return self.vault.kv_get("secret/ynab/api_token")
    
    def get_claude_api_key(self):
        """Get Claude API key from Vault"""
        return self.vault.kv_get("secret/claude/api_key")
    
    def get_db_credentials(self):
        """Get PostgreSQL credentials from Vault"""
        return self.vault.kv_get("secret/postgres/ynab")

config = Config()
