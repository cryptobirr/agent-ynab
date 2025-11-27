#!/usr/bin/env python3
"""
Vault Secrets Setup Script

This script securely stores API credentials and database connection details
in HashiCorp Vault for the YNAB Transaction Tagger project.

Usage:
    python3 scripts/setup_vault_secrets.py

Environment Variables (optional - for non-interactive mode):
    YNAB_API_KEY         - YNAB Personal Access Token
    CLAUDE_API_KEY       - Anthropic Claude API key
    POSTGRES_HOST        - PostgreSQL server host (default: 127.0.0.1)
    POSTGRES_PORT        - PostgreSQL server port (default: 5432)
    POSTGRES_DB          - PostgreSQL database name
    POSTGRES_USER        - PostgreSQL username
    POSTGRES_PASSWORD    - PostgreSQL password

Requirements:
    - Vault server must be running and accessible
    - VAULT_ADDR and VAULT_TOKEN environment variables must be set
    - common/vault_client.py must be accessible

Author: YNAB Agent Team
Created: 2025-11-27
"""

import getpass
import os
import sys

# Add project root to path to import common modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.vault_client import VaultClient


def check_vault_connectivity():
    """
    Verify Vault server is accessible before attempting operations.
    
    Returns:
        VaultClient: Initialized client if Vault is accessible
        
    Exits with code 1 if Vault is not accessible.
    """
    print("Checking Vault connectivity...")
    
    vault = VaultClient()
    
    if not vault.is_connected():
        print("\n" + "="*60)
        print("ERROR: Cannot connect to Vault server")
        print("="*60)
        print(f"\nVault Address: {vault.addr}")
        print(f"Vault Token: {'[set]' if vault.token else '[NOT SET]'} (length: {len(vault.token) if vault.token else 0})")
        print("\nPlease ensure Vault is running:")
        print("  $ vault server -dev -dev-root-token-id=\"dev-token\"")
        print("\nOr if using brew services:")
        print("  $ brew services start hashicorp/tap/vault")
        print("\nThen set environment variables:")
        print("  export VAULT_ADDR='http://127.0.0.1:8200'")
        print("  export VAULT_TOKEN='dev-token'")
        print("\nAnd re-run this script.")
        print("="*60)
        sys.exit(1)
    
    print("✓ Vault connection successful\n")
    return vault


def prompt_for_secret(prompt_text, env_var_name=None, default=None, allow_empty=False):
    """
    Securely prompt for a secret value.
    
    Checks environment variable first (if specified), then prompts interactively
    using getpass (hidden input). Re-prompts if empty (unless allow_empty=True).
    
    Args:
        prompt_text: Text to display when prompting
        env_var_name: Environment variable to check first (optional)
        default: Default value if no input provided (optional)
        allow_empty: Whether to allow empty input (default: False)
        
    Returns:
        str: Secret value
        
    Handles KeyboardInterrupt (Ctrl+C) gracefully.
    """
    # Check environment variable first
    if env_var_name:
        value = os.getenv(env_var_name)
        if value:
            print(f"Using {env_var_name} from environment")
            return value.strip()
    
    # Interactive prompt
    while True:
        try:
            if default:
                secret = input(f"{prompt_text} [default: {default}]: ").strip()
                if not secret:
                    return default
            else:
                secret = getpass.getpass(prompt_text).strip()
            
            if secret or allow_empty:
                return secret
            
            print("Error: Value cannot be empty. Please try again.")
            
        except KeyboardInterrupt:
            print("\n\nSetup cancelled by user.")
            sys.exit(0)


def store_ynab_credentials(vault):
    """
    Prompt for and store YNAB API credentials in Vault.
    
    Args:
        vault: VaultClient instance
        
    Returns:
        bool: True if storage successful, False otherwise
    """
    print("="*60)
    print("YNAB API Credentials")
    print("="*60)
    print("Get your YNAB Personal Access Token from:")
    print("  https://app.ynab.com/settings/developer")
    print()
    
    api_key = prompt_for_secret(
        "Enter YNAB API key: ",
        env_var_name="YNAB_API_KEY"
    )
    
    print("\nStoring YNAB credentials in Vault...")
    success = vault.kv_put("secret/ynab/credentials", {
        "api_key": api_key
    })
    
    if success:
        print("✓ YNAB credentials stored successfully\n")
        return True
    else:
        print("✗ Failed to store YNAB credentials\n")
        return False


def store_claude_credentials(vault):
    """
    Prompt for and store Claude API credentials in Vault.
    
    Args:
        vault: VaultClient instance
        
    Returns:
        bool: True if storage successful, False otherwise
    """
    print("="*60)
    print("Claude API Credentials")
    print("="*60)
    print("Get your Claude API key from:")
    print("  https://console.anthropic.com/settings/keys")
    print()
    
    api_key = prompt_for_secret(
        "Enter Claude API key: ",
        env_var_name="CLAUDE_API_KEY"
    )
    
    print("\nStoring Claude API key in Vault...")
    success = vault.kv_put("secret/claude/api_key", {
        "api_key": api_key
    })
    
    if success:
        print("✓ Claude API key stored successfully\n")
        return True
    else:
        print("✗ Failed to store Claude API key\n")
        return False


def store_postgres_credentials(vault):
    """
    Prompt for and store PostgreSQL connection credentials in Vault.
    
    Args:
        vault: VaultClient instance
        
    Returns:
        bool: True if storage successful, False otherwise
    """
    print("="*60)
    print("PostgreSQL Connection Credentials")
    print("="*60)
    print("Enter PostgreSQL connection details for ynab_db database.")
    print()
    
    host = prompt_for_secret(
        "PostgreSQL host",
        env_var_name="POSTGRES_HOST",
        default="127.0.0.1"
    )
    
    port_str = prompt_for_secret(
        "PostgreSQL port",
        env_var_name="POSTGRES_PORT",
        default="5432"
    )
    
    # Validate port
    try:
        port = int(port_str)
        if port < 1 or port > 65535:
            print(f"Warning: Port {port} is outside valid range 1-65535")
            print("Storing anyway - validation will occur when database is accessed")
    except ValueError:
        print(f"Warning: Port '{port_str}' is not a valid integer")
        print("Storing anyway - validation will occur when database is accessed")
        port = port_str  # Store as-is if conversion fails
    
    database = prompt_for_secret(
        "Database name: ",
        env_var_name="POSTGRES_DB"
    )
    
    username = prompt_for_secret(
        "PostgreSQL username: ",
        env_var_name="POSTGRES_USER"
    )
    
    password = prompt_for_secret(
        "PostgreSQL password: ",
        env_var_name="POSTGRES_PASSWORD"
    )
    
    print("\nStoring PostgreSQL credentials in Vault...")
    success = vault.kv_put("secret/postgres/ynab_db", {
        "host": host,
        "port": port,
        "database": database,
        "username": username,
        "password": password
    })
    
    if success:
        print("✓ PostgreSQL credentials stored successfully\n")
        return True
    else:
        print("✗ Failed to store PostgreSQL credentials\n")
        return False


def verify_all_secrets(vault):
    """
    Verify all secrets are retrievable and have expected fields.
    
    Args:
        vault: VaultClient instance
        
    Returns:
        bool: True if all verifications pass, False otherwise
    """
    print("="*60)
    print("Verifying Stored Secrets")
    print("="*60)
    print()
    
    all_valid = True
    
    # Verify YNAB credentials
    print("Checking secret/ynab/credentials...")
    ynab_creds = vault.kv_get("secret/ynab/credentials")
    if ynab_creds and "api_key" in ynab_creds:
        print("✓ secret/ynab/credentials - OK (api_key present)")
    else:
        print("✗ secret/ynab/credentials - FAILED (api_key missing or secret not found)")
        all_valid = False
    
    # Verify Claude API key
    print("Checking secret/claude/api_key...")
    claude_creds = vault.kv_get("secret/claude/api_key")
    if claude_creds and "api_key" in claude_creds:
        print("✓ secret/claude/api_key - OK (api_key present)")
    else:
        print("✗ secret/claude/api_key - FAILED (api_key missing or secret not found)")
        all_valid = False
    
    # Verify PostgreSQL credentials
    print("Checking secret/postgres/ynab_db...")
    pg_creds = vault.kv_get("secret/postgres/ynab_db")
    required_fields = ["host", "port", "database", "username", "password"]
    if pg_creds and all(field in pg_creds for field in required_fields):
        print(f"✓ secret/postgres/ynab_db - OK ({len(required_fields)} fields present)")
    else:
        print(f"✗ secret/postgres/ynab_db - FAILED (missing fields or secret not found)")
        if pg_creds:
            missing = [f for f in required_fields if f not in pg_creds]
            print(f"  Missing fields: {', '.join(missing)}")
        all_valid = False
    
    print()
    
    if all_valid:
        print("✓ All secrets verified successfully!")
    else:
        print("✗ Some secrets failed verification")
    
    print()
    return all_valid


def main():
    """Main entry point for Vault secrets setup."""
    print("\n" + "="*60)
    print(" YNAB Transaction Tagger - Vault Secrets Setup")
    print("="*60)
    print()
    
    try:
        # Step 1: Check Vault connectivity
        vault = check_vault_connectivity()
        
        # Step 2: Store YNAB credentials
        if not store_ynab_credentials(vault):
            print("ERROR: Failed to store YNAB credentials")
            sys.exit(1)
        
        # Step 3: Store Claude credentials
        if not store_claude_credentials(vault):
            print("ERROR: Failed to store Claude credentials")
            sys.exit(1)
        
        # Step 4: Store PostgreSQL credentials
        if not store_postgres_credentials(vault):
            print("ERROR: Failed to store PostgreSQL credentials")
            sys.exit(1)
        
        # Step 5: Verify all secrets
        if not verify_all_secrets(vault):
            print("ERROR: Secret verification failed")
            sys.exit(1)
        
        # Success!
        print("="*60)
        print("✓ Vault Secrets Configuration Complete")
        print("="*60)
        print()
        print("All secrets have been stored in Vault and verified:")
        print("  - secret/ynab/credentials")
        print("  - secret/claude/api_key")
        print("  - secret/postgres/ynab_db")
        print()
        print("To verify manually:")
        print("  $ vault kv get secret/ynab/credentials")
        print("  $ vault kv get secret/claude/api_key")
        print("  $ vault kv get secret/postgres/ynab_db")
        print()
        print("To rotate secrets:")
        print("  Re-run this script with updated credentials.")
        print()
        print("="*60)
        
        return 0
        
    except Exception as e:
        print(f"\n✗ ERROR: {str(e)}")
        print("\nSetup failed. Please check the error message above and try again.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
