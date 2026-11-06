# Clawhome

一组可复用的 agent skills，同时以 marketplace 形式提供给 Claude Code、Cursor 和 Codex。

## 包含的 skills

| Skill | 用途 |
| --- | --- |
| `exam-clean` | 把试卷/作业照片还原成干净、可打印的空白卷 PDF |
| `update-github-hosts` | 在 macOS 上发现、验证并安全更新 `/etc/hosts` 中的 GitHub IP |
| `gen-knowledge-video` | 把任意知识点/技能点做成旁白、画面、字幕逐句对齐的教学视频；可选不可见个人水印 |
| `biliup` | 用 biliup CLI 登录、上传、查询和管理 B 站稿件；支持频控处理与 README 链接回填（需本机 biliup 与 B 站登录） |

## Claude Code

```bash
claude plugin marketplace add yobdcdoll/skills

# 一次装齐四个技能（插件名前缀 yobdcdoll-skills:）
claude plugin install yobdcdoll-skills@skills

# 或按需单独安装
claude plugin install exam-clean@skills
claude plugin install update-github-hosts@skills
claude plugin install gen-knowledge-video@skills
claude plugin install biliup@skills
```

## Codex

```bash
codex plugin marketplace add yobdcdoll/skills

# 一次装齐四个技能
codex plugin add yobdcdoll-skills@skills

# 或按需单独安装
codex plugin add exam-clean@skills
codex plugin add update-github-hosts@skills
codex plugin add gen-knowledge-video@skills
codex plugin add biliup@skills
```

## Cursor

Cursor 从仓库根目录的 `.cursor-plugin/marketplace.json` 读取插件目录。

1. 打开 Cursor Dashboard 的 **Plugins & MCPs**。
2. 在 **Team Marketplaces** 中选择 **Add Marketplace**。
3. 使用 **Import from Repo**，填入 `https://github.com/yobdcdoll/skills`。
4. 在 **Customize** 中安装 `yobdcdoll-skills`（一次装齐），或按需安装 `exam-clean`、`update-github-hosts`、`gen-knowledge-video`、`biliup`。

Team marketplace 需要 Cursor Teams 或 Enterprise 套餐。公开分发可把同一仓库提交到
[Cursor Marketplace](https://cursor.com/marketplace/publish)。

## Marketplace manifests

- Claude Code / Codex：`.claude-plugin/marketplace.json`
- Cursor：`.cursor-plugin/marketplace.json`
- 根目录的 `.claude-plugin/plugin.json` / `.cursor-plugin/plugin.json` 是打包插件 `yobdcdoll-skills`；每个 skill 目录还包含各自的 manifest，用于单独安装。

更新已安装的插件时，需要提升对应插件清单中的 `version`。
