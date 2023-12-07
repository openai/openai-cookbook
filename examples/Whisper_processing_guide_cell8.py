def transcribe_audio(file,output_dir):
    audio_path = os.path.join(output_dir, file)
    with open(audio_path, 'rb') as audio_data:
        transcription = client.audio.transcriptions.create(
            model="whisper-1", file=audio_data)
        return transcription.text