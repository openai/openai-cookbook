"""
ARCA DFE Notifications — SQLite persistence.
Saves notification output so you can access it without re-scraping ARCA.
Update from ARCA only when explicitly requested.
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

def _get_db_path() -> Path:
    """Return DB path from env or default."""
    path = Path(__file__).resolve().parents[2] / "data" / "arca_notifications.db"
    env_path = __import__("os").environ.get("ARCA_DB_PATH")
    if env_path:
        path = Path(env_path)
    return path


def init_db(db_path: Path | None = None) -> None:
    """
    Create tables if they do not exist.
    """
    path = db_path or _get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS arca_notifications (
            id INTEGER NOT NULL,
            cuit TEXT NOT NULL,
            organismo TEXT,
            fecha_publicacion TEXT,
            fecha_vencimiento TEXT,
            fecha_notificacion TEXT,
            sistema INTEGER,
            estado INTEGER,
            prioridad INTEGER,
            tiene_adjunto INTEGER,
            oficio INTEGER,
            tipo INTEGER,
            mensaje_preview TEXT,
            mensaje_completo TEXT,
            clasificacion TEXT,
            sistema_desc TEXT,
            estado_desc TEXT,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (cuit, id)
        );

        CREATE INDEX IF NOT EXISTS idx_arca_notif_cuit ON arca_notifications(cuit);
        CREATE INDEX IF NOT EXISTS idx_arca_notif_fetched ON arca_notifications(fetched_at);

        CREATE TABLE IF NOT EXISTS arca_representados (
            cuit_usuario TEXT NOT NULL,
            cuit_representado TEXT NOT NULL,
            nombre TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (cuit_usuario, cuit_representado)
        );
        CREATE INDEX IF NOT EXISTS idx_arca_rep_usuario ON arca_representados(cuit_usuario);
    """)
    # Add pdf_content column if missing (SQLite has no IF NOT EXISTS for ALTER)
    try:
        conn2 = sqlite3.connect(str(path))
        conn2.execute("ALTER TABLE arca_notifications ADD COLUMN pdf_content BLOB")
        conn2.commit()
        conn2.close()
    except sqlite3.OperationalError:
        pass  # Column already exists


def save_notifications(cuit: str, notifications: list[dict[str, Any]]) -> None:
    """
    Replace all notifications for this CUIT with the new set.
    Called after a successful fetch from ARCA.
    """
    path = _get_db_path()
    init_db(path)

    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    fetched_at = datetime.utcnow().isoformat() + "Z"

    cur.execute("DELETE FROM arca_notifications WHERE cuit = ?", (cuit,))

    for n in notifications:
        pdf_blob = n.get("pdf_content")
        cur.execute(
            """
            INSERT INTO arca_notifications (
                id, cuit, organismo, fecha_publicacion, fecha_vencimiento,
                fecha_notificacion, sistema, estado, prioridad, tiene_adjunto,
                oficio, tipo, mensaje_preview, mensaje_completo, clasificacion,
                sistema_desc, estado_desc, fetched_at, pdf_content
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                n.get("id"),
                cuit,
                n.get("organismo") or "",
                n.get("fecha_publicacion"),
                n.get("fecha_vencimiento"),
                n.get("fecha_notificacion"),
                n.get("sistema"),
                n.get("estado"),
                n.get("prioridad"),
                1 if n.get("tiene_adjunto") else 0,
                1 if n.get("oficio") else 0,
                n.get("tipo"),
                n.get("mensaje_preview") or "",
                n.get("mensaje_completo") or "",
                n.get("clasificacion") or "",
                n.get("sistema_desc"),
                n.get("estado_desc"),
                fetched_at,
                pdf_blob,
            ),
        )

    conn.commit()
    conn.close()


def get_notifications(cuit: str) -> tuple[list[dict[str, Any]], str | None]:
    """
    Read notifications for CUIT from DB.
    Returns (notifications, fetched_at) or ([], None) if no data.
    """
    path = _get_db_path()
    if not path.exists():
        return [], None

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT id, organismo, fecha_publicacion, fecha_vencimiento, fecha_notificacion,
               sistema, estado, prioridad, tiene_adjunto, oficio, tipo,
               mensaje_preview, mensaje_completo, clasificacion, sistema_desc, estado_desc,
               fetched_at
        FROM arca_notifications
        WHERE cuit = ?
        ORDER BY COALESCE(fecha_publicacion, '') DESC, id DESC
        """,
        (cuit,),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return [], None

    notifications = []
    fetched_at = None
    for r in rows:
        fetched_at = fetched_at or r["fetched_at"]
        notifications.append({
            "id": r["id"],
            "organismo": r["organismo"] or "",
            "fecha_publicacion": r["fecha_publicacion"],
            "fecha_vencimiento": r["fecha_vencimiento"],
            "fecha_notificacion": r["fecha_notificacion"],
            "sistema": r["sistema"],
            "estado": r["estado"],
            "prioridad": r["prioridad"],
            "tiene_adjunto": bool(r["tiene_adjunto"]),
            "oficio": bool(r["oficio"]),
            "tipo": r["tipo"],
            "mensaje_preview": r["mensaje_preview"] or "",
            "mensaje_completo": r["mensaje_completo"] or "",
            "clasificacion": r["clasificacion"] or "",
            "sistema_desc": r["sistema_desc"],
            "estado_desc": r["estado_desc"],
        })

    return notifications, fetched_at


def get_pdf(cuit: str, notification_id: int) -> bytes | None:
    """
    Return PDF bytes for a notification, or None if not stored.
    """
    path = _get_db_path()
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(str(path))
        cur = conn.execute(
            "SELECT pdf_content FROM arca_notifications WHERE cuit = ? AND id = ?",
            (cuit, notification_id),
        )
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            return row[0]
    except sqlite3.OperationalError:
        pass  # Column may not exist in older DB
    return None


def save_pdf(cuit: str, notification_id: int, pdf_bytes: bytes) -> bool:
    """
    Store PDF attachment for a notification. The notification must already exist.
    Returns True if updated, False if no matching row.
    """
    path = _get_db_path()
    if not path.exists():
        return False
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        return False
    try:
        conn = sqlite3.connect(str(path))
        cur = conn.execute(
            "UPDATE arca_notifications SET pdf_content = ? WHERE cuit = ? AND id = ?",
            (pdf_bytes, cuit_clean, notification_id),
        )
        updated = cur.rowcount > 0
        conn.commit()
        conn.close()
        return updated
    except sqlite3.OperationalError:
        return False


def save_representados(cuit_usuario: str, representados: list[dict[str, Any]]) -> None:
    """
    Replace representados for this user (CUIT) with the new set.
    Each item: {cuit, nombre}.
    """
    path = _get_db_path()
    init_db(path)
    cuit_clean = "".join(c for c in cuit_usuario if c.isdigit())
    if len(cuit_clean) != 11:
        return
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    fetched_at = datetime.utcnow().isoformat() + "Z"
    cur.execute("DELETE FROM arca_representados WHERE cuit_usuario = ?", (cuit_clean,))
    for r in representados:
        cuit_rep = "".join(c for c in str(r.get("cuit", "")) if c.isdigit())
        if len(cuit_rep) != 11:
            continue
        cur.execute(
            "INSERT INTO arca_representados (cuit_usuario, cuit_representado, nombre, fetched_at) VALUES (?, ?, ?, ?)",
            (cuit_clean, cuit_rep, r.get("nombre", "") or r.get("name", ""), fetched_at),
        )
    conn.commit()
    conn.close()


def get_representados(cuit_usuario: str) -> list[dict[str, Any]]:
    """
    Read representados for user from DB.
    Returns list of {cuit, nombre}.
    """
    path = _get_db_path()
    if not path.exists():
        return []
    cuit_clean = "".join(c for c in cuit_usuario if c.isdigit())
    if len(cuit_clean) != 11:
        return []
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT cuit_representado, nombre FROM arca_representados WHERE cuit_usuario = ? ORDER BY nombre",
            (cuit_clean,),
        )
        rows = cur.fetchall()
        conn.close()
        return [{"cuit": r["cuit_representado"], "nombre": r["nombre"] or ""} for r in rows]
    except sqlite3.OperationalError:
        return []


# ──────────────────────────────────────────────────────────────────────────────
# Comprobantes (Recibidos & Emitidos)
# v3 schema: keyed by cuit_representado (the entity that owns the comprobante)
# ──────────────────────────────────────────────────────────────────────────────

def _init_comprobantes_table(db_path: Path | None = None) -> None:
    """Create the comprobantes table if it doesn't exist (v3 with cuit_representado)."""
    path = db_path or _get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))

    # Auto-migrate: drop old table versions (v1 without direccion, v2 without cuit_representado).
    # Safe because this is a cache — data can be re-fetched from ARCA.
    try:
        cur = conn.execute("PRAGMA table_info(arca_comprobantes)")
        cols = {row[1] for row in cur.fetchall()}
        if cols and "cuit_representado" not in cols:
            conn.execute("DROP TABLE arca_comprobantes")
            conn.execute("DROP INDEX IF EXISTS idx_arca_comp_cuit")
            conn.execute("DROP INDEX IF EXISTS idx_arca_comp_fecha")
            conn.execute("DROP INDEX IF EXISTS idx_arca_comp_dir")
            conn.commit()
    except sqlite3.OperationalError:
        pass

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS arca_comprobantes (
            cuit_representado TEXT NOT NULL,
            direccion TEXT NOT NULL DEFAULT 'R',
            fecha_emision TEXT,
            tipo_comprobante_codigo INTEGER,
            tipo_comprobante TEXT,
            punto_venta INTEGER,
            numero_desde INTEGER,
            numero_hasta INTEGER,
            numero TEXT,
            cod_autorizacion TEXT,
            tipo_doc_contraparte TEXT,
            cuit_contraparte TEXT,
            denominacion_contraparte TEXT,
            moneda TEXT,
            importe_total REAL,
            importe_total_display TEXT,
            fecha_emision_display TEXT,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (cuit_representado, direccion, tipo_comprobante_codigo, punto_venta, numero_desde)
        );
        CREATE INDEX IF NOT EXISTS idx_arca_comp_repr ON arca_comprobantes(cuit_representado);
        CREATE INDEX IF NOT EXISTS idx_arca_comp_fecha ON arca_comprobantes(fecha_emision);
        CREATE INDEX IF NOT EXISTS idx_arca_comp_dir ON arca_comprobantes(direccion);
    """)

    # v4 migration: add tax breakdown columns (forward-only, nullable)
    _tax_cols = ["tipo_cambio", "neto_gravado", "neto_no_gravado", "exento", "iva_total", "otros_tributos"]
    cur = conn.execute("PRAGMA table_info(arca_comprobantes)")
    existing = {row[1] for row in cur.fetchall()}
    for col in _tax_cols:
        if col not in existing:
            conn.execute(f"ALTER TABLE arca_comprobantes ADD COLUMN {col} REAL")
    conn.commit()
    conn.close()


def save_comprobantes(
    cuit_representado: str,
    comprobantes: list[dict[str, Any]],
    direccion: str = "R",
) -> None:
    """
    Save comprobantes for a specific entity (representado). Uses INSERT OR REPLACE.
    cuit_representado: the CUIT of the entity that owns these comprobantes.
    direccion: "R" = recibidos, "E" = emitidos.
    """
    path = _get_db_path()
    _init_comprobantes_table(path)
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    fetched_at = datetime.utcnow().isoformat() + "Z"

    for c in comprobantes:
        cur.execute(
            """
            INSERT OR REPLACE INTO arca_comprobantes (
                cuit_representado, direccion, fecha_emision, tipo_comprobante_codigo,
                tipo_comprobante, punto_venta, numero_desde, numero_hasta, numero,
                cod_autorizacion, tipo_doc_contraparte, cuit_contraparte,
                denominacion_contraparte, moneda, importe_total, importe_total_display,
                fecha_emision_display, fetched_at,
                tipo_cambio, neto_gravado, neto_no_gravado, exento, iva_total, otros_tributos
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cuit_representado,
                direccion,
                c.get("fecha_emision"),
                c.get("tipo_comprobante_codigo"),
                c.get("tipo_comprobante"),
                c.get("punto_venta"),
                c.get("numero_desde"),
                c.get("numero_hasta"),
                c.get("numero"),
                c.get("cod_autorizacion"),
                c.get("tipo_doc_contraparte"),
                c.get("cuit_contraparte"),
                c.get("denominacion_contraparte"),
                c.get("moneda"),
                c.get("importe_total"),
                c.get("importe_total_display"),
                c.get("fecha_emision_display"),
                fetched_at,
                c.get("tipo_cambio"),
                c.get("neto_gravado"),
                c.get("neto_no_gravado"),
                c.get("exento"),
                c.get("iva_total"),
                c.get("otros_tributos"),
            ),
        )

    conn.commit()
    conn.close()


def get_comprobantes(
    cuit_representado: str,
    direccion: str = "R",
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Read comprobantes from DB filtered by entity, direccion (R/E), and optional date range.
    Returns (comprobantes, fetched_at) or ([], None).
    """
    path = _get_db_path()
    if not path.exists():
        return [], None

    _init_comprobantes_table(path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    query = """
        SELECT fecha_emision, fecha_emision_display, tipo_comprobante_codigo,
               tipo_comprobante, punto_venta, numero_desde, numero_hasta,
               numero, cod_autorizacion, tipo_doc_contraparte, cuit_contraparte,
               denominacion_contraparte, moneda, importe_total, importe_total_display,
               fetched_at,
               tipo_cambio, neto_gravado, neto_no_gravado, exento, iva_total, otros_tributos
        FROM arca_comprobantes
        WHERE cuit_representado = ? AND direccion = ?
    """
    params: list[Any] = [cuit_representado, direccion]

    if fecha_desde:
        query += " AND fecha_emision >= ?"
        params.append(fecha_desde)
    if fecha_hasta:
        query += " AND fecha_emision <= ?"
        params.append(fecha_hasta)

    query += " ORDER BY fecha_emision DESC, numero_desde DESC"

    cur = conn.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return [], None

    comprobantes = []
    fetched_at = None
    for r in rows:
        fetched_at = fetched_at or r["fetched_at"]
        comprobantes.append({
            "fecha_emision": r["fecha_emision"],
            "fecha_emision_display": r["fecha_emision_display"],
            "tipo_comprobante_codigo": r["tipo_comprobante_codigo"],
            "tipo_comprobante": r["tipo_comprobante"],
            "punto_venta": r["punto_venta"],
            "numero_desde": r["numero_desde"],
            "numero_hasta": r["numero_hasta"],
            "numero": r["numero"],
            "cod_autorizacion": r["cod_autorizacion"],
            "tipo_doc_contraparte": r["tipo_doc_contraparte"],
            "cuit_contraparte": r["cuit_contraparte"],
            "denominacion_contraparte": r["denominacion_contraparte"],
            "moneda": r["moneda"],
            "importe_total": r["importe_total"],
            "importe_total_display": r["importe_total_display"],
            # Tax breakdown (v4 migration — nullable for older cache)
            "tipo_cambio": r["tipo_cambio"],
            "neto_gravado": r["neto_gravado"],
            "neto_no_gravado": r["neto_no_gravado"],
            "exento": r["exento"],
            "iva_total": r["iva_total"],
            "otros_tributos": r["otros_tributos"],
        })

    return comprobantes, fetched_at


def delete_comprobantes(
    cuit_representado: str,
    direccion: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> int:
    """
    Delete cached comprobantes from SQLite.  Returns the number of rows deleted.

    Filters:
      - cuit_representado (required)
      - direccion: "R" or "E" (optional — if None, deletes both)
      - fecha_desde / fecha_hasta: date range (optional)
    """
    path = _get_db_path()
    if not path.exists():
        return 0

    conn = sqlite3.connect(str(path))
    query = "DELETE FROM arca_comprobantes WHERE cuit_representado = ?"
    params: list[Any] = [cuit_representado]

    if direccion:
        query += " AND direccion = ?"
        params.append(direccion)
    if fecha_desde:
        query += " AND fecha_emision >= ?"
        params.append(fecha_desde)
    if fecha_hasta:
        query += " AND fecha_emision <= ?"
        params.append(fecha_hasta)

    cur = conn.execute(query, params)
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


def get_last_fetched(cuit: str) -> str | None:
    """Return last fetch timestamp for CUIT, or None."""
    path = _get_db_path()
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    cur = conn.execute(
        "SELECT fetched_at FROM arca_notifications WHERE cuit = ? LIMIT 1",
        (cuit,),
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


# ──────────────────────────────────────────────────────────────────────────────
# Retenciones / Percepciones (from ARCA Mis Retenciones / Mirequa)
# ──────────────────────────────────────────────────────────────────────────────

def _init_retenciones_table(db_path: Path | None = None) -> None:
    """Create the retenciones table if it doesn't exist."""
    path = db_path or _get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS arca_retenciones (
            cuit_representado TEXT NOT NULL,
            numero_certificado TEXT NOT NULL,
            cuit_agente_retencion TEXT,
            impuesto_retenido INTEGER,
            codigo_regimen INTEGER,
            fecha_retencion TEXT,
            descripcion_operacion TEXT,
            importe_retenido REAL,
            numero_comprobante TEXT,
            fecha_comprobante TEXT,
            descripcion_comprobante TEXT,
            fecha_ingreso TEXT,
            cod_seguridad TEXT,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (cuit_representado, numero_certificado)
        );
        CREATE INDEX IF NOT EXISTS idx_arca_ret_cuit ON arca_retenciones(cuit_representado);
        CREATE INDEX IF NOT EXISTS idx_arca_ret_fecha ON arca_retenciones(fecha_retencion);
        CREATE INDEX IF NOT EXISTS idx_arca_ret_agente ON arca_retenciones(cuit_agente_retencion);
    """)
    conn.commit()
    conn.close()


def save_retenciones(
    cuit_representado: str,
    retenciones: list[dict[str, Any]],
) -> None:
    """
    Save retenciones for a specific entity (representado). Uses INSERT OR REPLACE.
    Accepts the raw JSON format from Mirequa API (camelCase fields).
    """
    path = _get_db_path()
    _init_retenciones_table(path)
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    fetched_at = datetime.utcnow().isoformat() + "Z"

    for r in retenciones:
        cur.execute(
            """
            INSERT OR REPLACE INTO arca_retenciones (
                cuit_representado, numero_certificado, cuit_agente_retencion,
                impuesto_retenido, codigo_regimen, fecha_retencion,
                descripcion_operacion, importe_retenido, numero_comprobante,
                fecha_comprobante, descripcion_comprobante, fecha_ingreso,
                cod_seguridad, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cuit_representado,
                str(r.get("numeroCertificado", "")),
                str(r.get("cuitAgenteRetencion", "")),
                r.get("impuestoRetenido"),
                r.get("codigoRegimen"),
                r.get("fechaRetencion"),
                r.get("descripcionOperacion"),
                r.get("importeRetenido"),
                r.get("numeroComprobante"),
                r.get("fechaComprobante"),
                r.get("descripcionComprobante"),
                r.get("fechaIngreso"),
                r.get("codSeguridad"),
                fetched_at,
            ),
        )

    conn.commit()
    conn.close()


def get_retenciones(
    cuit_representado: str,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Read retenciones from DB filtered by entity and optional ISO date range.
    Returns dicts in the original Mirequa camelCase format for compatibility.
    Returns (retenciones, fetched_at) or ([], None).
    """
    path = _get_db_path()
    if not path.exists():
        return [], None

    _init_retenciones_table(path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    query = """
        SELECT numero_certificado, cuit_agente_retencion, impuesto_retenido,
               codigo_regimen, fecha_retencion, descripcion_operacion,
               importe_retenido, numero_comprobante, fecha_comprobante,
               descripcion_comprobante, fecha_ingreso, cod_seguridad,
               fetched_at
        FROM arca_retenciones
        WHERE cuit_representado = ?
    """
    params: list[Any] = [cuit_representado]

    if fecha_desde:
        query += " AND fecha_retencion >= ?"
        params.append(fecha_desde)
    if fecha_hasta:
        # Add T23:59:59 to include the full day
        query += " AND fecha_retencion <= ?"
        params.append(fecha_hasta + "T23:59:59" if "T" not in fecha_hasta else fecha_hasta)

    query += " ORDER BY fecha_retencion DESC, numero_certificado DESC"

    cur = conn.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return [], None

    retenciones = []
    fetched_at = None
    for r in rows:
        fetched_at = fetched_at or r["fetched_at"]
        retenciones.append({
            "numeroCertificado": r["numero_certificado"],
            "cuitAgenteRetencion": int(r["cuit_agente_retencion"]) if r["cuit_agente_retencion"].isdigit() else r["cuit_agente_retencion"],
            "impuestoRetenido": r["impuesto_retenido"],
            "codigoRegimen": r["codigo_regimen"],
            "fechaRetencion": r["fecha_retencion"],
            "descripcionOperacion": r["descripcion_operacion"],
            "importeRetenido": r["importe_retenido"],
            "numeroComprobante": r["numero_comprobante"],
            "fechaComprobante": r["fecha_comprobante"],
            "descripcionComprobante": r["descripcion_comprobante"],
            "fechaIngreso": r["fecha_ingreso"],
            "codSeguridad": r["cod_seguridad"],
        })

    return retenciones, fetched_at


def delete_retenciones(cuit_representado: str) -> int:
    """Delete all cached retenciones for a representado. Returns count deleted."""
    path = _get_db_path()
    if not path.exists():
        return 0
    _init_retenciones_table(path)
    conn = sqlite3.connect(str(path))
    cur = conn.execute(
        "DELETE FROM arca_retenciones WHERE cuit_representado = ?",
        (cuit_representado,),
    )
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


# ──────────────────────────────────────────────────────────────────────────────
# Reconciliation Acknowledgments
# ──────────────────────────────────────────────────────────────────────────────


def _init_acknowledgments_table(db_path: Path | None = None) -> None:
    """Create the reconciliation_acknowledgments table if it doesn't exist."""
    path = db_path or _get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS reconciliation_acknowledgments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discrepancy_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'revisado',
            reason TEXT NOT NULL DEFAULT '',
            acknowledged_by TEXT NOT NULL DEFAULT '',
            acknowledged_at TEXT NOT NULL,
            context_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_recon_ack_key
            ON reconciliation_acknowledgments(discrepancy_key);
        CREATE INDEX IF NOT EXISTS idx_recon_ack_status
            ON reconciliation_acknowledgments(status);
    """)
    conn.commit()
    conn.close()


def save_acknowledgment(
    discrepancy_key: str,
    status: str,
    category: str = "revisado",
    reason: str = "",
    acknowledged_by: str = "",
    context_json: str | None = None,
) -> int:
    """
    Create or update an acknowledgment. Uses INSERT OR REPLACE on the
    UNIQUE discrepancy_key, so re-acknowledging updates the existing record.
    Returns the row id.
    """
    path = _get_db_path()
    _init_acknowledgments_table(path)
    conn = sqlite3.connect(str(path))
    now = datetime.utcnow().isoformat() + "Z"
    cur = conn.execute(
        """
        INSERT OR REPLACE INTO reconciliation_acknowledgments (
            discrepancy_key, status, category, reason,
            acknowledged_by, acknowledged_at, context_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            discrepancy_key, status, category, reason,
            acknowledged_by, now, context_json,
            now, now,
        ),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_acknowledgments(status_filter: str | None = None) -> list[dict[str, Any]]:
    """Return all acknowledgments, optionally filtered by discrepancy status."""
    path = _get_db_path()
    if not path.exists():
        return []
    _init_acknowledgments_table(path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    query = "SELECT * FROM reconciliation_acknowledgments"
    params: list[Any] = []
    if status_filter:
        query += " WHERE status = ?"
        params.append(status_filter)
    query += " ORDER BY acknowledged_at DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_acknowledgment(discrepancy_key: str) -> int:
    """Delete an acknowledgment by key. Returns count deleted (0 or 1)."""
    path = _get_db_path()
    if not path.exists():
        return 0
    _init_acknowledgments_table(path)
    conn = sqlite3.connect(str(path))
    cur = conn.execute(
        "DELETE FROM reconciliation_acknowledgments WHERE discrepancy_key = ?",
        (discrepancy_key,),
    )
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


# ──────────────────────────────────────────────────────────────────────────────
# Banco Galicia — Bank transactions
# ──────────────────────────────────────────────────────────────────────────────

def _init_banco_table(db_path: Path | None = None) -> None:
    """Create the banco_transactions table if it doesn't exist."""
    path = db_path or _get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS banco_transactions (
            account TEXT NOT NULL,
            fecha TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            monto REAL NOT NULL,
            row_seq INTEGER NOT NULL DEFAULT 0,
            balance REAL,
            referencia TEXT,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (account, fecha, descripcion, monto, row_seq)
        );
        CREATE INDEX IF NOT EXISTS idx_banco_fecha ON banco_transactions(fecha);
        CREATE INDEX IF NOT EXISTS idx_banco_account ON banco_transactions(account);
    """)
    conn.commit()
    conn.close()


def save_banco_transactions(
    account: str,
    transactions: list[dict[str, Any]],
) -> int:
    """
    Save bank transactions. Uses INSERT OR IGNORE to avoid duplicates.
    Each transaction dict should have: date, description, amount, and optionally balance, reference.
    Returns number of new records inserted.
    """
    path = _get_db_path()
    _init_banco_table(path)
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    fetched_at = datetime.utcnow().isoformat() + "Z"
    inserted = 0

    # Group by (date, description, amount) to assign row_seq for duplicates
    from collections import Counter
    seen: Counter = Counter()

    for t in transactions:
        fecha_raw = t.get("date", "")
        # Convert DD/MM/YYYY → YYYY-MM-DD for correct sorting
        if "/" in fecha_raw and len(fecha_raw) == 10:
            parts = fecha_raw.split("/")
            if len(parts) == 3:
                fecha = f"{parts[2]}-{parts[1]}-{parts[0]}"
            else:
                fecha = fecha_raw
        else:
            fecha = fecha_raw
        desc = t.get("description", "")
        amount = t.get("amount", 0)
        key = (fecha, desc, amount)
        seq = seen[key]
        seen[key] += 1

        try:
            cur.execute(
                """
                INSERT OR IGNORE INTO banco_transactions
                    (account, fecha, descripcion, monto, row_seq, balance, referencia, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account,
                    fecha,
                    desc,
                    amount,
                    seq,
                    t.get("balance"),
                    t.get("reference"),
                    fetched_at,
                ),
            )
            if cur.rowcount > 0:
                inserted += 1
        except sqlite3.IntegrityError:
            pass  # Duplicate, skip

    conn.commit()
    conn.close()
    return inserted


def get_banco_transactions(
    account: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Read bank transactions from DB filtered by account and optional ISO date range.
    Dates stored as YYYY-MM-DD in DB. Returns DD/MM/YYYY in the response for display.
    Returns (transactions, fetched_at) or ([], None).
    """
    path = _get_db_path()
    if not path.exists():
        return [], None

    _init_banco_table(path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    query = "SELECT account, fecha, descripcion, monto, balance, referencia, fetched_at FROM banco_transactions WHERE 1=1"
    params: list[Any] = []

    if account:
        query += " AND account = ?"
        params.append(account)
    if fecha_desde:
        query += " AND fecha >= ?"
        params.append(fecha_desde)
    if fecha_hasta:
        query += " AND fecha <= ?"
        params.append(fecha_hasta)

    query += " ORDER BY fecha DESC, rowid DESC"

    cur = conn.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return [], None

    transactions = []
    fetched_at = None
    for r in rows:
        fetched_at = fetched_at or r["fetched_at"]
        # Convert YYYY-MM-DD back to DD/MM/YYYY for display
        fecha_iso = r["fecha"]
        if "-" in fecha_iso and len(fecha_iso) == 10:
            parts = fecha_iso.split("-")
            fecha_display = f"{parts[2]}/{parts[1]}/{parts[0]}"
        else:
            fecha_display = fecha_iso
        transactions.append({
            "account": r["account"],
            "date": fecha_display,
            "date_iso": fecha_iso,
            "description": r["descripcion"],
            "amount": r["monto"],
            "balance": r["balance"],
            "reference": r["referencia"],
        })

    return transactions, fetched_at


def delete_banco_transactions(account: str | None = None) -> int:
    """Delete cached bank transactions. If account is None, deletes all."""
    path = _get_db_path()
    if not path.exists():
        return 0
    _init_banco_table(path)
    conn = sqlite3.connect(str(path))
    if account:
        cur = conn.execute("DELETE FROM banco_transactions WHERE account = ?", (account,))
    else:
        cur = conn.execute("DELETE FROM banco_transactions")
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count
