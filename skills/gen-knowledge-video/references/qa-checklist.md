# 出片前 QA 清单

按顺序做。任何一项没有亲自确认，就不要说“已完成”。

## 1. 文件与元数据

```bash
ls -lh <id>.mp4 audio/full.wav <id>.srt
ffprobe -v error \
  -show_entries format=duration,size:stream=codec_name,width,height,r_frame_rate \
  -of default=nw=1 <id>.mp4
ffprobe -v error -show_entries format=duration \
  -of default=noprint_wrappers=1:nokey=1 audio/full.wav
```

- [ ] 视频时长与 `audio/full.wav` 相差 ≤ 0.1s。
- [ ] 1920×1080，帧率符合预期。
- [ ] 视频编码 H.264，音频 AAC。
- [ ] 文件大小合理（16 分钟 15fps 约 30–50MB）。
- [ ] `<id>.srt` 非空，首条不早于 `lead`，末条不超过视频时长。
- [ ] `cues.js`、`subtitles.js`、`scene-data.js` 均存在且非空。

### 1.1 隐藏水印（如果启用了 watermark.json）

```bash
python3 <skill>/scripts/watermark.py extract --video <id>.mp4 --config watermark.json
ffmpeg -y -v error -i <id>.mp4 -c:v libx264 -crf 30 -pix_fmt yuv420p /tmp/<id>-re30.mp4
python3 <skill>/scripts/watermark.py extract --video /tmp/<id>-re30.mp4 --config watermark.json
```

- [ ] 成片能提取出正确 mark，`crc_ok: true`。
- [ ] CRF 30 重编码副本仍能提取出同一个 mark。
- [ ] `watermark.json` 没有提交进仓库（含密钥）。
- [ ] `frames/.watermark.json` 显示 `complete: true`，没有重复嵌入。

### 1.2 读音与术语

- [ ] 多音字按词义读对：`行`（第几行、行号、行数）读 háng，`重`（重新、重复、重启、重试）读 chóng，`调用` 读 diào，`处理` 读 chǔ。
- [ ] `script.json` 里所有易错词都用 `〖显示|朗读〗` 标了读音，且**每个出现都标了**，不是只标第一次。
- [ ] `JSON` 念「杰森」而不是 J-S-O-N；`GIF`、`SQL`、`Nginx` 等术语全讲只有一种读法。
- [ ] 含读音标注的段落已完整试听；字幕和画面仍显示原词（`JSON`、`行`、`重新`），没有露出 `杰森`、`航`、`虫新` 这类朗读形。
- [ ] 含读音标注的段落，`cues.json` 的句数等于显示文本句数；标注没有把句号、问号、感叹号或换行包进去。

## 2. 帧完整性

```bash
find frames -name 'f*.jpg' | wc -l
```

- [ ] 帧数等于 `ceil(duration * fps)`。
- [ ] 编号从 `f00000.jpg` 连续到最后一帧，没有缺号。
- [ ] 随机打开 3 张帧，确认不是纯黑/纯白/加载中。

## 3. 抽帧看对齐

每个段落至少抽 **开头 + 中段**；涉及数字变化、高亮切换、场景切换的地方额外抽。

```bash
ffmpeg -v error -y -ss <time> -i <id>.mp4 -frames:v 1 check/t<time>.jpg
```

对每张帧确认：

- [ ] 字幕文字 = 该时刻旁白（不是上一句/下一句）。
- [ ] 高亮元素 = 旁白正在讲的那个。
- [ ] 数字 = 旁白刚说出的数字。
- [ ] 场景 = 该段落，没有提前/延后。
- [ ] 没有文字重叠、裁切、溢出画布。
- [ ] 用**最长真实文案**跑过 `node <skill>/scripts/check_layout.mjs`，无越界、横向溢出、元素重叠或压字幕。
- [ ] 每个场景至少抽一张“文字最多”的帧，确认没有裁字、叠字、文字被卡片边界切断。
- [ ] 底部字幕没有压住正文/代码/图示/公式。
- [ ] 页眉没有课程序号（LESSON 01、第 1 讲、EP01、01）；只写系列名或知识点名。
- [ ] 英文缩写首次出现同时有缩写和完整英文（如 `API（Application Programming Interface）`）；后续只写缩写，没有重复展开。
- [ ] `script.json.kind` 与内容一致；代码类必须是 `code`。
- [ ] 代码类已跑 `node <skill>/scripts/check_code_samples.mjs` 且通过。
- [ ] `code-plan.md` 存在，含 `## 声明与类型`、`## 入口`、`## 线程与异步`、`## 输出`、`## 变式与边界` 五个小节。
- [ ] 代码类至少一张抽帧同时包含：一个 5–14 行主块（含调用现场）+ 非空的真实输出或运行截图；抽帧时间点：___。
- [ ] 配套块（如有）为 3–4 行且是完整单元，不是片段。
- [ ] 代码不是只在旁白里被描述；数字表格、流程图、伪代码不能替代代码本体。
- [ ] 代码块完整可见：没有 `...`、`// 省略`、`/* ... */` 等占位行，也没有被裁切或滚出画面。
- [ ] 代码语义完整：每个出现的变量、类型、函数都有声明或定义，入口（main / 调用现场）可见；线程、异步、回调能看到创建和启动，以及和主流程的关系，不能只截内部片段。
- [ ] 输出块（`<pre class="code-out" data-for="...">`）与同屏代码严格对应：变量名、数字、顺序、格式都能由这段代码原样跑出；改过代码后输出已重跑更新。
- [ ] 输出优先确定性；顺序或时序不稳定的输出已标“一次可能的运行”，没有伪装成稳定结果。
- [ ] 整屏一致：输出块、状态表、计数器、图示标注的数字，都等于同屏代码在该 cue 时刻的真实状态。
- [ ] 代码当前行高亮与旁白同步；至少检查 2 个高亮切换点。
- [ ] 视频自包含：没有“源码在 GitHub / 仓库 / 课程页 / 简介 / 评论区”之类指路；必要代码和结论都在画面里。
- [ ] 旁白、字幕和画面都没有“这是一个真实例子 / 真实案例 / 实际场景”这类自我强调；例子直接用数字、代码和输出说话。只有示意/假设数据才明确披露。
- [ ] 字幕字号 ≥40px（默认 44px），正文 ≥32px，小标签 ≥18px。
- [ ] 把浏览器缩放到约 25% 宽（模拟手机竖屏）时，字幕仍能读出；横屏全屏时正文不费力。
- [ ] 中文没有变方块，字体已加载。
- [ ] 箭头、连线、树的节点位置正确（没有全叠在原点）。

重点抽：

- `hook` 的第一句和最后一个 chip；
- `example` 的每个数字变化点；
- 代码类的高亮行切换点，以及输出块首次出现的时刻；
- 新旧状态/数值对比的高亮切换；
- `interview` 的第一张和最后一张卡；
- `recap` 的第一帧和最后一帧。

## 4. 字幕数据

```bash
node -e "
const fs=require('fs');
const s=fs.readFileSync('subtitles.js','utf8');
const subs=JSON.parse(s.replace('window.SUBTITLES=','').replace(/;\$/,''));
let bad=0;
for(let i=1;i<subs.length;i++){
  if(subs[i].start < subs[i-1].end - 0.001){ console.log('overlap',i); bad++; }
  if(subs[i].end <= subs[i].start){ console.log('bad duration',i); bad++; }
}
const long=subs.filter(x=>x.text.length>42);
console.log({count:subs.length,bad,long:long.length,max:Math.max(...subs.map(x=>x.text.length))});
"
```

- [ ] 无负时长、无大面积重叠。
- [ ] 最长字幕条能在 1600px 内放下（允许两行）；超长已拆句。阈值按 `subtitle.max_cjk` / `subtitle.max_latin` 调整。
- [ ] 专有名词、数字、代码标识符、公式人工核对过。
- [ ] 字幕语言与课程语言一致，字体能正常显示该语言。
- [ ] `subtitles.js` 与 SRT 条数一致。

## 5. 场景数据与 cue

```bash
node -e "
const fs=require('fs');
const cues=JSON.parse(fs.readFileSync('cues.json','utf8'));
const tl=JSON.parse(fs.readFileSync('timeline.json','utf8'));
for(const s of tl.segments){
  const n=cues[s.id]?.sentences?.length || 0;
  console.log(s.id, 'sentences', n);
}
"
```

- [ ] 每个段落至少 1 句 cue。
- [ ] 场景渲染器里用到的最大索引 < 该段句数。
- [ ] 没有 `missing cue` 警告（`render_range.mjs` 会因此非零退出）。
- [ ] `timeline.segments` 的 `start/end` 单调递增，无重叠。
- [ ] 总时长 = 最后一段 `end` + tail，且等于 `ffprobe audio/full.wav`。

## 6. 播放页

在浏览器中打开 `index.html`：

```js
const v = document.querySelector('video');
({ duration: v.duration, readyState: v.readyState, error: v.error, networkState: v.networkState })
```

- [ ] `duration > 0`。
- [ ] `readyState >= 3`。
- [ ] `error === null`。
- [ ] 播放按钮可用，拖动进度条能跳转。
- [ ] 播放页的时长/分段表与实际成片一致。
- [ ] 重新出片后 `src` 带了新版本参数，未命中缓存。

## 7. 最终人工观看

- [ ] 从头到尾至少看一遍，速度 1.0。
- [ ] 在手机上（或缩到 25% 宽）看一遍，确认字幕和正文不用眯眼。
- [ ] 重点看段落切换处：有没有一帧空白、两层画面叠加、字幕突然消失。
- [ ] 听一遍音频：有没有吞字、重复、突然变调、段间静音过长。
- [ ] 结尾没有截断。

## 8. 交付说明

- [ ] 成片路径、时长、分辨率、帧率、体积。
- [ ] 内嵌字幕 + SRT 路径。
- [ ] 音色 / rate / pitch / speed。
- [ ] 隐藏水印的 mark、验证方式、抗压测试结果。
- [ ] 抽帧检查了哪些时间点，分别确认了什么。
- [ ] 明确列出仍存疑的数字/发音/画面。
- [ ] 未经确认不批量生产后续知识点。
