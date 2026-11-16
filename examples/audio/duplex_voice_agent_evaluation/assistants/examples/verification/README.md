# Offline verification and transfer example

Before using evaluation scores to improve a voice agent, check what those scores
establish. A requested tool, an actual application result and an accurate spoken
explanation each need their own evidence.

This example shows how to test those distinctions. Eight verification and transfer
scenarios define the intended outcomes. Regression tests introduce wrong
arguments, missing execution, unwanted or duplicate actions, and a false spoken
claim. Together, they show which failures the existing CRAWL graders detect and
which require independent semantic review.

Start with one task: correctly rejecting a date of birth that does not match.

## Follow a date-of-birth mismatch

In the `dob_mismatch` scenario, the caller gives September 1, 1992. The
application's independent fictional record contains September 5, 1990.

1. The scripted assistant requests a check of the caller's supplied date.
2. The application checks its private record and returns a mismatch. The caller
   remains unverified.
3. The scripted response reports that actual result.
4. The evaluator checks the requested date, tool execution and final application
   state against the scenario's expectations.

This should pass the action and state checks: the intended outcome is a correct
rejection. The application record is independent of the expected verdict and
stays private to the application.

Those action and state checks do not assess what the assistant says. A false
verification claim needs a separate assessment of the response's meaning. The
regression tests make this limit explicit: detecting speech after a tool result
does not establish truthful communication.

## Run the example

The example uses scripted responses, local tools and tone audio. It makes no
model, speech-synthesis or judge API calls and needs no API key. From a source
checkout, with Python 3.12 or later and `uv` installed:

```bash
cd examples/audio/duplex_voice_agent_evaluation
env -u VIRTUAL_ENV uv sync --locked
env -u VIRTUAL_ENV uv run python -m assistants.examples.verification --out /tmp/verification-example-001
```

Dependency setup may download packages. The example itself always runs offline.
Choose a new output directory outside the checkout for each run; existing runs
are never overwritten. To run just the mismatch fixture, add
`--scenario dob_mismatch`.

Run the focused application and harness tests from the same directory:

```bash
env -u VIRTUAL_ENV uv run pytest -q assistants/tests/test_verification_example.py crawl_harness/tests/test_verification_example.py
```

## Interpret the results

The eight scenarios cover matching, mismatched, incomplete and corrected dates;
a requested, declined or canceled transfer; and a transfer-service failure.
Their native fixture assessments should pass. A caller may request a person
regardless of verification state; these fixtures illustrate tool behavior, not a
production authentication policy.

Passing these fixtures verifies the exercised integration and deterministic
checks. Applicable semantic grades remain `not_assessed`. In particular, the
existing deterministic post-tool speech check confirms that speech followed a
result; it does not establish that the words agree with that result. Offline
scripts and tones do not measure live model behavior or speech recognition.

Use the native artifacts to inspect the evidence behind each assessment:

- `results.json`: native schema 2.0 results, including per-scenario checks,
  compact tool observations, artifact links and `assessment.passed`.
- `transcripts/<scenario_id>.json`: detailed transcript, tool executions and
  results, initial and final state, and grades.
- `events/<scenario_id>.jsonl`: session events.
- `audio/<scenario_id>/`: `input.wav`, `output.wav`, `conversation.wav` and
  `conversation.transcript.txt`. The WAV files contain synthetic tones.

## Adapt the example

Keep three responsibilities separate when adding your own application: the
application determines what happened, scenarios define what should happen, and
graders compare the evidence with those expectations. This example supplies the
application through the existing assistant resource boundary and uses the
harness's existing scoring and report format.

| Component | Responsibility |
| --- | --- |
| [`scenarios.json`](scenarios.json) | Canonical `Scenario` inputs, initial state and expected tool calls, state and answers. |
| [`resources.py`](resources.py) | Independent fictional records, exact-request offline scripts and application resources for each scenario. |
| [`application.py`](application.py) and [`tools.json`](tools.json) | Verification and transfer behavior, tool execution records and state snapshots. |
| [`frontend.txt`](frontend.txt) and [`backend.txt`](backend.txt) | The application's public-facing instructions. Private records are kept out of these prompts and scenario facts. |
| [CRAWL](../../../crawl_harness/README.md) | Session lifecycle, evidence collection, existing graders and native result serialization. |

The offline scripts select operations from exact fixture requests. They are
deliberate test inputs, not a language-understanding implementation. Use the
existing harness interfaces when connecting your own assistant; the example
launcher has no live mode.

Before using this application pattern for a live evaluation, validate the
graders with labeled successes and failures and review the unassessed dimensions.
See [Validate graders before scaling runs](../../../../voice_agent_evaluation.md#validate-graders-before-scaling-runs)
in the evaluation guide.
