# Route customer-support messages with the Decisions API

Route a small batch of public BANKING77 messages into four support queues using
`gpt-6-luna` and `POST https://api.openai.com/v1/decisions`. Display each actual
response, selected route, confidence, and request latency. Refusals or unusable
answers are marked `human_review`; the demo does not execute customer actions.

## Requirements

Python 3.10+, Bash for the hidden-input launcher, and an OpenAI project API key
with Decisions access. Jupyter is needed only for the interactive notebook.
The example uses the Python standard library. There are no npm, Promptfoo, or
other runtime package dependencies.

## Run a small live batch

From the repository root:

```bash
bash examples/decisions/run_demo.sh
```

Enter your key at the hidden prompt, or supply `OPENAI_API_KEY` through the
Terminal environment. The launcher downloads one public CSV, verifies its hash,
and makes **four billable API requests**, one message per support queue. It
prints the real responses and parsed routes. It has no automatic retries;
inspect failures before repeating a paid run.

Control the batch size:

```bash
# Two public messages per queue: 4 * 2 = 8 API requests
bash examples/decisions/run_demo.sh --samples-per-route 2

# One custom message: exactly 1 API request, no dataset download
bash examples/decisions/run_demo.sh --message "I forgot my app passcode."
```

The options are mutually exclusive. Counts must be positive and cannot exceed
available unique examples in the source CSV. The launcher disables shell tracing
before key handling and clears its key on exit. A key exported in the parent
shell remains there until you unset it. Do not put keys in source, cells, or CLI
arguments. Each live run makes new paid requests and prints its results directly;
there are no generated reports to clean or archive.

## Preview without network calls

```bash
python3 examples/decisions/run_customer_request_routing.py
```

This previews four hand-written messages and their request bodies. It does not
fetch BANKING77 or invent API responses. With `OPENAI_API_KEY` securely configured,
add `--live` for the public-data batch:

```bash
python3 examples/decisions/run_customer_request_routing.py --live
python3 examples/decisions/run_customer_request_routing.py --live --samples-per-route 2
```

The source dataset label is displayed as local context. Only message text and
the routing question are sent to the model. The demo has no calibration/test
split, confidence optimization, automated grading, or benchmark accuracy claim.

## Open the notebook

Open [customer_request_routing.ipynb](customer_request_routing.ipynb) in VS Code
or Jupyter, with its kernel started in the repository root or this directory.
It previews requests without network calls by default. Set `OPENAI_API_KEY`
securely and `RUN_DECISIONS_API=1` before starting the kernel for four live
requests. Set `DECISIONS_SAMPLES_PER_ROUTE=2` for eight, then restart the kernel.
The notebook and CLI import the same [routing helpers](routing.py).

A valid choice answer includes its selected queue, confidence, and per-choice
probabilities. Confidence is not a guarantee of correctness. The four queues
assume an in-scope message; a production router also needs unsupported/ambiguous
request handling and representative evaluation before enabling downstream actions.
A few displayed examples do not establish production performance.

## Data and attribution

BANKING77 is published by PolyAI and attributed to Iñigo Casanueva, Tadas Temcinas,
Daniela Gerz, Matthew Henderson, and Ivan Vulić (2020),
[Efficient Intent Detection with Dual Sentence Encoders](https://arxiv.org/abs/2003.04807).
The publisher distributes it under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/);
see the [source repository](https://github.com/PolyAI-LDN/task-specific-datasets/tree/57ec275d8078af65b7731c2a98be812d844a6d6b)
and [license text](https://github.com/PolyAI-LDN/task-specific-datasets/blob/57ec275d8078af65b7731c2a98be812d844a6d6b/LICENSE).

The demo pins commit `57ec275d8078af65b7731c2a98be812d844a6d6b`, verifies the test
CSV's SHA-256 hash, filters to four source intents, removes normalized duplicates
and conflicting labels, and samples deterministically. Original message wording
and source labels are retained. These are public benchmark messages, not private
customer records. CSVs are not committed, and no author endorsement is implied.
Model exposure to the public benchmark during training is unknown.

## Check the application code

```bash
python3 -m unittest discover -s examples/decisions -p 'test_*.py'
```

These tests mock the network. They check request budgets, sampling and checksum
validation, credentials, refusal/invalid-answer handling, and error behavior.
They make no paid requests and do not evaluate model quality.

Files: the walkthrough notebook; `routing.py` for shared helpers;
`run_customer_request_routing.py` for the CLI; `run_demo.sh` for hidden key input;
and `test_customer_request_routing.py` for offline application checks.

See the [Decisions guide](https://developers.openai.com/api/docs/guides/decisions)
for current availability, pricing, and API details.
