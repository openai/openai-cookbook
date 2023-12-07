transcription = client.audio.transcriptions.create(
    file=open("wikipediaOcelot.wav", "rb"),
    model=deployment,
)
print(transcription.text)