---
name: github-ai-trending
description: 抓取 GitHub Trending 每日/每周榜单，过滤 AI/ML 项目并按本期新增星排序，输出 Markdown 或 JSON。用户要求生成 GitHub AI 趋势日报、查看今日/本周热门 AI 仓库时使用；只负责取数和过滤，不负责发送。
metadata:
  version: 1.0.0
---

# GitHub AI Trending

把 GitHub Trending 变成可直接消费的 AI 项目日报。脚本只做抓取、过滤、排序和渲染；发到哪个渠道、发给谁，由调用方决定。

## 何时使用

- 用户要“GitHub AI 日报”“今日/本周热门 AI 项目”。
- 需要把趋势数据交给 OpenClaw、Claude Code、Cursor 或其他 agent 再发送。
- 不要用它发送消息，也不要让它读取渠道凭据。

## 依赖

- Python 3
- `requests`：`python3 -m pip install requests`

## 工作流

在技能目录下运行：

```bash
# 纯抓取，不调用 LLM
python3 scripts/github_ai_trending_daily.py --no-llm

# 用 LLM 过滤 AI 项目（推荐）
LLM_API_KEY=... LLM_BASE_URL=https://api.example.com/v1 LLM_MODEL=... \
  python3 scripts/github_ai_trending_daily.py

# JSON 给程序消费，Markdown 给人看
python3 scripts/github_ai_trending_daily.py --format json --output /tmp/trending.json
```

常用参数：

| 参数 | 作用 |
| --- | --- |
| `--format markdown\|json` | 输出格式，默认 `markdown` |
| `--output PATH` | 写入文件；默认 stdout |
| `--top-daily N` / `--top-weekly N` | 条目数，默认 10 / 10 |
| `--no-llm` | 跳过 AI 过滤 |
| `--api-key` / `--base-url` / `--model` | 覆盖环境变量 |
| `--fail-on-llm-error` | LLM 过滤失败时以非零状态退出 |

环境变量：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`；也兼容 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`。三项不齐时自动跳过 AI 步骤，只输出抓取结果。

## 输出约定

- 报告正文写 stdout（或 `--output` 文件），进度和警告写 stderr。
- Markdown 包含今日 Top N、本周 Top N，以及累计星和本期新增星。
- JSON 包含 `generated_at`、`source`、`llm_filtered`、`fallback_to_all`、`daily`、`weekly`；每条带 `rank`、`name`、`url`、`stars`、`period`、`period_label`、`desc`。
- 排序优先按本期新增星（`X stars today` / `X stars this week`）；解析不到时回退累计星。

## 发送

脚本不发送任何消息。调用方读取 stdout 后，用 OpenClaw 的 channel、飞书、Slack 或其他方式发送。收件人、app secret、cookie 都不要写进脚本或技能文件。
