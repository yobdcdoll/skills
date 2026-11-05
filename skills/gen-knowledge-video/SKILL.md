---
name: gen-knowledge-video
description: 把任意知识点或技能点做成可自学的教学视频（旁白 + 画面 + 内嵌字幕 + SRT + 播放页 + 复习节奏）。当用户要求为某个概念、原理、机制、操作步骤、语言发音或考试知识点做讲解视频、教学视频、微课、科普视频，或把讲义、脚本、样片做成 4–20 分钟成片时使用；尤其适用于画面、语音、字幕需要逐句对齐的场景。需要给成片加不可见、可抗同分辨率二次压缩的个人水印时也使用。
metadata:
  version: 1.3.4
---

# 知识点 / 技能点教学视频

把**一个**知识点或技能点做成一套能自学的课：视频 + 播放页 + 看前/看后检查 + 24h/3d/7d 复习节奏。时长按内容定，通常 4–12 分钟；内容确实多时可到 20 分钟，**不要把短知识点硬拉长**。

这不是把 PPT 录屏，也不是把讲稿念一遍。核心是把知识拆成一条**可看、可听、可复述**的因果链，并让画面严格跟着旁白走。

适用：概念解释、原理机制、操作步骤、语言发音、理科推导、历史事件、工具用法等。
不适用：纯素材剪辑、真人出镜拍摄、以实拍为主的 vlog。这类只借用本技能的时间码/字幕/渲染管线，不要套课程骨架。

## 不可违背的六条

1. **单一时间源**：所有画面节拍、字幕、章节进度都来自同一份逐句时间码（`cues.json`）。禁止在场景里写死“第 3.2 秒出现”。
2. **音频和 cues 必须来自同一次合成或对齐**：不要先生成音频、再跑一遍 TTS 取时间码。两次合成长度可能不同，后面必然漂移。用户自带录音时，必须用同一次强制对齐产出 cues。
3. **`renderAt(t)` 是纯函数**：给定任意 `t`，画面状态唯一确定。禁止依赖 CSS animation/transition、`Date.now()`、`requestAnimationFrame` 或上一帧状态。
4. **正片时间轴必须由帧号决定**：不要用实时录屏作为正片。CDP screencast、Playwright `recordVideo`、屏幕录制都会因机器负载产生不均匀帧间隔，导致音画漂移。录屏或实拍素材可以先录好，再按时间码嵌入逐帧渲染的场景。
5. **先做一讲，再批量**：先交付一个完整样片，让用户确认声音、节奏、画面风格。确认前不要批量生产其余知识点。
6. **交付前逐帧抽查**：`ffprobe` 只证明文件能播，不证明画面对。必须在每个段落的开头、中段和关键数字处抽帧，亲自看字幕和图形是否对得上。

## 快速开始

```bash
mkdir my-lesson && cd my-lesson

# 0. 可选：先标定目标音色的实际语速，用来估字数
python3 <skill>/scripts/calibrate.py

# 1. 写 script.json（结构见第 2.4 节；先定 lang、target_minutes、speed、槽位）
# 2. 一次 TTS：音频 + timeline + cues
python3 <skill>/scripts/build_audio.py
# 3. 字幕
node <skill>/scripts/build_subtitles.mjs
# 4. 复制 references/scene-template.html 为 scene.html，按你的槽位改
# 5. 逐帧渲染 + 编码（15fps，4 个分片；有 watermark.json 会自动嵌入水印）
bash <skill>/scripts/render.sh 15 4
# 6. 按 references/qa-checklist.md 抽帧检查，再改 index.html
```

先跑通一讲，再批量。

---

## 0. 先定契约

动手前先确认这些决定；能从上下文推断的就不要问，推断不了再问：

| 决定 | 默认 | 怎么定 |
| --- | --- | --- |
| 范围 | **一个**知识点或技能点一讲 | 一讲塞多个知识点必然变成念目录 |
| 时长 | 4–12 分钟，按内容定 | 见 `references/lesson-arc.md` 的分档；短知识点不要凑到 15 分钟 |
| 语言 | 跟随用户和材料；默认中文 | 决定音色、字体、字幕切分和语速预算 |
| 语速 | 在预设音色基础上再 **1.24×**（`speed: 1.24`） | 见 2.1 与 3.2；不要另外手工调 `rate` 来提速 |
| 声音 | 中文默认 `xiaoxiao-calm` 预设（Xiaoxiao + rate `-12%` + pitch `-6Hz`） | 见第 3.1 节 |
| 交付物 | 视频 + `index.html` + SRT + 检查题 | 只给 MP4 就只是“看过”，不是“学会” |
| 复习节奏 | 即时 + 24h + 3d + 7d | 把视频变成学习闭环 |
| 风格 | 纸感/墨色 + 两个强调色 | 高对比、低装饰、长时间看不累；可按主题换 |
| 画幅 | 16:9，1920×1080 | 短视频/竖屏需求要单独确认 |

如果用户只要视频，仍然建议附一个极简播放页和 SRT；但不要擅自扩成整套课程系统。

---

## 1. 课程结构

完整槽位、可选模块和时长分档见 `references/lesson-arc.md`。核心是七个**必选槽位**：

| # | 槽位 | 回答的问题 | 时长参考 |
| --- | --- | --- | --- |
| 01 | `hook` | 不知道它会怎样？ | 30–60s |
| 02 | `define` | 它到底是什么？ | 30–60s |
| 03 | `how` | 它为什么/怎么成立？ | 60–150s |
| 04 | `example` | 具体跑一遍是什么样？ | 60–120s |
| 05 | `boundary` | 什么时候不成立、容易错？ | 45–90s |
| 06 | `apply` | 怎么用、怎么选？ | 45–90s |
| 07 | `recap` | 带走什么？ | 30–50s |

可选模块：`context`、`compare`、`derive`、`misconception`、`practice`、`extension`、`interview`、`history`、`demo`、`pronunciation`。按知识点类型拼装，不要为了凑时长全加。

时长分档：

| 目标时长 | 段数 | 构成 |
| --- | --- | --- |
| 4–6 分钟 | 7–8 | 七个必选槽位；`how` 不拆 |
| 7–10 分钟 | 8–11 | 必选 + 1–3 个可选模块 |
| 11–15 分钟 | 11–14 | 必选 + 3–6 个可选模块 |
| 16–20 分钟 | 14–18 | 必选 + 6–9 个可选模块，仅当前置知识、多个例子、练习都需要时使用 |

关键不是段数，而是**每一段只回答一个问题**。如果一段里出现两个“为什么”，拆开。如果某段删掉后后面完全不受影响，删掉。

---

## 2. 写脚本

### 2.1 语速与字数

不要用固定常数估所有语言。先标定：

```bash
python3 <skill>/scripts/calibrate.py
```

它会读取 `script.json` 的 voice/rate/pitch/lang/speed，合成一段标准样本，按 `speed` 折算后输出当前音色的实测语速，以及 4/6/8/10/12/15/18 分钟对应的旁白预算。

没有标定工具时，用公式：

```
旁白字符数 ≈ (目标秒数 − lead − tail − gap × (段数 − 1)) × 实测字/秒
```

参考实测（`xiaoxiao-calm`，即 `zh-CN-XiaoxiaoNeural` + rate `-12%` + pitch `-6Hz`）：中文约 **4.0 字符/秒（含标点）**，约 **3.6 汉字/秒**。技能默认再叠加 `speed: 1.24`，所以按 **约 4.9 字符/秒、4.2 汉字/秒** 估预算。不同音色、语速、语言差异很大，英文按词/分钟另测，不要直接套用中文数字。

`calibrate.py` 已经算进 `speed`，直接看它输出的预算；`speed` 只作用于旁白，`lead/gap/tail` 的停顿不变。

先按目标时长估字数，写完再实测。不要先写 8000 字再指望剪到 16 分钟。

### 2.2 句子规则

- **一句一个画面节拍**。一句话里不要同时出现“定义 + 例子 + 例外”，否则画面只能猜。
- 短句优先。中文知识内容 20–35 字一句；英文 12–22 词一句。
- 先给结论，再给原因；先给直觉，再给术语。
- 术语第一次出现时，用一句人话解释，不要直接堆缩写。
- **代码类知识点必须配“可写可用”的例子**：至少一个最小可运行片段，展示完整语法、放在哪个类/方法、怎么调用、输入和输出是什么。例子可以简单，但要**完整、丰富**：完整上下文 + 真实输入输出 + 至少一个变式或边界；不要只给孤立的一行，也不要堆成一个项目。不要只讲定义、原理或伪代码；先给能跑的例子，再抽象规则。
- **视频是唯一 output**：不要在旁白或画面里说“源码在 GitHub / 仓库 / 课程页 / 简介 / 评论区”，也不要把关键内容留给外部资料。需要的代码、输入、输出、结论都必须在视频里出现；代码太长就拆场景，不要指路。
- 不逐行念代码、公式或表格。念**意图**：“先看表为空不空”，而不是“if table equals null resize”。
- 数字要具体：“容量 16，阈值 12，第 13 个元素触发扩容”，不要“容量比较小的时候”。
- 每段结尾留一句过渡，把下一段接上。

### 2.3 代码、公式与符号的读法

TTS 念符号经常翻车。脚本里写**口语化写法**，不要把手写符号直接粘进旁白：

| 类型 | 不要写 | 写成 |
| --- | --- | --- |
| 代码表达式 | `if ((e.hash & oldCap) == 0)` | `如果 hash 和 oldCap 按位与的结果是 0` |
| 位运算 | `h ^ (h >>> 16)` | `hash 异或上它自己右移 16 位` |
| 数学公式 | `a² + b² = c²` | `a 的平方加 b 的平方等于 c 的平方` |
| 分数 | `(x+1)/(x-1)` | `x 加 1 除以 x 减 1` |
| 化学式 | `H₂SO₄` | `硫酸`，画面里单独标注化学式 |
| 英文缩写 | `API`、`CPU` | 第一次出现：旁白念完整英文（或中文全称）；画面写 `API（Application Programming Interface）`。之后只写缩写、可念字母 |

写完后先让 TTS 念 2–3 句试听，确认没有把术语、数字、英文缩写念得奇怪。画面里可以显示原始符号，但旁白必须是能听懂的口语。

**英文缩写的首现规则（整讲只展开一次）：**

- 一个视频中第一次出现某个英文缩写时，**画面必须同时写缩写和完整英文**，例如 `API（Application Programming Interface）`、`CPU（Central Processing Unit）`。不要只写缩写，也不要只写中文翻译。
- 旁白第一次念完整英文，或念中文全称；之后念缩写。
- 后续出现只写缩写，不要每个场景重复展开；重复展开会挤占画面，也会让观众误以为换了概念。
- 全称太长时允许占两行或降到 30px，但不能省略；标题、页眉、定义卡里首次出现同样适用。
- 脚本阶段先列一份本讲 `缩写 → 完整英文` 清单，渲染前逐项核对首现位置。

### 2.4 脚本格式

`script.json`：

```json
{
  "id": "compound-interest",
  "title": "复利",
  "lang": "zh-CN",
  "audience": "高中生",
  "target_minutes": 8,
  "preset": "xiaoxiao-calm",
  "speed": 1.24,
  "gap": 0.35,
  "lead": 0.8,
  "tail": 0.8,
  "subtitle": { "max_cjk": 32, "max_latin": 42 },
  "segments": [
    { "id": "hook", "role": "hook", "label": "开场", "text": "..." },
    { "id": "define", "role": "define", "label": "定义", "text": "..." },
    { "id": "how", "role": "how", "label": "原理", "text": "..." },
    { "id": "example", "role": "example", "label": "算一遍", "text": "..." },
    { "id": "boundary", "role": "boundary", "label": "边界", "text": "..." },
    { "id": "apply", "role": "apply", "label": "怎么用", "text": "..." },
    { "id": "recap", "role": "recap", "label": "总结", "text": "..." }
  ]
}
```

- `id` 只能用字母、数字、下划线、连字符，且不能重复；一旦定下就不要改：场景、cues、字幕、文件名都依赖它。
- `role` 用于指导脚本和模板选择，渲染脚本不会读它；可以省略。
- `lang` 影响字幕切分、字体和播放页文案。
- `preset` 选语音预设，中文默认 `xiaoxiao-calm`；显式 `voice` / `rate` / `pitch` 会覆盖预设。预设定义见 `scripts/voice_presets.py`。
- `speed` 是**预设之上的整体语速倍率**，默认 `1.24`；`build_audio.py` 用 ffmpeg `atempo` 实现并同步缩放 cues，音高不变。`1.0` 表示保持原始语速；要更慢/更快就改这一个值，不要同时改 `rate`。
- `audience`、`target_minutes` 只用于规划，不参与合成。
- `subtitle` 可省略，默认中文 32 字、英文 42 字符。

---

## 3. 配音

### 3.1 声音选择

按语言选默认音色，再用 `edge-tts --list-voices` 确认当前可用名称：

| 预设 | 音色 | 参数 |
| --- | --- | --- |
| `xiaoxiao-calm`（默认） | `zh-CN-XiaoxiaoNeural` | rate `-12%`，pitch `-6Hz` |
| `xiaoxiao-default` | `zh-CN-XiaoxiaoNeural` | rate `-5%`，pitch `0Hz` |
| `yunxi-calm` | `zh-CN-YunxiNeural` | rate `-10%`，pitch `0Hz` |
| `aria-calm` | `en-US-AriaNeural` | rate `-8%`，pitch `0Hz` |
| `sonia-calm` | `en-GB-SoniaNeural` | rate `-8%`，pitch `0Hz` |
| `nanami-calm` | `ja-JP-NanamiNeural` | rate `-8%`，pitch `0Hz` |

- `script.json` 里写 `"preset": "xiaoxiao-calm"` 即可；显式 `voice` / `rate` / `pitch` 会覆盖预设。
- Edge TTS 免费接口没有 Azure 的 `mstts:express-as style="calm"` 参数；这里的 calm 是**音色 + 语速 + 音高**的固定预设。确实需要 Azure 的 calm style 时，按 `references/pipeline-contract.md` 替换 TTS 层。
- 默认只用 AI 配音，不用真人出镜或真人录音；如果用户要真人声，必须由用户提供并确认授权。
- 技术/知识内容不要用 TTS 裸默认语速；本技能默认是 `xiaoxiao-calm` 再叠 **1.24×**，节奏比“慢速讲课”紧，但仍留段间停顿。改 `speed` 后必须整讲试听，确认没有吞字、术语听不清。
- 如果用户要“更冷/更 nerd/更成熟”，优先在**`speed`、音高、停顿**上调，不要频繁换声线；换声线会让整讲气质断裂。
- 用户明确说不要男声，就不要推荐男声，也不要偷偷混用。
- **不要克隆真实人物的声音**，除非本人明确授权。可以推荐音色相近的授权声音，但不要做声音复刻。
- 声音比较页只保留一个文件、在同一页里切换试听；不要每轮新建一个 HTML。

### 3.2 音频规格

- Edge TTS 输出 MP3，转 **48kHz / 单声道 / PCM s16le WAV**。
- 提速用 ffmpeg `atempo`（默认 `speed: 1.24`），**不要**用 `asetrate`（会变调）或播放器倍速（不会写进成片）。`atempo` 只改旁白，`lead/gap/tail` 保持原值。
- 已生成过的课程：在 `script.json` 加/改 `speed`，然后按 `build_audio.py → build_subtitles.mjs → 重渲染` 全链路重跑。画面和字幕是烧进帧里的，**不能只换 `audio/full.wav`**。
- 提速后必须用**实测的新段时长 / 原 MP3 时长**缩放该段所有 cue，不能只按 1.24 除；MP3 容器有 padding，直接除会越到段尾越偏。
- 开头留 `lead = 0.8s`，段间 `gap = 0.35s`，结尾留 `tail = 0.8s`。
- 最后把所有分段拼成 `audio/full.wav`，视频以它为准。
- `timeline.total` 必须用 `ffprobe` 读 `full.wav` 的实际时长，不要只用 `lead + 各段时长 + gap + tail` 估算；拼接时最后一段后面不要再补一个 gap，否则音频会比时间轴长，`-shortest` 会悄悄截掉尾部。
- 如需统一响度，可在最终混音时做一次 `loudnorm`；不要在每段单独做，否则段间响度会跳。

### 3.3 一次合成，同时拿音频和 cues

用 `scripts/build_audio.py`。它在**同一次** `edge_tts.Communicate.stream()` 里同时收集：

- `type == "audio"` 的音频块 → 写 MP3
- `type == "SentenceBoundary"` 的逐句起止 → `cues.json`
- `type == "WordBoundary"` 的逐词起止 → 一并保存，英文场景可选用

随后按 `speed`（默认 1.24）对 MP3 做 `atempo`，转 WAV，并用实测时长比例缩放同一批 cues。因此音频、timeline、cues 仍然是**同一次合成 + 同一次提速**的结果，下游不用再乘除倍率。

中文的 `WordBoundary` 经常为空，**不要依赖它做对齐**；以 `SentenceBoundary` 为准。如果某段连 `SentenceBoundary` 都没有，脚本会按标点比例切分并给出警告。

```bash
cd <lesson-dir>
python3 <skill>/scripts/build_audio.py
```

产出：

```
audio/<segment>.mp3
audio/<segment>.wav
audio/full.wav
timeline.json
scene-data.js
cues.json
```

`timeline.json` 的 `segments[].start` 是**整段在成片中的绝对起点**；`cues.json` 的句子时间是**相对该段音频开头**的。渲染时记得加 `seg.start`。

### 3.4 用户自带录音或换 TTS

只要最终产出满足同一份契约，渲染管线不需要改：

- `audio/full.wav`：48kHz 单声道 PCM
- `timeline.json`：每段绝对起止
- `cues.json`：每段句级时间码（段内相对）

自带录音必须用**同一次强制对齐**产出 cues，不能先有音频再凭感觉写时间。详细格式和替换方法见 `references/pipeline-contract.md`。

---

## 4. 画面、语音、字幕对齐

这是整个流程最容易翻车、也最值得投入的地方。

### 4.1 唯一正确做法：cue 驱动

场景里的每个视觉节拍都调用：

```js
const c = i => cue('example', i);   // 第 example 段第 i 句的起点（段内秒）
```

例如：

```js
// 错：写死秒数，旁白一慢就漂
if (lt > 8.9) showOrderCard();

// 对：旁白说到这句才出现
if (lt >= c(2)) showOrderCard();
```

`cue()` 的时间是**段内相对时间**，所以场景渲染器里用 `lt = t - seg.start`，不要再加一次 `seg.start`。

### 4.2 不要吞掉缺失的 cue

```js
const cue = (id, i) => {
  const s = CU[id]?.sentences?.[i];
  if (!s) {
    console.warn(`missing cue: ${id}[${i}]`);
    return 0;
  }
  return s.start;
};
```

返回 `0` 会让缺失的节拍全部堆在段首，看起来像“画面提前了”。`render_range.mjs` 会收集 `missing cue` 警告并**阻止出片**；只要出现 missing cue，先修数据，不要靠抽帧碰运气。

### 4.3 改动即全链路重跑

只要改了以下任何一项：

- 旁白文字
- 声音 / 语速 / 音高（含 `speed`）
- 段落顺序或段落 id
- `gap` / `lead` / `tail`

就必须按顺序重跑：

```
build_audio.py → build_subtitles.mjs → 重新渲染帧 → ffmpeg
```

不要只改音频、或只改字幕。三者共用一份时间码，拆开改必然错位。

### 4.4 自检

- 随机抽 10 个句子，打印 `cue(seg,i)`，和 `timeline.json` 的段起点相加，确认落在成片时间轴上。
- 抽帧时优先选“数字变化”“高亮切换”“场景切换”的瞬间，而不是随便选中间帧。
- 如果某一整段都偏，先查 `seg.start` 是否加错；如果越到后面越偏，查是否用了实时录制或硬编码节拍。

---

## 5. 字幕

### 5.1 生成

`scripts/build_subtitles.mjs` 读取 `cues.json` + `timeline.json`，做三件事：

1. 把每句按标点切成字幕条；中文默认 ≤32 字，英文默认 ≤42 字符，可通过 `script.json` 的 `subtitle.max_cjk` / `subtitle.max_latin` 覆盖。
2. 在句子内部按字符数比例分配时间（句边界是精确的，句内是近似）。
3. 输出 `subtitles.js`（渲染用）、`cues.js`（场景用）和 `<id>.srt`（外挂）。

过长的中文句子优先在标点处切；没有标点时用词边界切，避免把词硬切成两半。仍然放不下时，渲染端允许两行显示，不要裁字。

```bash
node <skill>/scripts/build_subtitles.mjs
```

### 5.2 样式

- 位置：底部 `bottom: 76px`，避开进度条和时间码。
- 字号：**44px**（下限 40px），行高 1.36；最大宽度 1600px；居中；半透明纸色背景；圆角 10px。
- 手机优先：16:9 视频在手机横屏全屏时约按 0.44 缩放，44px 约等于屏幕上 19px；26px 只有约 11px，手机上会看不清。不要把字号缩回 20 多 px 来塞更多字。
- 单行优先；超过最大宽度时换行到两行，**不要裁掉**。两行还放不下就拆句，不要减字号。
- 字幕区域下方预留至少 **220px**，正文/代码/图示/公式不要压进来。
- 字幕颜色与正文一致，不要用高饱和色；字幕是辅助，但**可读性不能妥协**。

### 5.3 烧录与外挂

- **烧录**：`renderAt(t)` 里调用 `renderSubtitle(t)`，把当前字幕写进 `#subtitle`，随帧一起编码。任何播放器打开都有字幕。
- **外挂**：同时导出 SRT，方便剪辑、二次压制、无声播放。
- 两者必须来自同一份 `subtitles.js` 数据，不要分别维护。

### 5.4 字幕检查

- 每条 `end > start`，且不跨段落到下一段。
- Edge TTS 的句边界常带约 50ms 重叠，属正常；超过 80ms 才说明切分或时间分配有问题。
- 最长的一条必须能在 1600px 内放下（允许两行）；放不下就拆句，不要靠缩到 40px 以下解决。
- 专有名词、数字、代码标识符、公式要人工核对，TTS 的断句不等于正确断句。

---

## 6. 画面

### 6.1 画布与安全区

- 默认固定 `1920×1080`，`overflow: hidden`。用户要竖屏或其它画幅时，先确认再改场景和 viewport。
- 页眉：`top: 42px`，左右 64px，字号 20px。**只写课程系列名或知识点名，不要写课程序号**（`LESSON 01`、`第 1 讲`、`EP01`、`01` 都不要）；课程会被重排、单独发布或拆条，序号很容易过期。
- 标题：`left: 150px; top: 180px` 左右，字号 64px；正文从 `top: 320–380px` 开始。
- 底部 **220px** 留给两行 44px 字幕、章节名、进度条。
- 左右至少 140px 安全边距，避免不同播放器裁边。

字号是硬约束，不是审美偏好。视频大概率在手机上看，按 1920 宽设计时要假设观众看到的是缩小后的画面：

| 用途 | 最小字号 |
| --- | --- |
| 字幕 | 44px（下限 40px） |
| 正文、说明、列表 | 32–34px |
| 表格单元、步骤文字 | 30–34px |
| 关键数字、公式 | 50–60px |
| 小标签、章节名、时间码 | 18px（不要低于 16px） |

空间不够时：删内容 → 拆屏 → 换行，最后才考虑缩字号，且不得低于上表下限。

**字号放大后，溢出风险也会放大。** 必须按最长真实文案验证，不要用“复利”“示例”这种短占位：

- 允许纵向换行；不允许超出画面、压住字幕、或压住相邻文字/卡片。
- 文本容器加 `overflow-wrap:anywhere`；flex/grid 子项加 `min-width:0`；单行数字、公式、标签要设 `max-width` 或缩短文案。
- 不要靠固定高度或 `overflow:hidden` 把溢出“藏”起来，那等于裁字；优先拆屏或拆句。
- 渲染前跑 `LAYOUT_CHECK=1 bash <skill>/scripts/render.sh 15 4`，或单独跑 `node <skill>/scripts/check_layout.mjs`。它会沿整条时间轴扫描越界、横向溢出、元素重叠和压字幕。
- 抽帧 QA 必须包含每个场景的“最长句”时刻，不能只看短句帧。

### 6.2 视觉语法

完整画面原型见 `references/visual-grammar.md`。通用原则：

- 一屏只讲一件事。当前步骤高亮，其余降级为灰色/低透明度。
- 用**位置变化**表达流程，用**颜色变化**表达状态，用**数字变化**表达结果。
- 代码只高亮当前行；公式只高亮当前项；表格只高亮当前行/列。
- 图示元素出现要有顺序：先容器，再元素，再连线，最后结论。
- 动画时长短：0.4–0.8s；不要弹跳、旋转、闪烁。
- 两个强调色足够（例如蓝=主路径，橙=冲突/异常）；绿色/红色只用于对错结论。
- 默认用图解、表格、公式和数字说话。需要“人”时用抽象图标；操作技能可用无名的手部/实物特写或自绘素材，避免真人肖像。

### 6.3 确定性

```js
function renderAt(t) {
  setScene('hook', sceneOpacity('hook', t));
  // ...
  renderHook(t);
  renderSubtitle(t);
  updateProgress(t);
}
window.renderAt = renderAt;
```

- 每次调用都把**所有**受影响元素的 `opacity`、`transform`、`textContent`、`class` 重新设一遍。
- 不要用 `element.animate()`、CSS `@keyframes`、`transition`。
- 不要在渲染器里 `await`、`setTimeout`、读网络。
- `?preview` 可以用 `requestAnimationFrame` 做实时预览，但**正片渲染永远走 `renderAt(i/fps)`**。
- 场景函数要对缺失的段做保护：`sceneOpacity` 找不到段时返回 0，`renderXxx` 找不到段时直接 return。段 id 改名是常态，不要让模板在首帧崩掉。

### 6.4 SVG 与动态结构

- SVG 的 `<g>` 必须设置 `transform="translate(x,y)"`；只设 `x/y` 不会移动，所有节点会叠在原点。
- 需要“状态 A → 状态 B”时，**一开始就把两个状态都渲染出来**，用 `.late { opacity: 0 }` 控制显示；不要在渲染过程中 `appendChild`，否则不同帧的 DOM 结构不一致。
- 涉及数字、下标、坐标的例子，先手算一遍：结果、阈值、第几个元素触发变化。数字自洽比动画好看重要。
- 画面承诺存在的元素必须真实存在。文案说“第 17 个”，画面就要有第 17 个。

### 6.5 场景切换

场景显隐由 `timeline.json` 的段起止决定：

```js
function sceneOpacity(id, t, inD = 0.6, outD = 0.6) {
  const s = getSeg(id);
  if (!s) return 0;
  const a = inD > 0 ? clamp((t - (s.start - inD / 2)) / inD) : 1;
  const b = outD > 0 ? clamp(((s.end + outD / 2) - t) / outD) : 1;
  return Math.min(a, b);
}
```

不要用固定秒数切场景。段与段之间留 0.3–0.6s 的交叉淡入淡出即可。**第一段用 `inD = 0`，最后一段用 `outD = 0`**；否则首帧和末帧会落在淡入淡出的透明区，导出后就是空白。

---

## 7. 渲染管线

从课程目录运行：

```bash
python3 <skill>/scripts/build_audio.py        # 音频 + timeline + cues
node <skill>/scripts/build_subtitles.mjs      # cues.js + subtitles.js + SRT
# 写/改 scene.html，先用 ?preview 看一遍
bash <skill>/scripts/render.sh 15 4           # 分片渲染 + ffmpeg
```

- `render.sh` 先检查 `script.json`、`scene.html`、`audio/full.wav`、`cues.js`、`subtitles.js`、`scene-data.js`，再按 `audio/full.wav` 时长分片渲染并合成 `<id>.mp4`。
- `LAYOUT_CHECK=1` 会在渲染前跑 `check_layout.mjs`；发现文字越界、横向溢出、元素重叠或压字幕就直接失败。交付前至少跑一次。
- 当前目录有 `watermark.json` 时，`render.sh` 会在编码前对 `frames/` 嵌入隐藏水印；`WATERMARK=0` 可临时关闭。见第 12 节。
- `render_range.mjs` 检查 `window.TIMELINE/CUES/SUBTITLES` 是否加载，并收集 `missing cue`；有问题直接非零退出，不产出成片。
- 图解、文字、公式类 15fps；连续位移、手写、实拍素材 30fps。JPEG quality 88–92。
- 跑完核对成片时长与 `audio/full.wav` 一致（±0.1s）。
- 改旁白/声音/`speed`/段 id/`gap/lead/tail` 后必须全链路重跑。

目录结构、ffmpeg 参数、分片规则、跨平台浏览器与依赖安装见 `references/rendering.md`。

---

## 8. 播放页与学习闭环

`index.html` 至少包含（可直接改 `references/player-template.html`）：

1. `<video controls preload="metadata" poster="...">`，`src` 指向成片。
2. 看前基线 5 题（不评分，只暴露盲区）。
3. 看后检查 3 件事：手写主流程/复述、回答 N 个追问、做 3 道检查题。
4. 复习日期：看完当天 + 24h + 3d + 7d。**以首次打开页面为锚点**，存进 localStorage，不要每次加载都从今天重算。
5. 自评表：理解度/可复述度/可应用度，导出 JSON。
6. 时间轴表：每段起止时间 + 一句话内容，方便回看。建议直接从 `timeline.json` 生成，避免和成片脱节。

注意：

- 视频文件必须真实存在且完整，否则浏览器显示 `0:00`、播放按钮灰色。用 `ffprobe` 和页面里的 `video.duration`、`readyState` 双重确认。
- 重新出片后给 `src` 加 `?v=<timestamp>`，避免浏览器缓存旧文件。
- `file://` 下个别浏览器会限制视频 Range 请求；推荐 `python3 -m http.server` 后访问 `http://localhost:8000/`。
- 播放页不是装饰：没有检查题的课程，用户只会“看过”，不会“学会”。

---

## 9. 交付前 QA

完整清单见 `references/qa-checklist.md`。最低限度：

```bash
ffprobe -v error -show_entries format=duration,size:stream=codec_name,width,height,r_frame_rate \
  -of default=nw=1 <id>.mp4
```

- 时长与 `audio/full.wav` 一致；分辨率符合约定；帧率符合预期；有 H.264 + AAC。
- 跑 `node <skill>/scripts/check_layout.mjs`：没有越界、横向溢出、文字重叠、压字幕；检查必须覆盖最长文案时刻。
- 有 `watermark.json` 时，对成片和一次 CRF 30 重编码副本都能提取出同一 mark。
- 每个段落开头 + 中段 + 关键数字处抽帧，至少 10 张，逐张看：
  - 字幕文字是否就是该时刻旁白；
  - 高亮/数字是否已经切换；
  - 有没有文字重叠、裁切、空白场景；
  - 底部字幕有没有压住正文；
  - 字幕 ≥40px、正文 ≥32px；缩到约 25% 宽时仍能读出（模拟手机）。
- 第一帧和最后一帧不能是空白或半透明过渡。
- `subtitles.js` 条目数、SRT 条目数一致；无负时长、无跨段、无超宽。
- 播放页里 `video.duration > 0`、`readyState >= 3`、`video.error === null`。

**没有亲自看过抽帧，就不要说“已对齐”。** `ffprobe` 只能证明容器没问题。

---

## 10. 常见坑（血泪版）

1. **把长视频当默认**。短知识点硬加水，观众 3 分钟能学会的拖到 15 分钟。先按 `lesson-arc.md` 选档。
2. **用 CS 面试骨架套所有内容**。`thread`、`contract`、`interview` 是可选模块，不是每讲必选。
3. **实时录屏 = 音画漂移**。CDP screencast 在负载下帧间隔从 7fps 到 20fps 不等，合成后画面跟不上声音。逐帧渲染是唯一稳的方案。
4. **Playwright `recordVideo` 在 macOS 上缺 ffmpeg**。报 `ffmpeg-mac` 不存在；直接用系统 ffmpeg。
5. **硬编码动画节拍**。旁白一长，后面全漂；必须改成 `cue(seg, i)`。
6. **音频和 cues 分两次 TTS**。两次合成长度可能差几十毫秒到几百毫秒；必须同一次流里同时取。
7. **`WordBoundary` 当主力**。中文经常为空；用 `SentenceBoundary`，`WordBoundary` 只做英文增强。
8. **缺失 cue 返回 0**。所有缺失节拍堆在段首，看起来像“画面提前”；必须告警并阻止出片。
9. **SVG 节点不设 transform**。所有 `<g>` 叠在原点，画面看起来“树消失了”。
10. **例子数字不自洽**。先手算，再写代码；画面承诺的元素必须真实存在。
11. **字幕压住正文或裁字**。正文底部至少留 220px；字幕允许两行，不要 `overflow: hidden` 裁掉。
12. **语言/音色/字幕上限不匹配**。英文课用了中文字幕上限，或者中文字体栈里没有对应字体。
13. **视频显示 0s / 灰色按钮**。文件缺失、还在写入、`src` 路径错、缓存旧文件；先 `ffprobe`，再看 `video.error`。
14. **字体没加载完就截图**。渲染前 `document.fonts.ready`，并额外等 300ms。
15. **`-shortest` 掩盖了音频更长的事实**。成片比音频短会截尾；必须比对两者时长。
16. **改一句旁白只重跑音频**。cues、字幕、画面全部失效；必须全链路重跑。
17. **TTS 念代码/公式符号**。写口语化表达，先试听；画面里再显示原始符号。
18. **拼接音频时给最后一段也补了 gap**。`timeline.total` 和 `full.wav` 会对不上，`-shortest` 截掉尾部；以 `ffprobe full.wav` 的实际时长为准。
19. **批量生产**。第一讲没确认就做十讲，风格一错全部返工；先一讲，再批量。
20. **按桌面字号做画面**。26px 字幕在电脑上清楚，手机上只有 5–11px；字幕固定 44px，正文 ≥32px，空间不够就拆句、拆屏，不要缩字。
21. **提速只改了一半**。播放器倍速、只改 `rate`、只对音轨做 `atempo`、或者对成片提速后继续用旧 SRT，都会让声音和 cues/字幕/画面漂移；必须用 `script.json` 的 `speed` 让 `build_audio.py` 同步缩放，再全链路重跑。
22. **英文缩写只写缩写**。一个视频中第一次出现时必须写 `API（Application Programming Interface）` 这种“缩写 + 完整英文”，旁白念全称；之后才可只用缩写。整讲只展开一次，不要每个场景重复。
23. **代码课只讲概念**。只给定义、原理或伪代码，观众记住的是名词，不会写。每个代码知识点至少给一个“怎么写 + 怎么用 + 输出是什么”的最小例子；例子可以简单，但要完整、丰富（完整上下文 + 真实输入输出 + 一个变式或边界），必要时用“错 → 为什么错 → 改成什么”对照。
24. **在视频里给源码指路**。“完整代码见 GitHub / 仓库 / 简介链接”会让视频离开上下文就失效；视频是唯一 output，所有必要代码和结论都要在画面里。代码太长就拆场景，不要外链。
22. **字号放大了，却只用短占位词检查**。正文 34px 后，一句长句就可能把卡片撑破、压住公式或字幕；用最长真实文案跑 `check_layout.mjs`，不要用固定高度或 `overflow:hidden` 裁字。
23. **把隐藏水印当 DRM，或重复嵌入**。同分辨率重压能扛，缩放/裁剪不保证；对已带标记的帧再嵌一次会让 alpha 叠加变可见，换标记必须重新渲染。

---

## 11. 交付

交付时说明：

- 成片路径、时长、分辨率、帧率、体积；
- 字幕：内嵌 + SRT 路径；
- 声音：音色、rate、pitch、语言、`speed`；
- 隐藏水印：mark、是否已验证、验证命令；
- 抽帧检查了哪些时间点，分别确认了什么；
- 还有哪些存疑处（数字、发音、画面细节）；
- 下一步建议（先看哪一段、先做哪些检查题）。

不要擅自发布到外部平台；不要未经确认批量生产后续知识点。

---

## 12. 个人隐藏水印（可选）

用户要“视频里有我的隐藏标记”时使用。完整参数、抗压测试和排错见 `references/watermark.md`。

```bash
# 1. 课程目录放 watermark.json（可从 references/watermark.example.json 复制；不要提交，含密钥）
#    { "mark": "yobdcdoll", "key": "只有你知道的密钥", "alpha": 12 }
# 2. 正常出片；render.sh 会自动在编码前嵌入
bash <skill>/scripts/render.sh 15 4
# 3. 验证
python3 <skill>/scripts/watermark.py extract --video <id>.mp4 --config watermark.json
```

- 标记写进亮度通道的中频 DCT 系数，每帧重复；肉眼不可见，同分辨率重新压缩到 CRF 30–36 仍可提取。
- 需要 `numpy` + `pillow`；`watermark.json` 含密钥，必须加进 `.gitignore`。
- `mark` 最多 12 个 UTF-8 字节；身份较长时写短 ID。
- **不保证**扛缩放、裁剪、旋转或极低码率；要覆盖这些场景需重新出片。它是溯源标记，不是 DRM。
- 已经出好的 MP4 可用 `watermark.py embed-video` 补写，但会多一次 CRF 18 编码。
- 换标记必须重渲染，不能在一个已带标记的成片上覆盖另一个标记。

---

## 参考文件

- `references/lesson-arc.md` — 必选槽位、可选模块、时长分档、跨领域示例、检查题设计
- `references/visual-grammar.md` — 画面原型、公式与符号、技能类素材边界、最小片段
- `references/pipeline-contract.md` — `full.wav` / `timeline.json` / `cues.json` 契约与替换 TTS 的方法
- `references/rendering.md` — 目录结构、ffmpeg 参数、分片规则、跨平台环境
- `references/qa-checklist.md` — 出片前逐项检查清单
- `references/watermark.md` — 个人隐藏水印的原理、参数、抗压范围与排错
- `references/watermark.example.json` — `watermark.json` 模板
- `references/player-template.html` — 播放页骨架（视频、看前/看后检查、复习日期、自评导出）
- `references/scene-template.html` — 可直接改的 `renderAt(t)` 场景骨架（含字幕、cue、场景切换）
- `references/domains/cs.md` — 计算机类知识点的槽位映射、代码读法、HashMap 示例
- `references/domains/math-science.md` — 公式念法、推导、单位、演算类画面
- `scripts/build_audio.py` — 一次 TTS 同时产出音频、timeline、cues
- `scripts/build_subtitles.mjs` — 生成 `cues.js`、`subtitles.js`、SRT
- `scripts/calibrate.py` — 标定目标音色的实际语速和时长预算
- `scripts/voice_presets.py` — 语音预设（`xiaoxiao-calm` 等）与音色解析
- `scripts/watermark.py` — 不可见 DCT 水印的嵌入与提取
- `scripts/check_layout.mjs` — 沿时间轴检查文字越界、溢出、重叠和压字幕
- `scripts/render_range.mjs` — 按帧区间渲染
- `scripts/render.sh` — 并行分片渲染 + ffmpeg 合成
