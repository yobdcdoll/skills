# 画面语法

按知识点类型选择画面原型。原则是：**一屏只讲一件事；用位置表达关系，用颜色表达状态，用数字表达结果。**

## 1. 原型选择表

| 原型 | 适用内容 | 主要节拍 | 避免 |
| --- | --- | --- | --- |
| `title` | 开场、章节 | 先给结果/冲突，再给问题 | 一上来放目录 |
| `definition` | 概念、术语 | 定义逐词出现，关键词最后高亮 | 整段定义一次铺满 |
| `steps` | 流程、算法、操作 | 容器 → 当前步骤 → 下一步 | 所有步骤同时亮 |
| `layers` | 结构、组成、层级 | 先外层，再内层，再连线 | 节点一次全出现 |
| `timeline` | 历史、过程、演化 | 按时间顺序逐个出现 | 时间轴一次画完 |
| `compare` | 易混概念、方案选择 | 左栏 → 右栏 → 差异高亮 | 两栏同时铺满 |
| `worked-example` | 数字、演算、推导 | 输入 → 中间量 → 结果 | 只给答案不给过程 |
| `formula` | 数学、物理、化学 | 公式整体 → 逐项高亮 → 代入 | 公式和解释同时出现 |
| `map` | 地理、空间、结构 | 底图 → 路径/区域 → 结论 | 用装饰地图代替信息 |
| `checklist` | 边界、误区、总结 | 逐条出现，最后收束 | 一次列 10 条 |
| `demo` | 操作技能、工具、实验 | 预录素材按节拍切段 | 实时录屏当正片 |
| `pronunciation` | 语言学习 | 音标/口型 → 示例词 → 对比 | 只放文字不放音频 |

一张场景可以组合多个原型，但同一屏只保留一个主原型。

## 2. 通用原则

- 当前步骤高亮，其余降级为灰色或低透明度。
- 元素出现顺序：容器 → 元素 → 连线/关系 → 结论。
- 动画 0.4–0.8s；不要弹跳、旋转、闪烁。
- 两个强调色足够；绿色/红色只用于对错结论。
- 数字必须具体，并且和旁白同一时刻切换。
- 代码只亮当前行；公式只亮当前项；表格只亮当前行/列。代码类必须让**代码本体和真实输出同屏**，不能只画流程图或数字表。
- 画面里承诺存在的元素必须真实存在（第 17 个桶、第 5 年、第三阶段）。
- 页眉只写课程系列名或知识点名，**不要写课程序号**（LESSON 01、第 1 讲、EP01）。序号会随重排、单独发布、拆条而过期。
- 英文缩写**首次出现时画面写完整形式**：`API（Application Programming Interface）`；后续只写 `API`。整讲只展开一次，旁白首次念全称。
- 代码知识点先给一个最小可运行例子，再讲抽象。画面里要有 5–14 行、含调用现场的代码块，以及非空的真实输出块；数字表格、流程图、伪代码都不能替代。例子还要有一个变式或边界。
- 视频是唯一 output：不要把必要代码或结论指到 GitHub、仓库、课程页或简介链接；内容必须在画面里。
- **字号按手机可读性定，不按“桌面看着舒服”定**：正文 ≥32px，表格 ≥30px，说明/标签 ≥18px，字幕 44px。空间不够时先删内容，不要先缩字。
- 一屏装不下时，优先拆成两屏或两行，不要靠 24px 以下的字硬塞。
- 文字容器默认加 `overflow-wrap:anywhere`；flex/grid 子项加 `min-width:0`；单行数字/公式用 `white-space:nowrap` 时必须确认容器够宽。
- 放大字号后必须用**最长真实文案**检查；短占位词看不出溢出。渲染前跑 `check_layout.mjs`。

## 3. 公式与符号

### 3.1 画面

- 用 KaTeX 或 MathML 渲染，不要用截图。
- 公式完整出现后，再按旁白逐项高亮；不要一次把所有项都标红。
- 代入数字时，把符号替换过程单独做一帧或一段，不要跳步。
- 单位和量纲单独标注，避免只写数字。

```html
<!-- 最小公式块：完整公式 + 当前项高亮 -->
<div id="formula" class="formula">
  A = P<span class="term" id="f-r">(1 + r)</span><sup>n</sup>
</div>
<style>
.formula{font:700 60px/1.40 "Times New Roman","STIX Two Math",serif;}
.formula .term{padding:0 6px;border-radius:6px;}
.formula .term.on{background:rgba(37,99,235,.14);color:var(--blue);}
</style>
<script>
function renderFormula(t) {
  const s = getSeg('how');
  if (!s) return;
  const c = i => cue('how', i);
  document.getElementById('f-r').classList.toggle('on', t - s.start >= c(1));
}
</script>
```

### 3.2 旁白

公式必须念成人话，同时画面保留符号：

| 符号 | 旁白 |
| --- | --- |
| `A = P(1+r)^n` | `A 等于 P 乘以 1 加 r 的 n 次方` |
| `a² + b² = c²` | `a 的平方加 b 的平方等于 c 的平方` |
| `Δx → 0` | `德尔塔 x 趋近于 0` |
| `H₂SO₄` | `硫酸`（画面标注化学式） |
| `∫ f(x) dx` | `f x 对 x 的积分` |

专有名词、单位、缩写第一次出现时念全称；画面保留缩写，并且**首次出现要写 `缩写（完整英文）`**，之后只写缩写。

## 4. 技能类与实拍素材

- 默认用图解、表格、公式和数字，不默认真人出镜。
- 操作技能可以使用手部特写、实物、实验过程；优先自绘或无名素材，避免可识别的真人肖像。
- 实拍素材只作为**素材**：先录好，再按时间码切段嵌入场景；不要让实拍素材决定正片时间轴。
- 需要“人”的抽象表达时，用剪影/图标，不要用真人照片。

## 5. 最小片段

下面的 `--white`、`--ink`、`--line`、`--blue`、`--orange`、`--muted`、`--mono` 都来自 `scene-template.html` 的 `:root`。

### 5.1 定义卡

```html
<div class="card" id="def-card">
  <div class="k">DEFINITION</div>
  <div class="t">复利</div>
  <div class="d">利息也参与生息，本金随时间指数增长。</div>
</div>
<style>
.card{width:1100px;padding:36px 42px;background:var(--white);border:2px solid var(--ink);
  border-radius:18px;box-shadow:10px 10px 0 rgba(31,41,51,.10);}
.card .k{font:600 18px/1.2 var(--mono);letter-spacing:.14em;color:var(--muted);}
.card .t{font-size:58px;font-weight:800;margin-top:12px;}
.card .d{font-size:34px;line-height:1.6;color:#39424E;margin-top:14px;overflow-wrap:anywhere;}
</style>
```

### 5.2 步骤条

```html
<div class="steps" id="steps">
  <div class="step" id="st0"><b>01</b><span>识别输入</span></div>
  <div class="step" id="st1"><b>02</b><span>判断状态</span></div>
  <div class="step" id="st2"><b>03</b><span>处理结果</span></div>
</div>
<style>
.steps{display:flex;gap:24px;}
.step{width:420px;min-height:180px;padding:24px 28px;background:var(--white);
  border:1.5px solid var(--line);border-radius:16px;opacity:0;}
.step b{display:block;font:600 18px/1 var(--mono);color:var(--muted);}
.step span{display:block;font-size:34px;font-weight:800;margin-top:16px;}
.step.on{border-color:var(--blue);box-shadow:8px 8px 0 rgba(37,99,235,.12);}
</style>
```

### 5.3 对照表

```html
<table class="compare" id="cmp">
  <thead><tr><th></th><th>单利</th><th>复利</th></tr></thead>
  <tbody>
    <tr id="cmp-1"><td>利息来源</td><td>只有本金</td><td>本金 + 已得利息</td></tr>
    <tr id="cmp-2"><td>增长形状</td><td>线性</td><td>指数</td></tr>
  </tbody>
</table>
<style>
.compare{width:1300px;border-collapse:collapse;background:var(--white);border:1.5px solid var(--line);}
.compare th,.compare td{padding:18px 24px;border-bottom:1px solid var(--line);
  font-size:30px;text-align:left;overflow-wrap:anywhere;}
.compare th{font:600 18px/1.2 var(--mono);letter-spacing:.12em;color:var(--muted);background:#F1ECE2;}
.compare tr.on td{background:rgba(37,99,235,.07);color:var(--blue);}
</style>
```

### 5.4 计数/结果行

```html
<div class="row" id="r10"><span>10 年</span><b>19.7 万</b></div>
<div class="row" id="r20"><span>20 年</span><b>38.7 万</b></div>
<div class="row" id="r30"><span>30 年</span><b>76.1 万</b></div>
<style>
.row{width:900px;display:flex;justify-content:space-between;align-items:baseline;
  padding:18px 8px;border-bottom:1px dashed var(--line);opacity:0;}
.row span{min-width:0;font-size:34px;color:var(--muted);overflow-wrap:anywhere;}
.row b{font:800 50px/1 var(--mono);color:var(--ink);white-space:nowrap;}
.row.hot b{color:var(--orange);}
</style>
```

### 5.5 时间线

```html
<div class="tl" id="tl">
  <div class="node" id="tl0"><i></i><span>1850</span></div>
  <div class="node" id="tl1"><i></i><span>1900</span></div>
  <div class="node" id="tl2"><i></i><span>1950</span></div>
</div>
<style>
.tl{position:relative;display:flex;justify-content:space-between;width:1400px;}
.tl::before{content:"";position:absolute;left:0;right:0;top:10px;height:2px;background:var(--line);}
.node{position:relative;width:180px;display:flex;flex-direction:column;align-items:center;gap:14px;opacity:0;}
.node i{width:20px;height:20px;border-radius:50%;background:var(--white);border:3px solid var(--blue);}
.node span{font:700 28px/1 var(--mono);}
</style>
```

### 5.6 代码块与输出

完整可用场景见 `code-scene-template.html`；最小结构：

```html
<div class="code-card">
  <div class="k">JAVA · PUT DEMO</div>
  <pre class="code" id="ex-code" data-segment="example"><span class="cl" data-cue="0">import java.util.HashMap;</span><span class="cl" data-cue="0">Map&lt;String, Integer&gt; map = new HashMap&lt;&gt;();</span><span class="cl" data-cue="1">for (int i = 1; i &lt;= 13; i++) {</span><span class="cl" data-cue="2">    map.put("user_" + i, i);</span><span class="cl" data-cue="3">}</span></pre>
</div>
<pre class="code-out" id="ex-out" data-for="ex-code">13</pre>
<style>
.code-card{width:1100px;padding:20px 22px;background:var(--ink);border-radius:16px;}
.code-card .k{font:600 18px/1.2 var(--mono);letter-spacing:.14em;color:#9CA3AF;}
pre.code{margin:10px 0 0;font:400 30px/1.28 var(--mono);color:var(--paper);white-space:pre;}
pre.code .cl{display:block;padding:0 10px;border-radius:6px;}
pre.code .cl.on{background:rgba(37,99,235,.55);}
.code-out{padding:22px 26px;background:var(--ink);color:#86EFAC;
  font:400 40px/1.3 var(--mono);border-radius:14px;}
</style>
```

- 一行一个 `.cl`；`data-cue` 是该行开始高亮的旁白句号，当前行高亮、已执行行降级。
- 5–14 个非空行；必须有 import/类/方法/调用现场中的必要上下文，不能只放一行表达式。
- 输出块必须真实、非空；可以来自运行结果、终端截图或测试输出。
- 代码类设 `script.json.kind = "code"`，否则 `check_code_samples.mjs` 不会拦截。

## 6. 常见错误

- 一屏塞两个结论，观众不知道看哪。
- 所有元素同时出现，旁白还没讲到就剧透。
- 用颜色表达流程、用位置表达状态，语义和直觉相反。
- 公式只放截图，无法逐项高亮，也不好改字号。
- 代码只口述、只放伪代码或数字表格，画面里没有代码本体和真实输出。
- 数字和旁白不同步；旁白说“30 年”，画面还停在 20 年。
- 实拍素材露脸、有品牌或隐私信息。
- 动画超过 1 秒，或使用弹跳/闪烁吸引注意。
