# Segment audio
trimmed_audio = AudioSegment.from_wav(trimmed_filename)  # Load the trimmed audio file

one_minute = 1 * 60 * 1000  # Duration for each segment (in milliseconds)

start_time = 0  # Start time for the first segment

i = 0  # Index for naming the segmented files

output_dir_trimmed = "trimmed_earnings_directory"  # Output directory for the segmented files

if not os.path.isdir(output_dir_trimmed):  # Create the output directory if it does not exist
    os.makedirs(output_dir_trimmed)

while start_time < len(trimmed_audio):  # Loop over the trimmed audio file
    segment = trimmed_audio[start_time:start_time + one_minute]  # Extract a segment
    segment.export(os.path.join(output_dir_trimmed, f"trimmed_{i:02d}.wav"), format="wav")  # Save the segment
    start_time += one_minute  # Update the start time for the next segment
    i += 1  # Increment the index for naming the next file
