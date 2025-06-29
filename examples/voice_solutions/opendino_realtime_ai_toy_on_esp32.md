## 🦖 OpenDino: An Open, Realtime-AI Educational Toy on ESP32

[OpenDino](https://github.com/RASPIAUDIO/OpenDino) is an open-source project that connects low-cost ESP32 microcontrollers directly to OpenAI's Realtime API via secure WebSockets. It streams microphone audio to GPT-4o mini (or another model) and plays back the model's audio responses, enabling back-and-forth conversations without a local server.

Unlike the [ElatoAI example](running_realtime_api_speech_on_esp32_arduino_edge_runtime_elatoai.md), which relies on a companion server running on your PC, OpenDino performs the WebSocket communication entirely on the ESP32 board.

### Key features

- Runs on an ESP32 dev board with PSRAM and integrated audio.
- Real-time, bidirectional audio streaming over WebSocket.
- Firmware and hardware released under permissive licenses.
- Provider-agnostic architecture for future models or self-hosting.

### Getting started

The repository includes Arduino/PlatformIO firmware and assembly instructions. Flash the firmware with your own API key and Wi-Fi credentials, then hold the push-to-talk button to chat with the toy. Full details and a demo video are available in the project's README.

### License

OpenDino is released under the MIT license for firmware and CERN OHL for hardware. See the [OpenDino repo](https://github.com/RASPIAUDIO/OpenDino) for the complete documentation and latest updates.

---

**This article is part of the [OpenAI Cookbook](https://github.com/openai/openai-cookbook). For the full project, visit [OpenDino on GitHub](https://github.com/RASPIAUDIO/OpenDino) and consider starring the repo if you find it useful!**
