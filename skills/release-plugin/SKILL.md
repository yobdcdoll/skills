---
name: release-plugin
description: 把当前仓库的 skill 改动提交、推送，并更新 Claude Code（或当前 agent）已安装的插件，让最新内容立即可用。用户说“提交并推送”“更新插件”“让 Claude Code 用上最新 skill”“commit, push, update plugin”时使用；只提交代码或只发布普通软件包时不要用本技能。
metadata:
  version: 1.0.0
---

# 发布 skill 改动并更新插件

把仓库里的 skill 改动提交、推送，并让当前 agent（默认 Claude Code）加载最新插件。

## 1. 何时使用

- 用户要求“提交、推送，并更新插件/让 Claude Code 用上最新 skill”。
- 改动落在本仓库的 `skills/<name>/` 下，且需要当前 agent 立即生效。
- 用户只要求 commit / push，不要求更新插件：只做第 4、5 步，跳过第 6 步。

不适用：普通应用代码发布、只改 README、只发 npm/PyPI 包。

## 2. 发布前检查

```bash
git status --short
git branch --show-current
git remote -v
```

- 确认改动都属于本次发布；不要顺手带上无关文件。
- 运行被改技能的测试或校验；没有测试时至少 `node --check` 所有改动的脚本，并解析所有 JSON。
- 确认没有密钥、水印配置、大文件被加入。
- 默认直推 `main`（本仓库习惯）。用户要求分支时，先建分支再提交。

## 3. 版本规则

默认只 bump patch（`1.3.7 → 1.3.8`、`2.2.4 → 2.2.5`），除非用户明确要求 minor / major。

一次发布要同时 bump 两层版本：

| 层 | 位置 |
| --- | --- |
| skill 版本 | `skills/<name>/SKILL.md` frontmatter、该 skill 的 `.claude-plugin/plugin.json`、`.cursor-plugin/plugin.json` |
| 插件包版本 | 根 `.claude-plugin/plugin.json`、根 `.cursor-plugin/plugin.json`、根 `.cursor-plugin/marketplace.json` 的 `metadata.version` 与 `yobdcdoll-skills` 条目 |

用脚本一次同步，避免漏改：

```bash
node <skill>/scripts/bump_versions.mjs --skill <name>
```

只想指定版本时：

```bash
node <skill>/scripts/bump_versions.mjs --skill <name> --skill-version 1.4.0 --bundle-version 2.3.0
```

> 只改 skill 版本不够。`claude plugin update` 比较的是**插件包版本**；包版本没变，它会说 “already at the latest version”，新 skill 不会进入安装缓存。

## 4. 提交

```bash
git add <本次改动的文件>
git commit -m "$(cat <<'EOF'
feat(<skill>): <一句话说明>

- <要点>
- <要点>

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

约定：

- 使用 conventional commit：`feat` / `fix` / `docs` / `chore`。
- 一个提交只做一件事；版本 bump 跟着功能提交走，不单独提交。
- 不 amend 已推送的提交，不 force push。

## 5. 推送

```bash
git push origin "$(git branch --show-current)"
```

推送后再刷新 marketplace；未推送的提交不会进入插件的 marketplace clone。

## 6. 更新当前 agent 的插件（Claude Code）

先刷新 marketplace，再更新插件：

```bash
claude plugin marketplace update <marketplace>
claude plugin update <plugin>@<marketplace>
```

本仓库默认值：

```bash
claude plugin marketplace update skills
claude plugin update yobdcdoll-skills@skills
```

- `marketplace update` 可能要 1–2 分钟；超时就放后台，**不要并行开第二个**。
- 看到 “already at the latest version”：回到第 3 步，确认插件包版本真的 bump 了、推送成功、marketplace clone 已包含新提交。
- 更新完成会提示 **restart required**；告诉用户需要重启 agent 才能加载。

## 7. 验证

```bash
node <skill>/scripts/verify_install.mjs \
  --plugin yobdcdoll-skills@skills \
  --skill <name>
```

检查：

- `~/.claude/plugins/installed_plugins.json` 里的版本 = 根插件包版本；
- `gitCommitSha` = 当前 `HEAD`；
- 安装目录里 `skills/<name>/SKILL.md` 的版本 = 仓库版本；
- 新改动确实出现在安装缓存里（例如 grep 新增的小节或关键词）。

任一项不匹配，先修发布流程，不要只说“已完成”。

## 8. 失败处理

| 现象 | 处理 |
| --- | --- |
| `plugin update` 说已是最新 | 插件包版本没 bump，或 push 没成功，或 marketplace 没刷新 |
| marketplace clone 里没有新提交 | 检查 `git push`、远端分支、`claude plugin marketplace update` 输出 |
| 安装缓存有旧版本 | 用 `claude plugin update` 重装；必要时 `claude plugin uninstall` 后再 install |
| 验证脚本报版本不一致 | 先确认仓库版本、HEAD、安装版本三者哪一个是旧的，再重跑第 6 步 |
| 用户只要 commit / push | 跳过第 6、7 步，明确说明“插件未更新” |

## 9. 快速流程

```bash
node <skill>/scripts/bump_versions.mjs --skill <name>
# 跑测试 / 校验
git add <files> && git commit -m "..."
git push origin main
claude plugin marketplace update skills
claude plugin update yobdcdoll-skills@skills
node <skill>/scripts/verify_install.mjs --plugin yobdcdoll-skills@skills --skill <name>
```

最后报告：提交号、推送结果、插件新旧版本、是否需要重启。
