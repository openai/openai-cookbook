# define a wrapper function for seeing how prompts affect transcriptions
def transcribe(prompt: str, audio_filepath) -> str:
    """Given a prompt, transcribe the audio file."""
    transcript = openai.audio.transcriptions.create(
        file=open(audio_filepath, "rb"),
        model="whisper-1",
        prompt=prompt,
    )
    return transcript.text
