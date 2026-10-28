# Route customer-support messages with the Decisions API

Build a customer-support router that reads a message and selects the queue
responsible for it. This example sends ten public banking-support messages to
the Decisions API and displays each actual response, selected queue, and confidence.

Start with the [notebook](customer_request_routing.ipynb) for a guided walkthrough,
or use the [Terminal demo](#1-run-ten-customer-support-examples). Both run the
same ten examples through shared Python helpers.

## What is the Decisions API?

The [OpenAI Decisions API](https://developers.openai.com/api/docs/guides/decisions)
evaluates evidence against questions you define and returns typed answers your
application can use. For example, supply a customer message and ask which of four
support queues owns it. The API returns a selected queue; your application decides
how to use that answer.

You choose the question type:

| Type | Purpose | Example |
| --- | --- | --- |
| `choice` | Select one of your allowed options | Which support queue owns this message? |
| `predicate` | Estimate whether a condition holds | Does the message describe a duplicate charge? |
| `score` | Rate input against ordered levels | How severe is the reported issue? |

Each request has three parts:

- `model`: the model evaluating the request, `gpt-6-luna` in this demo.
- `input`: the customer message to evaluate.
- `questions`: the routing instructions and allowed queue choices.

The response contains an `answers` array. A question's `name` links it to its
answer. For a `choice` question, the answer includes the selected `choice`,
per-choice `probabilities`, and a separate `confidence` value. A question can also
return a refusal.

This example uses **`choice`**, model **`gpt-6-luna`**, and
**`POST https://api.openai.com/v1/decisions`**. It sends JSON directly using
Python's standard HTTP library; no SDK installation is needed. See the
[Decisions guide](https://developers.openai.com/api/docs/guides/decisions) for
concepts and current availability, the
[create-decision reference](https://developers.openai.com/api/reference/resources/decisions/methods/create)
for the exact schema, and
[pricing and availability](https://developers.openai.com/api/docs/guides/decisions#pricing-and-availability)
before running paid requests.

## Use case: route incoming banking-support messages

A banking support team receives messages about fees, account access, transfers,
and card delivery. Before a specialist can help, each message needs an owner.
This demo models that triage step: one message goes in, and a queue selection
comes back.

The routing question defines four choices with descriptions explaining their
scope. These messages are included in the ten-example batch:

| Example message | Intended queue |
| --- | --- |
| "I was charged a fee for a card payment. Why?" | `card_payment_fees` |
| "Tell me how to reset the passcode." | `account_access` |
| "I need to cancel an incorrect transaction." | `transfer_cancellation` |
| "How long should my new card take to arrive?" | `card_delivery` |

The demo runs **ten bundled BANKING77 messages covering all four queues**.
For each message, it:

1. Builds a named routing question and sends the message to Decisions.
2. Displays the actual response, including choice probabilities and confidence.
3. Validates the answer's type, name, allowed route, and confidence range.
4. Prints the route, confidence, and elapsed request time, or `human_review` for
   a refusal or unusable answer.

Only the message and question go to the model. The dataset's source label is
printed as local context. The demo displays routing decisions. Connecting them
to a ticketing system or customer workflow is a separate application step.

## Customer-support flow

Customers describe their problem in their own words. Decisions selects the
support queue that best fits the main request: payment fees, account access,
transfer cancellation, or card delivery.

![Customer messages are routed through Decisions to the card-payment fees, account access, transfer cancellation, or card delivery support team, with human review when a routing decision is unavailable.](../../images/decisions-customer-support-use-case.png)

In this demo, a queue selection is printed alongside the actual API response and
confidence. A refusal or unusable answer is printed as `human_review`. In a
support application, the next step would be assigning a ticket to that team;
the team would handle the customer's request. The demo stops at recommending
the queue and does not modify accounts or tickets.

HTTP, network, and invalid-JSON errors stop the run. Confidence is not a guarantee
of correctness; see [Understand the result](#understand-the-result) for the limits
of this example.

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

Paste your API key at the hidden prompt. The launcher loads ten bundled public
messages and makes **ten billable Decisions requests**. It prints each input,
actual response JSON, parsed route/confidence, and latency. A successful full run
ends after the result for `Example 10/10` and returns to your shell prompt.

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
