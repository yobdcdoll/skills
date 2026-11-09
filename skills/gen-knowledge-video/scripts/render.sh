#!/usr/bin/env bash
# Parallel deterministic frame render + ffmpeg encode.
#
# Usage (from the lesson directory):
#   bash render.sh [fps] [shards]
#
# Environment:
#   OUT=<id>.mp4     output file (default: <script.json id>.mp4)
#   CRF=20           x264 quality (lower = better/larger)
#   PRESET=veryfast  x264 preset
#   FORCE=1          delete a non-empty frames/ before rendering
#   LAYOUT_CHECK=1   run check_layout.mjs before rendering (fails on overflow)
#   WATERMARK=0      skip watermark.json embedding even when the file exists
#
# Code lessons (script.json kind="code") are also gated by
# check_code_samples.mjs: no visible code block + real output means no render.
#
# Requires: node, python3, ffmpeg, ffprobe, Playwright (or BROWSER_PATH).
# watermark.json additionally requires numpy + pillow.

set -euo pipefail

FPS="${1:-15}"
SHARDS="${2:-4}"
CRF="${CRF:-20}"
PRESET="${PRESET:-veryfast}"
FORCE="${FORCE:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "$FPS" in
  ''|*[!0-9]*) echo "fps must be a positive integer" >&2; exit 2 ;;
esac
case "$SHARDS" in
  ''|*[!0-9]*) echo "shards must be a positive integer" >&2; exit 2 ;;
esac
if [ "$FPS" -lt 1 ] || [ "$SHARDS" -lt 1 ]; then
  echo "fps and shards must be >= 1" >&2
  exit 2
fi

for cmd in node python3 ffmpeg ffprobe; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "missing command: $cmd" >&2
    exit 2
  fi
done

for f in script.json scene.html audio/full.wav cues.js subtitles.js scene-data.js; do
  if [ ! -f "$f" ]; then
    echo "missing $f (run from the lesson directory and finish build_audio.py / build_subtitles.mjs)" >&2
    exit 2
  fi
done

if [ "${LAYOUT_CHECK:-0}" = "1" ]; then
  echo "checking text layout against longest real copy ..."
  node "$SCRIPT_DIR/check_layout.mjs" || exit 1
fi

# Code lessons must actually show code + output. The checker exits 0 for
# non-code lessons, and warns when code blocks exist but kind is not "code".
echo "checking code lesson contract ..."
node "$SCRIPT_DIR/check_code_samples.mjs" || exit 1

if [ -f watermark.json ] && [ "${WATERMARK:-1}" != "0" ]; then
  python3 -c "import numpy, PIL" 2>/dev/null || {
    echo "watermark.json found but numpy/pillow are missing: python3 -m pip install numpy pillow" >&2
    exit 2
  }
fi

ID="$(python3 -c 'import json; print(json.load(open("script.json")).get("id") or "lesson")')"
OUT="${OUT:-${ID}.mp4}"

DUR="$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 audio/full.wav)"
FRAMES="$(python3 -c "import math; print(math.ceil(float('$DUR') * $FPS))")"

echo "audio ${DUR}s @ ${FPS}fps -> ${FRAMES} frames, ${SHARDS} shards"

if [ -d frames ] && [ -n "$(ls -A frames 2>/dev/null || true)" ]; then
  if [ "$FORCE" != "1" ]; then
    echo "frames/ is not empty. Re-run with FORCE=1 to delete and re-render." >&2
    exit 2
  fi
  rm -rf frames
fi
mkdir -p frames

pids=()
for ((i = 0; i < SHARDS; i++)); do
  s=$((FRAMES * i / SHARDS))
  e=$((FRAMES * (i + 1) / SHARDS))
  if [ "$s" -ge "$e" ]; then
    continue
  fi
  echo "shard ${i}: ${s}-${e}"
  node "$SCRIPT_DIR/render_range.mjs" "$s" "$e" "$FPS" >"render-${i}.log" 2>&1 &
  pids+=("$!")
done

status=0
for pid in "${pids[@]}"; do
  wait "$pid" || status=$?
done
if [ "$status" -ne 0 ]; then
  echo "a render shard failed; last lines of render-*.log:" >&2
  for f in render-*.log; do
    if [ -s "$f" ]; then
      echo "--- $f" >&2
      tail -n 8 "$f" >&2
    fi
  done
  exit "$status"
fi

GOT="$(find frames -name 'f*.jpg' | wc -l | tr -d ' ')"
if [ "$GOT" -ne "$FRAMES" ]; then
  echo "expected ${FRAMES} frames, got ${GOT}" >&2
  exit 1
fi

if [ -f watermark.json ] && [ "${WATERMARK:-1}" != "0" ]; then
  echo "embedding invisible watermark from watermark.json ..."
  python3 "$SCRIPT_DIR/watermark.py" embed-frames --frames frames --config watermark.json
fi

ffmpeg -y -framerate "$FPS" -i frames/f%05d.jpg -i audio/full.wav \
  -c:v libx264 -preset "$PRESET" -crf "$CRF" -pix_fmt yuv420p \
  -c:a aac -b:a 192k -shortest -movflags +faststart "$OUT"

echo "wrote ${OUT}"
ffprobe -v error \
  -show_entries format=duration,size:stream=codec_name,width,height,r_frame_rate \
  -of default=nw=1 "$OUT"
