## OpenAI Realtime API Integration for Node.js

This code file demonstrates how to integrate the OpenAI Realtime API into a Node.js application. It serves as a gateway for developers looking to interact with OpenAI's GPT models in real-time, using audio input and output to create a conversational assistant.

In this tutorial, developers will learn how to use WebSocket communication to connect to OpenAI's API, stream audio input, and receive responses in real time. This integration provides a way to implement dynamic interactions that utilize GPT's natural language processing capabilities in audio form, making it well suited for conversational AI, live assistant applications, and other real-time use cases.

### Machine Dependencies

To successfully run this application, the following machine dependencies are required:

1. **Node.js** (version 14 or higher): Required to run the JavaScript code.
2. **npm** (Node Package Manager): To install the necessary Node.js packages (`ws`, `mic`, `dotenv`, `speaker`).
3. **Sox**: The application uses the `mic` package, which relies on the Sox command line utility (`rec`) to capture audio. Install via Homebrew on macOS:
   ```sh
   brew install sox
   ```
4. **Microphone**: A working microphone is required for capturing live audio.
5. **Speakers or Headphones**: Needed to play back the audio response from the OpenAI API.
6. **Environment Variables**: You need to set the `OPENAI_API_KEY` in your environment to authenticate with OpenAI's API. You can add it to a `.env` file:
   ```
   OPENAI_API_KEY=your_openai_api_key_here
   ```
7. **Homebrew** (for macOS users): To install system dependencies like Sox.
8. **Network Connection**: A stable internet connection is required for communication with the OpenAI API.

### Summary

This tutorial is valuable for developers who want to:
- Understand how to use OpenAI’s Realtime API for conversational AI applications.
- Gain hands-on experience with audio streaming and real-time processing in Node.js.
- Create an interactive experience that takes full advantage of GPT's capabilities for spoken dialogue.

By providing a practical example of connecting and interacting with OpenAI, this tutorial serves as a foundational guide for building real-time AI-driven solutions. This example is designed to assist developers in quickly setting up a voice-based AI assistant using Node.js.

### Step-by-Step Guide for Implementing this Code

1. **Install Node.js and npm**
   - Make sure you have Node.js (version 14 or higher) and npm installed on your machine.

2. **Clone or Create the Project**
   - Create a new project directory and navigate into it:
   ```sh
   mkdir openai-realtime-api
   cd openai-realtime-api
   ```

3. **Install Required Dependencies**
   - Install the necessary packages using npm:
   ```sh
   npm install ws mic dotenv speaker
   ```

4. **Install Sox**
   - Sox is required for capturing microphone input. Install it using Homebrew (for macOS):
   ```sh
   brew install sox
   ```

5. **Create a `.env` File**
   - Create a `.env` file in the root of your project directory and add your OpenAI API key:
   ```
   OPENAI_API_KEY=your_openai_api_key_here
   ```

6. **Set Up the Code**
   - Copy the provided JavaScript code from audio_stream.mjs into a file named `app.js` in your project directory.

7. **Run the Application**
   - Run the application with Node.js:
   ```sh
   node app.js
   ```

8. **Verify Dependencies**
   - Ensure Sox is available in your system path. If you encounter an error related to `rec` command not found, add the following line to your code to adjust the path:
   ```javascript
   process.env.PATH = `${process.env.PATH}:/usr/local/bin`;
   ```

9. **Connect to the OpenAI API**
   
   To connect to the OpenAI API, the application uses a WebSocket to establish a real-time link:

   - **Initialize WebSocket Connection**: Once you run the application (`node app.js`), the code initializes a WebSocket connection to the OpenAI Realtime API using the provided URL (`wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01`).
     ```javascript
     const ws = new WebSocket(OPENAI_API_URL, {
       headers: {
         Authorization: `Bearer ${API_KEY}`,
         'OpenAI-Beta': 'realtime=v1',
       },
     });
     ```

   - **Handle Connection Events**: Once the WebSocket connection is open, you can start interacting with the API. Upon connection, the application sends an initial request to create a response stream.
     ```javascript
     ws.on('open', () => {
       console.log('Connected to OpenAI Realtime API.');
       ws.send(JSON.stringify({
         type: 'response.create',
         response: {
           modalities: ['text', 'audio'],
           instructions: 'Please assist the user.',
         },
       }));
       startAudioStream(ws);
     });
     ```

10. **Interact with the Assistant**

    Now that you are connected, you can start speaking to interact with the assistant:

    - **Audio Streaming**: The `startAudioStream()` function starts capturing audio from your microphone using the `mic` package and sends it to the OpenAI API via WebSocket.
      ```javascript
      function startAudioStream(ws) {
        const micInstance = mic({
          rate: '16000', // Increased rate to improve playback quality
          channels: '1',
          debug: false,
          exitOnSilence: 6,
          fileType: 'wav',
          encoding: 'signed-integer',
        });

        const micInputStream = micInstance.getAudioStream();
        micInstance.start();
        console.log('Microphone started streaming.');

        micInputStream.on('data', (data) => {
          if (data.length > 0) {
            console.log('Sending audio data chunk to server...');
            ws.send(JSON.stringify({ type: 'input_audio_buffer.append', audio: data.toString('base64') }));
          }
        });

        micInputStream.on('silence', () => {
          console.log('Committing audio buffer after silence...');
          ws.send(JSON.stringify({ type: 'input_audio_buffer.commit' }));
        });
      }
      ```

    - **Handle API Responses**: The application listens for responses from OpenAI through the WebSocket connection. It accumulates audio data, plays back the response, and logs the received messages.
      ```javascript
      ws.on('message', (message) => {
        const response = JSON.parse(message.toString());
        if (response.type === 'response.audio.delta') {
          console.log('Received audio delta, accumulating audio...');
          accumulatedAudio.push(response.delta);
        } else if (response.type === 'response.audio.done') {
          console.log('Received complete audio response, preparing to play...');
          const completeAudio = accumulatedAudio.join('');
          playAudio(completeAudio, () => {
            accumulatedAudio = []; // Clear accumulated audio after successful playback
          });
        } else {
          console.log('Received message:', response);
        }
      });
      ```

By following these steps, developers new to integrating real-time APIs can easily set up a voice-based assistant that interacts with OpenAI's models, providing an engaging example of real-time conversational AI.