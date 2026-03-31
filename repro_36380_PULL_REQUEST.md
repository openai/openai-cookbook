Made-with: Cursor

## Summary

Add `examples/langchain_core/repro_36380.py`, a minimal script that reproduces [langchain-ai/langchain#36380](https://github.com/langchain-ai/langchain/issues/36380): constructor-shaped LangChain JSON in a runnable’s output can be deserialized during `RunnableWithMessageHistory` history writes and persisted as a live `SystemMessage`. The script uses the same payload pattern as the issue (`dumps(SystemMessage(...))` + `json.loads`) and the same `input_messages_key` / `output_messages_key` shape. It resolves the cookbook repo root via `AGENTS.md`, prepends `<repo-root>/.langchain-src/libs/core` to `sys.path` when present, and documents `pip install -r examples/langchain_core/requirements.txt` for topic-scoped deps. Extend `.gitignore` with `.langchain-src/` and `.venv-lc/` so local clones and a dedicated venv stay untracked.

## Motivation

The cookbook repo is a convenient place to keep a **self-contained repro** under `examples/langchain_core/` (per `AGENTS.md`: Python samples live under `examples/<topic>/`) with a topic-scoped `requirements.txt`. Maintainers can run it while validating security fixes in `langchain_core` without hunting through issue comments. Ignoring `.langchain-src/` and `.venv-lc/` keeps optional local LangChain development artifacts out of git. This change does **not** add website-facing cookbook content; it is a developer utility aligned with the vulnerability described in #36380.

---

## For new content

This PR adds a **standalone repro script and gitignore entries**, not a new article or notebook for cookbook.openai.com.

- [ ] **registry.yaml / authors.yaml** — N/A: no new published cookbook page; nothing to register.
- [ ] **Self-review (contribution rubric)** — N/A for registry content; script is documented in its module docstring, runs with `pip install -e .langchain-src/libs/core`, and is scoped to LangChain/OpenAI-adjacent debugging.

If you prefer every PR to tick the full rubric for *any* file change, treat the script as **tooling**:

- **Relevance:** Helps verify behavior around LLM app frameworks and unsafe deserialization in chat history (common when building on OpenAI-style chat APIs).
- **Uniqueness:** Small, issue-linked repro not duplicated elsewhere in this repo.
- **Spelling / grammar:** Docstring reviewed.
- **Clarity:** Docstring includes clone, venv, install, and expected exit codes.
- **Correctness:** From repo root, run `python examples/langchain_core/repro_36380.py` after `pip install -r examples/langchain_core/requirements.txt` and optionally `pip install -e .langchain-src/libs/core` (vulnerable vs fixed tree determines exit 1 vs 0).
- **Completeness:** Links to #36380 and explains `.gitignore` rationale.
