# Harness-aware eval example

Companion to the [Harness-Aware Evaluation of Plugins](harness_aware_plugin_evals.ipynb) cookbook.
Refer to the cookbook for the purpose and tradeoffs of each evaluation level.
This README walks through the steps required to run the example.

From the repository root, change to this example directory before running the commands below:

```bash
cd examples/partners/harness_aware_plugin_evals
```

The notebook `harness_aware_plugin_evals.ipynb` runs the article top to bottom without an API key.
Open it with `uv run jupyter lab harness_aware_plugin_evals.ipynb`. It syncs its own dependencies
from `uv.lock`, checks Level One live, and replays the recorded runs under `data/` through the same
graders. Setting `RUN_LIVE=1` in `.env` runs Level Two and the Level Three baseline with paid API
calls. The guided Level Three result remains recorded unless you reproduce the steps in
"Fixing it" below. Only live Levels Two and Three require an API key.

Every install, config, and run step is a Make target.
See the [Makefile](Makefile) for the actual commands.

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/).
- Python 3.11+ (`uv python install 3.11`).
- [Node.js and npm](https://nodejs.org/en/download): Node.js 20.20.x or later in the 20.x line, or 22.22.0 or later, as required by the locked promptfoo version. npm ships with Node.js.
- An OpenAI API key for Levels Two and Three
- Levels Two and Three can incur additional cost. With the default settings in this example it is roughly $0.01 per run

## Setup

```bash
make setup
```

That installs Python and Node dependencies, creates `.env` from `.env.example`
if needed, writes absolute `CODEX_HOME` and `PROMPTFOO_PYTHON` into `.env`, and
generates Codex `config.toml` with the local marketplace path.

Then set `OPENAI_API_KEY` in `.env`. Levels Two and Three use it.

`PROMPTFOO_PYTHON` must point at this project's virtualenv. Promptfoo runs the
Python provider and assertions in its own worker; if it picks another
interpreter, the run hangs on a missing import instead of failing cleanly.

## Level One

Direct `resolve` calls on the structured `indicator` field.
No model, no API key, no MCP server. The script exits non-zero if any case fails.

```bash
make level-1
```

## MCP server for Levels Two and Three

Those levels call the fixture server over HTTP on `127.0.0.1:8000`. It answers from a handful of
hardcoded series, so it runs offline and needs no BLS API key. Start it in a **separate terminal**
from this directory and leave it running:

```bash
make server
```

You can stop it with Ctrl-C when the evals are done.

## Level Two

A model drives the MCP tools in a small function-calling loop through promptfoo.
Requires the server from the other terminal.

```bash
make level-2
```

Results go to `outputs/l2-results.json`. Open traces with `npx promptfoo view`.

## Level Three

The same queries through the Codex SDK provider, with the example plugin installed
into the local `CODEX_HOME`. Requires the server from the other terminal.
Installs the plugin, then runs promptfoo.

```bash
make level-3
```

Results go to `outputs/l3-results.json`. Open traces with `npx promptfoo view`.

In the saved evaluation results supplied with this example, `consumer-price-index` and `employment-ambiguous` pass at Level Two and fail at Level Three. The Level Two loop instructs the model not
to invent series IDs and to ask when candidates tie. Nothing tells Codex the same, so it supplies a
CPI series ID from its own knowledge. For the employment case, Codex may narrow the request before
calling `resolve`, choose one of the tied candidates afterward, or fetch both. The exact path varies
between runs, but each retrieves at least one series instead of stopping to clarify, so the grader
fails it.

The recorded run under `data/l3-trace-before.json` scores three out of five. Both cases depend on
the path the model takes, so a fresh run can land on a different count.

### Fixing it

The MCP server can publish this guidance in its `instructions` field. Define the text in
`server.py` and pass it to the server:

```python
GUIDANCE = """Answer only from this catalog. Call resolve first, passing the indicator the user
asked about without narrowing it. Pass fetch_bls_data only the series IDs that resolve returned,
never one from your own knowledge. If resolve returns no candidate, say the data is unavailable. If
several candidates tie for the best confidence, do not call fetch_bls_data at all. Name them and ask
which one the user wants."""

mcp = FastMCP("BLS evaluation fixture", instructions=GUIDANCE)
```

Servers send `instructions` in the `initialize` response. Codex reads that field and passes it to
the model, so the guidance reaches Level Three without any change to the tools or the resolver.
Restart the server and run `make level-3` again. In the included recorded run (`data/l3-trace-after.json`), all five cases pass.
The same behavior change can be observed in the ChatGPT desktop app.

The Level Two loop never reads that field, and relies on its own system prompt instead. The same
text sits on the same server for both levels, and only the level whose harness reads it is
affected.

`CODEX_HOME` must be the local one, generated at setup. Otherwise Codex
starts with the user default home, the plugin is missing, and the model cannot
call `resolve` or `fetch_bls_data`.

## Helpers

```bash
make help              # target list
make test              # grader and Level Two provider unit tests
```

## Environment

| Variable | Role |
|---|---|
| `OPENAI_API_KEY` | Required for Levels Two and Three |
| `MCP_URL` | MCP endpoint for Level Two; the server reads it from its process environment |
| `EVAL_MODEL` | Model id for promptfoo |
| `EVAL_REASONING_EFFORT` | Reasoning effort passed to the provider |
| `PROMPTFOO_PYTHON` | Interpreter for promptfoo's Python workers |
| `CODEX_HOME` | Isolated Codex home with the plugin installed |

Level Two reads `MCP_URL` from `.env`. The `make server` target does not load `.env`, so when
changing the endpoint, also pass it to the server, for example:

```bash
MCP_URL=http://127.0.0.1:8001/mcp make server
```

Level Three reads the URL from the plugin's own `.mcp.json`. Update that URL too so both levels
connect to the same server.

## Layout

| Path | Role |
|---|---|
| `server.py` | Fixture MCP server (`resolve`, `fetch_bls_data`) |
| `level_one.py` | Level One runner |
| `provider.py` | Level Two function-calling loop |
| `promptfooconfig.yaml` | Shared corpus and Level Two wiring |
| `promptfooconfig.codex.yaml` | Level Three Codex provider |
| `eval_grading.py` | Shared grader for Levels Two and Three |
| `data/` | Recorded promptfoo runs behind the article's numbers |
| `harness_aware_plugin_evals.ipynb` | The article, executed offline |
| `tests/` | Unit tests for the grader and the Level Two provider |
| `.codex-home/` | Isolated Codex home and plugin marketplace |
