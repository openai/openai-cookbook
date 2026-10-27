# Decisions API routing demo and evaluation

Route a customer-support message into one of four queues using the native
Decisions API, then measure routing quality against labeled public examples.
This example includes a Terminal demo, a walkthrough notebook, and an optional
Promptfoo evaluation with a local HTML report.

The model is `gpt-6-luna`, and requests go to
`POST https://api.openai.com/v1/decisions`. The API key is supplied through
`OPENAI_API_KEY` or hidden Terminal input. No real key is included in source.

## Quick demo: one request

Requirements: Python 3.10+, Bash, and a project API key with Decisions access.
No SDK, Node.js, Promptfoo, or Jupyter installation is required for this demo.

From the repository root:

```bash
bash examples/decisions/run_demo.sh
```

Paste your API key at the hidden prompt. The demo makes **one billable request**
using the fixed message, "My new card has not arrived. Can you help me track its
delivery?" It prints the request body, actual JSON response, extracted queue,
confidence, and request latency. A correct route for this message is
`card_delivery`; confidence and timing may vary. The request has no automatic
retries. This demonstration is separate from the labeled evaluation dataset.

The shell launcher clears its copy of the key on exit. If you exported a key
in your parent Terminal, unset it there when finished. Never paste a key into a
source file or share it in logs.

## Small notebook evaluation: 20 requests by default

To execute every notebook code cell against the live API, first securely export
`OPENAI_API_KEY` in your Terminal, then run from the repository root:

```bash
.venv/bin/python -u examples/decisions/run_customer_request_routing.py --live
```

The default is **20 billable requests**: 2 calibration and 3 test examples for
each of four routes (8 calibration + 12 test). Control the size explicitly:

```bash
# 4 * (1 + 2) = 12 requests
.venv/bin/python -u examples/decisions/run_customer_request_routing.py --live \
  --calibration-per-route 1 --test-per-route 2

# 4 * (10 + 20) = 120 requests, matching the recorded extended evaluation
.venv/bin/python -u examples/decisions/run_customer_request_routing.py --live \
  --calibration-per-route 10 --test-per-route 20
```

The runner prints the configured request budget before execution. Counts must be
positive and cannot exceed the available unique examples in the source dataset.
The small default illustrates the workflow; it is too small to establish reliable
production thresholds or accuracy. Offline mode remains 24 invented fixtures with
zero network calls. The notebook itself uses the same small live defaults; set
`DECISIONS_CALIBRATION_PER_ROUTE` and `DECISIONS_TEST_PER_ROUTE` before starting a
Jupyter kernel to change them there.

## Extended Promptfoo evaluation: 120 requests

The optional Promptfoo companion prepares the pinned public dataset, validates
the configuration, calls Decisions, grades the answers locally, and creates a
local HTML report. Read its [setup instructions](promptfoo/README.md) and
[security review](promptfoo/SECURITY_REVIEW.md) first: its npm dependency audit
currently has unresolved advisories.

After installing the pinned companion dependency:

```bash
bash examples/decisions/promptfoo/run_eval.sh
```

Each invocation clears the previous generated configuration and reports and
makes **120 new billable requests**, with no automatic retries. No manual
cleanup, temporary directory, or archive step is required. The fixed split is
40 calibration examples and 80 test examples. Repeating it checks
reproducibility, not performance on a new unseen holdout.

Expected labels stay local. An exact-match grader compares the returned queue
with the dataset label; no AI judge or separate grading API is used. Calibration
selects a confidence threshold before the test split is scored. Refusals and
unusable answers go to human review in the policy metrics.

Outputs are in `examples/decisions/promptfoo/.generated/`:

- `report.html`: messages, model answers, expected routes, grades, and latency.
- `results.json`: detailed Promptfoo results and responses.
- `summary.json`: separate test metrics, selected threshold, and per-route results.
- `manifest.json`: dataset commit/hashes, question hash, and selected case IDs.

To summarize the latest saved run without more API calls:

```bash
python3 examples/decisions/promptfoo/routing_eval.py summarize
```

## Read the code and run offline

- [Walkthrough notebook](customer_request_routing.ipynb): request schema, public
  data sampling, response validation, calibration, metrics, and observed results.
- [Python runner](run_customer_request_routing.py): executes notebook code without
  Jupyter; offline by default, with explicit `--preview` and `--live` modes.
- [Promptfoo preparation and summary](promptfoo/routing_eval.py): creates the
  config, cleans generated outputs, and checks completed result files.
- [End-to-end shell runner](promptfoo/run_eval.sh): handles clean execution and
  hidden key input with visible output.

From the repository root, run the notebook in its no-network fixture mode:

```bash
python3 examples/decisions/run_customer_request_routing.py
python3 -m unittest discover -s examples/decisions -p 'test_*.py'
python3 -m unittest discover -s examples/decisions/promptfoo -p 'test_*.py'
```

Offline fixtures are hand-authored examples with invented predictions. They test
the evaluation code and are not evidence of model performance.

## Data, results, and limits

Live evaluation uses four intents from public BANKING77, attributed to Casanueva
et al. (2020). Source CSVs are pinned and checksum-verified. The
[companion README](promptfoo/README.md#data-and-scope) documents the
[CC BY 4.0 license](promptfoo/DATA_LICENSE.txt), source citation, and our sampling
and label changes. No private customer records are included.

The observed runs correctly routed all 80 test cases, with one calibration
refusal sent to review. This small four-intent result does not establish
production accuracy or out-of-scope detection. The selected threshold was zero;
the runs do not show a benefit from confidence filtering. Model exposure to the
public dataset during training is unknown.

See the [official Decisions guide](https://developers.openai.com/api/docs/guides/decisions)
for API details and current availability.
