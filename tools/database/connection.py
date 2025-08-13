"""
Database connection management for AWS MySQL.
Simple, fast setup for data migration to HubSpot.
"""

import logging
from typing import Optional, Any, Dict, List
from contextlib import contextmanager
from sqlalchemy import create_engine, text, Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.pool import QueuePool

from .config import config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseConnection:
    """
    Simple database connection manager for read-only operations.
    Perfect for data migration and HubSpot integration.
    """
    
    def __init__(self):
        """Initialize database connection."""
        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker] = None
        self._setup_connection()
    
    def _setup_connection(self) -> None:
        """Setup database engine and session factory."""
        try:
            # Validate configuration
            config.validate()
            
            # Create engine with connection pooling
            self._engine = create_engine(
                config.connection_url,
                poolclass=QueuePool,
                pool_size=config.pool_size,
                max_overflow=config.max_overflow,
                pool_timeout=config.pool_timeout,
                pool_pre_ping=True,  # Validates connections before use
                echo=False,  # Set to True for SQL debugging
            )
            
            # Create session factory
            self._session_factory = sessionmaker(bind=self._engine)
            
            # Test connection
            self.test_connection()
            
            logger.info("Database connection established successfully")
            
        except Exception as e:
            logger.error(f"Failed to setup database connection: {e}")
            raise
    
    def test_connection(self) -> bool:
        """Test database connectivity."""
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                return result.fetchone()[0] == 1
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            raise
    
    @contextmanager
    def get_session(self):
        """
        Get database session with automatic cleanup.
        
        Usage:
            with db.get_session() as session:
                users = session.execute(text("SELECT * FROM users")).fetchall()
        """
        session = self._session_factory()
        try:
            yield session
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def execute_query(self, query: str, params: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Execute a read-only query and return results as list of dictionaries.
        
        Args:
            query: SQL query string
            params: Query parameters (optional)
            
        Returns:
            List of dictionaries with column names as keys
            
        Example:
            results = db.execute_query(
                "SELECT * FROM companies WHERE type = :company_type",
                {"company_type": "SMB"}
            )
        """
        try:
            with self.get_session() as session:
                result = session.execute(text(query), params or {})
                
                # Convert to list of dictionaries
                columns = result.keys()
                rows = result.fetchall()
                
                return [dict(zip(columns, row)) for row in rows]
                
        except SQLAlchemyError as e:
            logger.error(f"Query execution failed: {e}")
            raise
    
    def fetch_table_data(self, table_name: str, 
                        where_clause: Optional[str] = None,
                        params: Optional[Dict] = None,
                        limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Fetch data from a table with optional filtering.
        
        Args:
            table_name: Name of the table
            where_clause: Optional WHERE clause (without 'WHERE' keyword)
            params: Parameters for WHERE clause
            limit: Maximum number of records to fetch
            
        Returns:
            List of dictionaries with table data
            
        Example:
            # Get all active companies
            companies = db.fetch_table_data(
                "companies", 
                "status = :status AND created_date > :date",
                {"status": "active", "date": "2025-01-01"}
            )
        """
        query = f"SELECT * FROM {table_name}"
        
        if where_clause:
            query += f" WHERE {where_clause}"
        
        if limit:
            query += f" LIMIT {limit}"
        
        return self.execute_query(query, params)
    
    def get_table_columns(self, table_name: str) -> List[str]:
        """
        Get column names for a table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            List of column names
        """
        query = """
        SELECT COLUMN_NAME 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table
        ORDER BY ORDINAL_POSITION
        """
        
        result = self.execute_query(query, {
            "schema": config.database,
            "table": table_name
        })
        
        return [row["COLUMN_NAME"] for row in result]
    
    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """
        Get detailed information about a table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            Dictionary with table information
        """
        query = """
        SELECT 
            COLUMN_NAME,
            DATA_TYPE,
            IS_NULLABLE,
            COLUMN_DEFAULT,
            COLUMN_KEY,
            EXTRA
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table
        ORDER BY ORDINAL_POSITION
        """
        
        columns_info = self.execute_query(query, {
            "schema": config.database,
            "table": table_name
        })
        
        # Get row count
        count_result = self.execute_query(f"SELECT COUNT(*) as count FROM {table_name}")
        row_count = count_result[0]["count"] if count_result else 0
        
        return {
            "table_name": table_name,
            "columns": columns_info,
            "row_count": row_count
        }
    
    def list_tables(self) -> List[str]:
        """
        Get list of all tables in the database.
        
        Returns:
            List of table names
        """
        query = """
        SELECT TABLE_NAME 
        FROM INFORMATION_SCHEMA.TABLES 
        WHERE TABLE_SCHEMA = :schema AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
        """
        
        result = self.execute_query(query, {"schema": config.database})
        return [row["TABLE_NAME"] for row in result]
    
    def close(self) -> None:
        """Close database connections."""
        if self._engine:
            self._engine.dispose()
            logger.info("Database connections closed")

# Global database instance - will be initialized when first used
db = None

def get_db():
    """Get or create global database instance."""
    global db
    if db is None:
        db = DatabaseConnection()
    return db