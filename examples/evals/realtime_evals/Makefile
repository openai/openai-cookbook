UV_BIN := $(strip $(shell command -v uv 2>/dev/null))
PYTHON_BIN := $(strip $(shell command -v python 2>/dev/null || command -v python3 2>/dev/null))
VENV_DIR := .venv
VENV_PYTHON := $(VENV_DIR)/bin/python

ifeq ($(UV_BIN),)
RUFF := $(VENV_DIR)/bin/ruff
MYPY := $(VENV_DIR)/bin/mypy
PYTEST := $(VENV_DIR)/bin/pytest
STREAMLIT := $(VENV_DIR)/bin/streamlit
RUN_PYTHON := $(VENV_PYTHON)
else
RUFF := uv run --with ruff ruff
MYPY := uv run --with mypy --with pandas-stubs --with types-seaborn --with types-tqdm mypy
PYTEST := uv run --with pytest pytest
STREAMLIT := uv run --with streamlit streamlit
RUN_PYTHON := uv run python
endif

.PHONY: install streamlit format lint lint-fix typecheck test validate-input validate-output

HARNESS ?=
DATA_PATH ?=
RUN_DIR ?=

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
	cd results_viewer && $(STREAMLIT) run app.py

validate-input:
	@test -n "$(HARNESS)" || (echo "HARNESS is required, e.g. make validate-input HARNESS=run" && exit 2)
	$(RUN_PYTHON) shared/scripts/validate_eval_input.py --harness $(HARNESS) $(if $(DATA_PATH),--data-path "$(DATA_PATH)",)

validate-output:
	@test -n "$(HARNESS)" || (echo "HARNESS is required, e.g. make validate-output HARNESS=run" && exit 2)
	$(RUN_PYTHON) shared/scripts/validate_eval_output.py --harness $(HARNESS) $(if $(RUN_DIR),--run-dir "$(RUN_DIR)",)
