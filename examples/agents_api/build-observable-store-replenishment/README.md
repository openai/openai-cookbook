# Observable store replenishment with the Agents API

This folder contains the runnable support files for the Cookbook example. The
lesson is intentionally narrow: one retail incident continues across two turns
in one managed Agents API session, with application-owned tools, manager
approval, and an inspectable trace.

## Artifact map

| Path | Purpose |
| --- | --- |
| `../build-observable-store-replenishment.ipynb` | Runnable Cookbook notebook |
| `../build-observable-store-replenishment.md` | Registered Cookbook article |
| `replenishment_agent.py` | Reusable two-turn Agents API worker |
| `data/` | Small deterministic retail fixtures |
| `demo/` | Interactive store-manager experience |
| `github-actions/` | Offline checks and an approved live canary |
| `tests/` | Dataset, tool, session, recovery, and decision tests |

The notebook is the executable teaching artifact. The Markdown article sets the
stage, explains the important code, links to the notebook and demo, and closes
with production extensions. Support code keeps fixture loading, durable stream
recovery, and repeated operations out of the short teaching cells.

## Setup

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r examples/agents_api/build-observable-store-replenishment/requirements.txt
export OPENAI_API_KEY="your_api_key"
```

Open the notebook in JupyterLab or VS Code and run it from top to bottom. The
example uses synthetic data; live Agents API cells require an API key.

## Run the checks

```bash
pytest examples/agents_api/build-observable-store-replenishment/tests
pytest examples/agents_api/build-observable-store-replenishment/demo/tests
python .github/scripts/check_notebooks.py
```

## Run the interactive demo

```bash
cd examples/agents_api/build-observable-store-replenishment
uv run demo/main.py --port 8010
```

Open `http://127.0.0.1:8010`. Guided mode is deterministic. Live mode uses the
same worker and exposes the Agents API session and turn IDs for Platform Logs.
