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
        """Read secret from KV store"""
        headers = {"X-Vault-Token": self.token}
        resp = requests.get(f"{self.addr}/v1/{path}", headers=headers)
        if resp.status_code == 200:
            return resp.json().get('data', {})
        return None
    
    def kv_put(self, path, data):
        """Write secret to KV store"""
        headers = {"X-Vault-Token": self.token}
        resp = requests.post(f"{self.addr}/v1/{path}", headers=headers, json=data)
        return resp.status_code in [200, 204]
