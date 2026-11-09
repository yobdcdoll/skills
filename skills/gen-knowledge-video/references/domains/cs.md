# 计算机类知识点

这是 `gen-knowledge-video` 的一个领域包。槽位仍然用 `lesson-arc.md` 的七个必选，下面只补充计算机内容特有的写法。

## 1. 槽位映射

| 通用槽位 | 计算机类内容 |
| --- | --- |
| `hook` | 一个真实故障、性能对比或反直觉结果 |
| `define` | 一句话定义 + 核心数据结构/公式 |
| `how` | 主流程、数据流、关键分支；可拆成 `how1/how2` |
| `example` | 用一组真实数字跑完整个流程 |
| `boundary` | 冲突、扩容、空值、并发、极端输入 |
| `apply` | 复杂度、成本、选型标准 |
| `recap` | 五句话 + 手写流程 + 高频追问 |

可选模块：

- `compare`：和旧方案/相邻结构对比（数组 vs 链表、单利 vs 复利式优化）
- `extension`：并发、性能、版本差异
- `interview`：高频追问，先结论后一句为什么
- `misconception`：常见错误直觉

## 2. 旧 15 段到新槽位

| 旧段 | 新位置 |
| --- | --- |
| `hook` / `problem` | `hook` |
| `concept` | `define` |
| `structure` / `mechanism` / `mechanism2` | `how` |
| `example` | `example` |
| `edge` / `contract` | `boundary` |
| `use` | `apply` |
| `contrast` | `compare`（可选） |
| `thread` / `perf` | `extension`（可选） |
| `interview` | `interview`（可选） |
| `recap` | `recap` |

## 3. 代码怎么念

不要把源代码直接粘进旁白：

| 不要写 | 写成 |
| --- | --- |
| `if ((e.hash & oldCap) == 0)` | `如果 hash 和 oldCap 按位与的结果是 0` |
| `h ^ (h >>> 16)` | `hash 异或上它自己右移 16 位` |
| `O(log n)` | `O log n`，画面单独标注 |
| `putVal` | `put 的内部方法` |
| `null` | `空`，必要时画面写 `null` |

写完后让 TTS 念 2–3 句试听，确认 `put`、`hash`、`null` 没有被念得奇怪。

## 3.1 代码例子契约

代码知识点不能只讲定义和原理。`script.json` 设 `"kind": "code"`，并满足下面六条；缺一条就按“干讲”处理，不算交付。

1. **先有计划，再写旁白**：列清 1–3 个代码动作、完整上下文（import / 类 / 方法 / 调用现场）、输入、真实输出、一个变式或边界，以及每个代码块放在哪个 segment。写进 lesson 目录的 `code-plan.md`，或脚本旁边的备注。
2. **画面有代码本体**：至少一个 `<pre class="code">`，5–14 个非空行，包含调用现场；旁边或下方用 `<pre class="code-out">` 显示真实输出。数字表格、流程图、伪代码都不算“代码例子”。
3. **旁白逐句对代码**：顺序是“输入 → 这行做什么 → 输出/状态变成什么”；每句对应一次高亮行或状态变化，不要逐行念语法。
4. **能跑就跑**：能运行就展示真实输出；不能运行时明确说“示意代码”，但语义仍要完整。
5. **一屏最多 14 行**（建议 5–14 行）：超过就拆成“最小调用 + 变式”，不要缩字号，也不要外链。
6. **出片前过门禁**：`node <skill>/scripts/check_code_samples.mjs`；`kind: "code"` 时 `render.sh` 自动执行，不通过不出片。

代码计划最小示例：

| 动作 | 完整上下文 | 输入 | 真实输出 | 变式/边界 | segment |
| --- | --- | --- | --- | --- | --- |
| 13 次 `put` | import + 类 + main + `Map` 调用 | `user_1` 到 `user_13` | size 13，capacity 32 | `null` key | `example` |

模板：`references/code-scene-template.html`（代码卡 + 实时状态 + 真实输出 + 逐行高亮）。

## 4. 代码画面

- 代码卡、状态/输出必须同屏。推荐左侧代码、右侧 `size / capacity / threshold` 这类实时状态，输出单独用等宽字体块；不要只把结果写在旁白里。
- 只高亮当前行；每行用 `data-cue` 声明它从第几句旁白开始亮，已执行行降级。不要整块代码从头亮到尾。
- 代码字号 30–32px，一屏最多 14 行（建议 5–14 行）；超了就拆段。宁可拆成两个场景，不要缩到 28px 以下。
- 行号、关键字、注释不要同时用三种强调色；当前行背景比语法高亮更醒目。
- 代码和数据结构图同屏时，先代码后图，或先图后代码，不要来回跳；图只做辅助，不能替代代码本体。

## 5. 数据结构/流程画面

- 先容器，再元素，再连线，最后结论。
- 状态 A → 状态 B 的演示，一开始就把两个状态渲染出来，用 `.late { opacity: 0 }` 切换；不要在渲染过程中 `appendChild`。
- 涉及下标：先手算 `hash → index`、`容量 → 阈值`、第几个元素触发扩容。
- 文案说“第 17 个桶”，画面就必须真实存在第 17 个桶；不要只画 16 个。
- SVG 的 `<g>` 必须写 `transform="translate(x,y)"`，只写 `x/y` 会全部叠在原点。

## 6. 示例：HashMap

| 槽位 | 内容 |
| --- | --- |
| `hook` | 十万条用户数据，用数组按 id 查平均扫五万次；HashMap 把它变成一次。 |
| `define` | 用哈希函数把 key 映射到桶，平均 O(1) 查找。 |
| `how` | 算 hash → 定位桶 → 空位放入 / 冲突比较 / 链表或树化 → 超阈值扩容。 |
| `example` | 13 次 `put` 的完整调用：状态从 size 12 到 13，容量 16 翻到 32，输出 13。 |
| `boundary` | 哈希冲突、扩容时的 rehash、null key、并发修改。 |
| `apply` | 平均 O(1)，最坏 O(n)；适合频繁查找，不适合顺序遍历。 |
| `recap` | 定位、冲突、扩容、边界、成本。 |

`example` 段必须同时有代码、状态和输出。以 13 次 `put` 为例：

```java
import java.util.HashMap;
import java.util.Map;

public class PutDemo {
    public static void main(String[] args) {
        Map<String, Integer> map = new HashMap<>();
        for (int i = 1; i <= 13; i++) {
            map.put("user_" + i, i);
        }
        System.out.println(map.size()); // 13
    }
}
```

画面：左侧代码卡，右侧状态表（size / capacity / threshold），输出块显示 `13`。

| 句子 | 旁白 | 画面节拍 |
| --- | --- | --- |
| 0 | 先看调用现场：建一个 HashMap，键是字符串，值是整数。 | 高亮 import 和 `new HashMap<>()` |
| 1 | 循环放 13 个元素，每次 put 一个用户编号和序号。 | 高亮 for 和 put 行 |
| 2 | 前 12 次，size 从 0 涨到 12，容量 16，阈值 12。 | 状态表 size 0→12，capacity 16，threshold 12 |
| 3 | 第 13 次 put，size 变成 13，超过阈值。 | size 12→13，put 行保持高亮，阈值变橙 |
| 4 | 触发扩容：容量 16 变 32，阈值变 24，元素重新分配。 | capacity 16→32，threshold 12→24 |
| 5 | 最后打印 size，输出是 13。 | 输出块出现 `13` |

边界段再补 `null` key、哈希冲突、并发修改；这些是补充，不是用文字表格替代主代码例子。完整场景结构可直接改 `references/code-scene-template.html`。

## 7. 并发/性能模块

只在确实需要时加入：

- 用时间线表达线程交错，不要用旋转的锁图标。
- 环形链表、死锁、可见性问题，用状态快照对比，而不是实时动画。
- 复杂度标签单独放在角落，不要塞进旁白句子中间。

## 8. 常见坑

- hash 算出的 index 和画面高亮的桶对不上。
- 扩容例子只画了 16 个桶，文案却说桶 17。
- 把 `interview` 当成每讲必选，导致内容变成八股。
- 代码逐行念，观众跟不上。
- 代码只在旁白里描述，画面没有代码本体和真实输出；这种讲法观众不会写。
- 代码块超过 14 行还硬塞进一屏；应该拆成“最小调用 + 变式”。
- 复杂度只写大 O，不给具体数字感受。
