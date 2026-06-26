#!/usr/bin/env bash
set -euo pipefail

# AUMARA urgent photo-to-video renderer.
# Usage: ./animate_photo_ffmpeg.sh input.jpg output.mp4 [duration_seconds]
# Preserves the source orientation; creates continuous camera movement,
# subtle light breathing, and an original ambient audio bed.

INPUT="${1:?Input image is required}"
OUTPUT="${2:-AUMARA_Animated_Photo.mp4}"
DURATION="${3:-7}"
FPS=24
FRAMES=$((FPS * DURATION))

ffmpeg -y -loglevel error \
  -loop 1 -i "$INPUT" \
  -f lavfi -i "aevalsrc=0.055*sin(2*PI*55*t)+0.032*sin(2*PI*82.41*t+0.35*sin(2*PI*0.11*t))+0.018*sin(2*PI*110*t):s=48000:d=${DURATION}" \
  -filter_complex "
    [0:v]
      scale=-1:900,
      crop=720:900:(iw-720)/2:0,
      zoompan=
        z='min(zoom+0.00075,1.12)':
        x='iw/2-(iw/zoom/2)+6*sin(on/25)':
        y='ih/2-(ih/zoom/2)-0.15*on':
        d=${FRAMES}:s=720x900:fps=${FPS},
      eq=contrast=1.04:saturation=1.03:brightness='0.012*sin(2*PI*t/3)':eval=frame,
      vignette=PI/6,
      format=yuv420p[v];
    [1:a]
      afade=t=in:st=0:d=0.8,
      afade=t=out:st=$(awk "BEGIN {print ${DURATION}-0.8}"):d=0.8,
      volume=0.85[a]
  " \
  -map "[v]" -map "[a]" \
  -t "$DURATION" \
  -c:v libx264 -preset fast -crf 18 \
  -c:a aac -b:a 192k \
  -movflags +faststart \
  "$OUTPUT"

echo "Created: $OUTPUT"
