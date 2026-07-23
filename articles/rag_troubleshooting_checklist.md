# RAG Troubleshooting Checklist

Use this quick checklist when a retrieval pipeline underperforms in production.

## 1) Confirm retrieval quality before tuning prompts
- Check whether relevant chunks are returned in top-k for a small labeled test set.
- Inspect chunk boundaries (too small loses context, too large lowers precision).
- Verify embedding model and index settings match your content type.

## 2) Verify context assembly
- Ensure reranking/order is deterministic and sensible.
- Remove duplicate or near-duplicate chunks from final context.
- Include source metadata (doc id, section, timestamp) to aid debugging.

## 3) Control stale or conflicting data
- Validate that index refresh jobs run as expected.
- Add recency or version filters when sources evolve frequently.
- Prefer authoritative sources when conflicts are detected.

## 4) Reduce hallucination risk
- Instruct the model to abstain when evidence is insufficient.
- Require citations to provided context where possible.
- Evaluate with adversarial/no-answer test cases.

## 5) Instrument and evaluate continuously
- Track retrieval recall@k and answer quality separately.
- Log failures by category (retrieval miss, grounding miss, synthesis miss).
- Re-test after each change to retrieval, ranking, or prompting.

## Related Cookbook examples
- [Evaluate RAG with LlamaIndex](../examples/evaluation/Evaluate_RAG_with_LlamaIndex.ipynb)
- [RAG with graph DB](../examples/RAG_with_graph_db.ipynb)
- [How to call functions for knowledge retrieval](../examples/How_to_call_functions_for_knowledge_retrieval.ipynb)
- [Parse PDF docs for RAG](../examples/Parse_PDF_docs_for_RAG.ipynb)
