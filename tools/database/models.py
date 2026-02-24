"""
Base model classes and Colppy MySQL schema models.
Maps to actual Colppy staging/production database tables.
"""

from typing import Dict, List, Any, Optional
from abc import ABC, abstractmethod

from .connection import get_db


class BaseModel(ABC):
    """
    Base model class for database tables.
    Provides simple CRUD operations for data migration.
    """

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
    def find_all(
        cls,
        where_clause: Optional[str] = None,
        params: Optional[Dict] = None,
        limit: Optional[int] = None,
    ) -> List["BaseModel"]:
        """Find all records matching criteria."""
        data = get_db().fetch_table_data(
            cls.table_name, where_clause, params, limit
        )
        return [cls(**row) for row in data]

    @classmethod
    def find_by_id(cls, record_id: Any) -> Optional["BaseModel"]:
        """Find record by primary key."""
        pk = cls.primary_key
        records = cls.find_all(f"`{pk}` = :id", {"id": record_id}, limit=1)
        return records[0] if records else None

    @classmethod
    def find_one(
        cls, where_clause: str, params: Optional[Dict] = None
    ) -> Optional["BaseModel"]:
        """Find single record matching criteria."""
        records = cls.find_all(where_clause, params, limit=1)
        return records[0] if records else None

    @classmethod
    def count(
        cls,
        where_clause: Optional[str] = None,
        params: Optional[Dict] = None,
    ) -> int:
        """Count records matching criteria."""
        query = f"SELECT COUNT(*) as count FROM `{cls.table_name}`"
        if where_clause:
            query += f" WHERE {where_clause}"
        result = get_db().execute_query(query, params)
        return result[0]["count"] if result else 0

    @classmethod
    def execute_custom_query(
        cls, query: str, params: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Execute custom SQL query."""
        return get_db().execute_query(query, params)

    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary."""
        return {
            key: value
            for key, value in self.__dict__.items()
            if not key.startswith("_")
        }

    def get_id(self) -> Any:
        """Get primary key value."""
        return getattr(self, self.primary_key, None)

    def __repr__(self) -> str:
        """String representation of model."""
        class_name = self.__class__.__name__
        id_value = self.get_id()
        return f"<{class_name}(id={id_value})>"


# ---------------------------------------------------------------------------
# Colppy MySQL schema models (staging/production)
# See tools/docs/COLPPY_MYSQL_SCHEMA.md for full documentation
# ---------------------------------------------------------------------------


class Empresa(BaseModel):
    """
    Colppy company/empresa. Links to HubSpot via id_empresa (IdEmpresa).
    """

    table_name = "empresa"
    primary_key = "IdEmpresa"

    @classmethod
    def find_by_cuit(cls, cuit: str) -> Optional["Empresa"]:
        """Find empresa by CUIT (11 digits, normalized)."""
        cuit_norm = str(cuit).replace("-", "").strip()
        return cls.find_one("CUIT = :cuit", {"cuit": cuit_norm})

    @classmethod
    def find_by_id_plan(cls, id_plan: int) -> List["Empresa"]:
        """Find empresas by plan ID."""
        return cls.find_all("idPlan = :id_plan", {"id_plan": id_plan})

    @classmethod
    def find_activas(cls, limit: Optional[int] = None) -> List["Empresa"]:
        """Find active empresas (activa != 0; 0=inactive, 2/3=active states)."""
        return cls.find_all("activa != 0", limit=limit)


class Facturacion(BaseModel):
    """
    Colppy billing/facturacion. IdEmpresa links to empresa and HubSpot deals.
    """

    table_name = "facturacion"
    primary_key = "idFacturacion"

    @classmethod
    def find_by_id_empresa(cls, id_empresa: str) -> List["Facturacion"]:
        """Find facturacion rows by id_empresa."""
        return cls.find_all("IdEmpresa = :id_empresa", {"id_empresa": id_empresa})

    @classmethod
    def find_by_cuit(cls, cuit: str) -> List["Facturacion"]:
        """Find facturacion by customer CUIT."""
        cuit_norm = str(cuit).replace("-", "").strip()
        return cls.find_all("CUIT = :cuit", {"cuit": cuit_norm})

    @classmethod
    def find_activas(cls, limit: Optional[int] = None) -> List["Facturacion"]:
        """Find active billing (fechaBaja IS NULL)."""
        return cls.find_all("fechaBaja IS NULL", limit=limit)


class Usuario(BaseModel):
    """Colppy user. Links to empresa via usuario_empresa."""

    table_name = "usuario"
    primary_key = "id"

    @classmethod
    def find_by_email(cls, email: str) -> Optional["Usuario"]:
        """Find user by nombreUsuario (email)."""
        return cls.find_one("nombreUsuario = :email", {"email": email})

    @classmethod
    def find_by_id_ultima_empresa(
        cls, id_empresa: int, limit: Optional[int] = None
    ) -> List["Usuario"]:
        """Find users with given last-used empresa."""
        return cls.find_all(
            "idUltimaEmpresa = :id_empresa",
            {"id_empresa": id_empresa},
            limit=limit,
        )


class UsuarioEmpresa(BaseModel):
    """User–company association (many-to-many)."""

    table_name = "usuario_empresa"
    primary_key = "idUsuarioEmpresa"

    @classmethod
    def find_by_empresa(
        cls, id_empresa: int, limit: Optional[int] = None
    ) -> List["UsuarioEmpresa"]:
        """Find user–empresa links for a company."""
        return cls.find_all(
            "company_id = :id_empresa",
            {"id_empresa": id_empresa},
            limit=limit,
        )

    @classmethod
    def find_by_usuario(
        cls, id_usuario: int, limit: Optional[int] = None
    ) -> List["UsuarioEmpresa"]:
        """Find user–empresa links for a user."""
        return cls.find_all(
            "idUsuario = :id_usuario",
            {"id_usuario": id_usuario},
            limit=limit,
        )


class EmpresasHubspot(BaseModel):
    """HubSpot sync tracking: id_empresa synced to HubSpot."""

    table_name = "empresasHubspot"
    primary_key = "idEmpresa"

    @classmethod
    def find_by_id_empresa(cls, id_empresa: str) -> Optional["EmpresasHubspot"]:
        """Check if empresa is in HubSpot sync."""
        return cls.find_one("idEmpresa = :id_empresa", {"id_empresa": id_empresa})


class CrmMatch(BaseModel):
    """CRM matching: colppy_id ↔ crm_id (HubSpot)."""

    table_name = "crm_match"
    primary_key = "id"

    @classmethod
    def find_by_colppy_id(
        cls, colppy_id: str, table_name: Optional[str] = None
    ) -> List["CrmMatch"]:
        """Find CRM matches by Colppy ID."""
        if table_name:
            return cls.find_all(
                "colppy_id = :colppy_id AND table_name = :table_name",
                {"colppy_id": colppy_id, "table_name": table_name},
            )
        return cls.find_all("colppy_id = :colppy_id", {"colppy_id": colppy_id})

    @classmethod
    def find_by_crm_id(
        cls, crm_id: str, table_name: Optional[str] = None
    ) -> List["CrmMatch"]:
        """Find CRM matches by HubSpot/CRM ID."""
        if table_name:
            return cls.find_all(
                "crm_id = :crm_id AND table_name = :table_name",
                {"crm_id": crm_id, "table_name": table_name},
            )
        return cls.find_all("crm_id = :crm_id", {"crm_id": crm_id})


class Plan(BaseModel):
    """Colppy subscription plan."""

    table_name = "plan"
    primary_key = "idPlan"

    @classmethod
    def find_by_country(cls, country_id: int) -> List["Plan"]:
        """Find plans by country."""
        return cls.find_all("countryId = :country_id", {"country_id": country_id})
