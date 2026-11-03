# 管线契约

渲染管线只依赖三个产物。只要它们满足下面的格式，音频来自 Edge TTS、其它 TTS，还是用户自带录音，都可以。

## 1. 必需文件

```
script.json           # 课程元数据 + 分段旁白
audio/full.wav        # 48kHz / 单声道 / PCM s16le
timeline.json         # 每段在成片中的绝对起止
cues.json             # 每段的句级时间码（段内相对）
```

`scene.html` 还需要 `scene-data.js`（`window.TIMELINE`）、`cues.js`（`window.CUES`）、`subtitles.js`（`window.SUBTITLES`）。

## 2. `timeline.json`

```json
{
  "id": "compound-interest",
  "title": "复利",
  "lang": "zh-CN",
  "preset": "xiaoxiao-calm",
  "voice": "zh-CN-XiaoxiaoNeural",
  "rate": "-12%",
  "pitch": "-6Hz",
  "total": 483.2,
  "lead": 0.8,
  "gap": 0.35,
  "tail": 0.8,
  "segments": [
    {
      "id": "hook",
      "label": "开场",
      "text": "……",
      "audio": "audio/hook.wav",
      "start": 0.8,
      "duration": 42.4,
      "end": 43.2
    }
  ]
}
```

约束：

- `preset` 只记录选用的预设名；实际进入合成的是 `voice` / `rate` / `pitch`。
- `segments[].id` 唯一，且与 `script.json` 一致。
- `start/end` 单调递增，不重叠。
- `total` 必须等于 `ffprobe audio/full.wav` 的实际时长，不是估算值。
- 最后一段的 `end` 加 `tail` 应等于 `total`（最后一段后面不要再补 gap）。

## 3. `cues.json`

```json
{
  "hook": {
    "sentences": [
      { "text": "十万块，年化百分之七。", "start": 0.1, "end": 2.8 }
    ],
    "words": []
  }
}
```

约束：

- 时间段是**相对该段音频开头**的，不是成片绝对时间。
- 每段至少 1 句；为零时 `build_subtitles.mjs` 和渲染都会警告。
- 句边界来自同一次合成/对齐；`sentence.end` 允许比下一句 `start` 早 50ms 左右的重叠，超过 80ms 视为异常。
- `words` 可以为空；中文常常为空，不要依赖它做对齐。

## 4. 替换 TTS

保留 `script.json` 的分段文本和 `audio/full.wav` 的拼接方式即可。新 TTS 必须：

1. 对每段单独合成，并在**同一次合成**中拿到句级时间码；
2. 按 `lead / gap / tail` 拼接成 `audio/full.wav`；
3. 用实际音频时长写 `timeline.total`；
4. 产出与上面 schema 一致的 `timeline.json` 和 `cues.json`。

如果新 TTS 不返回句级时间码，就不要用它直接出片；先做强制对齐。

## 5. 用户自带录音

1. 让用户按 `script.json` 的分段提供 `audio/<segment>.wav`，或者直接提供一条完整录音。
2. 用强制对齐（forced alignment）把录音对齐到分段文本，得到每段的绝对起止和句级时间码。
3. 按契约写 `timeline.json` 和 `cues.json`；不要手工估时间。
4. 如果用户只有完整录音、没有分段，先在文本里切出段落边界，再对齐。

对齐工具不限；关键是**同一次对齐**同时产出段和句的时间码，之后所有画面、字幕都从这一份数据走。

## 6. 出片前校验

```bash
# 音频与时间轴一致
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 audio/full.wav

# 段起止单调、无重叠
node -e "
const t=require('./timeline.json');
for(let i=0;i<t.segments.length;i++){
  const s=t.segments[i];
  if(i && s.start < t.segments[i-1].end) console.log('overlap',s.id);
  if(s.end<=s.start) console.log('bad segment',s.id);
}
console.log('total',t.total,'last+tail',t.segments.at(-1).end+t.tail);
"

# 每段至少一句 cue
node -e "
const c=require('./cues.json'),t=require('./timeline.json');
for(const s of t.segments) console.log(s.id, c[s.id]?.sentences?.length||0);
"
```

出现任何一条不满足，先修数据，不要靠抽帧碰运气。
