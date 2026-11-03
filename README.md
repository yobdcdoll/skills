# Clawhome

一组可复用的 agent skills，同时以 marketplace 形式提供给 Claude Code、Cursor 和 Codex。

## 包含的 skills

| Skill | 用途 |
| --- | --- |
| `exam-clean` | 把试卷/作业照片还原成干净、可打印的空白卷 PDF |
| `update-github-hosts` | 在 macOS 上发现、验证并安全更新 `/etc/hosts` 中的 GitHub IP |
| `gen-knowledge-video` | 把任意知识点/技能点做成旁白、画面、字幕逐句对齐的教学视频 |

## Claude Code

```bash
claude plugin marketplace add yobdcdoll/clawhome
claude plugin install exam-clean@clawhome
claude plugin install update-github-hosts@clawhome
claude plugin install gen-knowledge-video@clawhome
```

## Codex

```bash
codex plugin marketplace add yobdcdoll/clawhome
codex plugin add exam-clean@clawhome
codex plugin add update-github-hosts@clawhome
codex plugin add gen-knowledge-video@clawhome
```

## Cursor

Cursor 从仓库根目录的 `.cursor-plugin/marketplace.json` 读取插件目录。

1. 打开 Cursor Dashboard 的 **Plugins & MCPs**。
2. 在 **Team Marketplaces** 中选择 **Add Marketplace**。
3. 使用 **Import from Repo**，填入 `https://github.com/yobdcdoll/clawhome`。
4. 在 **Customize** 中安装 `exam-clean`、`update-github-hosts` 或 `gen-knowledge-video`。

Team marketplace 需要 Cursor Teams 或 Enterprise 套餐。公开分发可把同一仓库提交到
[Cursor Marketplace](https://cursor.com/marketplace/publish)。

## Marketplace manifests

- Claude Code / Codex：`.claude-plugin/marketplace.json`
- Cursor：`.cursor-plugin/marketplace.json`
- 每个 skill 目录还包含 `.claude-plugin/plugin.json` 和 `.cursor-plugin/plugin.json`

更新已安装的插件时，需要提升对应插件清单中的 `version`。
