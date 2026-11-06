# Voice research assistant

Talk to GPT-Live, search the web with Parallel Search, and run independent requests while correcting or cancelling either one. Each request keeps its own card and citations.

You need Node.js 24+, an OpenAI API key on a paid usage tier ([gpt-live-1](https://developers.openai.com/api/docs/models/gpt-live-1) does not support the Free tier) with access to the models in [settings.json](settings.json), a Parallel API key, and a browser with a microphone.

```sh
git clone https://github.com/openai/openai-cookbook.git
cd openai-cookbook/examples/partners/parallel/voice-research
npm ci
cp .env.example .env.local
```

Open `.env.local` and fill in `OPENAI_API_KEY` and `PARALLEL_API_KEY`, then start the server:

```sh
npm start
```

Open [localhost:3000](http://localhost:3000), click **Start conversation**, and allow microphone access. Voice is billed by the second while a session is open ([pricing](https://developers.openai.com/api/docs/models/gpt-live-1)), so click **End conversation** when you finish. Interpretation and research use OpenAI Fast mode (`service_tier: "priority"`). For the configured backend model, this costs twice Standard processing; logs record the actual tier returned by OpenAI. Parallel calls are billed separately. If a session fails to start, OpenAI's error text is in the server terminal.

[Cookbook walkthrough](../../../../articles/voice-research-with-parallel.md) · [Evaluation guide](evals/README.md)

## Run the tests

Install `ffmpeg` for the runner tests. The browser tests launch headless Chromium, so install it once:

```sh
npx playwright install chromium
```

```sh
npm test
```

```sh
npm run typecheck
```

## Check a research model

`scripts/probe-research.ts` checks that a research model supports what the app relies on. It runs the app's research code and Parallel tool definitions against the real Responses API with synthetic search results, steers the response once, and returns async results on their original call IDs. Then it makes one real Parallel Search request and one Extract request. OpenAI documents async tools for GPT-6 Astra and later but doesn't name Luna, so run the probe to confirm `gpt-6-luna` support.

```sh
node --env-file-if-exists=.env.local scripts/probe-research.ts
```

It makes paid API calls. The model and reasoning effort default to `research_model` and `research_effort` in settings.json, and the app uses the same settings. Set `RESEARCH_MODEL_OVERRIDE` or `RESEARCH_EFFORT_OVERRIDE` to try something else. A failure exits nonzero. Requests, events, usage and timings are written to `evals/results/probe-*/trace.json`, which git ignores; check it before you share it. A passing probe confirms API compatibility. To judge voice quality, follow the evaluation guide.

## Try it by hand

Start a fresh session and try these in order:

1. Ask for two events in San Francisco this Saturday. While research runs, change it to Sunday and indoors.
2. Add an independent Node.js versus Deno release comparison. Cancel only the event research and confirm the comparison continues.
3. Ask a local question without a city, then supply San Francisco when asked. Confirm research uses that location.
4. Say “mm-hmm” during research. Confirm it does not restart. Inspect the source links and compare the spoken answer with the card.
5. Stop the session. Confirm the page shows “Conversation ended”, microphone use ends, and the results remain readable. Start a second session to check restart.

As you go, check that:

- Speech keeps the sources' qualifications and says when the evidence isn't enough.
- A later withdrawal replaces the earlier recommendation and its sources, and the card shows “Not enough evidence”.
- Longer findings are still useful when spoken. Investigate any update-preparation error or rejected append, even if the card looks right.

Ordinary browser sessions don't record audio; use the evaluation runner when you need a recording. When a session closes, the server still saves its transcripts and retrieved excerpts to `evals/runs/`, which git ignores. Delete those files when you no longer need them. The runner's automated checks can't grade listening quality, factual support, or whether a request was fulfilled.
