UV_BIN := $(strip $(shell command -v uv 2>/dev/null))
PYTHON_BIN := $(strip $(shell command -v python 2>/dev/null || command -v python3 2>/dev/null))
VENV_DIR := .venv
VENV_PYTHON := $(VENV_DIR)/bin/python

ifeq ($(UV_BIN),)
RUFF := $(VENV_DIR)/bin/ruff
MYPY := $(VENV_DIR)/bin/mypy
PYTEST := $(VENV_DIR)/bin/pytest
STREAMLIT := $(VENV_DIR)/bin/streamlit
else
RUFF := uv run --with ruff ruff
MYPY := uv run --with mypy --with pandas-stubs --with types-seaborn --with types-tqdm mypy
PYTEST := uv run --with pytest pytest
STREAMLIT := uv run --with streamlit streamlit
endif

.PHONY: install streamlit format lint lint-fix typecheck test

install:
ifeq ($(UV_BIN),)
	$(PYTHON_BIN) -m venv $(VENV_DIR)
	$(VENV_PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt
else
	uv venv $(VENV_DIR)
	uv sync --group dev
endif

format:
	$(RUFF) format .

lint:
	$(RUFF) check .

lint-fix:
	$(RUFF) check . --fix

typecheck:
	$(MYPY) --explicit-package-bases .

test:
	$(PYTEST)

streamlit:
	$(STREAMLIT) run results_viewer/app.py

