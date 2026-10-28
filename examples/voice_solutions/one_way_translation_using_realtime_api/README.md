# Translation Demo

> **Archived beta demo.** The preview model and `@openai/realtime-api-beta` protocol used by this app are retired. Do not run this as a GA sample, and do not put a project API key in a browser, a frontend build, or any `REACT_APP_` variable. Use the [Realtime translation guide](https://developers.openai.com/api/docs/guides/realtime-translation) and [browser WebRTC guide](https://developers.openai.com/api/docs/guides/voice-webrtc?api=realtime) for a current implementation with server-issued short-lived credentials.

This archived project demonstrated multilingual, conversational translation with the Realtime beta API and WebSockets. A speaker talked into the speaker app and listeners selected a language in the listener app. The beta model required the speaker to pause while it processed and translated speech.

## Migration

1. Build the server-side credential endpoint shown in the WebRTC guide. Only the server reads `OPENAI_API_KEY`; the browser receives a short-lived credential.
2. Use the current translation model and session fields from the translation guide. Changing the old preview model name alone will not update beta client events or session formats.
3. Retain the language selection and audio-mirroring architecture below if useful. The archived `SpeakerPage` points only to the local legacy relay at `ws://localhost:8081`; the relay still uses the retired beta protocol and is not a GA connection implementation.

## Historical beta architecture (not runnable)

The remaining sections describe how the retired app was organized and tested. They are for source reference only; they are not steps to run against the current API. Complete the migration above in a new implementation before testing any connection or audio.

### How the beta app added a language

The old language configuration touched these files:

1. **Socket Event Handling in Mirror Server:**

   - Open `mirror-server/mirror-server.cjs`.
   - Add a new socket event for the new language. For example, for Hindi:
     ```javascript
     socket.on('mirrorAudio:hi', (audioChunk) => {
       console.log('logging Hindi mirrorAudio', audioChunk);
       socket.broadcast.emit('audioFrame:hi', audioChunk);
     });
     ```

2. **Instructions Configuration:**

   - Open `src/utils/translation_prompts.js`.
   - Add new instructions for the new language. For example:
     ```javascript
     export const hindi_instructions = "Your Hindi instructions here...";
     ```

3. **Realtime Client Initialization in SpeakerPage:**

   - Open `src/pages/SpeakerPage.tsx`.
   - Import the new language instructions:
     ```typescript
     import { hindi_instructions } from '../utils/translation_prompts.js';
     ```
   - Add the new language to the `languageConfigs` array:
     ```typescript
     const languageConfigs = [
       // ... existing languages ...
       { code: 'hi', instructions: hindi_instructions },
     ];
     ```

4. **Language Configuration in ListenerPage:**

   - Open `src/pages/ListenerPage.tsx`.
   - Locate the `languages` object, which centralizes all language-related data.
   - Add a new entry for your language. The key should be the language code, and the value should be an object containing the language name.

     ```typescript
     const languages = {
       fr: { name: 'French' },
       es: { name: 'Spanish' },
       tl: { name: 'Tagalog' },
       en: { name: 'English' },
       zh: { name: 'Mandarin' },
       // Add your new language here
       hi: { name: 'Hindi' }, // Example for adding Hindi
     } as const;
     ```

   - The `ListenerPage` component will automatically handle the new language in the dropdown menu and audio stream handling.

5. **Historical language test:**

   - The beta test selected a new language from the dropdown and checked audio playback. It depended on the retired client and model.

### Historical demo flow

1. **Connect in the Speaker App:**

   - "Connect" opened WebSocket connections through the legacy relay. This no longer connects to a supported API.
   - The speaker chose voice activity detection (VAD) or manual push-to-talk mode and paused for translation.
   - The app showed beta translations for each language.

2. **Select Language in the Listener App:**

   - The listener selected a language from the dropdown.
   - The beta app processed all streams and played only the selected language.
