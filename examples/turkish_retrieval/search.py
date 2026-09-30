"""Compare lexical baselines and optional OpenAI embeddings on Turkish text."""

import argparse
import json
import math
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path

DATA_DIRECTORY = Path(__file__).resolve().parent
ASCII_MAP = str.maketrans("çğıöşü", "cgiosu")
ANSWERABLE_CATEGORIES = {"exact", "case", "ascii", "paraphrase", "suffix"}
SPLITS = {"development", "held-out"}


def normalize(text, method):
    """Normalize Turkish casing before optional, lossy ASCII folding."""
    text = unicodedata.normalize("NFC", text)
    if method == "unicode":
        return text.lower()
    text = text.translate(str.maketrans({"I": "ı", "İ": "i"})).lower()
    return text.translate(ASCII_MAP) if method == "ascii" else text


def tokenize(text, method):
    return re.findall(r"[^\W_]+", normalize(text, method), flags=re.UNICODE)


def validate_data(documents, queries, unanswerable_queries):
    """Validate fixture identifiers, labels, text, and leakage groups."""
    document_ids = [document.get("id") for document in documents]
    if not documents or any(not value for value in document_ids):
        raise ValueError("Document IDs must be nonempty.")
    if len(set(document_ids)) != len(document_ids):
        raise ValueError("Document IDs must be unique.")
    document_texts = []
    for document in documents:
        if not all(document.get(field, "").strip() for field in ("title", "text")):
            raise ValueError("Every document must have a nonempty title and text.")
        document_texts.append(
            unicodedata.normalize(
                "NFC", f"{document['title'].strip()}\n{document['text'].strip()}"
            )
        )
    if len(set(document_texts)) != len(document_texts):
        raise ValueError("Document text must be unique.")

    query_ids = []
    query_texts = []
    group_splits = {}
    for query in queries:
        query_ids.append(query.get("id"))
        query_texts.append(unicodedata.normalize("NFC", query.get("text", "").strip()))
        relevant_ids = query.get("relevant_ids")
        if query.get("category") not in ANSWERABLE_CATEGORIES:
            raise ValueError("Answerable queries must use a supported category.")
        if not isinstance(relevant_ids, list) or not relevant_ids:
            raise ValueError("Every answerable query must have relevant document IDs.")
        if not set(relevant_ids) <= set(document_ids):
            raise ValueError("A query references an unknown relevant document ID.")
        group_id = query.get("group_id")
        split = query.get("split")
        if not group_id or split not in SPLITS:
            raise ValueError("Every query must have a group ID and supported split.")
        if group_id in group_splits and group_splits[group_id] != split:
            raise ValueError("A query group appears in more than one split.")
        group_splits[group_id] = split

    for query in unanswerable_queries:
        query_ids.append(query.get("id"))
        query_texts.append(unicodedata.normalize("NFC", query.get("text", "").strip()))
        if query.get("category") != "unanswerable" or query.get("relevant_ids") != []:
            raise ValueError(
                "Unanswerable queries must have category 'unanswerable' and no labels."
            )
        group_id = query.get("group_id")
        split = query.get("split")
        if not group_id or split not in SPLITS:
            raise ValueError("Every query must have a group ID and supported split.")
        if group_id in group_splits and group_splits[group_id] != split:
            raise ValueError("A query group appears in more than one split.")
        group_splits[group_id] = split

    if any(not value for value in query_ids) or len(set(query_ids)) != len(query_ids):
        raise ValueError("Query IDs must be nonempty and unique across both query files.")
    if any(not value for value in query_texts) or len(set(query_texts)) != len(
        query_texts
    ):
        raise ValueError("Query text must be nonempty and unique across both query files.")


def load_data(split="development"):
    """Load all documents and only the selected answerable evaluation queries."""
    if split not in {*SPLITS, "all"}:
        raise ValueError("Split must be 'development', 'held-out', or 'all'.")
    documents = json.loads(
        (DATA_DIRECTORY / "documents.json").read_text(encoding="utf-8")
    )
    queries = json.loads((DATA_DIRECTORY / "queries.json").read_text(encoding="utf-8"))
    unanswerable_queries = json.loads(
        (DATA_DIRECTORY / "unanswerable_queries.json").read_text(encoding="utf-8")
    )
    validate_data(documents, queries, unanswerable_queries)
    selected_queries = (
        queries
        if split == "all"
        else [query for query in queries if query["split"] == split]
    )
    return documents, selected_queries


def lexical_search(documents, query, method, k):
    """Rank by term-frequency cosine; zero-overlap documents are excluded."""
    query_terms = Counter(tokenize(query, method))
    query_norm = math.sqrt(sum(value * value for value in query_terms.values()))
    results = []
    for document in documents:
        terms = Counter(tokenize(document["title"] + " " + document["text"], method))
        dot = sum(value * terms[term] for term, value in query_terms.items())
        if dot == 0 or query_norm == 0:
            continue
        norm = math.sqrt(sum(value * value for value in terms.values()))
        results.append((document["id"], dot / (norm * query_norm)))
    return sorted(results, key=lambda item: (-item[1], item[0]))[:k]


def embedding_vectors(texts, model):
    """Send original text to OpenAI only when an embedding method is selected."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("Set OPENAI_API_KEY locally before selecting embeddings.")
    from openai import OpenAI

    response = OpenAI().embeddings.create(input=texts, model=model)
    vectors = [
        item.embedding for item in sorted(response.data, key=lambda item: item.index)
    ]
    if len(vectors) != len(texts):
        raise ValueError("The embedding response has an unexpected number of vectors.")
    return vectors


def semantic_search(documents, document_vectors, query_vector, k):
    query_norm = math.sqrt(sum(value * value for value in query_vector))
    results = []
    for document, vector in zip(documents, document_vectors, strict=True):
        norm = math.sqrt(sum(value * value for value in vector))
        if not norm or not query_norm or len(vector) != len(query_vector):
            raise ValueError(
                "Embedding vectors must have equal dimensions and nonzero norms."
            )
        score = sum(a * b for a, b in zip(vector, query_vector, strict=True)) / (
            norm * query_norm
        )
        results.append((document["id"], score))
    return sorted(results, key=lambda item: (-item[1], item[0]))[:k]


def evaluate(queries, rankings, k):
    """Report macro Recall@k and MRR@k, including queries with no results."""
    if not queries:
        raise ValueError("At least one query is required.")
    recall = reciprocal_rank = 0.0
    categories = {}
    for query in queries:
        relevant = set(query["relevant_ids"])
        retrieved = [item[0] for item in rankings[query["id"]]][:k]
        query_recall = len(relevant & set(retrieved)) / len(relevant)
        recall += query_recall
        reciprocal_rank += next(
            (
                1 / rank
                for rank, doc_id in enumerate(retrieved, 1)
                if doc_id in relevant
            ),
            0.0,
        )
        category = categories.setdefault(query["category"], {"count": 0, "recall": 0.0})
        category["count"] += 1
        category["recall"] += query_recall
    return {
        f"recall@{k}": recall / len(queries),
        f"mrr@{k}": reciprocal_rank / len(queries),
        "categories": {
            name: {
                "count": item["count"],
                f"recall@{k}": item["recall"] / item["count"],
            }
            for name, item in categories.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--query",
        help="Search for one Turkish query instead of evaluating the fixture.",
    )
    parser.add_argument(
        "--method",
        choices=["all", "unicode", "turkish", "ascii", "embeddings"],
        default="all",
    )
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--model", default="text-embedding-3-small")
    parser.add_argument(
        "--split",
        choices=["development", "held-out", "all"],
        default="development",
        help="Select evaluation queries; the full document corpus remains searchable.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Save evaluation metrics and per-query rankings as JSON.",
    )
    args = parser.parse_args()
    if args.k < 1:
        parser.error("--k must be positive.")
    if args.method == "embeddings" and not os.environ.get("OPENAI_API_KEY"):
        parser.error("Set OPENAI_API_KEY locally before selecting embeddings.")
    documents, queries = load_data(args.split)
    methods = ["unicode", "turkish", "ascii"] if args.method == "all" else [args.method]
    output = {
        "documents": len(documents),
        "queries": len(queries),
        "split": args.split,
        "k": args.k,
        "methods": {},
    }
    for method in methods:
        if method == "embeddings":
            texts = [
                document["title"] + "\n" + document["text"] for document in documents
            ]
            queries_to_embed = (
                [args.query] if args.query else [query["text"] for query in queries]
            )
            vectors = embedding_vectors(texts + queries_to_embed, args.model)
            document_vectors = vectors[: len(documents)]
            query_vectors = vectors[len(documents) :]
        if args.query:
            results = (
                semantic_search(documents, document_vectors, query_vectors[0], args.k)
                if method == "embeddings"
                else lexical_search(documents, args.query, method, args.k)
            )
            print(
                json.dumps(
                    {"method": method, "query": args.query, "results": results},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            continue
        rankings = {
            query["id"]: (
                semantic_search(
                    documents, document_vectors, query_vectors[index], args.k
                )
                if method == "embeddings"
                else lexical_search(documents, query["text"], method, args.k)
            )
            for index, query in enumerate(queries)
        }
        metrics = evaluate(queries, rankings, args.k)
        output["methods"][method] = {"metrics": metrics, "rankings": rankings}
        if method == "embeddings":
            output["methods"][method]["model"] = args.model
        print(json.dumps({"method": method, **metrics}, ensure_ascii=False, indent=2))
    if args.output and not args.query:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
