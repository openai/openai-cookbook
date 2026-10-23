# Interaction metric contract v2

`metrics_version: "2.0"` identifies the interval and response-opportunity rules
below. It is independent of the result envelope's `schema_version: "2.0"`.
Older, unversioned interaction results must not be pooled with v2 results.

## Semantic judge scoring

`voice-semantic-v2` identifies the shared CRAWL/WALK/RUN semantic scoring
contract, independently of the interaction and result-envelope versions.
Each new individual judge score must be exactly one of five values:

| Score | Severity anchor |
| --- | --- |
| 1 | Fully satisfied: meets the rubric's required behavior. Stylistic preferences alone do not reduce the score. |
| 0.75 | Mostly satisfied: a small, localized error or omission with limited impact; the main required behavior remains correct. |
| 0.5 | Partially satisfied: useful behavior, but a material error or omission leaves an important requirement unmet. |
| 0.25 | Minimally satisfied: limited useful behavior; major errors or omissions leave most requirements unmet. |
| 0 | Wholly incorrect, fabricated, or unsafe behavior. |

The response schema and local validation enforce this set; unsupported scores
are rejected, not rounded or converted to target-agent failures. The five
rubric descriptions, scenario criteria, applicability, and pass/fail and
task-completion logic are unchanged. There is no new numeric pass threshold.

The restriction applies to individual judgments, not averages: samples of
0.75 and 1 still average to 0.875. Historical `voice-semantic-v1` scores can be
any number in 0–1 and remain readable without conversion. Do not treat a
rounded historical score as a new judgment or pool scoring versions without
accounting for the changed scale. Human calibration is needed to establish
whether the new anchors improve agreement.

RUN retains this version in its rubric results' `version` field. CRAWL/WALK
retain `rubric_version` in each assessed dimension's evidence. Missing version
metadata in older results must not be interpreted as the new contract.

## Response rate is deadline-qualified first audio

The response metric measures the start of the first qualifying voiced
assistant segment after an eligible caller turn's observed speech ends. It
does **not** establish that the answer was substantive, correct, or sufficient
to complete the task. Task-state checks and semantic grading remain separate.

The default deadline is **5,000 ms**, an explicit evaluation policy rather than
a model SLA. RUN accepts `--response-deadline-ms` and
`simulation.response_deadline_ms` in its TOML configuration. The shared metric
functions also accept `response_deadline_ms` directly. Save the chosen policy
with every result and hold it constant in a comparison.

| Classification | Rule | In the response-rate denominator? |
| --- | --- | --- |
| Answered | First post-request voiced audio starts by the deadline and no later than the next eligible caller request's start | Yes |
| Missed | The deadline expires without a timely response, or the next eligible request starts and closes the prior opportunity first | Yes |
| Censored | Observation ends before the deadline, without an answer or a later eligible request | No; counted explicitly |
| Excluded | Caller action is `BACKCHANNEL` or `STOP`, or assistant speech was already active at the request's end boundary | No; counted with a reason |

Audio starting exactly at the deadline is timely. Audio after the deadline
but no later than the next eligible request's start remains in
`late_response_latencies_ms` and `response_late_count`; it does not erase the
missed deadline. Once that next request starts, later audio is not
automatically attributed to the earlier request. A pending tool or delegation
does not extend the first-audio deadline.

The `assistant_active_at_request_end` exclusion preserves the existing
acoustic population. Its boundary rule is
`assistant.start_ms < request.end_ms <= assistant.end_ms`; it is not a claim
that the caller's request was satisfied. Use a separate semantic
request-completeness assessment for requests spoken through by the assistant.

The same classifier supplies aggregate and per-turn results. Existing per-turn
outcome names remain available; `response_status`, `response_reason`,
`response_deadline_at_ms`, and observed latency explain their classification.
The portable JSON report places `metrics_version`, `response_deadline_ms`, and
`response_exclusion_reasons` beside `response_rate` under `metrics.audio`.
Counts appear under `metrics.audio.response_opportunities`:

```text
response_total = response_count + no_response_count
response_eligible_count = response_total + response_censored_count
caller_turn_count = response_eligible_count + response_excluded_count
response_rate = response_count / response_total  (null when total is zero)
```

Here, `caller_turn_count` counts the caller segments with observed voiced
support that reach this classifier, not every transcript row or semantic
request. Text-only annotations do not invent speech or a response opportunity.

Under the default deadline, one answered request plus a final request followed
by 89 seconds of recorded silence yields 1 answered / 2 scored opportunities
= 50%. With only a 20 ms final observation tail, the second request is censored
instead. Missing audio evidence is not equivalent to recorded silence.

## Speech and yield use exact acoustic intervals

Reporting ticks are containers, not continuous speech. Voiced intervals are
unioned only when they overlap or touch. Positive silent gaps remain gaps,
including gaps inside one tick. Caller utterance annotations can group several
voiced spans into one semantic turn without turning pauses into sound.

Assistant intervals `[200,220)` and `[580,600)` do not overlap caller speech
`[350,370)`. Shifting all times by 100 ms or changing a reporting tick from
200 to 20 ms does not create an interruption.

Yield eligibility requires assistant activity before the cue. An explicit
interruption cue arriving exactly as assistant speech ends can be a successful
zero-overlap yield. Requiring positive realized overlap would incorrectly
exclude this success. A genuine positive gap is not exposure; simultaneous
speech onset alone is not evidence of pre-cue assistant activity.

## Delegated-work silence uses one correlated lifecycle

Handoff silence is the union of active delegated-work intervals minus the
union of voiced intervals on **both** audio tracks. Cumulative duration and the
longest silent episode use those exact boundaries, not a tick's final state.
For silent tracks, a handoff from 150 to 450 ms is 300 ms at every reporting
tick size; a 150–190 ms handoff is 40 ms, not zero.

Runtime state and replay share one reducer that distinguishes client delegation
IDs, response IDs, and tool call IDs. Completing one call cannot clear a
different same-name call. A successful tool result can still require a
follow-up backend response. Client completion/failure and correlated local
controller errors are retained as terminal evidence.

New RUN details preserve `run_metadata.delegation_lifecycle_events`, including
the minimal identifiers needed for replay. New ticks preserve
`delegation_intervals_ms` and `delegation_active_ms`;
`delegation_active` means that work was active anywhere in the tick. The
`delegation_timing_source` field distinguishes exact lifecycle evidence,
exact saved-tick intervals, and `legacy_tick_projection`. The legacy fallback
cannot recover a sub-tick event that was never recorded.

## Transport time is not speaker playback

Live RUN selects audio every **20 ms**, independently of `--tick-ms` reporting.
Offline fixtures retain their tick-sized input contract. New audio arriving
after one send can be selected for the next frame rather than waiting for a
200 ms preselected block.

The runner retains provider timestamps, receiver monotonic time, and relay
media position separately. Untimed lifecycle events use the relay position at
receipt, with transport-frame resolution. Send completion establishes delivery
to the participant transport, not physical speaker playback or human hearing.

Run metadata records transport/reporting frame sizes, audio-effect processing
size, queue delay, buffer high-water marks, underflow, and send latency. Paired
sends still apply backpressure to both directions. Do not subtract a universal
200 ms from old runs: the old relay changed the conversation itself.

Live audio effects now operate on 20 ms frames. Seeded noise and packet-loss
bursts can therefore differ from the earlier tick-sized processing, even with
the same seed. Compare matched frame/effect configurations and rerun controls.

## Completion and simulator validity are separate gates

The completion observer rechecks relevant caller and assistant turns,
application state, tool executions, and pending delegated work. It rejects
stale results and waits at least 500 ms between assessment starts. Unchanged
unresolved evidence can be assessed again after 5 seconds, provided the runner
is eligible to observe and no assessment is still running. Silent frames alone
do not trigger assessments.

New caller audio, a pending caller turn, caller backend work, or a later
correction revokes a drain decision. Session completion does not relabel the last caller request as
`STOP`; ending a session must not remove a genuine request from the denominator.
Explicit caller actions and the preexisting no-observer natural-closing
heuristic remain separate sources of action labels, not independent human
intent judgments.

Both participants' buffered speech and turns, quiet tails, and pending work
must be considered before termination. Finalized transcript evidence must
catch up with delivered speech on both tracks; delayed assistant audio or a
pending final transcript can invalidate an earlier completion decision. Missing
final transcript evidence does not waive the duration cap. An observer failure
remains visible and uses the existing verified-state/natural-closing fallback.

The live caller has its own managed Responses backend, with no application
tools or access to evaluator-only expectations or target-private state.
Supported Responses delegation is valid; caller work is tracked separately
and never contributes to target delegation, tool, or consumption metrics.
Pending caller reasoning blocks completion. Unsupported delegation, failed or
incomplete backend responses, and unfinished caller reasoning at the duration
limit set `run_metadata.simulator_validity.status: "invalid"`, with reason
`unsupported_caller_delegation`, `caller_backend_failed`, or
`caller_backend_pending`, respectively. Repeated copies of the same delegation
ID count once.

Invalid attempts retain their task evidence and configured artifacts. Portable
JSON reports use the existing excluded `infrastructure_error` status with
`error.stage: "caller_simulation"` and a separate `validity` object. Post-run
rubric judging is skipped. Completion-observer calls already made during the
conversation remain in the usage evidence. This preserves existing consumers'
pass/fail exclusion behavior without disguising a simulator defect as a
target-model failure.
Passing this narrow gate does not prove caller realism or scenario fidelity.

## Reusing old results

Recompute only when the saved speech intervals, lifecycle events, and clocks
support the new calculation. Preserve the original version and record the new
policy. Missing terminal events cannot be invented, and relay-induced changes
to conversational behavior require a rerun. A new metric version, a passing
offline test, an accepted API request, and a validated live benchmark are
separate evidence.
