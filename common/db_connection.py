"""PostgreSQL database connection management with Vault integration"""
import os
import logging
from typing import Dict, Any, List, Optional
import psycopg2
from psycopg2 import pool, Error
from psycopg2.extras import RealDictCursor
from common.vault_client import VaultClient


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseConnectionError(Exception):
    """Raised when database connection cannot be established"""
    pass


class DatabaseExecutionError(Exception):
    """Raised when SQL execution fails"""
    pass


class DatabaseConnection:
    """
    PostgreSQL connection wrapper with Vault and environment variable support.
    
    Retrieves database credentials from HashiCorp Vault (preferred) or falls
    back to environment variables. Provides simple interface for SQL execution
    and querying.
    
    Example:
        >>> db = DatabaseConnection()
        >>> db.execute("CREATE TABLE test (id SERIAL PRIMARY KEY)")
        True
        >>> results = db.query("SELECT * FROM test")
        []
        
    Context manager usage:
        >>> with DatabaseConnection() as db:
        ...     db.execute("INSERT INTO test VALUES (1)")
    """
    
    def __init__(self):
        """
        Initialize database connection with credentials from Vault or environment.
        
        Raises:
            DatabaseConnectionError: If credentials cannot be loaded
        """
        self._connection = None
        self._credentials = self._get_credentials()
        logger.info(f"DatabaseConnection initialized from {self._credentials.get('source')}")
        
    def _get_credentials(self) -> Dict[str, Any]:
        """
        Retrieve database credentials from Vault or environment variables.
        
        Priority:
        1. HashiCorp Vault (secret/postgres/ynab_db)
        2. Environment variables (POSTGRES_HOST, etc.)
        
        Returns:
            Dict with host, port, database, user, password, source
            
        Raises:
            DatabaseConnectionError: If no credentials found
        """
        # Try Vault first
        try:
            vault = VaultClient()
            if vault.is_connected():
                creds = vault.kv_get("secret/postgres/ynab_db")
                if creds and all(k in creds for k in ['host', 'port', 'database', 'username', 'password']):
                    logger.info("Loaded database credentials from Vault")
                    return {
                        'host': creds['host'],
                        'port': int(creds['port']),
                        'database': creds['database'],
                        'user': creds['username'],
                        'password': creds['password'],
                        'source': 'vault'
                    }
        except Exception as e:
            logger.warning(f"Vault connection failed: {e}. Falling back to environment variables.")
        
        # Fall back to environment variables
        host = os.getenv('POSTGRES_HOST')
        port = os.getenv('POSTGRES_PORT')
        database = os.getenv('POSTGRES_DB')
        user = os.getenv('POSTGRES_USER')
        password = os.getenv('POSTGRES_PASSWORD')
        
        if all([host, port, database, user, password]):
            logger.info("Loaded database credentials from environment variables")
            return {
                'host': host,
                'port': int(port),
                'database': database,
                'user': user,
                'password': password,
                'source': 'environment'
            }
        
        # No credentials available
        raise DatabaseConnectionError(
            "No database credentials found. "
            "Please configure Vault (secret/postgres/ynab_db) or set environment variables "
            "(POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD)"
        )
    
    def get_connection(self):
        """
        Get or create PostgreSQL connection.
        
        Returns:
            psycopg2 connection object
            
        Raises:
            DatabaseConnectionError: If connection fails
        """
        if self._connection is None or self._connection.closed:
            try:
                self._connection = psycopg2.connect(
                    host=self._credentials['host'],
                    port=self._credentials['port'],
                    database=self._credentials['database'],
                    user=self._credentials['user'],
                    password=self._credentials['password']
                )
                logger.debug("Database connection established")
            except Error as e:
                raise DatabaseConnectionError(f"Failed to connect to database: {e}")
        
        return self._connection
    
    def execute(self, sql: str) -> bool:
        """
        Execute SQL statement (INSERT, UPDATE, DELETE, CREATE, etc.).
        
        Args:
            sql: SQL statement to execute
            
        Returns:
            True on successful execution
            
        Raises:
            DatabaseExecutionError: If SQL execution fails
            
        Example:
            >>> db = DatabaseConnection()
            >>> db.execute("CREATE TABLE test (id SERIAL PRIMARY KEY)")
            True
        """
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute(sql)
                conn.commit()
            logger.debug(f"Executed SQL: {sql[:100]}...")
            return True
        except Error as e:
            if self._connection:
                self._connection.rollback()
            raise DatabaseExecutionError(f"SQL execution failed: {e}")
    
    def query(self, sql: str) -> List[Dict[str, Any]]:
        """
        Execute SQL query and return results as list of dictionaries.
        
        Args:
            sql: SQL SELECT query
            
        Returns:
            List of dictionaries (column_name -> value)
            
        Raises:
            DatabaseExecutionError: If query execution fails
            
        Example:
            >>> db = DatabaseConnection()
            >>> results = db.query("SELECT id, name FROM users WHERE active = true")
            >>> results[0]['name']
            'John Doe'
        """
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql)
                results = cursor.fetchall()
                # Convert RealDictRow to regular dict
                return [dict(row) for row in results]
        except Error as e:
            raise DatabaseExecutionError(f"Query execution failed: {e}")
    
    @property
    def is_connected(self) -> bool:
        """
        Check if database connection is active.
        
        Returns:
            True if connected, False otherwise
        """
        return self._connection is not None and not self._connection.closed
    
    @property
    def connection_string(self) -> str:
        """
        Get connection string for debugging (password masked).
        
        Returns:
            Connection string with masked password
        """
        return (
            f"postgresql://{self._credentials['user']}:***@"
            f"{self._credentials['host']}:{self._credentials['port']}/"
            f"{self._credentials['database']}"
        )
    
    def close(self):
        """Close database connection if open."""
        if self._connection and not self._connection.closed:
            self._connection.close()
            logger.debug("Database connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - always closes connection."""
        self.close()
        return False  # Don't suppress exceptions
