---
name: hackernews-daily
description: 抓取 Hacker News 今日与本周热门条目，可选生成中文解读，输出 Markdown 或 JSON。用户要求生成 HN 早报、汇总今日/本周科技新闻时使用；只负责取数和整理，不负责发送。
metadata:
  version: 1.0.0
---

# Hacker News Daily

把 Hacker News 热门榜单整理成可直接消费的早报。脚本只做抓取、可选中文解读和渲染；发到哪个渠道、发给谁，由调用方决定。

## 何时使用

- 用户要“Hacker News 早报”“HN 今日/本周热门”。
- 需要把新闻列表或中文解读交给 OpenClaw、Claude Code、Cursor 或其他 agent 再发送。
- 不要用它发送消息，也不要让它读取渠道凭据。

## 依赖

- Python 3
- `requests`：`python3 -m pip install requests`

## 工作流

在技能目录下运行：

```bash
# 纯抓取，不调用 LLM
python3 scripts/hackernews_daily.py --no-llm

# 生成中文解读（推荐）
LLM_API_KEY=... LLM_BASE_URL=https://api.example.com/v1 LLM_MODEL=... \
  python3 scripts/hackernews_daily.py

# 控制条目数并输出 JSON
python3 scripts/hackernews_daily.py --format json \
  --today-limit 10 --weekly-limit 15 --output /tmp/hn.json
```

常用参数：

| 参数 | 作用 |
| --- | --- |
| `--format markdown\|json` | 输出格式，默认 `markdown` |
| `--output PATH` | 写入文件；默认 stdout |
| `--today-limit N` / `--weekly-limit N` | 输出条目数，默认 10 / 15 |
| `--fetch-today N` / `--fetch-weekly N` | 抓取条数，默认 20 / 50 |
| `--no-llm` | 跳过中文解读 |
| `--api-key` / `--base-url` / `--model` | 覆盖环境变量 |
| `--fail-on-llm-error` | 解读失败时以非零状态退出 |

环境变量：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`；也兼容 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`。三项不齐时自动跳过中文解读，只输出标题和链接。

## 输出约定

- 报告正文写 stdout（或 `--output` 文件），进度和警告写 stderr。
- 今日榜按北京时间当天过滤，本周榜取最近 7 天。
- JSON 包含 `generated_at`、`source`、`summary_attempted`、`summary_generated`、`today`、`weekly`；每条带 `title`、`url`、`points`、`author`、`created_at`、`object_id`、`desc`。
- LLM 解读失败或被截断时，保留已有解读并继续输出，不阻断报告。

## 发送

脚本不发送任何消息。调用方读取 stdout 后，用 OpenClaw 的 channel、飞书、Slack 或其他方式发送。收件人、app secret、cookie 都不要写进脚本或技能文件。
