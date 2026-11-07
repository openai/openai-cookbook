# Local verification

Date: 2026-10-23. Candidate: **Evidence-driven agent teams**.
Author: Sophia Cole / ColeWorld. MIT licensed; see LICENSE.
This report records validation evidence, not contribution acceptance.

## Executed checks

Environment: Python 3.12.14; notebook validator `nbformat` 5.11.1.
Commands were run from the recipe directory, with `nbformat` provided by an
existing isolated validation environment.

| Check | Command | Result |
| --- | --- | --- |
| Unit and fake-client contract tests | `python -m unittest discover -s tests -v` | 37 tests passed; exit 0 |
| Notebook schema | `python validate_notebook.py` | nbformat validation passed; exit 0 |
| Notebook code syntax | Same command | All 9 code cells compiled |
| Sequential notebook behavior | Same command | All 9 code cells executed in order with assertions passing |
| Python source compilation | `python -m compileall -q evidence_teams.py validate_notebook.py tests` | Passed; exit 0 |

The notebook contains 22 total cells, including 9 code cells. Saved code cells
are clean and unexecuted; no execution-count metadata falsely implies a kernel
run. The validation script executes the same cells in a shared Python namespace.

## Observed fixture results

| Fixture | Adaptive calls | Fixed-plan calls | Outcome |
| --- | ---: | ---: | --- |
| Agreement | 2 | 4 | supported, v3 |
| Conflict | 3 | 4 | resolved by configured policy, v3; v2 dissent retained |
| Unresolved | 4 | 4 | unresolved; no selected value |

Logical call counts are synthetic control-flow observations, not measured
quality, monetary cost, token consumption, or latency improvements.

## Coverage

Tests exercise evidence-ID and same-source-fact deduplication, task/probe
deduplication, terminal redundant/empty branches, branch/call/depth limits,
round-robin conflict scheduling, unknown and out-of-scope citations, whole-result
validation before evidence admission, source-scope separation, failure accounting,
empty initial reads, repeated runs without leaked state, majority-independent
contradiction handling, and preservation of unresolved dissent.

The optional Responses adapter is tested only through a fake client for request
shape, refusal/incomplete handling, malformed JSON, oversized/extra fields,
fabricated IDs, and transport errors. No SDK/service call was made.

## Not established

- A full Jupyter-kernel run or notebook UI/rendering verification. Full-kernel
  execution was not retried because a kernel socket restriction had already been
  identified in this task environment. No attempt was made to bypass it.
- Live OpenAI SDK compatibility, service acceptance, model behavior, factual
  extraction, prompt-injection resistance, or output completeness.
- General semantic evidence deduplication, trusted document extraction,
  cryptographic verification, real-world source authority, or actual API cost.
- Contribution acceptance or production readiness.

All fixture data is fictional. No credentials were read or created. Full-kernel and live checks remain pending.
