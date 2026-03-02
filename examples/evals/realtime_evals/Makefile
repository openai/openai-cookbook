.PHONY: install streamlit format lint lint-fix typecheck test

install:
	uv venv .venv
	uv sync --group dev

streamlit:
	uv run --group dev streamlit run results_viewer/app.py

format:
	uv run --group dev ruff format .

lint:
	uv run --group dev ruff check .

lint-fix:
	uv run --group dev ruff check . --fix

typecheck:
	uv run --group dev mypy .

test:
	uv run --group dev pytest
