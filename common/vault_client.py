"""Vault client wrapper for secrets management"""
import os
import requests

class VaultClient:
    """HashiCorp Vault API client"""
    
    def __init__(self):
        self.addr = os.getenv('VAULT_ADDR', 'http://127.0.0.1:8200')
        self.token = os.getenv('VAULT_TOKEN', 'dev-token')
        
    def is_connected(self):
        """Check if Vault is accessible"""
        try:
            resp = requests.get(f"{self.addr}/v1/sys/health", timeout=2)
            return resp.status_code == 200
        except:
            return False
    
    def kv_get(self, path):
        """Read secret from KV store (supports both KV v1 and v2)"""
        headers = {"X-Vault-Token": self.token}

        # Try KV v2 first (path needs /data/ inserted)
        if path.startswith('secret/') and '/data/' not in path:
            v2_path = path.replace('secret/', 'secret/data/', 1)
            resp = requests.get(f"{self.addr}/v1/{v2_path}", headers=headers)
            if resp.status_code == 200:
                data = resp.json().get('data', {})
                if 'data' in data:
                    return data['data']  # KV v2

        # Fallback to KV v1 or direct path
        resp = requests.get(f"{self.addr}/v1/{path}", headers=headers)
        if resp.status_code == 200:
            return resp.json().get('data', {})
        return None
    
    def kv_put(self, path, data):
        """Write secret to KV store"""
        headers = {"X-Vault-Token": self.token}
        resp = requests.post(f"{self.addr}/v1/{path}", headers=headers, json=data)
        return resp.status_code in [200, 204]

    def get_postgres_credentials(self, db_name):
        """
        Get PostgreSQL credentials from Vault.

        Args:
            db_name: Database name (e.g., 'birrbot_test', 'ynab_db')

        Returns:
            Dict with host, port, database, username, password

        Raises:
            ValueError: If credentials not found or incomplete
        """
        path = f"secret/postgres/{db_name}"
        creds = self.kv_get(path)

        if not creds:
            raise ValueError(f"No credentials found in Vault at {path}")

        required_keys = ['host', 'port', 'database', 'username', 'password']
        missing_keys = [k for k in required_keys if k not in creds]

        if missing_keys:
            raise ValueError(f"Incomplete credentials at {path}. Missing: {missing_keys}")

        return creds
