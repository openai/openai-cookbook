SHELL := /bin/bash

UV ?= uv
PYTHON := $(UV) run --no-sync python
NPM ?= npm
HOST ?= 127.0.0.1
PORT ?= 8732
LOG_DIR ?= state/logs
PID_FILE ?= state/deployment-manager.pid
LOG_FILE ?= $(LOG_DIR)/deployment-manager.log

.PHONY: help setup frontend-install build run start stop restart health logs deploy py-compile clean

help:
	@echo "Targets:"
	@echo "  setup      Install Python and frontend dependencies"
	@echo "  build      Compile backend files and build the React frontend"
	@echo "  run        Build and run the Deployment Manager in the foreground"
	@echo "  start      Build and start the Deployment Manager in the background"
	@echo "  stop       Stop the background Deployment Manager"
	@echo "  restart    Restart the background Deployment Manager"
	@echo "  health     Check the manager health endpoint"
	@echo "  logs       Tail the manager log"
	@echo "  deploy     Deploy PROJECT_PATH through the manager"

node_modules: package.json
	$(NPM) install

frontend-install: node_modules

setup: frontend-install
	$(UV) venv --allow-existing
	$(UV) pip install -e .

py-compile:
	$(PYTHON) -m py_compile app/*.py scripts/*.py

build: setup py-compile
	$(NPM) run build

run: build
	HOST="$(HOST)" PORT="$(PORT)" $(PYTHON) -m app.main

start: build
	@mkdir -p $(LOG_DIR)
	@if curl -fsS http://$(HOST):$(PORT)/api/health >/dev/null 2>&1; then \
		echo "Deployment Manager already running at http://$(HOST):$(PORT)"; \
	else \
		$(PYTHON) scripts/start_manager.py --host $(HOST) --port $(PORT) --log-file $(LOG_FILE) --pid-file $(PID_FILE); \
		echo "Deployment Manager starting at http://$(HOST):$(PORT)"; \
	fi

stop:
	@if [ -f $(PID_FILE) ] && kill -0 $$(cat $(PID_FILE)) >/dev/null 2>&1; then \
		kill $$(cat $(PID_FILE)); \
		rm -f $(PID_FILE); \
		echo "Deployment Manager stopped"; \
	else \
		pid=$$(lsof -tiTCP:$(PORT) -sTCP:LISTEN 2>/dev/null | head -n 1); \
		if [ -n "$$pid" ]; then \
			kill $$pid; \
			echo "Deployment Manager stopped"; \
		else \
			echo "Deployment Manager is not running"; \
		fi; \
	fi

restart: stop start

health:
	curl -fsS http://$(HOST):$(PORT)/api/health
	@echo

logs:
	@mkdir -p $(LOG_DIR)
	@touch $(LOG_FILE)
	tail -f $(LOG_FILE)

deploy:
	@if [ -z "$(PROJECT_PATH)" ]; then \
		echo "PROJECT_PATH is required. Example: make deploy PROJECT_PATH=/path/to/agents-sdk-app"; \
		exit 2; \
	fi
	$(PYTHON) scripts/local_deploy.py $(PROJECT_PATH) --manager-port $(PORT) $(if $(APP_PORT),--app-port $(APP_PORT),) $(if $(NAME),--name "$(NAME)",) $(if $(SANDBOX_BACKEND),--sandbox-backend $(SANDBOX_BACKEND),) $(if $(TARGET),--target $(TARGET),) $(if $(NO_START),--no-start,)

clean:
	rm -rf dist node_modules
