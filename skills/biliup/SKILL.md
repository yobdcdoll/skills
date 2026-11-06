---
name: biliup
description: 用 biliup CLI 完成 B 站登录、上传、追加上传、查询、评论、下载、合集管理和 WebUI/Fleet 服务。用户要求发布视频到 B 站、查看审核/转码状态、列出稿件、管理合集，或处理投稿频控时使用。
metadata:
  version: 1.1.0
---

# biliup：B 站投稿与稿件管理

用本机 `biliup` CLI 完成 B 站视频发布、状态查询、合集管理和频控处理。核心原则：**一次只发一支、相邻两支至少间隔 15 分钟、发布前明确视频、发布后记录 BV、失败先查状态再重试**。

## 适用场景

- 把本地视频上传到 B 站，设置标题、分区、标签、简介、封面。
- 查询稿件是否在审核、转码、已通过或被退回。
- 列出已投稿件，管理合集（season）。
- 处理 `投稿过于频繁`、`上传视频过快` 等频控。
- 把已发布链接回填到项目 README 的知识点表格。

## 安装

优先用包管理器；已有二进制时跳过。

```bash
# npm（需要 Node.js）
npm i -g @biliup/cli
biliup --version
```

GitHub Releases：

- macOS/Linux：下载 `biliupR-*-<arch>-<os>.tar.xz`，解压后把 `biliup` 放进 `PATH`。
- Windows：下载 `biliupR-v*-x86_64-windows.zip`，解压后把 `biliup.exe` 放进 `PATH`。
- 架构：`x86_64` / `aarch64`（Apple Silicon 用 aarch64）。
- 安装后 `biliup --help` 验证。

如果目录不在 `PATH`，用绝对路径或把目录加入 `PATH`。

## 本机环境

优先使用 `PATH` 中的 `biliup`。如果不在 `PATH`，按以下顺序查找：

```bash
BIN="${BILIUP_BIN:-$(command -v biliup || true)}"
[ -n "$BIN" ] || BIN="$HOME/Documents/tools/biliupR/biliup"
[ -x "$BIN" ] || { echo "biliup not found"; exit 1; }
"$BIN" --version
```

本机典型位置是 `$HOME/Documents/tools/biliupR/biliup`；`~/Documents/tools/env/env.sh` 会把该目录加入 `PATH`。

### Cookie 与登录

- CLI 默认读取当前目录的 `cookies.json`。
- WebUI 登录后的凭据通常在 biliup 工作目录的 `data/<mid>.json`。
- 用 `-u/--user-cookie` 显式指定，不要假设默认文件存在：

```bash
COOKIE="${BILIUP_COOKIE:-cookies.json}"
"$BIN" -u "$COOKIE" list --max-pages 1 >/dev/null
echo "cookie ok"
```

- 不要打印 cookie 内容，也不要把 `data/*.json` 提交到仓库。
- 登录是交互式扫码：`"$BIN" -u "$COOKIE" login`；续期用 `renew`。
- 如果 `list` 返回 0，说明 cookie 可用；如果提示登录失效，让用户扫码，不要反复试。

## 发布边界

公开上传会创建公开面，属于对外动作：

1. 用户必须**点名具体视频文件或标题**，不能只说“发一个”“随便发”。
2. 不能因为“之前同意过上传”就批量补发未点名的视频。
3. 一次只发一支；**相邻两支至少间隔 15 分钟**；每支成功后记录 BV，再发下一支。
4. 失败后先查该视频是否已经创建（`show` / manifest / `list`），确认没有重复再重试。
5. 默认公开；如果用户要“先 review”，优先用 `--is-only-self` 或先问清楚可见性，不要擅自公开。

### 投稿节奏

- **一次只发一支**，不要批量上传。
- **相邻两支至少间隔 15 分钟**；这是硬规则，不是建议。
- 间隔从上一支投稿成功的时间算起；定时发布不改变这个节奏。
- 连续上传会触发 `21566` / `601`；被限后等 15–20 分钟，不要用循环硬重试。
- 需要一次发多支时，排好顺序，每支成功后记录 BV，再等 15 分钟发下一支。

## 标准上传

```bash
BIN="${BILIUP_BIN:-biliup}"
COOKIE="${BILIUP_COOKIE:-cookies.json}"

"$BIN" -u "$COOKIE" upload \
  --tid 231 \
  --copyright 1 \
  --no-reprint 1 \
  --title "系列名：知识点" \
  --desc "两到四句话说明内容与场景，不放源码路径。" \
  --tag "Java,Java基础,Java并发,多线程,面试题" \
  --cover "/absolute/path/poster.jpg" \
  "/absolute/path/video.mp4"
```

### 参数速查

| 参数 | 用途 | 建议 |
| --- | --- | --- |
| `--tid` | 投稿分区 | 编程/计算机类用 `231`（科技 → 计算机技术）；不确定时查分区表 |
| `--copyright` | 1 自制，2 转载 | 原创课程用 `1` |
| `--no-reprint` | 1 禁止转载 | 原创课程用 `1` |
| `--title` | 标题 | 简洁、不夸张；`系列名：知识点` |
| `--desc` | 简介 | 2–4 句；不写源码路径、不写夸大宣传 |
| `--tag` | 标签 | ASCII 逗号分隔；6–10 个；包含领域必备标签 |
| `--cover` | 封面 | 16:9 JPG/PNG，建议 1920×1080，< 2 MB |
| `--dtime` | 定时发布 | 距提交 > 4 小时，10 位时间戳 |
| `--submit` | 提交接口 | `app`（默认）/ `web` / `b-cut-android` |
| `--is-only-self` | 仅自己可见 | 取值以当前版本 `--help` 为准；未验证前不要假设是布尔开关 |

### 元信息规范

- **标题**：短、具体、可搜索；不要“震惊”“彻底搞懂”“保姆级”等夸张词。
- **标签**：至少包含领域标签；技术课常用 `Java`、`Java基础`、`Java并发`，再加 3–6 个主题标签。
- **简介**：写清覆盖的场景和可运行示例，不写“源码在某某目录”，不写无法验证的承诺。
- **封面**：优先用视频配套的 `poster.jpg`；避免纯文字堆叠和夸张标题党。
- **分区**：计算机技术 `tid=231`；分区不确定时先查 biliup 的 tid 参考表，不要凭感觉填。

## 频控与失败处理

### `code 21566 投稿过于频繁`

- 这是**投稿接口**频控，不是文件损坏。
- 立即停止连续投稿；等 **10–20 分钟**再试。
- 可以尝试 `--submit web` 切换接口，但不要连续切换重试。
- 重试前先查是否已经创建稿件，避免重复。

### `code 601 您上传视频过快`

- 这是**上传接口**频控；biliup 内部会做若干次指数退避，仍失败就退出。
- 同样等 10–20 分钟，不要写循环硬重试。
- 等待期间不要重复上传同一个文件。

### TLS 证书告警

日志里出现：

```text
failed to verify TLS certificate: ... *.bilivideo.com certificate is expired
```

通常是某条上传线路的证书问题。biliup 会跳过该线路并继续测速/上传；只要最终返回 `code: 0` 并打印 `投稿成功`，就不是失败。

### 断点与重复

- 上传过程中 biliup 会保存 checkpoint；成功后自动删除。
- 如果进程中断，先看 checkpoint / 日志 / `show`，不要直接重传。
- 重传前先查 manifest 和 `biliup show <BV>`。

## 状态查询

```bash
"$BIN" -u "$COOKIE" show BV1xxxxxxxxx
"$BIN" -u "$COOKIE" list --is-pubing
"$BIN" -u "$COOKIE" list --pubed
"$BIN" -u "$COOKIE" list --not-pubed
```

`show` 输出 JSON，重点看：

- `state_desc`：`审核中`、`转码中` 等；以这个字段为准。
- `state`：常见 `-30` 审核中、`-60` 转码中；不同接口可能变化。
- `had_passed`：`false` 表示尚未过审。
- `is_only_self`：是否为仅自己可见。
- `title`、`desc`、`cover`、`copyright`：核对元信息是否写对。

链接格式：

```text
https://www.bilibili.com/video/<BV>/
```

注意：BV 创建成功不等于已公开；审核/转码期间链接可能存在但不可正常播放。

## 记录与回填

每支成功后追加一行 manifest（TSV）：

```bash
MANIFEST=/tmp/biliup-uploads.tsv
printf '%s\t%s\t%s\n' "$SLUG" "$BV" "$TITLE" >> "$MANIFEST"
```

示例：

```text
cas-atomics	BV1xxxxxxxxx	Java 并发：CAS 与原子类
aqs	BV1yyyyyyyyy	Java 并发：AQS 原理
```

回填 README 时：

- 优先加到知识点表格的“配套视频”列，不要单独开“视频课”小节。
- 用 `[短标题](https://www.bilibili.com/video/<BV>/)`。
- 一支视频覆盖两个知识点时，两行都可以链接同一支。
- 未发布或未过审的视频不要写成“已发布”；可以留空或标注状态。

## 合集管理

`season` 子命令读取 `-u/--user-cookie`，所有子命令都支持 `--json`：

```bash
"$BIN" -u "$COOKIE" season --json list
"$BIN" -u "$COOKIE" season --json sections <season_id>
"$BIN" -u "$COOKIE" season add <section_id> --vid <BV> [--vid <BV>...]
"$BIN" -u "$COOKIE" season remove <episode_id>
"$BIN" -u "$COOKIE" season sort <section_id> <episode_id>...
"$BIN" -u "$COOKIE" season sort <section_id> --reverse
```

- `list` 看合集与小节 ID（`season_id` / `section_id`）。
- `sections <season_id>` 看每集的 `episode_id`（不是 aid）；`remove` / `sort` 用的是这个 ID。
- `add <section_id> --vid <BV>` 自动查 cid 和标题，`--vid` 可重复。
- `sort` 把列出的 episode 按给定顺序移到最前，其余保持原顺序；`--reverse` 反转整个小节。
- 某个小节信息里没有合集 ID 时，`sort` 可加 `--season-id <season_id>`。

## 登录与服务

```bash
"$BIN" -u "$COOKIE" login       # 扫码登录，写入 cookie
"$BIN" -u "$COOKIE" renew       # 续期
"$BIN" server --auth            # WebUI，默认 127.0.0.1:19159
"$BIN" server --bind 0.0.0.0 --port 19159 --auth
"$BIN" server --config config.toml   # 1.0.7 风格配置，启动录制任务
```

- `--bind 0.0.0.0` 必须同时 `--auth`，否则拒绝启动。
- 后台运行：`nohup "$BIN" server --auth &`。
- WebUI 登录凭据与 CLI cookie 可能不是同一份，先确认 `-u` 指向哪个文件。
- `--secure-session-cookie` 只在 HTTPS 反向代理后开启；纯 HTTP 远程访问开启会导致登录态被浏览器丢弃。
- Fleet：`--controller` 显式作为控制面运行；`--relay-listen <addr|off>` 和 `--relay-url <url>` 控制内嵌/外部 relay。作为节点运行时这两个参数被忽略。
- `user` / `node` 子命令必须在 biliup 服务的工作目录执行（读写 `data/data.sqlite3` / `data/node.json`）。

## 其余子命令

### append：给已有稿件追加视频

```bash
"$BIN" -u "$COOKIE" append --vid <BV或av> \
  --title "..." --desc "..." --tag "..." --cover "..." \
  "/path/part2.mp4"
```

- 必填 `--vid`；其余元信息参数与 `upload` 相同。
- 适合分 P/续集；不要用它重复投稿新视频。

### comments：查看评论

```bash
"$BIN" -u "$COOKIE" comments <BV或av> [--sort 0|2] [--pn 1] [--ps 20]
```

- `--sort 0` 按时间，`2` 按热度。
- 只读，不会发评论。

### reply：回复评论

```bash
"$BIN" -u "$COOKIE" reply <BV或av> <rpid> "回复内容"
```

- 默认只打印将要回复的内容；确认后加 `--execute` 才真正发送。
- `rpid` 从 `comments` 输出里取。

### download：下载视频

```bash
"$BIN" download "<URL>" -o "./video/%(title)s.%(ext)s"
```

- 支持 `--split-size`、`--split-time`。
- 只下载用户有权访问的内容。

### dump-flv：查看 FLV 元数据

```bash
"$BIN" dump-flv "/path/file.flv"
```

### user：管理 WebUI 用户

```bash
"$BIN" user list
"$BIN" user reset-password <username>
```

- 必须在 biliup 服务的工作目录执行（读写 `data/data.sqlite3`）。
- `reset-password` 会让该用户所有会话失效；新密码从终端提示或 stdin 读取。

### node：Fleet 节点

```bash
"$BIN" node status
"$BIN" node join <bfleet-ticket> [--allow-hooks]
"$BIN" node leave
```

- 在 biliup 服务的工作目录执行（读写 `data/node.json`）。
- `join` 成功后重启 `biliup server` 生效。
- `--allow-hooks` 允许控制面下发的房间在本机执行钩子/ffmpeg 参数，等于允许执行命令，谨慎使用。

### help

```bash
"$BIN" --help
"$BIN" <command> --help
"$BIN" season add --help
```

遇到不认识的参数，先看 `--help`，不要猜。

## 常见坑

- `biliup: command not found`：`source ~/Documents/tools/env/env.sh`，或用 `BILIUP_BIN` 指到二进制。
- cookie 不对：`-u` 显式指定；不要用 `data/*.json` 猜。
- 标签没生效：用 ASCII 逗号，不要用中文逗号或空格分隔。
- 上传成功但没 BV：看 `ResponseData`；`code` 非 0 说明投稿未成功。
- 连续投稿被限：相邻两支至少间隔 15 分钟；被限后等 15–20 分钟，不要用循环绕过。
- 重复稿件：重试前查 manifest / `show` / `list`。
- 公开面：未点名的视频不要发；用户说“先 review”时优先仅自己可见。
- `reply` 默认是 dry-run：不加 `--execute` 不会真正发送。
- `append` 必须带 `--vid`，否则不知道往哪个稿件追加。
- `user` / `node` 要在 biliup 服务工作目录执行，否则读不到 `data/data.sqlite3` / `data/node.json`。
