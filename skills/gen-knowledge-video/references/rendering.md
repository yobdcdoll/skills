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
  watermark.json    # 可选；含 mark/key，不要提交
  audio/
    full.wav
    <segment>.wav
  frames/
    f00000.jpg
    .watermark.json # 水印状态，自动生成
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

改了旁白、声音、`speed`、段落 id 或 `gap/lead/tail` 之后，必须从第一步重跑。不要只改音频或只改字幕。

## 3. render.sh 的行为

1. 检查 `script.json`、`scene.html`、`audio/full.wav`、`cues.js`、`subtitles.js`、`scene-data.js` 是否存在；
2. 如果 `LAYOUT_CHECK=1`，先跑 `check_layout.mjs`，发现文字越界/重叠/压字幕就退出；
3. 如果 `script.json.kind === "code"`，跑 `check_code_samples.mjs`：没有代码块、代码少于 5 行/多于 14 行、没有真实输出、没有 `data-cue`，都直接退出；
4. 从 `audio/full.wav` 读时长，算出 `ceil(duration × fps)` 帧；
5. 把帧区间均分给 N 个 `render_range.mjs` 进程；区间左闭右开、互不重叠；
6. 检查帧数完整；
7. 如果存在 `watermark.json`，对 `frames/` 嵌入隐藏水印（`WATERMARK=0` 跳过）；
8. 用 ffmpeg 合成 H.264 + AAC，输出 `<id>.mp4`；
9. 打印 `ffprobe` 结果。

环境变量：

- `OUT=...` 输出文件名
- `CRF=20`、`PRESET=veryfast`
- `FORCE=1` 清空非空 `frames/` 后重渲
- `LAYOUT_CHECK=1` 渲染前检查文字排版
- `WATERMARK=0` 即使有 `watermark.json` 也不嵌入水印

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

依赖：`ffmpeg` / `ffprobe`、`python3` + `edge-tts`、`node` + Playwright（或 `playwright-core` + 本机 Chrome/Edge）。启用隐藏水印时还需要 `python3` 的 `numpy` 和 `pillow`。

```bash
python3 -m pip install edge-tts
python3 -m pip install numpy pillow        # 仅隐藏水印需要
npm i playwright && npx playwright install chromium   # 或复用本机 Chrome/Edge
```

- `render_range.mjs` 依次尝试 `BROWSER_PATH`、macOS/Linux/Windows 常见 Edge/Chrome/Chromium 路径，再退回 Playwright 自带 Chromium。
- `playwright-core` 不自带浏览器；都找不到时先 `npm i playwright && npx playwright install chromium`。
- macOS 上不要依赖 Playwright 自带 ffmpeg 做 `recordVideo`，常见报错是 `ffmpeg-mac` 不存在。用系统 ffmpeg 自己合成。
- 渲染前等 `document.fonts.ready`，非中文语言也要确认对应字体存在。
- 同一台机器并行 4 个浏览器实例通常足够；再多会抢 CPU。
- Windows 下 `render.sh` 需要 WSL 或 Git Bash；也可以直接对每个分片运行 `node render_range.mjs <start> <end> <fps>`，再用 ffmpeg 合成。

## 7. 排版检查

```bash
node <skill>/scripts/check_layout.mjs          # 从课程目录运行
node <skill>/scripts/check_layout.mjs --warn   # 只报告，不失败
LAYOUT_CHECK=1 bash <skill>/scripts/render.sh 15 4
```

它沿时间轴每 0.5s 调用一次 `renderAt(t)`，检查所有可见文字元素：

- 是否越出 1920×1080 画布；
- `scrollWidth > clientWidth`（横向溢出）；
- 有 `overflow:hidden`/`max-height` 时的纵向裁切；
- 两个文字元素是否互相压住；
- 是否压住 44px 字幕。

大字号本身的行框高于字形是正常现象，不会被误报。发现问题时先改文案/拆屏，不要缩到最小字号以下。

## 8. 代码样例检查

```bash
node <skill>/scripts/check_code_samples.mjs
```

只对 `script.json.kind === "code"` 生效，`render.sh` 会自动执行。检查：

- 至少一个 `<pre class="code">`，5–14 个非空行；
- 代码块声明 `data-segment`，且落在 `example` / `how` / `apply` / `demo` 段；
- 每行用 `data-cue` 绑定旁白句；
- 至少一个非空的 `<pre class="code-out">` 输出块。

不通过直接退出，不产出成片。完整结构见 `code-scene-template.html`。

## 9. 隐藏水印

```bash
python3 <skill>/scripts/watermark.py embed-frames --frames frames --config watermark.json
python3 <skill>/scripts/watermark.py extract --video <id>.mp4 --key "<key>"
```

`render.sh` 会在编码前自动执行 embed-frames。原理、参数、抗压范围和排错见 `references/watermark.md`。需要 `numpy` + `pillow`。
