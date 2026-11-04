# 个人隐藏水印

给成片写入一个**肉眼不可见、但用脚本能读出来**的个人标记。用于证明“这版视频是我做的”，不是 DRM，也不阻止别人观看或转载。

实现见 `scripts/watermark.py`。它把 128 位标记写进每一帧亮度通道的中频 DCT 系数，用密钥决定块到位的分配和 ±1 扩频序列。每个 8×8 块都带一点信号，每帧重复整份标记；提取时把多帧的相关性叠加再判决，所以单帧被压坏不会丢标记。

## 1. 能扛什么、不能扛什么

实测（1920×1080、15fps、本技能的纸感文字画面，alpha=12）：

| 处理 | 结果 |
| --- | --- |
| 原片 / JPEG 90–95 往返 | 可读，置信度高 |
| H.264 重编码 CRF 20 → 30 | 可读，多数单帧直接通过 CRC |
| H.264 重编码 CRF 20 → 36 | 可读；建议提取时用 `--fps 4` 多采几帧 |
| H.264 重编码 CRF 38（极低码率） | 边界附近；可能失败 |
| 1080p → 720p 缩放后再提取 | **不可靠**（约 50–75% 位正确） |
| 裁剪、旋转、重拍屏幕、强降噪 | **不保证** |

结论：**同分辨率重新压缩**能保留；**改分辨率/裁剪**不要指望它。要覆盖这些场景，需要重新出片并重新嵌入，或另做音频水印/可见角标。

> 不要把它当成“防盗”。它只解决“这版是我出的”这类溯源问题。

## 2. 准备

依赖：

```bash
python3 -m pip install numpy pillow
```

在课程目录建 `watermark.json`（可从 `references/watermark.example.json` 复制）：

```json
{
  "mark": "yobdcdoll",
  "key": "换成一个只有你知道的密钥",
  "alpha": 12,
  "coef": "3,2"
}
```

- `mark`：最多 **12 个 UTF-8 字节**（约 4 个汉字，或 12 个 ASCII 字符）。身份较长时写短 ID，完整身份自己另存。
- `key`：提取时必须用同一个密钥。没有密钥只能得到随机位，CRC 不过。
- `alpha`：默认 12；实测 PSNR 约 44–48 dB，肉眼不可见。压得更狠可试 14–16，但不要超过 18。
- `coef`：默认 `3,2`，中频亮度系数；不理解就不要改。

**不要把 `watermark.json` 提交到仓库**（含密钥）。加到 `.gitignore`。

## 3. 出片时自动嵌入

`render.sh` 发现当前目录有 `watermark.json` 时，会在渲染完帧、编码前自动执行：

```bash
python3 <skill>/scripts/watermark.py embed-frames --frames frames --config watermark.json
```

然后才用 ffmpeg 编码。这样水印是在最终编码**之前**写进像素的，只多一次 JPEG 重存，没有额外视频代际损失。

```bash
bash <skill>/scripts/render.sh 15 4          # 有 watermark.json 就自动嵌入
WATERMARK=0 bash <skill>/scripts/render.sh 15 4   # 临时关闭
```

脚本会在 `frames/.watermark.json` 记录状态：

- 同一 mark/key 重跑：检测到已完成，直接跳过，不会二次嵌入。
- 中途失败：状态标为未完成，重跑会报错；删掉 `frames/` 重渲染即可。
- 已有不同 mark：报错；换标记必须重渲染，不能叠加。

## 4. 给已经出好的 MP4 补水印

```bash
python3 <skill>/scripts/watermark.py embed-video \
  --video lesson.mp4 --out lesson-wm.mp4 --config watermark.json
```

这会解码、逐帧嵌入、再以 CRF 18 重编码，质量损失很小，但会多一次编码。能用帧管线重出片时，优先用第 3 节。

## 5. 提取与验证

```bash
# 从成片提取（推荐：直接读 watermark.json，密钥不进 shell history）
python3 <skill>/scripts/watermark.py extract --video lesson.mp4 --config watermark.json

# 或显式给密钥
python3 <skill>/scripts/watermark.py extract --video lesson.mp4 --key "你的密钥"

# 从单帧/帧目录提取（调试用）
python3 <skill>/scripts/watermark.py extract --image frames/f00100.jpg --config watermark.json
python3 <skill>/scripts/watermark.py extract --frames frames --config watermark.json --max-frames 120
```

输出：

```json
{
  "found": true,
  "mark": "yobdcdoll",
  "crc_ok": true,
  "frames": 240,
  "frames_valid": 238,
  "confidence": 8.7,
  "source": "vote"
}
```

- `found` + `crc_ok`：标记存在且通过 CRC。
- `frames_valid / frames`：单帧独立通过 CRC 的比例，可粗略看作抗压程度。
- `confidence`：相关性平均幅度；正常嵌入通常 >3，重压后可能降到 1–2。
- 默认抽 2fps；压得很狠时加 `--fps 4` 或 `--fps 6` 增加投票帧数。
- 密钥错误时 `found:false`，退出码 1。

**验收标准**：至少对成片本身和一次 CRF 30 重编码副本都能提取出同一个 mark。

## 6. 和元数据一起用

DCT 水印是主证据；MP4 元数据只能当“给正常工具看”的辅助层，重新编码/上传后经常被清掉。需要时可在编码命令加：

```bash
-metadata "comment=© yobdcdoll · 2026"
```

不要把密钥或完整身份信息写进元数据。

## 7. 常见问题

- **提取不到**：密钥不对、`coef`/分辨率变了、视频被缩放或裁剪、压缩过狠。先用 `--image` 对原始帧验证，再换 `--fps 6` 多投票。
- **怀疑重复嵌入**：检查 `frames/.watermark.json`；重复嵌入会叠加 alpha，可能变可见。不要对同一批帧手动跑两次。
- **想换标记**：必须重新渲染帧再嵌入，不能在一个已带标记的成片上覆盖另一个标记。
- **觉得画面有纹理**：把 `alpha` 从 12 降到 8–10；代价是更不耐压。
- **标记太长**：用短 ID（如 `lex-01`），完整姓名/网址放在自己的私有登记表里。
