"""Offline checks for Turkish retrieval, split integrity, and API request ordering."""

import os
import sys
import unicodedata
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from search import (
    embedding_vectors,
    evaluate,
    lexical_search,
    load_data,
    normalize,
    semantic_search,
    validate_data,
)


class SearchTests(unittest.TestCase):
    def test_turkish_casing_and_unicode_equivalence(self):
        self.assertEqual(normalize("IŞIK İZİN", "turkish"), "ışık izin")
        self.assertEqual(
            normalize(unicodedata.normalize("NFD", "İZİN"), "turkish"), "izin"
        )

    def test_folding_is_optional_and_lossy(self):
        self.assertNotEqual(normalize("sık", "turkish"), normalize("sik", "turkish"))
        self.assertEqual(normalize("sık", "ascii"), normalize("sik", "ascii"))

    def test_zero_overlap_does_not_produce_arbitrary_hits(self):
        documents = [{"id": "fixture-a", "title": "Kargo", "text": "Takip kodu"}]
        self.assertEqual(lexical_search(documents, "", "ascii", 3), [])
        self.assertEqual(lexical_search(documents, "astronot", "ascii", 3), [])

    def test_ascii_query_recovers_expected_fixture_document(self):
        documents = [
            {"id": "fixture-password", "title": "Şifre sıfırlama", "text": "Parola yenileme"},
            {"id": "fixture-invoice", "title": "Fatura", "text": "Ödeme belgesi"},
        ]
        self.assertEqual(
            lexical_search(documents, "sifre sifirlama", "turkish", 3), []
        )
        self.assertEqual(
            lexical_search(documents, "sifre sifirlama", "ascii", 3)[0][0],
            "fixture-password",
        )

    def test_development_is_default_and_full_document_corpus_is_kept(self):
        documents, queries = load_data()
        held_documents, held_queries = load_data("held-out")
        all_documents, all_queries = load_data("all")
        self.assertEqual(len(documents), 40)
        self.assertEqual(len(queries), 56)
        self.assertEqual(len(held_queries), 32)
        self.assertEqual(len(held_documents), len(all_documents))
        self.assertEqual(len(all_queries), 88)
        self.assertEqual({query["split"] for query in queries}, {"development"})
        self.assertEqual({query["split"] for query in held_queries}, {"held-out"})

    def test_data_validation_rejects_split_group_collisions(self):
        documents = [{"id": "doc-a", "title": "A", "text": "Alpha"}]
        queries = [
            {
                "id": "q-a",
                "category": "exact",
                "text": "Alpha",
                "relevant_ids": ["doc-a"],
                "group_id": "family-a",
                "split": "development",
            }
        ]
        unanswerable = [
            {
                "id": "ua-a",
                "category": "unanswerable",
                "text": "Beta",
                "relevant_ids": [],
                "group_id": "family-a",
                "split": "held-out",
            }
        ]
        with self.assertRaisesRegex(ValueError, "more than one split"):
            validate_data(documents, queries, unanswerable)

    def test_data_validation_rejects_duplicate_query_text_and_bad_labels(self):
        documents = [{"id": "doc-a", "title": "A", "text": "Alpha"}]
        query = {
            "id": "q-a",
            "category": "exact",
            "text": "Alpha",
            "relevant_ids": ["doc-a"],
            "group_id": "family-a",
            "split": "development",
        }
        duplicate = {
            "id": "ua-a",
            "category": "unanswerable",
            "text": "Alpha",
            "relevant_ids": [],
            "group_id": "family-b",
            "split": "development",
        }
        with self.assertRaisesRegex(ValueError, "text must be nonempty and unique"):
            validate_data(documents, [query], [duplicate])

        invalid_label = {**query, "relevant_ids": ["missing"]}
        with self.assertRaisesRegex(ValueError, "unknown relevant document"):
            validate_data(documents, [invalid_label], [])

    def test_metrics_include_misses_and_multiple_relevant_documents(self):
        queries = [
            {"id": "a", "category": "test", "relevant_ids": ["x", "y"]},
            {"id": "b", "category": "test", "relevant_ids": ["z"]},
        ]
        metrics = evaluate(queries, {"a": [("other", 1), ("x", 0.5)], "b": []}, 2)
        self.assertEqual(metrics["recall@2"], 0.25)
        self.assertEqual(metrics["mrr@2"], 0.25)

    def test_semantic_ranking_with_known_vectors(self):
        documents = [{"id": "a"}, {"id": "b"}]
        result = semantic_search(documents, [[0, 1], [1, 0]], [1, 0], 1)
        self.assertEqual(result, [("b", 1.0)])

    def test_embedding_request_payload_and_response_order_are_mocked(self):
        received = {}

        def create(**kwargs):
            received.update(kwargs)
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=1, embedding=[0.0, 1.0]),
                    SimpleNamespace(index=0, embedding=[1.0, 0.0]),
                ]
            )

        client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
        fake_openai = SimpleNamespace(OpenAI=lambda: client)
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
            patch.dict(sys.modules, {"openai": fake_openai}),
        ):
            vectors = embedding_vectors(
                ["document text", "query text"], "test-model"
            )

        self.assertEqual(
            received, {"input": ["document text", "query text"], "model": "test-model"}
        )
        self.assertEqual(vectors, [[1.0, 0.0], [0.0, 1.0]])


if __name__ == "__main__":
    unittest.main()
