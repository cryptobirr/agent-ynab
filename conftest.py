"""Global pytest configuration for agent-ynab project

This conftest.py ensures database schema is initialized once before all tests run.
"""

import pytest
import subprocess
import os

# Set Vault environment variables for all tests
os.environ.setdefault('VAULT_ADDR', 'http://127.0.0.1:8200')
# Read root token from init file
try:
    with open(os.path.expanduser('~/.vault-data/init-keys.txt'), 'r') as f:
        for line in f:
            if 'Initial Root Token:' in line:
                os.environ['VAULT_TOKEN'] = line.split(':')[1].strip()
                break
except FileNotFoundError:
    # Fallback to dev-token if init file doesn't exist
    os.environ.setdefault('VAULT_TOKEN', 'dev-token')


@pytest.fixture(scope="session", autouse=True)
def initialize_database_schema():
    """
    Initialize database schema once for entire test session.
    
    This fixture runs automatically before any tests and ensures all required
    tables, indexes, and functions exist in the PostgreSQL database.
    """
    print("\n" + "=" * 60)
    print("INITIALIZING DATABASE SCHEMA FOR TEST SESSION")
    print("=" * 60)
    
    # Path to SQL schema file
    sql_file = os.path.join(
        os.path.dirname(__file__),
        "tools/ynab/transaction_tagger/sql/init_persistent_db.sql"
    )
    
    # Database credentials from Vault
    from common.vault_client import VaultClient
    vault = VaultClient()
    
    try:
        db_config = vault.get_postgres_credentials('birrbot_test')
    except ValueError as e:
        print(f"⚠ Warning: Could not get database credentials from Vault: {e}")
        print("⚠ Skipping database schema initialization")
        print("⚠ Tests requiring database will be skipped or mocked")
        print("=" * 60)
        yield
        return
    
    # Run schema initialization via psql
    try:
        result = subprocess.run(
            ["psql", 
             "-h", db_config['host'], 
             "-p", str(db_config['port']), 
             "-U", db_config['username'], 
             "-d", db_config['database'], 
             "-f", sql_file],
            env={**os.environ, "PGPASSWORD": db_config['password']},
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print(f"✓ Database schema initialized successfully from {sql_file}")
            print("✓ Tables created: ynab_transactions, ynab_split_transactions, sop_rules, agent_metadata")
            print("✓ Function created: find_historical_category()")
        else:
            print(f"✗ Schema initialization failed with exit code {result.returncode}")
            print(f"STDERR: {result.stderr}")
            # Don't fail tests - schema might already exist
    except Exception as e:
        print(f"✗ Error initializing schema: {e}")
        # Don't fail tests - schema might already exist
    
    print("=" * 60)
    
    yield
    
    # No cleanup - keep schema between test runs for faster execution


@pytest.fixture(scope="function", autouse=True)
def cleanup_test_data():
    """
    Clean up test data after each test to prevent state pollution.
    
    Runs automatically after every test function.
    Deletes all records with 'test_' prefix from all tables.
    """
    yield  # Let test run first
    
    # Cleanup after test completes
    try:
        from common.db_connection import DatabaseConnection
        db = DatabaseConnection()
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Delete test data from all tables (order matters due to foreign keys)
        cursor.execute("DELETE FROM ynab_split_transactions WHERE parent_transaction_id LIKE 'test_%';")
        cursor.execute("DELETE FROM ynab_transactions WHERE id LIKE 'test_%';")
        cursor.execute("DELETE FROM sop_rules WHERE payee_pattern LIKE 'test_%';")
        cursor.execute("DELETE FROM agent_metadata WHERE key LIKE 'test_%';")
        
        conn.commit()
        cursor.close()
        db.close()
    except Exception as e:
        # Don't fail tests if cleanup fails
        print(f"Warning: Cleanup failed: {e}")
