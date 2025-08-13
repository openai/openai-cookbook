"""
Generic query builder for complex database operations.
Helps build queries for data migration to HubSpot.
"""

from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
from enum import Enum

from .connection import get_db

class JoinType(Enum):
    """SQL join types."""
    INNER = "INNER JOIN"
    LEFT = "LEFT JOIN"
    RIGHT = "RIGHT JOIN"
    FULL = "FULL OUTER JOIN"

@dataclass
class QueryCondition:
    """Represents a WHERE condition."""
    column: str
    operator: str
    value: Any
    param_name: Optional[str] = None

class QueryBuilder:
    """
    Generic SQL query builder for read operations.
    Makes it easy to build complex queries for data migration.
    """
    
    def __init__(self):
        """Initialize query builder."""
        self.reset()
    
    def reset(self) -> "QueryBuilder":
        """Reset query builder to initial state."""
        self._select_columns: List[str] = []
        self._from_table: str = ""
        self._joins: List[str] = []
        self._where_conditions: List[str] = []
        self._group_by: List[str] = []
        self._having_conditions: List[str] = []
        self._order_by: List[str] = []
        self._limit_value: Optional[int] = None
        self._params: Dict[str, Any] = {}
        return self
    
    def select(self, *columns: str) -> "QueryBuilder":
        """
        Add SELECT columns.
        
        Args:
            columns: Column names or expressions
            
        Example:
            builder.select("id", "name", "email", "COUNT(*) as total")
        """
        self._select_columns.extend(columns)
        return self
    
    def from_table(self, table_name: str) -> "QueryBuilder":
        """
        Set FROM table.
        
        Args:
            table_name: Name of the table
        """
        self._from_table = table_name
        return self
    
    def join(self, table: str, condition: str, join_type: JoinType = JoinType.INNER) -> "QueryBuilder":
        """
        Add JOIN clause.
        
        Args:
            table: Table to join
            condition: JOIN condition
            join_type: Type of join
            
        Example:
            builder.join("companies c", "u.company_id = c.id", JoinType.LEFT)
        """
        self._joins.append(f"{join_type.value} {table} ON {condition}")
        return self
    
    def where(self, condition: str, **params) -> "QueryBuilder":
        """
        Add WHERE condition.
        
        Args:
            condition: WHERE condition with parameter placeholders
            **params: Named parameters
            
        Example:
            builder.where("status = :status AND created_date > :date", 
                         status="active", date="2025-01-01")
        """
        self._where_conditions.append(condition)
        self._params.update(params)
        return self
    
    def where_in(self, column: str, values: List[Any]) -> "QueryBuilder":
        """
        Add WHERE IN condition.
        
        Args:
            column: Column name
            values: List of values
            
        Example:
            builder.where_in("company_type", ["SMB", "Enterprise"])
        """
        if values:
            param_name = f"{column}_in_values"
            self._where_conditions.append(f"{column} IN :{param_name}")
            self._params[param_name] = values
        return self
    
    def where_between(self, column: str, start_value: Any, end_value: Any) -> "QueryBuilder":
        """
        Add WHERE BETWEEN condition.
        
        Args:
            column: Column name
            start_value: Start value
            end_value: End value
        """
        start_param = f"{column}_start"
        end_param = f"{column}_end"
        
        self._where_conditions.append(f"{column} BETWEEN :{start_param} AND :{end_param}")
        self._params.update({start_param: start_value, end_param: end_value})
        return self
    
    def where_like(self, column: str, pattern: str) -> "QueryBuilder":
        """
        Add WHERE LIKE condition.
        
        Args:
            column: Column name
            pattern: LIKE pattern (use % for wildcards)
            
        Example:
            builder.where_like("email", "%@colppy.com")
        """
        param_name = f"{column}_like"
        self._where_conditions.append(f"{column} LIKE :{param_name}")
        self._params[param_name] = pattern
        return self
    
    def group_by(self, *columns: str) -> "QueryBuilder":
        """
        Add GROUP BY columns.
        
        Args:
            columns: Column names
        """
        self._group_by.extend(columns)
        return self
    
    def having(self, condition: str, **params) -> "QueryBuilder":
        """
        Add HAVING condition.
        
        Args:
            condition: HAVING condition
            **params: Named parameters
        """
        self._having_conditions.append(condition)
        self._params.update(params)
        return self
    
    def order_by(self, column: str, direction: str = "ASC") -> "QueryBuilder":
        """
        Add ORDER BY clause.
        
        Args:
            column: Column name
            direction: ASC or DESC
        """
        self._order_by.append(f"{column} {direction}")
        return self
    
    def limit(self, count: int) -> "QueryBuilder":
        """
        Add LIMIT clause.
        
        Args:
            count: Maximum number of records
        """
        self._limit_value = count
        return self
    
    def build_query(self) -> str:
        """
        Build the complete SQL query.
        
        Returns:
            Complete SQL query string
        """
        if not self._from_table:
            raise ValueError("FROM table is required")
        
        # SELECT clause
        select_clause = "SELECT " + (", ".join(self._select_columns) if self._select_columns else "*")
        
        # FROM clause
        query_parts = [select_clause, f"FROM {self._from_table}"]
        
        # JOIN clauses
        if self._joins:
            query_parts.extend(self._joins)
        
        # WHERE clause
        if self._where_conditions:
            where_clause = "WHERE " + " AND ".join(self._where_conditions)
            query_parts.append(where_clause)
        
        # GROUP BY clause
        if self._group_by:
            group_clause = "GROUP BY " + ", ".join(self._group_by)
            query_parts.append(group_clause)
        
        # HAVING clause
        if self._having_conditions:
            having_clause = "HAVING " + " AND ".join(self._having_conditions)
            query_parts.append(having_clause)
        
        # ORDER BY clause
        if self._order_by:
            order_clause = "ORDER BY " + ", ".join(self._order_by)
            query_parts.append(order_clause)
        
        # LIMIT clause
        if self._limit_value:
            query_parts.append(f"LIMIT {self._limit_value}")
        
        return "\n".join(query_parts)
    
    def execute(self) -> List[Dict[str, Any]]:
        """
        Execute the query and return results.
        
        Returns:
            Query results as list of dictionaries
        """
        query = self.build_query()
        return get_db().execute_query(query, self._params)
    
    def count(self) -> int:
        """
        Execute query and return count of results.
        
        Returns:
            Number of matching records
        """
        # Build count query
        original_select = self._select_columns.copy()
        original_order = self._order_by.copy()
        original_limit = self._limit_value
        
        try:
            # Modify for count
            self._select_columns = ["COUNT(*) as count"]
            self._order_by = []
            self._limit_value = None
            
            result = self.execute()
            return result[0]["count"] if result else 0
            
        finally:
            # Restore original query
            self._select_columns = original_select
            self._order_by = original_order
            self._limit_value = original_limit

# Utility functions for common queries

def build_migration_query(source_table: str, 
                         target_mapping: Dict[str, str],
                         where_conditions: Optional[str] = None,
                         **params) -> QueryBuilder:
    """
    Build query for data migration with column mapping.
    
    Args:
        source_table: Source table name
        target_mapping: Dict mapping source columns to target names
        where_conditions: Optional WHERE conditions
        **params: Query parameters
        
    Returns:
        Configured QueryBuilder
        
    Example:
        # Map database columns to HubSpot properties
        mapping = {
            "company_name": "name",
            "company_email": "email",
            "company_type": "industry"
        }
        
        query = build_migration_query("companies", mapping, "status = :status", status="active")
        results = query.execute()
    """
    builder = QueryBuilder().from_table(source_table)
    
    # Add mapped columns
    select_columns = [f"{source_col} as {target_col}" for source_col, target_col in target_mapping.items()]
    builder.select(*select_columns)
    
    # Add conditions
    if where_conditions:
        builder.where(where_conditions, **params)
    
    return builder

def find_records_for_migration(table: str, 
                              last_sync_date: Optional[str] = None,
                              batch_size: int = 1000) -> List[Dict[str, Any]]:
    """
    Find records that need migration to HubSpot.
    
    Args:
        table: Table name
        last_sync_date: Last synchronization date (YYYY-MM-DD)
        batch_size: Number of records per batch
        
    Returns:
        List of records to migrate
    """
    builder = QueryBuilder().from_table(table).limit(batch_size)
    
    if last_sync_date:
        builder.where("updated_at > :sync_date OR created_at > :sync_date", sync_date=last_sync_date)
    
    return builder.execute()