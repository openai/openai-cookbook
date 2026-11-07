# Reject stale evidence after source revisions

Author: Sophia Cole (QueenFi703). MIT licensed; see LICENSE.

Read `evidence_revision_gate.ipynb` for the tutorial. All data is fictional.
The central distinction is that an exact quote can survive while the source's
surrounding context changes. The application binds findings to the immutable
retrieval snapshot and flags any later byte-level revision. Passing the gate
is not proof of truth, semantic support, freshness on the web, or authenticity.

## Setup

Python 3.10+; tested with Python 3.12.14. From this directory:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m unittest discover -s . -p 'test_*.py' -v
python revision_gate.py
python verify_notebook.py
```

The utility tests also work without dependencies: 18 tests run and two optional
SDK-boundary tests skip when the OpenAI SDK is absent. With requirements installed,
all 20 run offline. No key or network request is needed by the tests.

`verify_notebook.py` validates notebook structure and executes its plain Python
cells sequentially without a kernel. For full Jupyter validation in a normal
local environment, run every notebook cell top to bottom. Alternatively:

```python
import nbformat
from nbclient import NotebookClient
nb = nbformat.read('evidence_revision_gate.ipynb', as_version=4)
NotebookClient(nb, timeout=60, kernel_name='python3').execute()
```

Clear execution counts before submitting. Synthetic outputs can remain for review.

## Expected offline example output

```text
Unchanged snapshot: snapshot_matches_not_semantically_verified
Quote still exists: True
Revised snapshot: source_changed
```

## Optional live extraction

Keep LIVE=False for offline review. To test live, set OPENAI_API_KEY in your
shell using your secret-management workflow, then explicitly set LIVE=True in
the notebook. Never paste a key into a cell or commit it. The model defaults to
gpt-6-astra and is configurable; verify your account's model access. The live
path transmits the synthetic sources to OpenAI and may cost money. It uses a
20-second SDK timeout, max_retries=0, max_output_tokens=512, and store=False.
The timeout is not an end-to-end spending guarantee. A timeout can leave the
server outcome uncertain; no retry is automatic. No live call was made while
preparing this contribution. The mocked SDK test verifies request construction,
not remote model availability or API success.

## Verified locally

- 20 offline tests passed with dependencies installed.
- nbformat validation and all notebook Python cells passed sequential execution.
- The current upstream checker `is_valid_notebook` accepted this notebook.
- Full Jupyter-kernel execution could not run in the preparation sandbox because
  socket creation is restricted. This remains a pre-merge check.

For a checkout of the official Cookbook, also run its
`python .github/scripts/check_notebooks.py` after the changes are present on a
branch relative to origin/main. The local draft is not an upstream Git checkout.
