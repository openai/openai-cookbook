# Evaluate the voice research assistant

The app can run without errors and still give an unsupported answer. It can also answer honestly without doing what the user asked. Grade task completion separately from answer quality, time to a useful answer, correction handling, and cost. The runner collects the evidence; you do the grading.

## Run the scenarios

Start the app in another terminal and install `ffmpeg`, which the runner uses to check recordings. Generate or supply the WAV fixtures described below, then install Chromium and run the suite:

```sh
npx playwright install chromium
npm run eval -- --repeat=1 --out=evals/results/first-pass
```

Use `--scenario=correction` to run a single scenario. Every session uses paid API time, so do one pass before you add repetitions. The output directory must not already exist, which keeps interrupted attempts on disk.

The example doesn't include audio recordings. On macOS, `node scripts/generate-fixtures.ts` creates synthetic fixtures with `say` and `ffmpeg` and writes their hashes to `evals/fixtures/manifest.json`. Follow the speech provider's terms when you use generated audio.

On other systems, record the nine prompts in [the fixture manifest](fixtures/manifest.json) as mono 24 kHz PCM WAV files. Keep their IDs and file names, set each `sha256` to the SHA-256 of your file, and set `synthetic` to `false`. To keep recordings elsewhere, put them in one folder with the manifest and pass `--fixtures=/absolute/path/to/fixtures`. The runner checks every fixture before it starts a paid session.

### What the scenarios cover

[scenarios.json](scenarios.json) lists each scenario's required behavior, forbidden behavior, and the evidence to inspect. Only the caller audio reaches the assistant; the expectations stay in the evaluation files. The suite covers:

- A request for two events
- A Sunday and indoor correction while that research is still running
- A spoken "Mm-hmm" during research
- An event request without a city
- A software comparison that needs no location
- Two concurrent requests, with a correction to one of them
- Cancelling one of two running requests
- An ambiguous correction followed by a clarification

Follow-up audio plays once its target task is researching, rather than after a fixed delay. If that task has already finished when playback starts, the run fails. The correction is deliberately short, so the app has to keep the city from the request it corrects.

Synthetic speech makes runs reproducible, but it doesn't tell you how the app performs with real users. For a representative evaluation, replace the WAV files with human recordings and update their hashes.

The offline tests cover missing evidence. `tests/backend.test.ts` checks that empty search results stay empty. `tests/research.test.ts` checks that citations to unretrieved sources are rejected, that an uncited positive answer fails, and that an explicit insufficient-evidence conclusion can finish without sources. Those tests exercise the code path; they can't show that a live model will always answer honestly.

### What the runner checks

The runner turns on audio capture with `window.cookbook.start({ capture: true })`; ordinary sessions don't record. For each trial, it saves server logs, browser events, expectations, configuration and fixture hashes, a stereo recording, and an annotation template.

A trial fails when:

- Either recording channel has less than 100 ms of audio
- An answer is stale or repeated, or a tool call ID runs twice
- The recording is missing, or the session's closure isn't confirmed
- A voice update can't be prepared, or a required append is rejected, including during session close
- A finished task has no accepted final update or cancellation confirmation
- A correction doesn't keep the event task's location, use the requested Sunday in the session’s time zone, and add the indoor constraint, or it changes another task
- In the correction and multi-task correction scenarios, the correction reaches the event task only after its research finished
- A cancellation affects anything other than the event task

A prepared answer can be sent after its card completes, but it must still match the current revision, summary, and outcome. Before closing a session, the runner waits until the required voice updates are accepted and the transcript has been quiet for six seconds. That wait decides when the trial ends; it doesn't measure playback latency. A failed trial exits with a nonzero status and keeps the evidence it collected, even when recording validation fails.

Each correction trial records how the correction reached the research, in `structure.correction_path`:

- `steer`: it steered a response that was still generating.
- `next_request`: no response was generating, so the new objective went out with the next request.
- `restarted`: the research had already finished, so the correction started a new run.

`summary.json` counts these for each scenario under `correction_paths`. With fast search, corrections often arrive between responses, so expect plenty of `next_request` runs. If you want to exercise steering specifically, check that some runs report `steer`.

The runner checks the date on the corrected task. Check dates in the sources, search relevance, and the spoken answer by hand. Audio activity only shows that capture worked.

## Review the evidence

In each `*-annotation.json`, leave fields `null` until you've reviewed them. Listen to the saved stereo WebM recording, and compare the `ui.task` snapshots and `parallel.completed` source excerpts with the trial's `expectations`. If capture failed, leave the audio-dependent grades and timing unreviewed and say why in `notes`.

- **Task completion:** grade `task_completion_pass` separately from `quality_pass`. For the normal, correction, and acknowledgment scenarios, the assistant must give two supported recommendations that meet the latest request's city, date, and constraints. Finding fewer than two fails, even if the assistant is honest about it. For missing-city, a useful spoken clarification with no search passes. A runner status of `completed` only means the trial ran to the end. The required and forbidden behavior saved with the trial decide the outcome.
- **Answer quality:** check every spoken recommendation against the retrieved evidence. Confirm the city, date, event details, and indoor constraint against detailed listings from reputable event calendars, publications, ticketing sites, organizers, or venues. Primary sources are preferred but not required. Check admission conditions, since free admission can still require a purchase. A venue's opening hours don't establish an event on a given day. An honest insufficient-evidence answer can pass. Invented details, a different date, or an unsupported indoor claim fails. Check the card's summary on its own as well, because the spoken paraphrase can drop or fix an error in it. Record your reasons and supporting URLs in `notes`.
- **Correction handling:** check the revised task, the search arguments, the displayed sources, and the spoken answer. Sunday and indoors must carry through to the research and the final answer. Late Saturday results must not reach the final context or the source list. A later delegation for the same request must not start duplicate research. Set `correction_pass` only for correction scenarios.
- **Cost:** include completed and superseded backend work and every dispatched Parallel request. Aborting an HTTP request doesn't prove that billing stopped. Final GPT-Live usage requires a confirmed `session.closed`. Logs can contain personal speech and retrieved material, so keep recordings local unless you mean to share them.

For the software comparison, check both versions against the projects’ release indexes as of the session date. A dated release note shows which channel a version belonged to at release. It cannot establish which version is current today. Grade a stale version as a factual error even if the task routing passed.

While you listen, also judge intelligibility and pacing, whether the assistant stops for a meaningful interruption, and whether it reports the backend result and its uncertainty accurately. Put specific findings in `notes`. Fail `quality_pass` when speech is unintelligible or misstates the result, and fail `correction_pass` when speech ignores the correction. The runner's checks can't make these judgments for you.

This guide measures time to useful information. OpenAI's [first-audio latency](https://developers.openai.com/cookbook/examples/audio/voice_agent_evaluation) is a different measure, because it also counts spoken preambles. Interruption rates and subjective audio scores aren't calculated.

## Summarize the results

```sh
npm run eval:summary -- --out=evals/results/first-pass
```

`summary.json` groups metrics by scenario under `by_scenario`: task-completion, quality, and correction pass rates, the number of reviewed samples, and per-task P50 and P90 latency for the first useful answer and the final answer. Individual runs, notes, structural checks, and cost estimates are under `runs`. Unreviewed grades stay unknown. Timing comes from your audio annotations and skips recordings marked invalid. Failed runs stay in the summary; when the evidence can't support a judgment, leave the field unreviewed and explain why in `notes`. Report sample counts beside rates and percentiles. A handful of runs is a smoke test and can't support a performance claim.

`evals/rates.json` holds Standard short-context prices checked on November 2, 2026, with links to the official sources. Refresh them before you report a new evaluation.

- Responses rates are in USD per million input, cached input, cache-write, and output tokens. The estimate treats cache-write tokens as a separate subset of input tokens.
- Fast mode rates for the configured backend model, checked on the same date, are under `responses_fast`. The estimate uses the `service_tier` OpenAI returns, including a downgrade to Standard. An unreported or unsupported tier leaves the total unknown.
- GPT-Live costs $0.05 per minute, billed per second. Use the final `usage.seconds / 60 * rate`. Don't add WebRTC's 15-second startup charge again: OpenAI credits it once the session runs, and the estimate assumes the final duration already reflects that. Reconcile short, failed-start, or reconnected sessions against your bill.
- Parallel Extract costs $0.001 per billed URL. A Parallel Search call in turbo mode costs $0.001 and includes the default ten results.

The runner records every dispatched call, including aborted and superseded requests. It prices the units in Parallel’s usage receipts. Missing or unrecognized usage leaves the total unknown, and the subtotal includes only work with a known price. Don't present that subtotal as the full cost of the conversation. Account discounts, credits, regional processing, long context, and other service tiers aren't included.

Report a compact table with the scenario, number of runs, reviewed task completion, quality and correction passes, first-useful and final P50 and P90, and cost, or say that cost is unknown. Keep the recordings and your source notes available for review.

## Annotate concurrent tasks

Each annotation has one `tasks` entry per task ID and revision, and these entries are the only source of timing. Record these times in milliseconds from the start of the recording:

- `request_end_ms`: the audible end of the user's complete request. For a correction, use the end of the correction.
- `first_useful_speech_ms`: when the first useful answer grounded in the sources becomes audible.
- `final_speech_ms`: when the final answer becomes audible.

Skip greetings, backchannels, and "I'm searching" acknowledgments. Use the audio itself, because captions and append acknowledgments don't show that anything played. Grade completion, quality, correction, and cancellation for each task, and add notes; cite snapshot versions where they help. A run with no task, such as missing-city, uses the run-level grades. A cancelled task has no final-answer latency. A superseded revision can keep the partial timing you observed, but don't give it a final grade.

A scenario's ordered `steps` can wait for a task count and task state before playing the next fixture. A step that targets a running task selects it by location and records its ID, revision, and playback timing. The summary reports first and final timing for each task and keeps nulls and unreviewed outcomes as they are. Usage accounting includes automatic Responses successors even though the app never dispatched them, and a response with no terminal event makes the cost incomplete. Each run records hashes of the application, UI, scenario, and rate files.
