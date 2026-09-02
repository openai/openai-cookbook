.PHONY: test lint typecheck notebook-smoke demo

test:
	cd ../.. && pytest -q

lint:
	cd ../.. && ruff check .
	cd ../.. && ruff format --check .

typecheck:
	cd ../.. && mypy topoattack

notebook-smoke:
	cd ../.. && python -m jupyter nbconvert --to notebook --execute examples/topology/jailbreak_topology.ipynb --output jailbreak_topology.executed.ipynb

demo:
	cd ../.. && python -m topoattack analyze --prompts examples/topology/prompts.txt --out examples/topology/out/
