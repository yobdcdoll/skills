---
name: update-github-hosts
description: 在 macOS 上诊断、更新并验证 /etc/hosts 中的 GitHub 固定 IP 映射。用户要求修复 GitHub 访问、合并 GitHub520 重复条目、切换 github.com 的 IP，或刷新 DNS 时使用；普通网络排障或非 GitHub 域名修改不要使用本技能。
metadata:
  version: 1.1.0
---

# Update GitHub Hosts

用可验证的最小改动修复 GitHub 固定 IP 映射。不要因为某个 GitHub520 条目“更新”就认为它的 IP 可用，也不要把 hosts 当成跨境线路或 TLS 故障的通用修复。

## 安全边界

- 修改 `/etc/hosts` 前必须取得用户当次明确授权。技能被调用不等于授权写入系统文件。
- 只修改用户指定的 GitHub 域名。保留 `localhost`、`broadcasthost`、`aTrustAgent` 和其他无关条目原样不动。
- 先备份，再修改。使用 `cp -p /etc/hosts /etc/hosts.bak.YYYYMMDD-HHMMSS`。
- 用 `cat /tmp/hosts.staged > /etc/hosts` 写入现有 inode，避免替换文件后丢失权限、ACL 或扩展属性。
- 不编辑 `aTrustAgent` 自动维护的行。
- 修改前展示 `diff -u`。如果目标域名存在多个有效映射，先合并重复块；不要让脚本猜测该保留哪一个。
- 自动更新工具可能覆盖这次修改。交付时明确说明这一点。

## 工作流

### 1. 查看现状

```bash
sed -n '1,240p' /etc/hosts
dscacheutil -q host -a name github.com
grep -nE '^[^#].*[[:space:]]github\.com([[:space:]]|$)' /etc/hosts
```

如果存在重复的 GitHub520 块：

1. 保留更新时间较新的完整块。
2. 只删除明确重复的旧块，不要把两个块逐行混合。
3. 生成临时文件并展示差异。
4. 经授权写入、刷新 DNS、验证后，再进行 IP 切换。

这次工作得到的具体教训是：正则替换时不要用 `\s+` 捕获行尾空白，Perl 的 `\s` 可能吞掉换行。优先使用内置的 staging 子命令，或至少使用 `[ \t]+`。

### 2. 动态发现并探测候选 IP

不要维护 GitHub IP 列表。`discover` 在运行时汇总这些来源：

- GitHub 官方 Meta API 中指定分类的 `/32` 入口。
- 系统 DNS 的 A 记录，使用 `dig` 绕过 `/etc/hosts`。
- 当前 `/etc/hosts` 中目标域名的映射。
- GitHub520 上游 hosts 中目标域名的映射。

```bash
python3 scripts/github_hosts.py discover --domain github.com --category web
```

脚本先去重，再并发探测所有动态候选；首轮成功者继续多轮复测。某个来源失败只产生警告，不会阻止其他来源继续。可分别用 `--no-meta`、`--no-dns`、`--no-hosts`、`--no-github520` 排除来源。

资源域名要使用真实路径，避免把根路径重定向误判为资源域名故障：

```bash
python3 scripts/github_hosts.py discover \
  --domain raw.githubusercontent.com \
  --category web \
  --path /github/gitignore/main/README.md
```

只有用户显式提供候选或需要复核已知地址时才使用 `probe`，它不接受隐式默认列表：

```bash
python3 scripts/github_hosts.py probe \
  --domain github.com \
  --candidates "$CANDIDATE_IP"
```

选择标准：

- 连续探测成功率优先，其次看中位连接时间。
- 一次成功但随后失败的路由不要选。
- TLS 必须校验成功，不能只测 TCP 端口。
- 不要用根路径的重定向结果判断 `raw.githubusercontent.com` 或 `codeload.github.com` 坏了；要测真实文件或归档地址。

网络探测可能需要沙箱外权限。按当前环境要求发起授权，不要自行放宽权限。

### 3. 生成暂存文件

```bash
python3 scripts/github_hosts.py stage \
  --domain github.com \
  --ip "$RECOMMENDED_IP" \
  --source /etc/hosts \
  --output /tmp/hosts.github

diff -u /etc/hosts /tmp/hosts.github
```

`stage` 只替换一个有效映射并保留该行的缩进、域名列表和行尾注释。没有映射或存在多个映射时它会失败，这是有意的安全保护。

### 4. 授权写入并刷新 DNS

如果非交互 `sudo` 已可用：

```bash
sudo cp -p /etc/hosts /etc/hosts.bak.YYYYMMDD-HHMMSS
sudo sh -c 'cat /tmp/hosts.github > /etc/hosts'
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
```

如果 `sudo -n` 提示需要密码，改用 macOS 管理员授权窗口，并替换为真实时间戳和暂存路径：

```bash
osascript -e 'do shell script "cp -p /etc/hosts /etc/hosts.bak.YYYYMMDD-HHMMSS && cat /tmp/hosts.github > /etc/hosts && dscacheutil -flushcache && killall -HUP mDNSResponder" with administrator privileges'
```

不要把 sudo 密码写入脚本、日志或响应。

### 5. 验证

```bash
dscacheutil -q host -a name github.com

curl -LsS --connect-timeout 5 --max-time 15 \
  https://github.com -o /dev/null \
  -w 'GET HTTP %{http_code} connect=%{time_connect}s total=%{time_total}s\n'

curl -sS --connect-timeout 5 --max-time 12 \
  'https://github.com/git/git.git/info/refs?service=git-upload-pack' \
  -o /dev/null -w 'Git HTTP %{http_code}\n'
```

判断规则：

- `dscacheutil` 必须返回刚写入的 IP。
- 网页 GET 返回 2xx 或合理的 3xx 才算链路可用。
- Git Smart HTTP 端点对 `HEAD` 返回 `405` 是正常的；这里使用 GET，期望 `200`。
- `git ls-remote` 提示用户名、token 或认证失败时，报告为凭据问题，不要误判为 hosts 问题。
- 网页仍偶发超时但 Git 端点稳定时，如实说明 hosts 无法完全修复跨境 HTTPS 线路。

### 6. 回滚

```bash
osascript -e 'do shell script "cat /etc/hosts.bak.YYYYMMDD-HHMMSS > /etc/hosts && dscacheutil -flushcache && killall -HUP mDNSResponder" with administrator privileges'
```

回滚后再次用 `dscacheutil` 验证。

## 常见误判

- **DNS 与 hosts 同时返回同一个坏 IP**：说明不是 DNS 缓存，而是该 IP 的线路或服务不可达；必须换候选 IP 或代理。
- **只测根路径并跟随重定向**：Raw/Codeload 根路径可能跳回 `github.com`，超时来自主站，不代表资源域名坏了。
- **`curl -I` 成功一次就写入**：GitHub 线路可能间歇性丢包，至少连续探测 3 次。
- **把 401/403/405 都当成网络失败**：先区分认证、请求方法和端点行为。
- **静态 IP 当成长期方案**：IP 会变化；需要稳定访问时优先统一代理，Git 可单独使用 SSH over 443。
