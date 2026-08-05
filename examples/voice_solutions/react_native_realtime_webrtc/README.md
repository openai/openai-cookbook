# React Native Realtime WebRTC example

This is the complete companion code for `react_native_realtime_webrtc.mdx`.
It deliberately separates three concerns:

- `src/server` mints a 60-second Realtime client secret with a standard API key that never reaches the app.
- `src/mobile/openai-webrtc-transport.ts` contains the React Native-compatible WebRTC transport.
- `src/mobile/session-controller.ts` owns idempotency, AppState-driven pause/resume, bounded reconnects, and teardown.

The example is intentionally synthetic. It captures ordinary task notes and contains no production prompts, endpoints, credentials, user records, or sensitive-domain data.

## Run the checks

```bash
npm install
npm run check
```

## Run the local token server

Copy `.env.example` to `.env`, replace every placeholder, then run:

```bash
cp .env.example .env
npm run dev:server
```

The fixed bearer token and `X-Demo-User` header are local-demo authentication only. In a real app, derive the safety identifier from the authenticated server-side principal and replace the demo bearer token with your existing login/session mechanism.

## Bind React Native WebRTC

Install and configure `react-native-webrtc` in a React Native development build. The included typed adapter exposes the small interface consumed by `OpenAIWebRtcTransport`:

```ts
import {
  reactNativeWebRtcBindings as webRtc,
} from "./src/mobile/react-native-webrtc-bindings";
```

Create a new `OpenAIWebRtcTransport` in the controller's `createTransport` callback. Connect `AppState` changes to `controller.setAppActive(nextState === "active")`, and call `controller.stop()` when the owning screen unmounts.

When `onToolApprovalRequest` fires, show the proposed note in the native UI. Save it only after the user approves, then call `request.respond({ saved: true })`. If the user declines, call `request.respond({ saved: false })`. The transport never performs a side effect automatically.
