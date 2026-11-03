# 渲染管线

从课程目录运行；所有脚本读写当前工作目录的 `script.json`、`audio/`、`frames/`。

## 1. 目录

```
lesson/
  script.json
  scene.html
  scene-data.js
  timeline.json
  cues.json
  cues.js
  subtitles.js
  <id>.srt
  audio/
    full.wav
    <segment>.wav
  frames/
    f00000.jpg
  <id>.mp4          # render.sh 默认按 script.json 的 id 命名，可用 OUT= 覆盖
  index.html
  render-0.log ...
```

## 2. 顺序

```bash
python3 <skill>/scripts/build_audio.py        # 音频 + timeline + cues
node <skill>/scripts/build_subtitles.mjs      # cues.js + subtitles.js + SRT
# 写/改 scene.html，先用 ?preview 看一遍
bash <skill>/scripts/render.sh 15 4           # 分片渲染 + ffmpeg
```

改了旁白、声音、语速、段落 id 或 `gap/lead/tail` 之后，必须从第一步重跑。不要只改音频或只改字幕。

## 3. render.sh 的行为

1. 检查 `script.json`、`scene.html`、`audio/full.wav`、`cues.js`、`subtitles.js`、`scene-data.js` 是否存在；
2. 从 `audio/full.wav` 读时长，算出 `ceil(duration × fps)` 帧；
3. 把帧区间均分给 N 个 `render_range.mjs` 进程；区间左闭右开、互不重叠；
4. 检查帧数完整；
5. 用 ffmpeg 合成 H.264 + AAC，输出 `<id>.mp4`；
6. 打印 `ffprobe` 结果。

环境变量：

- `OUT=...` 输出文件名
- `CRF=20`、`PRESET=veryfast`
- `FORCE=1` 清空非空 `frames/` 后重渲

## 4. render_range.mjs 的行为

- 每帧调用 `window.renderAt(i / fps)`，不依赖墙上时间；
- 启动后检查 `window.TIMELINE`、`window.CUES`、`window.SUBTITLES`；
- 收集 `missing cue` 警告和 pageerror，发现任何一项就非零退出；
- 等 `document.fonts.ready` 后再开始截图；
- 可用 `SCENE`、`BROWSER_PATH`、`WIDTH`、`HEIGHT`、`QUALITY` 覆盖默认值。

## 5. 帧率与体积

- 图解、文字、公式类内容 **15fps 足够**。
- 有连续位移动画、手写笔迹、实拍素材时，才用 30fps。
- 16 分钟 15fps 约 14,400 帧，成品约 30–50MB；8 分钟约 15–25MB。
- JPEG quality 88–92；纯文字场景可以到 92。不要用 PNG 存上万帧。

编码参数起点：

```bash
ffmpeg -y -framerate 15 -i frames/f%05d.jpg -i audio/full.wav \
  -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -shortest -movflags +faststart "<id>.mp4"
```

`-shortest` 防止音频比画面长时尾部黑屏；跑完必须核对 `duration` 与 `audio/full.wav` 一致（±0.1s）。渲染完先别删 `frames/`，QA 抽帧还要用。

## 6. 环境与跨平台

依赖：`ffmpeg` / `ffprobe`、`python3` + `edge-tts`、`node` + Playwright（或 `playwright-core` + 本机 Chrome/Edge）。

```bash
python3 -m pip install edge-tts
npm i playwright && npx playwright install chromium   # 或复用本机 Chrome/Edge
```

- `render_range.mjs` 依次尝试 `BROWSER_PATH`、macOS/Linux/Windows 常见 Edge/Chrome/Chromium 路径，再退回 Playwright 自带 Chromium。
- `playwright-core` 不自带浏览器；都找不到时先 `npm i playwright && npx playwright install chromium`。
- macOS 上不要依赖 Playwright 自带 ffmpeg 做 `recordVideo`，常见报错是 `ffmpeg-mac` 不存在。用系统 ffmpeg 自己合成。
- 渲染前等 `document.fonts.ready`，非中文语言也要确认对应字体存在。
- 同一台机器并行 4 个浏览器实例通常足够；再多会抢 CPU。
- Windows 下 `render.sh` 需要 WSL 或 Git Bash；也可以直接对每个分片运行 `node render_range.mjs <start> <end> <fps>`，再用 ffmpeg 合成。
