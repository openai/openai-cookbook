"""
Schema and DB init for facturacion–HubSpot mapping.
"""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    cuit                TEXT,
    cuit_display        TEXT,
    hubspot_id          TEXT,
    name                TEXT,
    type                TEXT,
    tipo_icp_contador   TEXT,
    PRIMARY KEY (cuit, hubspot_id)
);

CREATE TABLE IF NOT EXISTS deals (
    id_empresa      TEXT PRIMARY KEY,
    hubspot_id      TEXT,
    deal_name       TEXT,
    deal_stage      TEXT,
    amount          TEXT,
    close_date      TEXT,
    id_plan         TEXT,
    fecha_primer_pago TEXT,
    deal_type       TEXT,
    plan_name       TEXT
);

CREATE TABLE IF NOT EXISTS facturacion (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT,
    customer_cuit   TEXT,
    plan            TEXT,
    id_plan         TEXT,
    amount          TEXT,
    product_cuit    TEXT,
    id_empresa      TEXT,
    self_billed     INTEGER DEFAULT 0,
    FOREIGN KEY (customer_cuit) REFERENCES companies(cuit),
    FOREIGN KEY (id_empresa)    REFERENCES deals(id_empresa)
);

CREATE TABLE IF NOT EXISTS deal_associations (
    deal_hubspot_id     TEXT,
    company_hubspot_id  TEXT,
    association_type_id INTEGER,
    association_category TEXT,
    PRIMARY KEY (deal_hubspot_id, company_hubspot_id, association_type_id)
);

CREATE INDEX IF NOT EXISTS idx_facturacion_cuit ON facturacion(customer_cuit);
CREATE INDEX IF NOT EXISTS idx_facturacion_id_empresa ON facturacion(id_empresa);
CREATE INDEX IF NOT EXISTS idx_companies_hubspot_id ON companies(hubspot_id);
CREATE INDEX IF NOT EXISTS idx_deals_hubspot_id ON deals(hubspot_id);

CREATE TABLE IF NOT EXISTS deals_any_stage (
    id_empresa      TEXT PRIMARY KEY,
    hubspot_id      TEXT,
    deal_name       TEXT,
    deal_stage      TEXT,
    amount          TEXT,
    close_date      TEXT,
    id_plan         TEXT,
    fecha_primer_pago TEXT,
    deal_type       TEXT,
    plan_name       TEXT
);
CREATE INDEX IF NOT EXISTS idx_deals_any_stage_hubspot_id ON deals_any_stage(hubspot_id);

CREATE INDEX IF NOT EXISTS idx_deal_assoc_deal ON deal_associations(deal_hubspot_id);
CREATE INDEX IF NOT EXISTS idx_deal_assoc_company ON deal_associations(company_hubspot_id);

CREATE TABLE IF NOT EXISTS edit_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    script          TEXT NOT NULL,
    action          TEXT NOT NULL,
    outcome         TEXT NOT NULL,
    detail          TEXT,
    deal_id         TEXT,
    deal_name       TEXT,
    deal_url        TEXT,
    company_id      TEXT,
    company_name    TEXT,
    company_url     TEXT,
    company_id_secondary TEXT,
    customer_cuit   TEXT
);

CREATE INDEX IF NOT EXISTS idx_edit_logs_script ON edit_logs(script);
CREATE INDEX IF NOT EXISTS idx_edit_logs_timestamp ON edit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_edit_logs_deal ON edit_logs(deal_id);

CREATE TABLE IF NOT EXISTS reconciliation_logs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT NOT NULL,
    script              TEXT NOT NULL,
    reconciliation_type TEXT NOT NULL,
    period              TEXT,
    match_count         INTEGER NOT NULL,
    source_a_total      INTEGER NOT NULL,
    source_b_total      INTEGER NOT NULL,
    source_a_only_count INTEGER NOT NULL,
    source_b_only_count INTEGER NOT NULL,
    match_ids           TEXT,
    source_a_only_ids   TEXT,
    source_b_only_ids   TEXT,
    source_metadata     TEXT,
    extra               TEXT
);
CREATE INDEX IF NOT EXISTS idx_recon_logs_script ON reconciliation_logs(script);
CREATE INDEX IF NOT EXISTS idx_recon_logs_type ON reconciliation_logs(reconciliation_type);
CREATE INDEX IF NOT EXISTS idx_recon_logs_timestamp ON reconciliation_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_recon_logs_period ON reconciliation_logs(period);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    """Create or open database and apply schema."""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn
