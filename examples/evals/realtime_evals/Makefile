.PHONY: format lint lint-fix typecheck test

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
