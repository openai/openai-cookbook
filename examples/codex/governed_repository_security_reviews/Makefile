PYTHON ?= python3
export PYTHONDONTWRITEBYTECODE := 1
.DEFAULT_GOAL := demo
.PHONY: demo notebook verify verify-docker context-eval soak

demo:
	$(PYTHON) -B scripts/run_security_review_cookbook.py --cycles 2

notebook:
	$(PYTHON) -B scripts/execute_notebook.py governed_repository_security_reviews.ipynb

verify:
	$(PYTHON) -B scripts/verify_cookbook_example.py

verify-docker:
	$(PYTHON) -B scripts/verify_cookbook_example.py --docker

context-eval:
	$(PYTHON) -B scripts/evaluate_threat_context.py

soak:
	$(PYTHON) -B scripts/run_security_stress_soak.py --cycles 2
