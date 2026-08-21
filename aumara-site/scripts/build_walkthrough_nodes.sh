#!/usr/bin/env bash
set -euo pipefail

INPUT="${1:-/tmp/IMG_8063.MOV}"
OUTDIR="${2:-aumara-site/media/nodes}"
mkdir -p "$OUTDIR"

# Real route points cut from IMG_8063.MOV. Each clip is deliberately short,
# mobile-friendly and fast-start enabled for progressive playback.
# Format: filename start duration
NODES=(
  "node-01.mp4 2 7"
  "node-02.mp4 14 8"
  "node-03.mp4 23 8"
  "node-04.mp4 35 9"
  "node-05.mp4 56 10"
  "node-06.mp4 76 10"
  "node-07.mp4 124 10"
  "node-08.mp4 162 10"
)

for spec in "${NODES[@]}"; do
  read -r name start duration <<< "$spec"
  ffmpeg -y -hide_banner -loglevel error \
    -ss "$start" -i "$INPUT" -t "$duration" \
    -vf "scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2" \
    -c:v libx264 -preset veryfast -crf 27 -profile:v high -level 4.0 \
    -pix_fmt yuv420p -r 25 -an -movflags +faststart \
    "$OUTDIR/$name"
  test -s "$OUTDIR/$name"
done

cat > "$OUTDIR/manifest.json" <<'JSON'
{
  "source": "IMG_8063.MOV",
  "version": 1,
  "nodes": [
    {"id":"01","title":"Central view","subtitle":"Green house, ochre houses and valley","file":"node-01.mp4"},
    {"id":"02","title":"West approach","subtitle":"Turning toward the red house","file":"node-02.mp4"},
    {"id":"03","title":"Red house","subtitle":"The western house and its entrance path","file":"node-03.mp4"},
    {"id":"04","title":"Return to the centre","subtitle":"Back past the green house","file":"node-04.mp4"},
    {"id":"05","title":"The descent","subtitle":"The path drops between the houses","file":"node-05.mp4"},
    {"id":"06","title":"Upper path","subtitle":"Moving along the higher route","file":"node-06.mp4"},
    {"id":"07","title":"Lower route","subtitle":"The lower section and house entrances","file":"node-07.mp4"},
    {"id":"08","title":"Western return","subtitle":"The red-green pair and the road below","file":"node-08.mp4"}
  ]
}
JSON

for f in "$OUTDIR"/node-*.mp4; do
  ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 "$f"
done
