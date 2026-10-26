# Translation Demo

> **Archived beta demo.** The preview model and `@openai/realtime-api-beta` protocol used by this app are retired. Do not run this as a GA sample, and do not put a project API key in a browser, a frontend build, or any `REACT_APP_` variable. Use the [Realtime translation guide](https://developers.openai.com/api/docs/guides/realtime-translation) and [browser WebRTC guide](https://developers.openai.com/api/docs/guides/voice-webrtc?api=realtime) for a current implementation with server-issued short-lived credentials.

This project demonstrates how to use the [OpenAI Realtime API](https://platform.openai.com/docs/guides/realtime) to build a one-way translation application with WebSockets. It is implemented using the [Realtime + Websockets integration](https://platform.openai.com/docs/guides/realtime-websocket). A real-world use case for this demo is multilingual, conversational translation—where a speaker talks into the speaker app and listeners hear translations in their selected native languages via the listener app. Imagine a conference room with multiple participants with headphones, listening live to a speaker in their own languages. Due to the current turn-based nature of audio models, the speaker must pause briefly to allow the model to process and translate speech. However, as models become faster and more efficient, this latency will decrease significantly and the translation will become more seamless.

## Migration

1. Build the server-side credential endpoint shown in the WebRTC guide. Only the server reads `OPENAI_API_KEY`; the browser receives a short-lived credential.
2. Use the current translation model and session fields from the translation guide. Changing the old preview model name alone will not update beta client events or session formats.
3. Retain the language selection and audio-mirroring architecture below if useful. The archived `SpeakerPage` points only to the local legacy relay at `ws://localhost:8081`; the relay still uses the retired beta protocol and is not a GA connection implementation.

### Adding a New Language

To add a new language to the codebase, follow these steps:

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

5. **Test the New Language:**

   - Run your application and test the new language by selecting it from the dropdown menu.
   - Ensure that the audio stream for the new language is correctly received and played.

### Demo Flow

1. **Connect in the Speaker App:**

   - Click "Connect" and wait for the WebSocket connections to be established with the Realtime API.
   - Choose between VAD (Voice Activity Detection) and Manual push-to-talk mode.
   - the speaker should ensure they pause to allow the translation to catch up - the model is turn based and cannot constantly stream translations. 
   - The speaker can view live translations in the Speaker App for each language. 

2. **Select Language in the Listener App:**

   - Select the language from the dropdown menu.
   - The listener app will play the translated audio. The app translates all audio streams simultaneously, but only the selected language is played. You can switch languages at any time.
