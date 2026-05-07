# LiveKit Realtime Translation Demo

Local Next.js 16 demo for a LiveKit video room with per-listener OpenAI
Realtime Translation. LiveKit carries browser-to-browser camera and microphone
media. Each browser translates subscribed remote microphone tracks through an
OpenAI WebRTC connection and keeps captions/transcripts in local React state.

## Setup

Create `.env` in this demo folder:

```bash
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
LIVEKIT_URL=
OPENAI_API_KEY=
OPENAI_TRANSLATION_MODEL=gpt-realtime-translate
```

`OPENAI_TRANSLATION_MODEL` is optional and defaults to
`gpt-realtime-translate`.

## Run

From the cookbook repo root:

```bash
cd examples/voice_solutions/realtime_translation_guide/livekit-translation-demo
pnpm install
pnpm dev
```

Open the local URL printed by Next.js. Use the same meeting code in two browser
windows to join the same LiveKit room.

## Validation

From the cookbook repo root:

```bash
cd examples/voice_solutions/realtime_translation_guide/livekit-translation-demo
pnpm test
pnpm lint
pnpm typecheck
pnpm build
```

The OpenAI translation payload tests cover the translation client secret request,
the translation WebRTC call endpoint, `session.audio.output.language`, optional
input transcription, and optional near-field noise reduction.
