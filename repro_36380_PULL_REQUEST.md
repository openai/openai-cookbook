Made-with: Cursor

## Summary

Add `examples/langchain_core/repro_36380.py` plus **`langchain_issue_36380_fix.py`**, an in-repo mitigation for [langchain-ai/langchain#36380](https://github.com/langchain-ai/langchain/issues/36380). Stock `langchain-core` deserializes traced run I/O with `allowed_objects="all"`, so constructor-shaped output (e.g. `dumps(SystemMessage(...))` + `json.loads`) can become a live `SystemMessage` in history. The fix module monkeypatches `RunnableWithMessageHistory` to use the same explicit message allowlist as the intended upstream patch. The repro calls `apply_langchain_issue_36380_fix()` by default so **`pip install -r examples/langchain_core/requirements.txt` alone** yields a safe exit (no persisted `SystemMessage`). Set `REPRO_36380_NO_FIX=1` to exercise stock vulnerable behavior (expect exit 1 with PyPI core). Optional: prepend `<repo-root>/.langchain-src/libs/core` when a local clone exists. `.gitignore` includes `.langchain-src/` and `.venv-lc/`.

## Motivation

The cookbook branch should **actually address** the unsafe deserialization behavior for developers who cannot wait on a `langchain-core` release: import `apply_langchain_issue_36380_fix()` at app startup (with `examples/langchain_core` on `PYTHONPATH`, or copy the module into your project) until upstream merges. The repro stays aligned with `AGENTS.md` (`examples/<topic>/`) and topic-scoped `requirements.txt`. This is **not** a substitute for merging the fix into `langchain-ai/langchain`, but it **does** resolve the issue in-process for this branch. No website-facing cookbook page.

---

## For new content

This PR adds a **standalone repro script and gitignore entries**, not a new article or notebook for cookbook.openai.com.

- [ ] **registry.yaml / authors.yaml** — N/A: no new published cookbook page; nothing to register.
- [ ] **Self-review (contribution rubric)** — N/A for registry content; repro and fix modules are documented; scoped to LangChain/OpenAI-adjacent security debugging.

If you prefer every PR to tick the full rubric for *any* file change, treat the script as **tooling**:

- **Relevance:** Helps verify behavior around LLM app frameworks and unsafe deserialization in chat history (common when building on OpenAI-style chat APIs).
- **Uniqueness:** Small, issue-linked repro not duplicated elsewhere in this repo.
- **Spelling / grammar:** Docstring reviewed.
- **Clarity:** Docstring includes clone, venv, install, and expected exit codes.
- **Correctness:** From repo root, `pip install -r examples/langchain_core/requirements.txt`, then `python examples/langchain_core/repro_36380.py` (expect exit 0). With `REPRO_36380_NO_FIX=1`, expect exit 1 against stock PyPI `langchain-core`.
- **Completeness:** Links to #36380 and explains `.gitignore` rationale.
