#!/usr/bin/env bash
set -euo pipefail

INPUT="${1:-/tmp/IMG_8063.MOV}"
OUTPUT="${2:-aumara-site/media/AUMARA_walkthrough_preview_v1.mp4}"
FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

mkdir -p "$(dirname "$OUTPUT")"

ffmpeg -y -hide_banner -loglevel error -i "$INPUT" -filter_complex "
[0:v]split=8[v1][v2][v3][v4][v5][v6][v7][v8];
[0:a]asplit=8[a1][a2][a3][a4][a5][a6][a7][a8];
[v1]trim=start=2:end=7,setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,drawtext=fontfile=${FONT}:text='ТОЧКА 1 · ПАНОРАМА':fontcolor=white:fontsize=36:borderw=2:bordercolor=black@0.8:box=1:boxcolor=black@0.45:boxborderw=16:x=36:y=h-th-36,fade=t=in:st=0:d=0.2,fade=t=out:st=4.8:d=0.2[v1o];
[a1]atrim=start=2:end=7,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.2,afade=t=out:st=4.8:d=0.2[a1o];
[v2]trim=start=16:end=21,setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,drawtext=fontfile=${FONT}:text='ТОЧКА 2 · ПОДХОД К КРАСНОМУ ДОМУ':fontcolor=white:fontsize=34:borderw=2:bordercolor=black@0.8:box=1:boxcolor=black@0.45:boxborderw=16:x=36:y=h-th-36,fade=t=in:st=0:d=0.2,fade=t=out:st=4.8:d=0.2[v2o];
[a2]atrim=start=16:end=21,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.2,afade=t=out:st=4.8:d=0.2[a2o];
[v3]trim=start=36:end=41,setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,drawtext=fontfile=${FONT}:text='ТОЧКА 3 · ВЕРХНИЙ КЛАСТЕР':fontcolor=white:fontsize=36:borderw=2:bordercolor=black@0.8:box=1:boxcolor=black@0.45:boxborderw=16:x=36:y=h-th-36,fade=t=in:st=0:d=0.2,fade=t=out:st=4.8:d=0.2[v3o];
[a3]atrim=start=36:end=41,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.2,afade=t=out:st=4.8:d=0.2[a3o];
[v4]trim=start=62:end=67,setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,drawtext=fontfile=${FONT}:text='ТОЧКА 4 · ВИД НА ДОЛИНУ':fontcolor=white:fontsize=36:borderw=2:bordercolor=black@0.8:box=1:boxcolor=black@0.45:boxborderw=16:x=36:y=h-th-36,fade=t=in:st=0:d=0.2,fade=t=out:st=4.8:d=0.2[v4o];
[a4]atrim=start=62:end=67,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.2,afade=t=out:st=4.8:d=0.2[a4o];
[v5]trim=start=78:end=83,setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,drawtext=fontfile=${FONT}:text='ТОЧКА 5 · ВЕРХНЯЯ ДОРОЖКА':fontcolor=white:fontsize=36:borderw=2:bordercolor=black@0.8:box=1:boxcolor=black@0.45:boxborderw=16:x=36:y=h-th-36,fade=t=in:st=0:d=0.2,fade=t=out:st=4.8:d=0.2[v5o];
[a5]atrim=start=78:end=83,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.2,afade=t=out:st=4.8:d=0.2[a5o];
[v6]trim=start=100:end=105,setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,drawtext=fontfile=${FONT}:text='ТОЧКА 6 · ЦЕНТРАЛЬНЫЙ ПЕРЕКРЁСТОК':fontcolor=white:fontsize=32:borderw=2:bordercolor=black@0.8:box=1:boxcolor=black@0.45:boxborderw=16:x=36:y=h-th-36,fade=t=in:st=0:d=0.2,fade=t=out:st=4.8:d=0.2[v6o];
[a6]atrim=start=100:end=105,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.2,afade=t=out:st=4.8:d=0.2[a6o];
[v7]trim=start=128:end=133,setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,drawtext=fontfile=${FONT}:text='ТОЧКА 7 · НИЖНИЙ МАРШРУТ':fontcolor=white:fontsize=36:borderw=2:bordercolor=black@0.8:box=1:boxcolor=black@0.45:boxborderw=16:x=36:y=h-th-36,fade=t=in:st=0:d=0.2,fade=t=out:st=4.8:d=0.2[v7o];
[a7]atrim=start=128:end=133,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.2,afade=t=out:st=4.8:d=0.2[a7o];
[v8]trim=start=165:end=170,setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,drawtext=fontfile=${FONT}:text='ТОЧКА 8 · ВОЗВРАТ':fontcolor=white:fontsize=36:borderw=2:bordercolor=black@0.8:box=1:boxcolor=black@0.45:boxborderw=16:x=36:y=h-th-36,fade=t=in:st=0:d=0.2,fade=t=out:st=4.8:d=0.2[v8o];
[a8]atrim=start=165:end=170,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.2,afade=t=out:st=4.8:d=0.2[a8o];
[v1o][a1o][v2o][a2o][v3o][a3o][v4o][a4o][v5o][a5o][v6o][a6o][v7o][a7o][v8o][a8o]concat=n=8:v=1:a=1[v][a]
" -map "[v]" -map "[a]" \
  -c:v libx264 -preset veryfast -crf 28 -profile:v high -level 4.0 \
  -pix_fmt yuv420p -r 25 -c:a aac -b:a 96k -movflags +faststart "$OUTPUT"

ffprobe -v error -show_entries format=duration,size -show_entries stream=codec_name,width,height -of json "$OUTPUT"
