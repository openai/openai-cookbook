# Twilio Realtime Translation Demo

This is a server-side demo for two-person phone translation with Twilio Media Streams and `gpt-realtime-translate`.

Each caller dials the same Twilio number, says the language they want to hear, and waits for a second caller. The server pairs the calls and opens two Realtime Translation sessions:

```txt
Caller A audio -> Realtime Translation -> Caller B hears B's selected language
Caller B audio -> Realtime Translation -> Caller A hears A's selected language
```

## Why WebSocket here

Twilio Media Streams are already server-side WebSocket connections. The server receives `audio/x-mulaw` 8 kHz audio from Twilio, converts it to 24 kHz PCM16 for Realtime Translation, converts translated 24 kHz PCM16 output back to 8 kHz mulaw, and sends it back to Twilio as `media` messages.

## Setup

From the cookbook repo root:

```bash
cd examples/voice_solutions/realtime_translation_guide/twilio-translation-demo
npm install
cp .env.example .env
```

Set:

```bash
OPENAI_API_KEY=your-openai-api-key
PUBLIC_URL=https://your-public-host.example.com
PORT=5050
OPENAI_TRANSLATION_MODEL=gpt-realtime-translate
TWILIO_AUTH_TOKEN=your-twilio-auth-token
ALLOWED_CALLER_NUMBERS=+15551234567,+15557654321
MAX_ACTIVE_CALLERS=4
```

Run:

```bash
npm run dev
```

Configure your Twilio phone number Voice webhook to:

```txt
POST https://your-public-host.example.com/incoming-call
```

For local testing, expose port `5050` through a public HTTPS/WSS tunnel or deploy this server somewhere Twilio can reach over port 443.

## Public deployment notes

Twilio must be able to reach the same public HTTPS/WSS origin for `/incoming-call`, `/choose-language`, and `/media-stream`. Use a stable public deployment for repeatable demos.

Set `OPENAI_API_KEY` and `TWILIO_AUTH_TOKEN` as deployment secrets. Set `PUBLIC_URL` to the deployed origin so Twilio signature validation uses the same public URL that Twilio requested.

Use `ALLOWED_CALLER_NUMBERS` when you want the phone number to be callable only from known test phones. Leave it empty for an open demo. Use `MAX_ACTIVE_CALLERS` to cap concurrent callers and prevent runaway Twilio/OpenAI spend.

## Known limitation

This demo only sends audio back to a caller when the Realtime Translation session emits translated audio. It does not pass the speaker's original Twilio audio through as a fallback. If the speaker is already using the listener's selected language, or if no translated audio is emitted for a short stretch, the listener may hear silence rather than the original speech.

Adding original-audio fallback requires a server-side playout/mixing layer that buffers Twilio media frames, decides when translated audio should take priority, and optionally mixes original audio under translated output. That is intentionally out of scope for this demo.

## Call Flow

1. Caller dials your Twilio number.
2. Twilio requests `/incoming-call`.
3. The server returns TwiML with `<Gather input="speech">` so the caller can say an output language.
4. Twilio posts the recognized speech to `/choose-language`. If the speech is missing, unclear, or names an unsupported language, the server reprompts instead of defaulting to a language.
5. The server returns `<Connect><Stream>` with custom parameters for the call SID and selected output language.
6. Twilio opens `/media-stream`.
7. The server pairs the caller with the next waiting caller.
8. The server streams each caller's audio through a separate Realtime Translation session and plays translated audio to the other caller.

## Notes

- This demo intentionally uses direct server-side Realtime Translation WebSockets, not browser client secrets.
- Direct server-side WebSockets select the translation model with the `model` query parameter, then configure the target language with `session.audio.output.language`.
- Input and output transcripts are emitted as JSON log lines prefixed with `[translation-transcript]`. Each line includes `callSid`, `direction`, `targetLanguage`, `phase`, `eventType`, and `text` so eval tooling can compare input speech against translated output.
- Twilio two-way Media Streams receive only the inbound track and allow the server to send audio back to the call.
- The demo keeps call state in memory. Use durable state if you deploy beyond local demos.
- Twilio request signature validation is enabled when `TWILIO_AUTH_TOKEN` is set. Leave `SKIP_TWILIO_SIGNATURE_VALIDATION=true` only for local debugging.

## Test

From the cookbook repo root:

```bash
cd examples/voice_solutions/realtime_translation_guide/twilio-translation-demo
npm test
```
