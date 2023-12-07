transcription = openai.Audio.transcribe(
    file=open("wikipediaOcelot.wav", "rb"),
    model="whisper-1",
    deployment_id=deployment_id,
)
print(transcription.text)