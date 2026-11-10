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

1. **先有计划，再写旁白**：`kind: "code"` 必须在 lesson 目录写 `code-plan.md`，包含五个小节——`## 声明与类型`（每个变量的声明、类型、初始化）、`## 入口`（main / 调用现场）、`## 线程与异步`（创建、启动、等待；没有写“无”）、`## 输出`（真实输出及产生它的行）、`## 变式与边界`。另列 1–3 个代码动作，以及每个代码块放在哪个 segment。门禁会检查文件和这五个标题。
2. **画面有语义完整的代码本体**：每个场景至少一个 5–14 个非空行的主块，包含调用现场，而且画面内自洽、能独立运行。允许 3–4 行的配套块（线程体、回调体、辅助方法），但配套块本身也必须是完整单元。每个出现的变量、类型、函数都要有声明或定义；入口（main / 调用现场）要可见；线程、异步任务、回调要能看到创建和启动，以及和主流程的关系，不能只截内部几行。不要用 `...`、`// 省略`、`/* ... */` 或注释跳过任何行，也不要让代码被裁切或滚出画面。旁边或下方用 `<pre class="code-out" data-for="<代码块 id>">` 显示输出。数字表格、流程图、伪代码都不算“代码例子”。
3. **旁白逐句对代码**：顺序是“输入 → 这行做什么 → 输出/状态变成什么”；每句对应一次高亮行或状态变化，不要逐行念语法。
4. **能跑就跑，输出与代码对得上**：展示的输出必须由同屏这段代码原样运行得到，变量名、数字、顺序、格式一一对应；优先设计成确定性输出（join、lock、排序），确实要讲不确定性时标“一次可能的运行”。改了代码就重跑并同步更新输出，不能手写、拼接或沿用旧结果。不能运行时是唯一例外：同时标“示意代码 / 预期输出”，并在计划里写明原因。
5. **放不下就拆场景**：保持一屏 5–14 行主块；装不下就拆成连续场景，每屏重复最小必要上下文，保证各自仍是完整单元；完整清单可以跨两页连续编号，但不要用省略号、不要缩字号、不要外链。
6. **出片前过门禁**：`node <skill>/scripts/check_code_samples.mjs`；`kind: "code"` 时 `render.sh` 自动执行。门禁检查 `code-plan.md` 与五个小节、主块行数、占位行、`data-segment`、`data-cue`、`data-for`；不通过不出片。

完整性反例（出现任意一条就算片段）：

| 反例 | 缺什么 |
| --- | --- |
| 只放循环里的 `map.put(...)` | `map` 的声明和类型、循环所在方法、入口 |
| 只放 `run()` 或线程体内部几行 | `new Thread(...)`、`start()`、`join()`、与 main 的关系 |
| 引用了 `executor`、`queue`、`lock` 却没在画面里声明 | 变量声明、初始化、生命周期 |
| 直接调用一个没定义过的辅助方法 | 方法签名和方法体，或至少说明它是外部库 |
| 异步回调只放回调体 | 注册/提交回调的位置、触发条件、与主流程的关系 |

代码计划最小示例：

| 动作 | 完整上下文 | 输入 | 真实输出 | 变式/边界 | segment |
| --- | --- | --- | --- | --- | --- |
| 13 次 `put` | import + 类 + main + `Map` 调用 | `user_1` 到 `user_13` | size 13，capacity 32 | `null` key | `example` |

`code-plan.md` 的最小结构（门禁按标题检查）：

```markdown
## 声明与类型
Map<String, Integer> map：String 键，Integer 值，new HashMap<>()。

## 入口
PutDemo.main，第 6 行。

## 线程与异步
无。

## 输出
13，由 main 里的 System.out.println(map.size()) 产生。

## 变式与边界
null key、哈希冲突。
```

完整性正例（声明、入口、创建、启动、等待、输出都在同一屏；演示完整性规则，不限于线程，也不涉及线程池）：

```java
import java.util.*;

public class ThreadDemo {
    public static void main(String[] args) throws Exception {
        int[] results = new int[3];
        Thread[] ts = new Thread[3];
        for (int i = 0; i < 3; i++) {
            int id = i;
            ts[i] = new Thread(() -> results[id] = (id + 1) * 10);
            ts[i].start();
        }
        for (Thread t : ts) t.join();
        System.out.println(Arrays.toString(results));
    }
}
```

输出：`[10, 20, 30]`。join 之后才打印，结果是确定的；换成线程池只是把“创建”换成“提交”，完整性要求不变。

模板：`references/code-scene-template.html`（代码卡 + 实时状态 + 真实输出 + 逐行高亮）。

## 4. 代码画面

- 代码卡、状态/输出必须同屏。推荐左侧代码、右侧 `size / capacity / threshold` 这类实时状态，输出单独用等宽字体块；不要只把结果写在旁白里。
- 代码用编辑器风格配色（One Dark 系）：关键字紫、类型黄、函数蓝、字符串绿、数字橙、注释灰斜体；一行保持纯文本，`pre.code[data-lang]` 会自动上色。
- 代码字号 30–32px，行高 1.45–1.6；长行自动换行，不横向裁切。30px/1.45 下 12 行是单屏安全上限，13–14 行要拆场或抽帧确认不压字幕。
- 只高亮当前行；每行用 `data-cue` 声明它从第几句旁白开始亮，已执行行降到 72% 不透明度。不要整块代码从头亮到尾。
- 当前行用浅色底 + 左侧色条，不要用整块高饱和蓝底；行号和语法色分开，不要额外加荧光色。
- 没有右侧状态栏时用宽版代码卡（`#code-card.wide`），减少长行折行。
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
