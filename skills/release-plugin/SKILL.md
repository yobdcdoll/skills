---
name: release-plugin
description: 把当前仓库的 skill 改动做发布前检查、版本 bump、提交并推送。用户说“提交并推送”“推送 skill 改动”“commit, push”时使用；不负责更新已安装的插件；只发布普通软件包时不要用本技能。
metadata:
  version: 1.0.0
---

# 发布 skill 改动

把仓库里的 skill 改动做发布前检查、版本 bump、提交并推送。已安装插件的更新与重启不在本技能范围内。

## 1. 何时使用

- 用户要求提交并推送本仓库的 skill 改动。
- 改动落在本仓库的 `skills/<name>/` 下，需要进入远端仓库。
- 用户只要求 commit 或只要求 push：做对应步骤，其余跳过。

不适用：更新已安装插件、重启 agent；普通应用代码发布、只改 README、只发 npm/PyPI 包。

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

> 只改 skill 版本不够。安装端按**插件包版本**判断是否有新版本；包版本没变，新 skill 不会被视为一次更新。

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

未推送的提交不会进入任何安装端或 marketplace clone。

## 6. 验证（可选）

如需核对安装缓存与本仓库是否一致（前提是安装端已拉到本次提交）：

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

任一项不匹配时，先确认是仓库、HEAD 还是安装缓存旧；安装缓存落后时请用户更新插件，再重跑验证。

## 7. 失败处理

| 现象 | 处理 |
| --- | --- |
| 远端没有新提交 | 检查 `git push` 输出、远端分支、网络与凭证 |
| 安装缓存有旧版本 | 属于插件更新环节；提示用户更新后再验证，本技能不代为更新 |
| 验证脚本报版本不一致 | 先确认仓库版本、HEAD、安装版本三者哪一个是旧的；安装版本落后时请用户更新插件 |
| 用户只要 commit / push | 做到对应步骤即可，明确说明“插件未更新” |

## 8. 快速流程

```bash
node <skill>/scripts/bump_versions.mjs --skill <name>
# 跑测试 / 校验
git add <files> && git commit -m "..."
git push origin main

# 可选：用户更新插件后核对安装缓存
node <skill>/scripts/verify_install.mjs --plugin yobdcdoll-skills@skills --skill <name>
```

最后报告：提交号、推送结果。
