"""
Base model classes for database operations.
Simple ORM-like interface for data migration.
"""

from typing import Dict, List, Any, Optional, Type
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .connection import get_db

class BaseModel(ABC):
    """
    Base model class for database tables.
    Provides simple CRUD operations for data migration.
    """
    
    # Subclasses must define these
    table_name: str = ""
    primary_key: str = "id"
    
    def __init__(self, **kwargs):
        """Initialize model with data."""
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    @classmethod
    def get_table_info(cls) -> Dict[str, Any]:
        """Get information about the table."""
        return get_db().get_table_info(cls.table_name)
    
    @classmethod
    def get_columns(cls) -> List[str]:
        """Get table column names."""
        return get_db().get_table_columns(cls.table_name)
    
    @classmethod
    def find_all(cls, where_clause: Optional[str] = None, 
                params: Optional[Dict] = None,
                limit: Optional[int] = None) -> List["BaseModel"]:
        """
        Find all records matching criteria.
        
        Args:
            where_clause: SQL WHERE clause (without 'WHERE')
            params: Parameters for WHERE clause
            limit: Maximum records to return
            
        Returns:
            List of model instances
            
        Example:
            companies = Company.find_all(
                "status = :status AND type = :type",
                {"status": "active", "type": "SMB"},
                limit=100
            )
        """
        data = get_db().fetch_table_data(cls.table_name, where_clause, params, limit)
        return [cls(**row) for row in data]
    
    @classmethod
    def find_by_id(cls, record_id: Any) -> Optional["BaseModel"]:
        """
        Find record by primary key.
        
        Args:
            record_id: Primary key value
            
        Returns:
            Model instance or None
        """
        records = cls.find_all(f"{cls.primary_key} = :id", {"id": record_id}, limit=1)
        return records[0] if records else None
    
    @classmethod
    def find_one(cls, where_clause: str, params: Optional[Dict] = None) -> Optional["BaseModel"]:
        """
        Find single record matching criteria.
        
        Args:
            where_clause: SQL WHERE clause (without 'WHERE')
            params: Parameters for WHERE clause
            
        Returns:
            Model instance or None
        """
        records = cls.find_all(where_clause, params, limit=1)
        return records[0] if records else None
    
    @classmethod
    def count(cls, where_clause: Optional[str] = None, params: Optional[Dict] = None) -> int:
        """
        Count records matching criteria.
        
        Args:
            where_clause: SQL WHERE clause (without 'WHERE')
            params: Parameters for WHERE clause
            
        Returns:
            Number of matching records
        """
        query = f"SELECT COUNT(*) as count FROM {cls.table_name}"
        if where_clause:
            query += f" WHERE {where_clause}"
        
        result = get_db().execute_query(query, params)
        return result[0]["count"] if result else 0
    
    @classmethod
    def execute_custom_query(cls, query: str, params: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Execute custom SQL query.
        
        Args:
            query: SQL query
            params: Query parameters
            
        Returns:
            Query results as list of dictionaries
        """
        return get_db().execute_query(query, params)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary."""
        return {
            key: value for key, value in self.__dict__.items() 
            if not key.startswith('_')
        }
    
    def get_id(self) -> Any:
        """Get primary key value."""
        return getattr(self, self.primary_key, None)
    
    def __repr__(self) -> str:
        """String representation of model."""
        class_name = self.__class__.__name__
        id_value = self.get_id()
        return f"<{class_name}(id={id_value})>"

# Example model classes for common tables
# You can customize these based on your actual database schema

class Company(BaseModel):
    """Company model - customize based on your table structure."""
    table_name = "companies"
    primary_key = "id"
    
    @classmethod
    def find_active_companies(cls) -> List["Company"]:
        """Find all active companies."""
        return cls.find_all("status = :status", {"status": "active"})
    
    @classmethod
    def find_by_type(cls, company_type: str) -> List["Company"]:
        """Find companies by type (SMB, etc.)."""
        return cls.find_all("type = :type", {"type": company_type})

class User(BaseModel):
    """User model - customize based on your table structure."""
    table_name = "users"
    primary_key = "id"
    
    @classmethod
    def find_by_email(cls, email: str) -> Optional["User"]:
        """Find user by email."""
        return cls.find_one("email = :email", {"email": email})
    
    @classmethod
    def find_active_users(cls) -> List["User"]:
        """Find all active users."""
        return cls.find_all("status = :status", {"status": "active"})

class Account(BaseModel):
    """Account model - customize based on your table structure."""
    table_name = "accounts"
    primary_key = "id"
    
    @classmethod
    def find_by_company(cls, company_id: int) -> List["Account"]:
        """Find accounts by company."""
        return cls.find_all("company_id = :company_id", {"company_id": company_id})