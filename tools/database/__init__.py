"""
Database package for AWS MySQL connectivity.
Provides simple, fast database operations for Colppy data and HubSpot migration.
"""

from .connection import DatabaseConnection, get_db
from .models import (
    BaseModel,
    Empresa,
    Facturacion,
    Usuario,
    UsuarioEmpresa,
    EmpresasHubspot,
    CrmMatch,
    Plan,
)
from .query_builder import QueryBuilder

__all__ = [
    "DatabaseConnection",
    "get_db",
    "BaseModel",
    "Empresa",
    "Facturacion",
    "Usuario",
    "UsuarioEmpresa",
    "EmpresasHubspot",
    "CrmMatch",
    "Plan",
    "QueryBuilder",
]