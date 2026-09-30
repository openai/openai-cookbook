"""Create an offline report of missed relevant documents in retrieval results."""

import argparse
import json
from pathlib import Path

DATA_DIRECTORY = Path(__file__).resolve().parent


def build_report(results, queries, document_ids):
    """Render development-split retrieval misses from search.py JSON output."""
    if not isinstance(results, dict) or results.get("split") != "development":
        raise ValueError("Input must be a search result for the development split.")
    methods = results.get("methods")
    if not isinstance(methods, dict) or not methods:
        raise ValueError("Input must contain a nonempty methods object.")

    query_by_id = {query["id"]: query for query in queries}
    if any(query.get("split") != "development" for query in queries):
        raise ValueError("Query fixture must contain only development queries.")
    known_documents = set(document_ids)
    failures = []
    for method, method_results in methods.items():
        rankings = method_results.get("rankings") if isinstance(method_results, dict) else None
        if not isinstance(rankings, dict):
            raise TypeError(f"Method {method!r} must contain rankings.")
        if set(rankings) != set(query_by_id):
            raise ValueError(f"Method {method!r} has missing or unknown query IDs.")
        for query_id, ranking in rankings.items():
            if not isinstance(ranking, list):
                raise TypeError(f"Ranking for query {query_id!r} must be a list.")
            retrieved = []
            for item in ranking:
                if not isinstance(item, list) or not item or item[0] not in known_documents:
                    raise ValueError(f"Ranking for query {query_id!r} has an unknown document ID.")
                retrieved.append(item[0])
            query = query_by_id[query_id]
            relevant = query.get("relevant_ids")
            if not isinstance(relevant, list) or not relevant or not set(relevant) <= known_documents:
                raise ValueError(f"Query {query_id!r} has invalid relevant document IDs.")
            missing = [doc_id for doc_id in relevant if doc_id not in retrieved]
            if missing:
                failures.append((method, query, relevant, retrieved, missing))

    lines = ["# Retrieval failure report", "", "Split: `development`", ""]
    if not failures:
        lines.append("No relevant documents were missed.")
    else:
        for method, query, relevant, retrieved, missing in failures:
            lines.extend(
                [
                    f"## {method} — {query['id']}",
                    "",
                    f"Query: {query['text']}",
                    f"Relevant: {', '.join(relevant)}",
                    f"Retrieved: {', '.join(retrieved) if retrieved else '(none)'}",
                    f"Missing: {', '.join(missing)}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="search.py JSON output")
    parser.add_argument("--output", required=True, type=Path, help="Markdown report path")
    args = parser.parse_args()
    results = json.loads(args.input.read_text(encoding="utf-8"))
    queries = json.loads((DATA_DIRECTORY / "queries.json").read_text(encoding="utf-8"))
    queries = [query for query in queries if query["split"] == "development"]
    documents = json.loads((DATA_DIRECTORY / "documents.json").read_text(encoding="utf-8"))
    report = build_report(results, queries, [document["id"] for document in documents])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
