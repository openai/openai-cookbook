"""Offline graph regressions.

Run from the repository root with the example's dependencies installed:
    python -m unittest discover -s examples/partners/temporal_agents_with_knowledge_graphs/tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cb_functions import build_graph
from db_interface import insert_triplet, make_connection


class BuildGraphTests(unittest.TestCase):
    def setUp(self):
        self.connection = make_connection(memory=True)
        self.addCleanup(self.connection.close)
        self.connection.executemany(
            "INSERT INTO entities (id, name) VALUES (?, ?)",
            [("company", "Company"), ("partner", "Partner")],
        )

    def add_fact(self, suffix, *, literal=False, predicate="CONTRACT_WITH"):
        event_id = f"event-{suffix}"
        valid_at = f"{suffix}-01-01"
        self.connection.execute(
            "INSERT INTO events (id, statement, valid_at, invalid_at) "
            "VALUES (?, ?, ?, ?)",
            (event_id, f"Fact from {suffix}", valid_at, f"{int(suffix) + 1}-01-01"),
        )
        insert_triplet(
            self.connection,
            {
                "id": f"triplet-{suffix}",
                "event_id": event_id,
                "subject_id": "company",
                "subject_name": "Company",
                "predicate": predicate,
                "object_id": None if literal else "partner",
                "object_name": f"Revenue {suffix}" if literal else "Partner",
                "value": suffix if literal else None,
            },
        )

    def assert_history_preserved(self, *, literal=False, nodes_as_names=False):
        self.add_fact("2020", literal=literal)
        self.add_fact("2024", literal=literal)
        graph = build_graph(self.connection, nodes_as_names=nodes_as_names)
        subject = "Company" if nodes_as_names else "company"
        target = subject if literal else "Partner" if nodes_as_names else "partner"
        self.assertEqual(graph.number_of_edges(subject, target), 2)
        facts = {data["event_id"]: data for _, _, data in graph.edges(data=True)}
        self.assertEqual(set(facts), {"event-2020", "event-2024"})
        for year in ("2020", "2024"):
            data = facts[f"event-{year}"]
            self.assertEqual(data["triplet_id"], f"triplet-{year}")
            self.assertEqual(data["predicate"], "CONTRACT_WITH")
            self.assertEqual(data["statement"], f"Fact from {year}")
            self.assertEqual(data["valid_at"], f"{year}-01-01")
            self.assertEqual(data["invalid_at"], f"{int(year) + 1}-01-01")
            if literal:
                self.assertEqual(data["literal_object"], f"Revenue {year}")
                self.assertEqual(data["value"], year)
        historical = [
            data
            for data in facts.values()
            if data["valid_at"] <= "2020-06-01" < data["invalid_at"]
        ]
        self.assertEqual([data["event_id"] for data in historical], ["event-2020"])

    def test_repeated_entity_relationship_keeps_both_events(self):
        self.assert_history_preserved()

    def test_repeated_entity_relationship_with_name_nodes(self):
        self.assert_history_preserved(nodes_as_names=True)

    def test_repeated_literal_self_loop_keeps_both_events(self):
        self.assert_history_preserved(literal=True)

    def test_repeated_literal_self_loop_with_name_nodes(self):
        self.assert_history_preserved(literal=True, nodes_as_names=True)

    def test_single_relationship_preserves_nodes_and_metadata(self):
        self.add_fact("2020")
        graph = build_graph(self.connection)
        self.assertEqual(set(graph.nodes), {"company", "partner"})
        self.assertEqual(graph.nodes["company"]["name"], "Company")
        self.assertEqual(graph.nodes["partner"]["name"], "Partner")
        self.assertEqual(graph.number_of_edges(), 1)
        data = next(iter(graph.edges(data=True)))[2]
        self.assertEqual(data["event_id"], "event-2020")
        self.assertEqual(data["canonical_subject_name"], "Company")
        self.assertEqual(data["canonical_object_name"], "Partner")
        self.assertIsNone(data["value"])

    def test_different_predicates_remain_separate(self):
        self.add_fact("2020", predicate="CONTRACT_WITH")
        self.add_fact("2024", predicate="INVESTED_IN")
        graph = build_graph(self.connection)
        self.assertEqual(graph.number_of_edges(), 2)
        self.assertEqual(
            {data["predicate"] for _, _, data in graph.edges(data=True)},
            {"CONTRACT_WITH", "INVESTED_IN"},
        )

    def test_empty_database_produces_empty_graph(self):
        graph = build_graph(self.connection)
        self.assertEqual(graph.number_of_nodes(), 0)
        self.assertEqual(graph.number_of_edges(), 0)

    def test_unresolved_subject_is_skipped(self):
        self.add_fact("2020")
        self.connection.execute("UPDATE triplets SET subject_id = NULL")
        self.assertEqual(build_graph(self.connection).number_of_edges(), 0)


if __name__ == "__main__":
    unittest.main()
