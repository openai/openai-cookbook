"""Reusable functions for the cookbook."""

import sqlite3
import networkx as nx
from typing import Any
from datasets import load_dataset

from db_interface import get_all_triplets


def load_db_from_hf(db_path: str = "temporal_graph.db", hf_dataset_name: str = "TomoroAI/temporal_cookbook_db") -> sqlite3.Connection:
    """Load the pre-processed database from HuggingFace."""
    conn = sqlite3.connect(db_path)
    table_names = [
        "transcripts",
        "chunks",
        "events",
        "triplets",
        "entities",
    ]

    for table in table_names:
        print(f"Loading {table}...")
        ds = load_dataset(hf_dataset_name, name=table, split="train")
        df = ds.to_pandas()
        df.to_sql(table, conn, if_exists="replace", index=False)

        conn.commit()
    print("✅ All tables written to SQLite.")

    return conn

def build_graph(
        conn: sqlite3.Connection,
        *,
        nodes_as_names: bool = False
        ) -> nx.MultiDiGraph:
    """Build graph using canonical entity IDs and names."""
    graph = nx.MultiDiGraph()

    # Always load canonical mappings
    entity_to_canonical, canonical_names = _load_entity_maps(conn)
    event_temporal_map = _load_event_temporal(conn)

    for t in get_all_triplets(conn):
        if not t["subject_id"]:
            continue

        event_attrs = event_temporal_map.get(t["event_id"])
        _add_triplet_edge(
            graph,
            t,
            entity_to_canonical,
            canonical_names,
            event_attrs,
            nodes_as_names,
        )

    return graph

def _load_entity_maps(conn: sqlite3.Connection) -> tuple[dict[bytes, bytes], dict[bytes, str]]:
    """
    Return mappings for canonical entities:
    • entity_to_canonical: maps entity ID → canonical ID (using resolved_id)
    • canonical_names: maps canonical ID → canonical name.
    """
    cur = conn.cursor()

    # Get all entities with their resolved IDs
    cur.execute("""
        SELECT id, name, resolved_id
        FROM entities
    """)

    entity_to_canonical: dict[bytes, bytes] = {}
    canonical_names: dict[bytes, str] = {}

    for row in cur.fetchall():
        entity_id = row[0]
        name = row[1]
        resolved_id = row[2]

        if resolved_id:
            # If entity has a resolved_id, map to that
            entity_to_canonical[entity_id] = resolved_id
            # Store name of the canonical entity
            canonical_names[resolved_id] = name
        else:
            # If no resolved_id, entity is its own canonical version
            entity_to_canonical[entity_id] = entity_id
            canonical_names[entity_id] = name

    return entity_to_canonical, canonical_names

def _load_event_temporal(conn: sqlite3.Connection) -> dict[bytes, dict[str, Any]]:
    """
    Read the `events` table once and build a mapping
    event_id (bytes) → dict of temporal / descriptive attributes.
    Only the columns that are useful on the graph edges are pulled;
    extend this list freely if you need more.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT  id,
                statement,
                statement_type,
                temporal_type,
                created_at,
                valid_at,
                expired_at,
                invalid_at,
                invalidated_by
        FROM events
    """)
    event_map: dict[bytes, dict[str, Any]] = {}
    for (
        eid,
        statement,
        statement_type,
        temporal_type,
        created_at,
        valid_at,
        expired_at,
        invalid_at,
        invalidated_by,
    ) in cur.fetchall():
        event_map[eid] = {
            "statement": statement,
            "statement_type": statement_type,
            "temporal_type": temporal_type,
            "created_at": created_at,
            "valid_at": valid_at,
            "expired_at": expired_at,
            "invalid_at": invalid_at,
            "invalidated_by": invalidated_by,
        }
    return event_map


def _add_triplet_edge(
        graph: nx.MultiDiGraph, t: dict,
        entity_to_canonical: dict[bytes, bytes],
        canonical_names: dict[bytes, str],
        event_attrs: dict[str, Any] | None = None,
        use_names: bool = False,
        ) -> None:
    """Add one edge using canonical IDs and names."""
    subj_id = t["subject_id"]
    obj_id = t["object_id"]

    if subj_id is None:
        return

    # Get canonical IDs
    canonical_subj = entity_to_canonical.get(subj_id, subj_id)
    canonical_obj = entity_to_canonical.get(obj_id, obj_id) if obj_id else None

    # Get canonical names
    subj_name = canonical_names.get(canonical_subj, t["subject_name"]) if canonical_subj is not None else t["subject_name"]
    obj_name = canonical_names.get(canonical_obj, t["object_name"]) if canonical_obj is not None else t["object_name"]

    subj_node = subj_name if use_names else canonical_subj
    obj_node  = obj_name  if use_names else canonical_obj

    # Add nodes with canonical names
    graph.add_node(
        subj_node,
        canonical_id=canonical_subj,
        name=subj_name,
    )

    # Core edge attributes (triplet-specific)
    edge_attrs: dict[str, Any] = {
        "predicate": t["predicate"],
        "triplet_id": t["id"],
        "event_id": t["event_id"],
        "value": t["value"],
        "canonical_subject_name": subj_name,
        "canonical_object_name": obj_name,
    }

    # Merge in temporal data, if we have it
    if event_attrs:
        edge_attrs.update(event_attrs)

    if canonical_obj is None:
        # Handle self-loops for null objects
        graph.add_edge(
            subj_node, subj_node,
            key=t["predicate"],
            **edge_attrs,
            literal_object=t["object_name"],
        )
    else:
        graph.add_node(
            obj_node,
            canonical_id=canonical_obj,
            name=obj_name,
        )
        graph.add_edge(
            subj_node, obj_node,
            key=t["predicate"],
            **edge_attrs,
        )
