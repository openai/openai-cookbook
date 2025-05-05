![Elato Logo](https://raw.githubusercontent.com/openai/openai-cookbook/refs/heads/main/examples/voice_solutions/arduino_ai_speech_assets/elato-alien.png)

## 👾 ElatoAI: Running OpenAI Realtime API Speech on ESP32 on Arduino with Deno Edge Functions

This guide shows how to build a AI voice agent device with Realtime AI Speech powered by OpenAI Realtime API, ESP32, Secure WebSockets, and Deno Edge Functions for >10-minute uninterrupted global conversations.

An active version of this README is available at [ElatoAI](https://github.com/akdeb/ElatoAI).

<div align="center">
    <a href="https://www.youtube.com/watch?v=o1eIAwVll5I" target="_blank">
    <img src="https://raw.githubusercontent.com/akdeb/ElatoAI/refs/heads/main/assets/thumbnail.png" alt="Elato AI Demo Video" width="100%" style="border-radius:10px" />
  </a>
</div>

## ⚡️ DIY Hardware Design

The reference implementation uses an ESP32-S3 microcontroller with minimal additional components:

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/refs/heads/main/examples/voice_solutions/arduino_ai_speech_assets/pcb-design.png" alt="Hardware Setup" width="100%">

**Required Components:**
- ESP32-S3 development board
- I2S microphone (e.g., INMP441)
- I2S amplifier and speaker (e.g., MAX98357A)
- Push button to start/stop the conversation
- RGB LED for visual feedback
- Optional: touch sensor for alternative control

**Hardware options:**
A fully assembled PCB and device is available in the [ElatoAI store](https://www.elatoai.com/products).

## 📱 App Design

Control your ESP32 AI device from your phone with your own webapp.

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/refs/heads/main/examples/voice_solutions/arduino_ai_speech_assets/mockups.png" alt="App Screenshots" width="100%">

| Select from a list of AI characters | Talk to your AI with real-time responses | Create personalized AI characters |
|:--:|:--:|:--:|


## ✨ Quick Start Tutorial

<a href="https://www.youtube.com/watch?v=bXrNRpGOJWw">
  <img src="https://img.shields.io/badge/Quick%20start%20Tutorial-YouTube-yellow?style=for-the-badge&logo=youtube" alt="Watch Demo on YouTube">
</a>

1. **Clone the repository**

Head over to the [ElatoAI GitHub repository](https://github.com/akdeb/ElatoAI) and clone the repository.

```bash
git clone https://github.com/akdeb/ElatoAI.git
cd ElatoAI
```

2. **Set your environment variables (OPENAI_API_KEY, SUPABASE_ANON_KEY)**

In the `frontend-nextjs` directory, create a `.env.local` file and set your environment variables.

```bash
cd frontend-nextjs
cp .env.example .env.local

# In .env.local, set your environment variables 
# NEXT_PUBLIC_SUPABASE_ANON_KEY=<your-supabase-anon-key>
# OPENAI_API_KEY=<your-openai-api-key>
```

In the `server-deno` directory, create a `.env` file and set your environment variables.

```bash
cd server-deno
cp .env.example .env

# In .env, set your environment variables 
# SUPABASE_KEY=<your-supabase-anon-key>
# OPENAI_API_KEY=<your-openai-api-key>
```

2. **Start Supabase**

Install [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) and set up your Local Supabase Backend. From the root directory, run:
```bash
brew install supabase/tap/supabase
supabase start # Starts your local Supabase server with the default migrations and seed data.
```

3. **Set up your NextJS Frontend**

([See the Frontend README](https://github.com/akdeb/ElatoAI/tree/main/frontend-nextjs/README.md)) 

From the `frontend-nextjs` directory, run the following commands. (**Login creds:** Email: `admin@elatoai.com`, Password: `admin`)
```bash
cd frontend-nextjs
npm install

# Run the development server
npm run dev
```

4. **Start the Deno server**

([See the Deno server README](https://github.com/akdeb/ElatoAI/tree/main/server-deno/README.md))
```bash
# Navigate to the server directory
cd server-deno

# Run the server at port 8000
deno run -A --env-file=.env main.ts
```

5. **Setup the ESP32 Device firmware**

([See the ESP32 Device README](https://github.com/akdeb/ElatoAI/tree/main/firmware-arduino/README.md))

In `Config.cpp` set `ws_server` and `backend_server` to your local IP address. Run `ifconfig` in your console and find `en0` -> `inet` -> `192.168.1.100` (it may be different for your Wifi network). This tells the ESP32 device to connect to your NextJS frontend and Deno server running on your local machine. All services should be on the same Wifi network.

6. **Setup the ESP32 Device Wifi**

Build and upload the firmware to your ESP32 device. The ESP32 should open an `ELATO-DEVICE` captive portal to connect to Wifi. Connect to it and go to `http://192.168.4.1` to configure the device wifi.

7. Once your Wifi credentials are configured, turn the device OFF and ON again and it should connect to your Wifi and your server.

8. Now you can talk to your AI Character!

## 🚀 Ready to Launch?

1. Register your device by adding your ESP32 Device's MAC Address and a unique user code to the `devices` table in Supabase.
> **Pro Tip:** To find your ESP32-S3 Device's MAC Address, build and upload `test/print_mac_address_test.cpp` using PlatformIO and view the serial monitor.


2. On your frontend client in the [Settings page](http://localhost:3000/home/settings), add the unique user code so that the device is linked to your account in Supabase.


3. If you're testing locally, you can keep enabled the `DEV_MODE` macro in `firmware-arduino/Config.h` and the Deno server env variable to use your local IP addresses for testing.


4. Now you can register multiple devices to your account by repeating the process above.

## Project Architecture

ElatoAI consists of three main components:

1. **Frontend Client** (`Next.js` hosted on Vercel) - to create and talk to your AI agents and 'send' it to your ESP32 device
2. **Edge Server Functions** (`Deno` running on Deno/Supabase Edge) - to handle the websocket connections from the ESP32 device and the OpenAI API calls
3. **ESP32 IoT Client** (`PlatformIO/Arduino`) - to receive the websocket connections from the Edge Server Functions and send audio to the OpenAI API via the Deno edge server.


## 🌟 Key Features

1. **Realtime Speech-to-Speech**: Instant speech conversion powered by OpenAI's Realtime APIs.
2. **Create Custom AI Agents**: Create custom agents with different personalities and voices.
3. **Customizable Voices**: Choose from a variety of voices and personalities.
4. **Secure WebSockets**: Reliable, encrypted WebSocket communication.
5. **Server VAD Turn Detection**: Intelligent conversation flow handling for smooth interactions.
6. **Opus Audio Compression**: High-quality audio streaming with minimal bandwidth.
7. **Global Edge Performance**: Low latency Deno Edge Functions ensuring seamless global conversations.
8. **ESP32 Arduino Framework**: Optimized and easy-to-use hardware integration.
9. **Conversation History**: View your conversation history.
10. **Device Management and Authentication**: Register and manage your devices.
11. **User Authentication**: Secure user authentication and authorization.
12. **Conversations with WebRTC and Websockets**: Talk to your AI with WebRTC on the NextJS webapp and with websockets on the ESP32.
13. **Volume Control**: Control the volume of the ESP32 speaker from the NextJS webapp.
14. **Realtime Transcripts**: The realtime transcripts of your conversations are stored in the Supabase DB.
15. **OTA Updates**: Over the Air Updates for the ESP32 firmware.
16. **Wifi Management with captive portal**: Connect to your Wifi network from the ESP32 device.
17. **Factory Reset**: Factory reset the ESP32 device from the NextJS webapp.
18. **Button and Touch Support**: Use the button OR touch sensor to control the ESP32 device.
19. **No PSRAM Required**: The ESP32 device does not require PSRAM to run the speech to speech AI.
20. **OAuth for Web client**: OAuth for your users to manage their AI characters and devices.

## 🛠 Tech Stack

| Component       | Technology Used                          |
|-----------------|------------------------------------------|
| Frontend        | Next.js, Vercel            |
| Backend         | Supabase DB  |
| Edge Functions  | Edge Functions on Deno / Supabase Edge Runtime         |
| IoT Client      | PlatformIO, Arduino Framework, ESP32-S3  |
| Audio Codec     | Opus                                     |
| Communication   | Secure WebSockets                        |
| Libraries       | ArduinoJson, WebSockets, AsyncWebServer, ESP32_Button, Arduino Audio Tools, ArduinoLibOpus        |

## 📈 Core Use Cases

We have a [Usecases.md](https://github.com/akdeb/ElatoAI/tree/main/Usecases.md) file that outlines the core use cases for the [Elato AI device](https://www.elatoai.com/products) or any other custom conversational AI device.

## 🗺️ High-Level Flow

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/refs/heads/main/examples/voice_solutions/arduino_ai_speech_assets/flowchart.png" alt="App Screenshots" width="100%">

## Project Structure

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/refs/heads/main/examples/voice_solutions/arduino_ai_speech_assets/structure.png" alt="App Screenshots" width="100%">

## ⚙️ PlatformIO Config

```ini
[env:esp32-s3-devkitc-1]
platform = espressif32 @ 6.10.0
board = esp32-s3-devkitc-1
framework = arduino
monitor_speed = 115200

lib_deps =
    bblanchon/ArduinoJson@^7.1.0
    links2004/WebSockets@^2.4.1
    ESP32Async/ESPAsyncWebServer@^3.7.6
    https://github.com/esp-arduino-libs/ESP32_Button.git#v0.0.1
    https://github.com/pschatzmann/arduino-audio-tools.git#v1.0.1
    https://github.com/pschatzmann/arduino-libopus.git#a1.1.0
```

## 📊 Important Stats

- ⚡️ **Latency**: <2s round-trip globally
- 🎧 **Audio Quality**: Opus codec at bitrate 12kbps (high clarity)
- ⏳ **Uninterrupted Conversations**: Up to 10 minutes continuous conversations
- 🌎 **Global Availability**: Optimized with edge computing with Deno

## 🛡 Security

- Secure WebSockets (WSS) for encrypted data transfers
- Optional: API Key encryption with 256-bit AES
- Supabase DB for secure authentication
- Supabase RLS for all tables

## 🚫 Limitations
- 3-4s Cold start time while connecting to edge server
- Limited to upto 10 minutes of uninterrupted conversations
- Edge server stops when wall clock time is exceeded
- No speech interruption detection on ESP32

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**This example is part of the [OpenAI Cookbook](https://github.com/openai/openai-cookbook). For the full project and latest updates, check out [ElatoAI](https://github.com/akdeb/ElatoAI) and consider giving it a ⭐️ if you find it useful!**
