# Evaluate Turkish document retrieval

This example extends the [semantic text search example](../Semantic_text_search_using_embeddings.ipynb) with a comparison of lexical retrieval methods for Turkish casing, ASCII spelling, paraphrases, and suffix changes. The fixture contains 40 fictional documents, 88 labeled answerable queries, and 20 unanswerable queries. The content and labels were authored for this example; they are not independently adjudicated and do not support general claims about Turkish retrieval quality.

## Requirements

Use Python 3.10 or newer. Create and activate a virtual environment before running the example.

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

The lexical methods and tests use only the Python standard library. The optional embedding method requires the `openai` package and an `OPENAI_API_KEY` environment variable.

## Run the development evaluation

From the repository root, on Windows:

```powershell
python -m unittest discover -s examples/turkish_retrieval -p test_search.py
python examples/turkish_retrieval/search.py
python examples/turkish_retrieval/search.py --method ascii --query "urun iade talebi"
```

On macOS or Linux, use your Python executable in place of `python` if needed. The default split is `development`, which contains 56 answerable queries across 14 intent groups. The full 40-document corpus remains searchable for every split.

The `--split` option also accepts `held-out` and `all`. Keep all records that share a `group_id` together. Use the held-out split only for a final evaluation after you have finished making retrieval choices; the development results below do not include held-out queries. The `unanswerable_queries.json` file contains 20 queries with no relevant document. These queries are split with their related answerable intent groups where applicable, but the current evaluator does not score abstention.

## Retrieval methods

The default `--method all` compares three lexical baselines:

1. `unicode` applies NFC normalization and Python's default lowercase conversion.
2. `turkish` maps `I` to `ı` and `İ` to `i` before lowercasing.
3. `ascii` applies Turkish casing and folds `çğıöşü` to `cgiosu`.

All methods tokenize whole words and rank by term-frequency cosine similarity. They exclude documents with no query-token overlap and break ties by document ID. They do not perform stemming, suffix analysis, or BM25 ranking. ASCII folding loses information; for example, `sık` and `sik` become the same token.

The answerable query set includes exact title phrases, Turkish uppercase variants, ASCII spellings, paraphrases, and inflected queries. A few queries intentionally label multiple relevant documents when they ask about both topics. Each record has a `group_id` and a `split`; the loader rejects duplicate IDs or query text, unknown labels, and groups assigned to more than one split. It also validates the separate unanswerable set.

## Development results

The following offline lexical evaluation uses the 56 answerable development queries, `k=3`, and no API calls. **Recall@k** is the fraction of relevant documents retrieved in the top `k`, averaged over queries. For a query with multiple relevant documents, its recall divides the number found in the top `k` by the total number labeled relevant. **MRR@k** is the average reciprocal rank of the first relevant result in the top `k`, or zero when none is retrieved.

| Method | Recall@3 | MRR@3 |
| --- | ---: | ---: |
| Unicode lowercase | 0.866 | 0.833 |
| Turkish casing | 0.920 | 0.887 |
| ASCII folding | 0.920 | 0.887 |

These scores describe this fictional fixture only. They are not estimates of general Turkish retrieval quality. The evaluator supports multiple relevant documents in recall calculations, but it does not score unanswerable queries or false positives.

## Inspect missed relevant documents

Save development rankings, then generate an offline Markdown report:

```powershell
python examples/turkish_retrieval/search.py --split development --output ../work/development-results.json
python examples/turkish_retrieval/report_failures.py --input ../work/development-results.json --output ../work/development-failures.md
```

The report lists queries where a method missed one or more labeled relevant documents, including the retrieved and missing IDs. For queries with multiple relevant documents, this makes partial misses distinguishable from cases where all relevant documents were missed. The report reads the saved `search.py` JSON and the bundled development fixtures; it makes no API calls. Treat it as a diagnostic for this fictional fixture, not as a general retrieval-quality claim.

## Optional: compare OpenAI embeddings

This command sends every document and every query in the selected split to the OpenAI API and incurs API usage charges. It embeds the original text without lexical normalization. Set `OPENAI_API_KEY` in your local environment; do not put the key in source files or commit it.

```powershell
python -m pip install -r examples/turkish_retrieval/requirements.txt
python examples/turkish_retrieval/search.py --method embeddings --split development
```

See the [OpenAI embeddings guide](https://developers.openai.com/api/docs/guides/embeddings) for API details. The default model is `text-embedding-3-small`; use `--model` to select another model. Each run recomputes embeddings. The example does not add persistent caching, a vector database, PDF extraction, or chunking. The embedding request is covered by a mocked test. The live embedding path has not been run for this contribution.

To save development metrics and per-query rankings outside this example directory:

```powershell
python examples/turkish_retrieval/search.py --split development --output ../work/baseline-results.json
```

Add documents to `documents.json` with unique `id`, `title`, and `text` fields. Add answerable queries to `queries.json` with `id`, `category`, `text`, a nonempty list of `relevant_ids`, `group_id`, and `split`. Keep unanswerable queries in `unanswerable_queries.json` with an empty `relevant_ids` list because the answerable evaluator requires at least one relevant document.
