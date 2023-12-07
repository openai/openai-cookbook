# Get list of trimmed and segmented audio files and sort them numerically
audio_files = sorted(
    (f for f in os.listdir(output_dir_trimmed) if f.endswith(".wav")),
    key=lambda f: int(''.join(filter(str.isdigit, f)))
)
