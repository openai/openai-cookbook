# Translation Demo

This project demonstrates how to use the [OpenAI Realtime API](https://platform.openai.com/docs/guides/realtime) to build a one-way translation application with WebSockets. It is implemented using the [Realtime + Websockets integration](https://platform.openai.com/docs/guides/realtime-websocket). A real-world use case for this demo is multilingual, conversational translation—where a speaker talks into the speaker app and listeners hear translations in their selected native languages via the listener app. Imagine a conference room with multiple participants with headphones, listening live to a speaker in their own languages. Due to the current turn-based nature of audio models, the speaker must pause briefly to allow the model to process and translate speech. However, as models become faster and more efficient, this latency will decrease significantly and the translation will become more seamless.

## How to Use

### Running the Application

1. **Set up the OpenAI API:**

   - If you're new to the OpenAI API, [sign up for an account](https://platform.openai.com/signup).
   - Follow the [Quickstart](https://platform.openai.com/docs/quickstart) to retrieve your API key.

2. **Clone the Repository:**

   ```bash
   git clone <repository-url>
   ```

3. **Set your API key:**

   - Create a `.env` file at the root of the project and add the following line:
     ```bash
     REACT_APP_OPENAI_API_KEY=<your_api_key>
     ```

4. **Install dependencies:**

   Navigate to the project directory and run:

   ```bash
   npm install
   ```

5. **Run the Speaker & Listener Apps:**

   ```bash
   npm start
   ```

   The speaker and listener apps will be available at:
   - [http://localhost:3000/speaker](http://localhost:3000/speaker)
   - [http://localhost:3000/listener](http://localhost:3000/listener)

6. **Start the Mirror Server:**

   In another terminal window, navigate to the project directory and run:

   ```bash
   node mirror-server/mirror-server.mjs
   ```

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