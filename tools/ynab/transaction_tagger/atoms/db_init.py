"""Database initialization atom - Idempotent schema creation for YNAB Transaction Tagger"""
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
import logging

from common.db_connection import DatabaseConnection, DatabaseConnectionError, DatabaseExecutionError


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def initialize_database() -> Dict[str, Any]:
    """
    Initialize PostgreSQL database schema for YNAB Transaction Tagger.
    
    Idempotent: Safe to run multiple times. Checks agent_metadata table
    for initialization flag before executing schema. On first run, creates
    all tables, indexes, constraints, functions, and triggers from
    init_persistent_db.sql.
    
    Returns:
        Dict with the following keys:
            - status: 'initialized', 'already_initialized', or 'error'
            - version: Schema version (e.g., '1.0.0')
            - tables_created: List of table names (empty if already initialized)
            - timestamp: ISO 8601 timestamp of initialization
            - error: Error message if status='error', None otherwise
            
    Raises:
        Does not raise exceptions - returns error status dict instead
        
    Example:
        >>> result = initialize_database()
        >>> result['status']
        'initialized'
        >>> result['tables_created']
        ['ynab_transactions', 'ynab_split_transactions', 'sop_rules', 'agent_metadata']
        
        >>> result = initialize_database()  # Second call
        >>> result['status']
        'already_initialized'
    """
    db = None
    
    try:
        # Step 1: Create database connection
        logger.info("Initializing database connection...")
        db = DatabaseConnection()
        
        # Step 2: Check if already initialized
        logger.info("Checking if database already initialized...")
        try:
            result = db.query(
                "SELECT value FROM agent_metadata WHERE key = 'database_initialized'"
            )
            
            if result and len(result) > 0:
                value = result[0]['value']
                if isinstance(value, dict) and value.get('initialized'):
                    # Already initialized
                    logger.info("Database already initialized. Skipping schema creation.")
                    return {
                        'status': 'already_initialized',
                        'version': value.get('version', 'unknown'),
                        'tables_created': [],
                        'timestamp': value.get('timestamp', 'unknown'),
                        'error': None
                    }
        except DatabaseExecutionError as e:
            # Table might not exist yet - this is expected on first run
            logger.info("agent_metadata table not found. Proceeding with initialization.")
        
        # Step 3: Load SQL schema file
        logger.info("Loading SQL schema file...")
        sql_file = Path(__file__).parent.parent / 'sql' / 'init_persistent_db.sql'
        
        if not sql_file.exists():
            raise FileNotFoundError(f"SQL schema file not found: {sql_file}")
        
        sql_content = sql_file.read_text()
        logger.info(f"Loaded {len(sql_content)} bytes from {sql_file.name}")
        
        # Step 4: Execute SQL schema
        logger.info("Executing SQL schema (this may take a few seconds)...")
        db.execute(sql_content)
        logger.info("SQL schema executed successfully")
        
        # Step 5: Set initialization flag in agent_metadata
        logger.info("Setting initialization flag in agent_metadata...")
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        db.execute(f"""
            INSERT INTO agent_metadata (key, value, created_at, updated_at)
            VALUES (
                'database_initialized',
                '{{"initialized": true, "version": "1.0.0", "timestamp": "{timestamp}"}}'::jsonb,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (key) 
            DO UPDATE SET 
                value = EXCLUDED.value,
                updated_at = CURRENT_TIMESTAMP
        """)
        
        logger.info("Initialization flag set successfully")
        
        # Step 6: Return success status
        tables_created = [
            'ynab_transactions',
            'ynab_split_transactions',
            'sop_rules',
            'agent_metadata'
        ]
        
        logger.info(f"Database initialization complete. Created {len(tables_created)} tables.")
        
        return {
            'status': 'initialized',
            'version': '1.0.0',
            'tables_created': tables_created,
            'timestamp': timestamp,
            'error': None
        }
        
    except DatabaseConnectionError as e:
        # Connection error
        error_msg = f"Database connection error: {e}"
        logger.error(error_msg)
        return {
            'status': 'error',
            'version': None,
            'tables_created': [],
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'error': error_msg
        }
        
    except DatabaseExecutionError as e:
        # SQL execution error
        error_msg = f"SQL execution error: {e}"
        logger.error(error_msg)
        return {
            'status': 'error',
            'version': None,
            'tables_created': [],
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'error': error_msg
        }
        
    except FileNotFoundError as e:
        # SQL file not found
        error_msg = str(e)
        logger.error(error_msg)
        return {
            'status': 'error',
            'version': None,
            'tables_created': [],
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'error': error_msg
        }
        
    except Exception as e:
        # Unexpected error
        error_msg = f"Unexpected error during database initialization: {e}"
        logger.error(error_msg)
        return {
            'status': 'error',
            'version': None,
            'tables_created': [],
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'error': error_msg
        }
        
    finally:
        # Always close connection
        if db is not None:
            db.close()
            logger.debug("Database connection closed")
