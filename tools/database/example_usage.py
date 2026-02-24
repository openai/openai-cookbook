"""
Example usage of the database package for Colppy MySQL.
Shows how to use models and queries for empresa, facturacion, usuario, etc.
"""

from database import (
    get_db,
    Empresa,
    Facturacion,
    Usuario,
    Plan,
    CrmMatch,
    QueryBuilder,
)
from database.query_builder import JoinType


def example_basic_usage():
    """Basic database operations."""
    db = get_db()
    print("Testing database connection...")
    if db.test_connection():
        print("Database connected successfully!")

    tables = db.list_tables()
    print(f"\nAvailable tables: {len(tables)}")
    print("Key tables: empresa, facturacion, usuario, plan, crm_match, empresasHubspot")


def example_empresa_queries():
    """Empresa (company) model examples."""
    print("\n--- Empresa examples ---")

    # By ID
    e = Empresa.find_by_id(100)
    if e:
        print(f"Empresa 100: {e.Nombre} | CUIT: {e.CUIT}")

    # Active empresas (limit 5)
    empresas = Empresa.find_activas(limit=5)
    print(f"Sample active empresas: {[(x.IdEmpresa, x.Nombre) for x in empresas]}")

    # Count
    total = Empresa.count()
    activas = Empresa.count("activa != 0")
    print(f"Total: {total}, Active: {activas}")


def example_facturacion_queries():
    """Facturacion (billing) model examples."""
    print("\n--- Facturacion examples ---")

    count = Facturacion.count()
    print(f"Total facturacion rows: {count}")

    activas = Facturacion.find_activas(limit=3)
    print(f"Sample active billing: {[(x.IdEmpresa, x.razonSocial) for x in activas]}")


def example_plan_queries():
    """Plan model examples."""
    print("\n--- Plan examples ---")

    plans = Plan.find_all(limit=5)
    for p in plans:
        print(f"  {p.idPlan}: {p.nombre} | precio: {p.precio}")


def example_query_builder():
    """Query builder with Colppy tables."""
    print("\n--- Query Builder ---")

    results = (
        QueryBuilder()
        .select("e.IdEmpresa", "e.Nombre", "e.CUIT", "p.nombre as plan_nombre")
        .from_table("empresa e")
        .join("plan p", "e.idPlan = p.idPlan", join_type=JoinType.LEFT)
        .where("e.activa != 0")
        .limit(5)
        .execute()
    )
    print(f"Empresa + Plan join: {len(results)} rows")
    for r in results[:3]:
        print(f"  {r}")


if __name__ == "__main__":
    """
    Run examples. Requires tools/.env with DB_HOST, DB_USER, DB_PASSWORD.
    """
    try:
        example_basic_usage()
        example_empresa_queries()
        example_facturacion_queries()
        example_plan_queries()
        example_query_builder()
        print("\nAll examples completed successfully!")
    except Exception as e:
        print(f"Error: {e}")
        print("Ensure tools/.env has correct database credentials.")
