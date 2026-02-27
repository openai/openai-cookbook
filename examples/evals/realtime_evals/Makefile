.PHONY: format lint lint-fix typecheck test

format:
	uv run --with ruff ruff format .

lint:
	uv run --with ruff ruff check .

lint-fix:
	uv run --with ruff ruff check . --fix

typecheck:
	uv run --with mypy --with pandas-stubs --with types-tqdm mypy --explicit-package-bases .

test:
	uv run --with pytest pytest
