# Route customer-support messages with the Decisions API

Learn what the Decisions API returns and use it to route a small batch of public
banking-support messages. This example includes an interactive notebook and a
Terminal demo that share the same Python helpers.

## What is the Decisions API?

The [OpenAI Decisions API](https://developers.openai.com/api/docs/guides/decisions)
evaluates input against questions you define and returns typed answers. Use it
when an application needs a bounded judgment, such as a category, a condition,
or a rating. Your application decides what to do with the answer.

You choose the question type:

| Type | Purpose | Example |
| --- | --- | --- |
| `choice` | Select one of your allowed options | Which support queue owns this message? |
| `predicate` | Estimate whether a condition holds | Does the message describe a duplicate charge? |
| `score` | Rate input against ordered levels | How severe is the reported issue? |

A request contains `model`, `input`, and `questions`. Responses contain an
`answers` array, with the question's `name` echoed in its answer. A `choice`
answer includes the selected `choice`, per-choice `probabilities`, and a
`confidence` value. A question can also return a refusal.

This example uses **`choice`**, model **`gpt-6-luna`**, and
**`POST https://api.openai.com/v1/decisions`**. It sends JSON directly using
Python's standard HTTP library; no SDK installation is needed. See the
[Decisions guide](https://developers.openai.com/api/docs/guides/decisions) for
concepts and current availability, the
[create-decision reference](https://developers.openai.com/api/reference/resources/decisions/methods/create)
for the exact schema, and
[pricing and availability](https://developers.openai.com/api/docs/guides/decisions#pricing-and-availability)
before running paid requests.

## What does this demo do?

A support application needs to determine which queue should handle a customer's
message. The demo defines four choices with descriptions explaining their scope.
These example messages illustrate the intended mapping:

| Example message | Intended queue |
| --- | --- |
| "Why was a fee added to my card purchase?" | `card_payment_fees` |
| "I forgot the passcode for the app." | `account_access` |
| "Can I cancel a transfer I just made?" | `transfer_cancellation` |
| "My new card has not arrived." | `card_delivery` |

The runnable demo uses public BANKING77 messages. It runs **ten bundled messages covering all four queues**. For each message, it:

1. Builds a named routing question and sends the message to Decisions.
2. Displays the actual response, including choice probabilities and confidence.
3. Validates the answer's type, name, allowed route, and confidence range.
4. Prints the route, confidence, and elapsed request time, or `human_review` for
   a refusal or unusable answer.

Only the message and question go to the model. The dataset's source label is
printed as local context. The code does not reply to customers, create tickets,
modify accounts, or execute transactions. This is a routing demonstration with
no calibration/test split, threshold selection, or model-quality grading.

## Before you start

- Use Python 3.10 or later. The Terminal launcher also uses Bash.
- For live requests, use an OpenAI project API key with Decisions access.
- To run the notebook interactively, use Jupyter or VS Code with a Python kernel.

The demo requires no third-party Python packages, npm packages, or Promptfoo.
Run the following commands from the **root of the openai-cookbook repository**.

## 1. Run ten customer-support examples

```bash
bash examples/decisions/run_demo.sh
```

Paste your API key at the hidden prompt. The launcher loads ten bundled public messages and makes
**ten billable Decisions requests**. It
prints each input, actual response JSON, parsed route/confidence, and latency.

The key can also come from an existing `OPENAI_API_KEY` environment variable.
The launcher disables shell tracing before handling it and clears its copy on
exit. A key exported in the parent shell remains there until you unset it.
Never put a real key in source, notebook cells, or CLI arguments, or share it in
logs. Each live invocation makes new paid requests.

## 2. Try your own message (optional)

```bash
bash examples/decisions/run_demo.sh --message "I forgot my app passcode."
```

This sends exactly one request. To rerun the ten examples, run the original
command again. There are no sample-count settings to configure.

With `OPENAI_API_KEY` securely configured, you can also run Python directly:

```bash
python3 examples/decisions/run_customer_request_routing.py
```

Results are printed to Terminal; there are no generated reports to clean or
archive. Requests have a 30-second timeout and **no automatic retries**. Inspect
errors before rerunning: an interrupted request may already have been processed.

## Understand the result

The full response shows what the API returned. The final summary reads
`answers[0].choice` and `answers[0].confidence` after validating them. For a
card-delivery message, the intended route is `card_delivery`; actual choices,
confidence, and timing can vary.

A refusal can arrive with a successful HTTP response. Refused or unusable answers
produce `human_review` with null confidence. HTTP, network, and invalid-JSON errors
stop the run. Request latency includes network and connection setup and is not
an inference-only benchmark.

Confidence is not a correctness guarantee. This demo assumes each message belongs
to one of four queues and imposes no unvalidated confidence cutoff. Production
routing also needs an unsupported/ambiguous-message policy and representative
evaluation before enabling downstream actions. A few displayed examples do not
establish production performance.

## Run the notebook instead

1. Open [customer_request_routing.ipynb](customer_request_routing.ipynb) in VS Code
   or Jupyter and select a Python 3.10+ kernel. Start the kernel in the repository
   root or `examples/decisions/`.
2. Select **Run All**. The notebook loads the ten bundled messages and displays
   the request body, then asks for your API key with hidden input if needed.
3. Enter the key to see ten actual model responses and parsed routing decisions.
   Do not paste a real key into a code cell.

Every full run makes ten new billable requests. An existing `OPENAI_API_KEY`
environment variable is also supported. The notebook clears its key variable
after the request loop; an existing environment variable remains in the kernel.

The notebook and CLI share the same messages, question, and response validation
from `routing.py`.

## Find the code

| File | Purpose |
| --- | --- |
| [customer_request_routing.ipynb](customer_request_routing.ipynb) | Explains and executes the routing workflow step by step |
| [customer_requests.json](customer_requests.json) | Ten public messages and source/license attribution |
| [routing.py](routing.py) | Loads the ten messages, builds requests, sends API calls, and validates answers |
| [run_customer_request_routing.py](run_customer_request_routing.py) | Runs the public batch or a custom message and displays actual responses |
| [run_demo.sh](run_demo.sh) | Collects the key with hidden input and starts the live demo |
| [test_customer_request_routing.py](test_customer_request_routing.py) | Runs offline application checks with mocked network calls |
| `README.md` | Introduces the API, use case, commands, outputs, and data source |

The main helpers are `load_demo_messages()`, `build_request()`,
`request_prediction()`, and `parse_prediction()`. Change `QUESTION` in `routing.py`
to adapt the queue choices and descriptions to your application.

## Optional developer checks

```bash
python3 -m unittest discover -s examples/decisions -p 'test_*.py'
```

You do not need to run these tests to use the demo. They are developer checks
for request budgets, bundled-data validation, credentials,
refusals, invalid answers, and error handling. They make no paid requests and do
not evaluate model quality.

## Data and attribution

BANKING77 is published by PolyAI and attributed to Iñigo Casanueva, Tadas Temcinas,
Daniela Gerz, Matthew Henderson, and Ivan Vulić (2020),
[Efficient Intent Detection with Dual Sentence Encoders](https://arxiv.org/abs/2003.04807).
The publisher distributes it under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/);
see the [source repository](https://github.com/PolyAI-LDN/task-specific-datasets/tree/57ec275d8078af65b7731c2a98be812d844a6d6b)
and [license text](https://github.com/PolyAI-LDN/task-specific-datasets/blob/57ec275d8078af65b7731c2a98be812d844a6d6b/LICENSE).

The ten messages in `customer_requests.json` are selected from four intents in
the test CSV at commit `57ec275d8078af65b7731c2a98be812d844a6d6b`.
The source CSV's SHA-256 was verified when preparing the selection:
`d12d6e3bc4c3103966ae786dc435913c0c563dfa328f5a3646d0e62cfeeb474d`.
Original wording and source labels are retained. The full CSV is not bundled;
no dataset download is needed to run the demo. No author endorsement is implied.
These are public benchmark messages, not private customer records; model exposure
to this public dataset during training is unknown.
