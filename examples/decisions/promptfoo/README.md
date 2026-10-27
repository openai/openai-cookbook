# Evaluate Decisions routing with Promptfoo

This optional companion runs the notebook's four-intent BANKING77 subset through
Promptfoo's native `openai:decisions:gpt-6-luna` provider. It calls
`POST https://api.openai.com/v1/decisions` and uses exact-match JavaScript assertions.
No model judge is needed.

Read the [security review](SECURITY_REVIEW.md) before installing this optional
companion. Its dependency audit has unresolved advisories. The standard-library
notebook runner does not require these npm dependencies.

## Data and scope

The public dataset is BANKING77 by Iñigo Casanueva, Tadas Temcinas, Daniela Gerz,
Matthew Henderson, and Ivan Vulić (2020), from PolyAI's
[task-specific-datasets repository](https://github.com/PolyAI-LDN/task-specific-datasets/tree/57ec275d8078af65b7731c2a98be812d844a6d6b).
Please cite [Efficient Intent Detection with Dual Sentence Encoders](https://arxiv.org/abs/2003.04807).
The publisher distributes the datasets under
[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
The original license is included in `DATA_LICENSE.txt`; the dataset is provided
without warranties. This package selects four intents, renames their labels,
removes normalized duplicates/conflicts, and deterministically samples 40
calibration and 80 test examples. The notebook checks both source CSV hashes.
The original message wording is retained. No endorsement by the dataset authors
is implied.

`prepare` downloads the public CSVs from pinned commit
`57ec275d8078af65b7731c2a98be812d844a6d6b`; source CSVs are not committed here.
Generated tests and results stay in the ignored `.generated/` directory.
Only the rendered `{{message}}` prompt is sent as API input; expected labels,
case IDs, and split names are local evaluation variables.

These are the **same cases evaluated in the notebook**, so this run tests
reproducibility across harnesses. It is not another unseen holdout. BANKING77 is
a public benchmark that may have been encountered during model training; no
training-data exclusion is claimed. The four selected intents do not measure
out-of-scope detection or production performance. Do not replace the public
examples with private/customer content without the applicable authorization.

## Install

Requirements: Python 3.10+, Node.js 22.22.0+, npm, and a project API key with
Decisions access. Promptfoo is pinned to `0.124.1` in `package.json` and
`package-lock.json`.

From the repository root:

```bash
cd examples/decisions/promptfoo
npm ci
```

If the default npm cache is not writable, use
`npm ci --cache "$PWD/.npm-cache"`. Do not change system ownership to work around
a sandbox write restriction.

## Clean and run end to end

```bash
bash run_eval.sh
```

Each invocation clears the previous `.generated/` configuration, results, and
reports, then starts a fresh run. No manual cleanup or archive directory is
required. Source code, installed dependencies, and local Promptfoo storage are
retained. Requests are uncached, so each invocation makes new paid requests.

The script prepares and validates the configuration before asking for a key
with hidden input. Alternatively, export `OPENAI_API_KEY` in that Terminal first.
Never put the key in a source file or pass it as a command-line argument.

The live eval makes **120 sequential billable requests** with caching disabled
and `maxRetries: 0`. It keeps terminal output visible, disables usage telemetry
and update checks, uses local Promptfoo storage in `.local/`, and sets
`sharing: false`. It does not sign in to Promptfoo Cloud or upload/share a report.
The script clears its copy of the key when done; if you exported one in the
parent Terminal, run `unset OPENAI_API_KEY` there afterward.

Review these generated files:

- `.generated/report.html`: local report showing messages, response answers,
  expected routes, grades, and latency. Open it in your browser.
- `.generated/results.json`: detailed Promptfoo export. The native provider
  scores the `answers` field; the detailed export also retains the raw response.
- `.generated/summary.json`: threshold chosen using calibration data only,
  held-out coverage, accepted accuracy, misroutes, per-route metrics, and limits.
- `.generated/manifest.json`: source commit/hashes, question hash, and case IDs.

Promptfoo's headline pass rate is exact-match accuracy over all 120 examples.
Use `summary.json` for the separate 80-example test result and threshold policy.
Refusals and unusable answers fail exact match and go to review in policy metrics.
The illustrative operational loss weights are 5 per accepted misroute and 1 per
review; they are not API prices. HTTP/provider errors or incomplete exports stop
summary generation rather than becoming model-quality scores.

The script overwrites the generated results on each invocation. Inspect failures
before retrying: a request may already have been processed. To analyze an existing run
without making requests:

```bash
python3 routing_eval.py summarize
```

## Offline checks

From the repository root:

```bash
.venv/bin/python -m unittest discover -s examples/decisions -p 'test_*.py'
.venv/bin/python -m unittest discover -s examples/decisions/promptfoo -p 'test_*.py'
```

These tests mock the API and network. They check grading, calibration selection,
malformed answers, and rejection of incomplete or mismatched result files. They
do not measure model quality. Preparing the live config downloads public data
but does not call OpenAI:

```bash
python3 examples/decisions/promptfoo/routing_eval.py prepare
```

References: [Promptfoo Decisions provider](https://www.promptfoo.dev/docs/providers/openai-decisions/),
[OpenAI Decisions guide](https://developers.openai.com/api/docs/guides/decisions),
and [Promptfoo telemetry configuration](https://www.promptfoo.dev/docs/configuration/telemetry/).
