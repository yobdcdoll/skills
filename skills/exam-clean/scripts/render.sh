#!/usr/bin/env bash
# render.sh — HTML → A4 PDF / 单页 PNG / 拼接长图
#
# 用法:
#   bash render.sh restored.html --outdir hw_restore --name 试卷_还原版 [--long]
#
# 依赖: google-chrome (headless), python3 + Pillow, 可选 ImageMagick(convert)
set -euo pipefail

HTML=""
OUTDIR="."
NAME="output"
LONG=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --outdir) OUTDIR="$2"; shift 2;;
    --name)   NAME="$2";   shift 2;;
    --long)   LONG=1; shift;;
    *) HTML="$1"; shift;;
  esac
done

[[ -z "$HTML" ]] && { echo "用法: bash render.sh <file.html> --outdir DIR --name BASE [--long]"; exit 1; }
[[ -f "$HTML" ]] || { echo "找不到 HTML: $HTML"; exit 1; }
mkdir -p "$OUTDIR"

ABS=$(readlink -f "$HTML")
PDF="$OUTDIR/$NAME.pdf"

CHROME=$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)
if [[ -z "$CHROME" ]]; then echo "找不到 chrome/chromium"; exit 1; fi

echo "[1/4] 渲染 PDF ..."
"$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
  --no-pdf-header-footer --print-to-pdf="$PDF" "file://$ABS" 2>&1 | tail -1 || true

PAGES=$(python3 - "$PDF" <<'PY'
import re,sys
d=open(sys.argv[1],'rb').read()
print(len(re.findall(rb'/Type\s*/Page[^s]', d)))
PY
)
echo "      PDF 页数 = $PAGES  (应等于 HTML 里 .page 的数量；多了就收紧边距/字号)"

echo "[2/4] 长截图 ..."
SHOT="$OUTDIR/_render_full.png"
"$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
  --force-device-scale-factor=2 --window-size=1050,2600 \
  --screenshot="$SHOT" "file://$ABS" 2>&1 | tail -1 || true

echo "[3/4] 按空白行切分单页 + 居中裁边 ..."
python3 - "$SHOT" "$OUTDIR" "$NAME" "$LONG" <<'PY'
import sys
from PIL import Image
import numpy as np
shot, outdir, name, long = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == "1"
im = Image.open(shot).convert("L")
a = np.array(im)
dark = (a < 200).sum(axis=1)
# 横向裁边：去掉左右空白
cols = (a < 200).sum(axis=0)
cnz = np.where(cols > 0)[0]
x0, x1 = (cnz.min() - 20, cnz.max() + 20) if len(cnz) else (0, a.shape[1])
x0, x1 = max(0, x0), min(a.shape[1], x1)

# 找大段空白（页与页之间）
empty = dark <= 3
runs, start = [], None
for i, e in enumerate(empty):
    if e and start is None: start = i
    if not e and start is not None:
        if i - start > 120: runs.append((start, i - 1))
        start = None
if start is not None and len(empty) - start > 120: runs.append((start, len(empty) - 1))

rows = np.where(dark > 3)[0]
if not runs or not len(rows):
    segs = [(rows.min(), rows.max())] if len(rows) else []
else:
    segs, prev = [], rows.min()
    for s, e in runs:
        if s > prev: segs.append((prev, s - 1))
        prev = e + 1
    if prev <= rows.max(): segs.append((prev, rows.max()))

rgb = Image.open(shot).convert("RGB")
crops = []
for i, (r0, r1) in enumerate(segs, 1):
    r0 = max(0, r0 - 30); r1 = min(rgb.height, r1 + 30)
    c = rgb.crop((x0, r0, x1, r1))
    p = f"{outdir}/{name}_p{i}.png"
    c.save(p); crops.append(c)
    print(f"      {p}  {c.size}")

if long and crops:
    gap = 60
    W = max(c.width for c in crops)
    H = sum(c.height for c in crops) + gap * (len(crops) - 1)
    out = Image.new("RGB", (W, H), "white")
    y = 0
    for c in crops:
        out.paste(c, ((W - c.width) // 2, y)); y += c.height + gap
    out.save(f"{outdir}/{name}_长图.png")
    out.convert("RGB").save(f"{outdir}/{name}_长图.jpg", quality=92)
    print(f"      {outdir}/{name}_长图.png  {out.size}")
PY

echo "[4/4] 完成："
ls -la "$OUTDIR"/${NAME}*.pdf "$OUTDIR"/${NAME}*_p*.png 2>/dev/null || true
[[ $LONG -eq 1 ]] && echo "长图: $OUTDIR/${NAME}_长图.png"
