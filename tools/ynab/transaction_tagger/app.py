"""
YNAB Transaction Tagger - Flask Application Entry Point
"""
from flask import Flask
from common.vault_client import VaultClient

app = Flask(__name__)

# Initialize Vault client
vault = VaultClient()

@app.route('/')
def index():
    return {"status": "YNAB Transaction Tagger is running"}

@app.route('/health')
def health():
    return {"status": "healthy", "vault": vault.is_connected()}

if __name__ == '__main__':
    app.run(debug=True)
