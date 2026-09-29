SHELL := /bin/bash
EXAMPLE_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
CODEX_HOME := $(EXAMPLE_DIR)/.codex-home
MARKETPLACE := $(CODEX_HOME)/marketplaces/cookbook-plugins
VENV_PYTHON := $(EXAMPLE_DIR)/.venv/bin/python
PLUGIN := BLS@cookbook-plugins
L2_OUTPUT := outputs/l2-results.json
L3_OUTPUT := outputs/l3-results.json

.DEFAULT_GOAL := help
.PHONY: help setup python-deps node-deps env config server plugin-install test level-1 level-2 level-3 l1 l2 l3

help:
	@echo "Harness-aware eval example"
	@echo
	@echo "Setup"
	@echo "  make setup            Install Python and Node deps, write .env and Codex config"
	@echo
	@echo "Run"
	@echo "  make level-1          Direct tool check (no model, no server)"
	@echo "  make level-2          Controlled MCP loop via promptfoo"
	@echo "  make level-3          Full Codex harness via promptfoo"
	@echo
	@echo "Helpers"
	@echo "  make test             Unit tests for the grader and the Level Two provider"
	@echo "  make server           Start the MCP server in the foreground (separate terminal)"
	@echo "  make plugin-install   Install the example plugin into CODEX_HOME"
	@echo
	@echo "Levels Two and Three need the MCP server already running: make server"
	@echo "After setup, set OPENAI_API_KEY in .env before Levels Two and Three."
	@echo "Exact commands for every target live in this Makefile."

setup: python-deps node-deps env config
	@echo
	@echo "Setup complete."
	@set -a && . ./.env && set +a; \
	key="$${OPENAI_API_KEY:-}"; \
	if [ -z "$$key" ] || [ "$$key" = "your-api-key" ]; then \
	  echo "OPENAI_API_KEY is not set in .env. Levels Two and Three need it. Change it manually."; \
	fi

python-deps:
	uv sync

node-deps:
	npm ci

# Copy .env.example once, then rewrite only the two paths that must be absolute
# on this machine. Leaves OPENAI_API_KEY and the rest of the file alone.
env:
	@if [ ! -f .env ]; then cp .env.example .env; fi
	@awk -v home="$(CODEX_HOME)" -v py="$(VENV_PYTHON)" ' \
	  BEGIN { h = 0; p = 0 } \
	  /^CODEX_HOME=/ { print "CODEX_HOME=" home; h = 1; next } \
	  /^PROMPTFOO_PYTHON=/ { print "PROMPTFOO_PYTHON=" py; p = 1; next } \
	  { print } \
	  END { \
	    if (!h) print "CODEX_HOME=" home; \
	    if (!p) print "PROMPTFOO_PYTHON=" py; \
	  }' .env > .env.tmp && mv .env.tmp .env

# Codex requires an absolute marketplace path in config.toml.
config:
	@sed 's|^source = .*|source = "$(MARKETPLACE)"|' \
	  $(CODEX_HOME)/config.toml.example > $(CODEX_HOME)/config.toml

test: python-deps
	uv run pytest -q

server:
	uv run server.py

# Export .env into this process so Codex CLI sees CODEX_HOME and the API key.
plugin-install: node-deps env config
	@set -a && . ./.env && set +a && \
	  CODEX_HOME="$(CODEX_HOME)" npx codex plugin add "$(PLUGIN)"

level-1 l1: python-deps
	uv run level_one.py

# Load .env for EVAL_MODEL / MCP_URL / PROMPTFOO_PYTHON.
# --no-cache so repeats are real model runs, not promptfoo replays.
level-2 l2: setup
	@mkdir -p outputs
	@set -a && . ./.env && set +a && \
	  npx promptfoo eval -c promptfooconfig.yaml --no-cache --output $(L2_OUTPUT)

# Note: on a fresh checkout, this target is expected to fail (exit non-zero), most often for the
# 'consumer-price-index' and 'employment-ambiguous' cases. Both depend on the path the model takes,
# so the count can differ between runs; the recorded run scores three of five. To resolve this,
# refer to "Fixing it" in the README.md, restart the server, and rerun.
# Any other failures indicate an unexpected issue that requires investigation.
level-3 l3: setup plugin-install
	@mkdir -p outputs
	@set -a && . ./.env && set +a && \
	  npx promptfoo eval -c promptfooconfig.codex.yaml --no-cache --output $(L3_OUTPUT)
