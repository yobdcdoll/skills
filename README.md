# Clawhome

一组可复用的 agent skills，同时以 marketplace 形式提供给 Claude Code、Cursor 和 Codex。

## 包含的 skills

| Skill | 用途 |
| --- | --- |
| `exam-clean` | 把试卷/作业照片还原成干净、可打印的空白卷 PDF |
| `update-github-hosts` | 在 macOS 上发现、验证并安全更新 `/etc/hosts` 中的 GitHub IP |
| `gen-knowledge-video` | 把任意知识点/技能点做成旁白、画面、字幕逐句对齐的教学视频；可选不可见个人水印 |
| `github-ai-trending` | 抓取 GitHub Trending，过滤 AI 项目并按本期新增星排序，输出 Markdown/JSON（只取数，不发送） |
| `hackernews-daily` | 抓取 Hacker News 今日/本周热门，可选中文解读，输出 Markdown/JSON（只取数，不发送） |
| `biliup` | 用 biliup CLI 登录、上传、查询和管理 B 站稿件；支持频控处理与 README 链接回填（需本机 biliup 与 B 站登录） |
| `release-plugin` | 提交、推送并更新已安装插件，让最新 skill 立即生效 |

## Claude Code

```bash
claude plugin marketplace add yobdcdoll/skills

# 一次装齐七个技能（插件名前缀 yobdcdoll-skills:）
claude plugin install yobdcdoll-skills@skills

# 或按需单独安装
claude plugin install exam-clean@skills
claude plugin install update-github-hosts@skills
claude plugin install gen-knowledge-video@skills
claude plugin install github-ai-trending@skills
claude plugin install hackernews-daily@skills
claude plugin install biliup@skills
claude plugin install release-plugin@skills
```

## Codex

```bash
codex plugin marketplace add yobdcdoll/skills

# 一次装齐七个技能
codex plugin add yobdcdoll-skills@skills

# 或按需单独安装
codex plugin add exam-clean@skills
codex plugin add update-github-hosts@skills
codex plugin add gen-knowledge-video@skills
codex plugin add github-ai-trending@skills
codex plugin add hackernews-daily@skills
codex plugin add biliup@skills
codex plugin add release-plugin@skills
```

## Cursor

Cursor 从仓库根目录的 `.cursor-plugin/marketplace.json` 读取插件目录。

1. 打开 Cursor Dashboard 的 **Plugins & MCPs**。
2. 在 **Team Marketplaces** 中选择 **Add Marketplace**。
3. 使用 **Import from Repo**，填入 `https://github.com/yobdcdoll/skills`。
4. 在 **Customize** 中安装 `yobdcdoll-skills`（一次装齐），或按需安装 `exam-clean`、`update-github-hosts`、`gen-knowledge-video`、`github-ai-trending`、`hackernews-daily`、`biliup`、`release-plugin`。

Team marketplace 需要 Cursor Teams 或 Enterprise 套餐。公开分发可把同一仓库提交到
[Cursor Marketplace](https://cursor.com/marketplace/publish)。

## 日报脚本

`github-ai-trending` 和 `hackernews-daily` 两个技能里的脚本只负责抓取和整理数据，输出 Markdown 或 JSON，**不包含发送逻辑**；发到哪个渠道、发给谁，由 OpenClaw 或其他调用方决定。

```bash
# GitHub AI Trending
python3 skills/github-ai-trending/scripts/github_ai_trending_daily.py --format markdown

# Hacker News
python3 skills/hackernews-daily/scripts/hackernews_daily.py --format json --output /tmp/hn.json
```

需要 AI 过滤/中文解读时，通过环境变量提供任意 OpenAI 兼容接口：

```bash
LLM_API_KEY=... LLM_BASE_URL=https://api.example.com/v1 LLM_MODEL=... \
  python3 skills/github-ai-trending/scripts/github_ai_trending_daily.py
```

未配置 LLM 时会跳过 AI 步骤，只输出抓取结果。进度和警告写到 stderr，报告正文写到 stdout（或 `--output` 指定的文件）。

## Marketplace manifests

- Claude Code / Codex：`.claude-plugin/marketplace.json`
- Cursor：`.cursor-plugin/marketplace.json`
- 根目录的 `.claude-plugin/plugin.json` / `.cursor-plugin/plugin.json` 是打包插件 `yobdcdoll-skills`；每个 skill 目录还包含各自的 manifest，用于单独安装。

更新已安装的插件时，需要提升对应插件清单中的 `version`。
