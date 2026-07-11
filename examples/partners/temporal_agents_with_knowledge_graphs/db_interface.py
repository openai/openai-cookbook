import os
import sqlite3
import uuid
from typing import Any

import pandas as pd

from models import Entity, TemporalEvent
from utils import safe_iso


def make_connection(
    db_path: str = "my_database.db",
    memory: bool = False,
    refresh: bool = False,
) -> sqlite3.Connection:
    """Make a connection to the database.

    Args:
        db_path (str, optional): The path to the database file. Defaults to "my_database.db".
        memory (bool, optional): Whether to create a memory database. Defaults to False.
        refresh (bool, optional): Whether to refresh the database. Defaults to False.
    Returns:
        sqlite3.Connection: The database connection.
    """
    if not memory and refresh:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except PermissionError as e:
                raise RuntimeError(
                    "Could not delete the database file. Please ensure all connections are closed."
                ) from e
    conn = sqlite3.connect(":memory:") if memory else sqlite3.connect(db_path)
    if memory and refresh:
        _drop_all_tables(conn)
    _create_lite_tables(conn)
    return conn


def _drop_all_tables(conn: sqlite3.Connection, tables: list[str] | None = None) -> None:
    """Drop all tables in the database.

    Args:
        conn (sqlite3.Connection): The database connection.
    """
    c = conn.cursor()
    if not tables:
        c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        )
        tables = [row[0] for row in c.fetchall()]
    for table in tables:
        c.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()


def _create_lite_tables(conn: sqlite3.Connection) -> None:
    """Create all tables for the database if they do not exist.

    Args:
        conn (sqlite3.Connection): The database connection.
    """
    c = conn.cursor()

    c.execute(
        """
    CREATE TABLE IF NOT EXISTS transcripts (
        id BLOB PRIMARY KEY,
        text TEXT,
        company TEXT,
        date TEXT,
        quarter TEXT
    )
    """
    )

    c.execute(
        """
    CREATE TABLE IF NOT EXISTS chunks (
        id BLOB PRIMARY KEY,
        transcript_id BLOB,
        text TEXT,
        metadata TEXT,
        FOREIGN KEY(transcript_id) REFERENCES transcripts(id)
    )
    """
    )
    c.execute(
        """CREATE INDEX IF NOT EXISTS idx_chunks_transcript_id ON chunks (transcript_id)"""
    )

    c.execute(
        """
    CREATE TABLE IF NOT EXISTS events (
        id BLOB PRIMARY KEY,
        chunk_id BLOB,
        statement TEXT,
        triplets TEXT,
        statement_type TEXT,
        temporal_type TEXT,
        created_at TEXT,
        valid_at TEXT,
        expired_at TEXT,
        invalid_at TEXT,
        invalidated_by BLOB,
        embedding BLOB,
        FOREIGN KEY(chunk_id) REFERENCES chunks(id),
        FOREIGN KEY(invalidated_by) REFERENCES events(id)
    )
    """
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_chunk_id ON events (chunk_id)")

    c.execute(
        """
    CREATE TABLE IF NOT EXISTS triplets (
        id BLOB PRIMARY KEY,
        event_id BLOB,
        subject_name TEXT,
        subject_id BLOB,
        predicate TEXT,
        object_name TEXT,
        object_id BLOB,
        value TEXT,
        FOREIGN KEY(event_id) REFERENCES events(id)
    )
    """
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_triplets_event_id ON triplets (event_id)")

    c.execute(
        """
    CREATE TABLE IF NOT EXISTS entities (
        id BLOB PRIMARY KEY,
        event_id BLOB,
        name TEXT,
        type TEXT,
        description TEXT,
        resolved_id BLOB,
        FOREIGN KEY(event_id) REFERENCES events(id),
        FOREIGN KEY(resolved_id) REFERENCES entities(id)
    )
    """
    )

    conn.commit()


def view_db_table(
    conn: sqlite3.Connection, table_name: str, max_rows: int | None = None
) -> pd.DataFrame:
    """View a table in the database as a pandas DataFrame.

    Args:
        conn (sqlite3.Connection): The database connection.
        table_name (str): The name of the table to view.
        max_rows (int, optional): Maximum number of rows to return. Defaults to 10.

    Returns:
        pd.DataFrame: The table data as a DataFrame.
    """
    if max_rows:
        query = f"SELECT * FROM {table_name} LIMIT {max_rows}"
    else:
        query = f"SELECT * FROM {table_name}"
    return pd.read_sql_query(query, conn)


def insert_transcript(conn: sqlite3.Connection, transcript: dict[str, Any]) -> None:
    """Insert a transcript into the database.

    Args:
        conn (sqlite3.Connection): The database connection.
        transcript (dict[str, Any]): The transcript to insert.
    """
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO transcripts
        (id, text, company, date, quarter)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            transcript["id"],
            transcript["text"],
            transcript["company"],
            transcript["date"].isoformat(),
            transcript.get("quarter"),
        ),
    )


def insert_chunk(conn: sqlite3.Connection, chunk: dict[str, Any]) -> None:
    """Insert a chunk into the database.

    Args:
        conn (sqlite3.Connection): The database connection.
        chunk (dict[str, Any]): The chunk to insert.
    """
    c = conn.cursor()
    c.execute(
        "INSERT INTO chunks (id, transcript_id, text, metadata) VALUES (?, ?, ?, ?)",
        (chunk["id"], chunk["transcript_id"], chunk["text"], chunk.get("metadata")),
    )


# ======================
# TRIPLET INTERACTIONS
# ======================


def insert_triplet(conn: sqlite3.Connection, triplet: dict[str, Any]) -> None:
    """Insert a triplet with both names and resolved IDs."""
    conn.execute(
        """
        INSERT INTO triplets
        (id, event_id, subject_name, subject_id, predicate, object_name, object_id, value)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            triplet["id"],
            triplet["event_id"],
            triplet["subject_name"],
            triplet.get("subject_id"),
            triplet["predicate"],
            triplet["object_name"],
            triplet.get("object_id"),
            triplet.get("value"),
        ),
    )


def get_all_triplets(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Get all triplets with both names and resolved IDs."""
    c = conn.cursor()
    c.execute(
        """
        SELECT
            id, event_id,
            subject_name, subject_id,
            predicate,
            object_name, object_id,
            value
        FROM triplets
    """
    )
    return [
        {
            "id": row[0],
            "event_id": row[1],
            "subject_name": row[2],
            "subject_id": row[3],
            "predicate": row[4],
            "object_name": row[5],
            "object_id": row[6],
            "value": row[7],
        }
        for row in c.fetchall()
    ]


def get_all_unique_predicates(conn: sqlite3.Connection) -> list[str]:
    """Get all unique predicates from the triplets table.

    Args:
        conn (sqlite3.Connection): The database connection.

    Returns:
        list[str]: List of unique predicates.
    """
    c = conn.cursor()
    c.execute("SELECT DISTINCT predicate FROM triplets")
    rows = c.fetchall()
    return [row[0] for row in rows]


# =====================
# ENTITY INTERACTIONS
# =====================


def insert_entity(conn: sqlite3.Connection, entity: dict[str, Any]) -> None:
    """Insert an entity into the database.

    Args:
        conn (sqlite3.Connection): The database connection.
        entity (dict[str, Any]): The entity to insert.
    """
    c = conn.cursor()
    c.execute(
        """
              INSERT OR IGNORE INTO entities (id, name, type, description)
              VALUES (?, ?, ?, ?)""",
        (entity["id"], entity["name"], entity.get("type"), entity.get("description")),
    )


def get_all_canonical_entities(conn: sqlite3.Connection) -> list[Entity]:
    """
    Get all canonical entities from the entities table.
    Returns a list of dicts with id, name, type, and description.
    """
    c = conn.cursor()
    c.execute("SELECT id, name, type, description FROM entities")
    rows = c.fetchall()
    return [
        Entity(
            id=uuid.UUID(row[0]),
            name=row[1],
            type=row[2] or "",
            description=row[3] or "",
        )
        for row in rows
    ]


def insert_canonical_entity(conn: sqlite3.Connection, entity: dict[str, Any]) -> None:
    """
    Insert a new canonical entity into the entities table.
    entity: dict with keys 'id', 'name', 'type', 'description'.
    """
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO entities (id, name, type, description) VALUES (?, ?, ?, ?)",
        (entity["id"], entity["name"], entity.get("type"), entity.get("description")),
    )


def update_entity_references(
    conn: sqlite3.Connection, old_id: str, new_id: str
) -> None:
    """
    Update all references from old_id to new_id in the database.
    """
    conn.execute(
        "UPDATE entities SET resolved_id = ? WHERE resolved_id = ?", (new_id, old_id)
    )
    conn.execute(
        "UPDATE triplets SET subject_id = ? WHERE subject_id = ?", (new_id, old_id)
    )
    conn.execute(
        "UPDATE triplets SET object_id = ? WHERE object_id = ?", (new_id, old_id)
    )
    conn.commit()


def remove_entity(conn: sqlite3.Connection, entity_id: str) -> None:
    """
    Remove the entity from the entities table.
    """
    conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
    conn.commit()


# ====================
# EVENT INTERACTIONS
# ====================


def insert_event(conn: sqlite3.Connection, event_dict: dict[str, Any]) -> None:
    """Insert an event into the database.

    Args:
        conn (sqlite3.Connection): The database connection.
        event (dict[str, Any]): The event to insert, preprocessed as a dict.
    """
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO events
        (id, chunk_id, statement, embedding, triplets, statement_type, temporal_type,
         created_at, valid_at, expired_at, invalid_at, invalidated_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (event_dict["id"]),
            event_dict["chunk_id"],
            event_dict["statement"],
            event_dict["embedding"],
            event_dict["triplets"],
            event_dict["statement_type"],
            event_dict["temporal_type"],
            event_dict["created_at"],
            event_dict["valid_at"],
            event_dict["expired_at"],
            event_dict["invalid_at"],
            event_dict.get("invalidated_by"),
        ),
    )


def has_events(conn: sqlite3.Connection) -> bool:
    """Check if there are any FACT events in the database to validate against."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM events WHERE statement_type = ?", ("FACT",))
    count = cursor.fetchone()[0]
    return count > 0  # type: ignore


def update_events_batch(conn: sqlite3.Connection, events: list[TemporalEvent]) -> None:
    """Batch update multiple events."""
    if not events:
        return

    c = conn.cursor()
    update_data = [
        (
            safe_iso(event.invalid_at) if hasattr(event, "invalid_at") else None,
            safe_iso(event.expired_at) if hasattr(event, "expired_at") else None,
            (
                str(event.invalidated_by)
                if hasattr(event, "invalidated_by") and event.invalidated_by
                else None
            ),
            str(event.id) if hasattr(event, "id") else event.id,
        )
        for event in events
    ]

    c.executemany(
        """UPDATE events SET
           invalid_at = ?,
           expired_at = ?,
           invalidated_by = ?
           WHERE id = ?""",
        update_data,
    )
    conn.commit()
