# Use a loop to apply the transcribe function to all audio files
transcriptions = [transcribe_audio(file, output_dir_trimmed) for file in audio_files]
