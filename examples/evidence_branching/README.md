# Evidence-driven agent teams

Draft Cookbook contribution by Sophia Cole / ColeWorld. MIT licensed; see LICENSE.
This contribution has not been accepted or endorsed by OpenAI.

## The recipe

Start with two bounded evidence readers. When their records disagree about the
same claim in the same scope, application code creates a specialist task that
queries a relevant source. The scheduler stops creating work when observed
conflicts are resolved by an explicit source policy, sources are exhausted, or a
budget is reached. Duplicate queries do not consume another call. Duplicate
facts do not count as more evidence. Every admitted contradictory record remains
in the result, including after a policy-based resolution.

This is **not a hosted Astra multi-agent API** and does not reproduce an internal
agent orchestration system. It is a small, application-owned Python scheduler.
The offline backend is a deterministic fixture, not an AI model. The optional
`ResponsesSpecialist` transports a bounded evidence-selection task using
`client.responses.create`; it does not provide an API for creating agent teams.

The scheduler is sequential on purpose. A *branch* is a newly created specialist
assignment, not a thread or subprocess. The topic/probe routing table is configured
by the application, but concrete specialist tasks, their conflict context, and
whether they run are determined after observing evidence. This differs from
prelaunching every specialist and merging all answers.

## Run locally

Use Python 3.10 or newer. From this directory:

```bash
python -m unittest discover -s tests -v
python -m pip install -r requirements.txt
python validate_notebook.py
```

Open `evidence_driven_agent_teams.ipynb` in your notebook viewer to follow the
walkthrough. All code cells are offline, contain no credential lookup, and make
no API calls. The validation script validates notebook format, compiles every
code cell, then executes cells in order in a shared Python namespace. That is
**not a full Jupyter-kernel run** and does not exercise kernel transport, notebook
UI, IPython magics, or rich rendering. No socket restriction workaround is used.

Files:

- `evidence_driven_agent_teams.ipynb`: teaching walkthrough with assertions.
- `evidence_teams.py`: immutable evidence records, explicit adjudication policy,
  bounded scheduler, three fictional fixtures, and optional Responses adapter.
- `tests/test_evidence_teams.py`: offline scheduler and fake-client contract tests.
- `validate_notebook.py`: reproducible non-kernel notebook checks.
- `VALIDATION.md`: actual checks and residual gaps for this draft.

## Outcomes, not majority votes

| Outcome | Meaning |
| --- | --- |
| `supported` | All admitted records agree; not a claim of objective truth or exhaustive research. |
| `resolved_by_policy` | Records disagree, but the configured authoritative sources have one value; dissent remains available. |
| `unresolved` | Conflicting records remain without a unique policy-preferred value. |
| `unknown` | No valid evidence was admitted for this topic. |

The sample source priority is a **fictional application rule**, not a universal
trust ranking. The `signed_manifest` source name is a fixture label: this example
does not implement cryptographic signature verification. A production system
must verify source identity, freshness, scope, and authority before cataloging a
record. A model cannot promote a source or submit an unseen claim in this design.

`termination` describes why scheduling stopped; `needs_review` also accounts for
unknown or unresolved topics, failed/skipped calls, and empty initial reads. `no_open_conflicts` does
not mean the research is complete. For example, a failed or empty reader can leave one
supported value but still require review. This recipe routes **conflicts**, not
missing-evidence questions. It does not automatically retry failed workers.

## Controlled fixed-fanout comparison

The fixed control runs both initial readers plus every configured probe,
regardless of the initial evidence. It uses the same catalog, specialist backend,
decision rule, and total-call limit. Both modes run sequentially. With the included
default fixtures, the observed logical specialist-call counts are:

| Fixture | Adaptive | Fixed | Adaptive decision |
| --- | ---: | ---: | --- |
| Agreement | 2 | 4 | supported, v3 |
| Conflict | 3 | 4 | resolved_by_policy, v3; v2 dissent retained |
| Unresolved | 4 | 4 | unresolved; no selected value |

These are **control-flow observations from hand-built synthetic fixtures**, not
measurements of model quality, latency, token usage, dollar cost, or performance
on real investigations. Adaptive scheduling may miss a contradiction in an
unqueried source. A real evaluation needs adversarial and held-out cases, equal
resource envelopes, source-coverage measures, answer correctness with human
review, omitted-evidence rates, and actual usage/latency telemetry. No quality or
cost advantage is established here.

## Optional Responses integration

The adapter uses the documented Structured Outputs `text.format` JSON-schema
shape. It rejects incomplete responses, refusals, malformed JSON, unknown IDs,
extra keys, and oversized outputs. It supplies no tools and keeps application
routing, source precedence, and record admission outside model output.

No OpenAI SDK is required or imported by the offline recipe. For a separately
authorized live experiment, install a current compatible `openai` SDK and supply
your own client and a Structured Outputs-capable model. Configure a finite client
timeout and `max_retries=0`, since this scheduler counts logical specialist calls,
not transport retries. A token cap is not a dollar-spend guarantee. Obtain any
required permissions before transmitting real records, and budget API usage.

This construction is illustrative and is not executed in the notebook:

```python
# Optional, separately authorized live experiment only:
# from openai import OpenAI
# client = OpenAI(timeout=20.0, max_retries=0)
# backend = ResponsesSpecialist(client, model="YOUR_SUPPORTED_MODEL")
# result = fixtures()["conflict"].run(specialist=backend)
```

Fake-client tests establish request construction and local validation only. They
do not verify SDK compatibility, service acceptance, factual extraction, prompt
injection resistance, model refusal rates, or live response quality. Even an
allowlisted citation can be selectively omitted; Structured Outputs do not make
the selection faithful. For arbitrary documents, record extraction, source
verification, and domain-specific claim normalization are additional stages, not
solved by these fixtures.

## Limits and safety boundaries

- All fixture records, service names, release identifiers, and failures are fictional.
- Evidence is append-only. New source probes can add counterevidence, never erase dissent.
- Total calls include failures; dynamically created branches and per-topic depth
  are capped. Fixed mode has a total-call cap, but the adaptive branch/depth caps
  do not apply to its predeclared plan.
- The task catalog and configured routing table are trusted application inputs.
  Document excerpts and model output are untrusted. Never build source authority
  or task permissions from a model's assertion.
- The synchronous backend must provide its own timeout. The scheduler cannot
  preempt a hung Python callable. No network, browser, shell, or write tool is
  exposed to a specialist here.
- The deduplication key is `(source, claim, scope, value)`. This is intentionally
  narrow, not general semantic deduplication. Source identity/versioning and
  provenance lineage require domain-specific handling in a real system.
- No external state changes, publication, API calls, or credentials are part of
  the local verification. This folder does not modify any existing PR.

## Related official material

- [Parallel agents with the OpenAI Agents SDK](https://developers.openai.com/cookbook/examples/agents_sdk/parallel_agents)
  demonstrates independent parallel analysis and synthesis. This candidate focuses
  instead on application-controlled conflict branching and evidence retention.
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
  documents the response schema used by the optional adapter.

The novelty claim is deliberately narrow: this is an example illustrating
a particular evidence-led scheduling policy, not a claim that adaptive agent
orchestration or these individual techniques are new.
