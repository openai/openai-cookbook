# Shared GPT Live frontend

`assistant.py` owns the GPT Live WebSocket, voice session, incoming events,
streamed caller audio, and connection lifecycle. Both delegation modes reuse
this frontend. `transport.py` owns shared protocol validation, session payloads,
authentication, and WebSocket connections.

Edit `prompts/voice.txt` to change the assistant's spoken behavior. Configure
the GPT Live model, voice, endpoint, and credentials in the selected `.env` file
or shell. See [environment-file selection](../../README.md#environment-file-selection)
and [security and artifact handling](../../README.md#artifact-and-connection-safety).
