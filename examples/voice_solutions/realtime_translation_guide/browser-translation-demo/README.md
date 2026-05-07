# Browser Realtime Translation Demo

This is a small browser demo for one-way live translation from tab audio. The
server creates a short-lived OpenAI Realtime Translation client secret, and the
browser uses WebRTC to send captured tab audio and play translated speech with
captions.

## Setup

Create a local `.env` file in this demo folder using `.env.example` as the list
of required variables.

Required:

```bash
OPENAI_API_KEY=your-openai-api-key
```

Optional:

```bash
OPENAI_TRANSLATION_MODEL=gpt-realtime-translate
OPENAI_INPUT_TRANSCRIPTION_MODEL=gpt-realtime-whisper
PORT=5173
HOST=127.0.0.1
```

## Run

From the cookbook repo root:

```bash
cd examples/voice_solutions/realtime_translation_guide/browser-translation-demo
npm install
npm run dev
```

Open the local URL printed by the server. Choose a browser tab with audio, pick
the language you want to hear, and start translation.

## Audio mix

The app includes an Audio mix slider for balancing translated speech with the
original tab audio. By default, it plays 85% translated audio and 15% original
audio, matching the LiveKit demo.

When the selected source is a browser tab, the demo still requests
`suppressLocalAudioPlayback` in the `getDisplayMedia()` audio constraints.
If the browser honors that setting, the slider controls both the translated
audio and the original audio playback from this app. If the browser does not
support local playback suppression, the source tab may continue playing outside
the slider, so lower or mute the source tab if you hear too much original audio.

## Validation

From the cookbook repo root:

```bash
cd examples/voice_solutions/realtime_translation_guide/browser-translation-demo
npm test
```

To run a live API smoke test:

```bash
npm run smoke
```

## Notes

- The browser uses `getDisplayMedia()` so the user explicitly chooses the source
  tab.
- WebRTC handles browser audio transport, so the browser does not need to
  resample tab audio or manually send PCM chunks.
