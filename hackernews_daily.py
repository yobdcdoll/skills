#!/usr/bin/env python3
"""
Hacker News 每日早报 - Algolia API -> 本地存档 -> LLM 总结 -> 飞书卡片
"""
import json
import subprocess
import sys
import requests
import re
import uuid
from datetime import datetime, timezone, timedelta


def get_config():
    with open("/root/.openclaw/openclaw.json") as f:
        return json.load(f)


def get_token(app_id, app_secret):
    r = subprocess.run([
        "curl", "-s", "-X", "POST",
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"app_id": app_id, "app_secret": app_secret})
    ], capture_output=True, text=True)
    return json.loads(r.stdout)["tenant_access_token"]


def fetch_hn_today(limit=20):
    """抓取今日 HN Top（北京时间当天）"""
    url = "https://hn.algolia.com/api/v1/search"
    params = {"tags": "front_page", "hitsPerPage": limit}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    hits = resp.json().get("hits", [])

    bj = timezone(timedelta(hours=8))
    now_bj = datetime.now(bj)
    today_start = now_bj.replace(hour=0, minute=0, second=0, microsecond=0)

    filtered = []
    for h in hits:
        ts = h.get("created_at", "")
        if not ts:
            continue
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(bj)
        if dt >= today_start:
            filtered.append({
                "title": h.get("title", ""),
                "url": h.get("url", ""),
                "points": h.get("points", 0),
                "author": h.get("author", ""),
                "objectID": h.get("objectID", ""),
                "created_at": dt.strftime("%Y-%m-%d %H:%M"),
            })

    return sorted(filtered, key=lambda x: -x["points"])


def fetch_hn_weekly(limit=50):
    """抓取本周 HN Top（7天内），用 Algolia 日期过滤"""
    bj = timezone(timedelta(hours=8))
    now_bj = datetime.now(bj)
    week_ago = now_bj - timedelta(days=7)
    week_ts = int(week_ago.timestamp())

    url = "https://hn.algolia.com/api/v1/search"
    params = {
        "tags": "front_page",
        "hitsPerPage": limit,
        "numericFilters": f"created_at_i>{week_ts}",
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    hits = resp.json().get("hits", [])

    results = []
    for h in hits:
        ts = h.get("created_at", "")
        if not ts:
            continue
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(bj)
        sid = h.get("objectID", "")
        results.append({
            "title": h.get("title", ""),
            "url": h.get("url", f"https://news.ycombinator.com/item?id={sid}"),
            "points": h.get("points", 0),
            "author": h.get("author", ""),
            "objectID": sid,
            "created_at": dt.strftime("%Y-%m-%d %H:%M"),
        })

    return sorted(results, key=lambda x: -x["points"])[:15]


def save_raw(today, weekly):
    """原始数据存档到 /tmp/hn_YYYY-MM-DD_[4位uuid].txt"""
    today_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    suffix = uuid.uuid4().hex[:4]
    filepath = f"/tmp/hn_{today_str}_{suffix}.txt"

    lines = ["[TODAY]\n"]
    for i, item in enumerate(today, 1):
        lines.append(f"{i}. {item['title']} | {item['url']} | {item['points']} pts | {item['author']} | {item['created_at']}")

    lines.append("\n[WEEKLY]\n")
    for i, item in enumerate(weekly, 1):
        lines.append(f"{i}. {item['title']} | {item['url']} | {item['points']} pts | {item['author']} | {item['created_at']}")

    with open(filepath, "w") as f:
        f.write("\n".join(lines))

    print(f"   原始数据已存档: {filepath}")
    return filepath


def extract_json_from_response(raw):
    """从 LLM 响应内容中提取 JSON，去除 think tags，取第一个 { 到配对 } 的内容"""
    # 去除 <think>...</think> thinking tags
    cleaned = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)

    # 找第一个 {
    json_start = cleaned.find('{')
    if json_start == -1:
        raise ValueError("No '{' found in response: " + repr(raw[:200]))

    after = cleaned[json_start:]

    # 先尝试直接解析
    try:
        json.loads(after)
        return after.strip()
    except Exception:
        pass

    # 尝试去除 markdown code fences
    after_clean = after.strip()
    if after_clean.startswith("```"):
        for part in after_clean.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                try:
                    json.loads(part)
                    return part
                except Exception:
                    pass

    # Brace counting：找配对的闭合 }
    depth = 0
    for i, ch in enumerate(after):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return after[:i+1].strip()

    raise ValueError("Could not find matching } in: " + repr(after[:200]))


def llm_summarize(filepath, api_key, base_url, llm_model, retries=3, retry_delay=5):
    """读取本地存档，LLM 批量生成描述（失败自动重试）"""
    with open(filepath) as f:
        raw_content = f.read()

    today_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y年%m月%d日")

    prompt = f"""以下是从 Hacker News 抓取的今日 Top 和本周 Top 新闻，请为每条生成约100字的中文解读，说明该新闻的背景、意义或值得关注的点。

{raw_content}

Output ONLY valid JSON，格式如下（不要输出任何其他内容）：
{{
  "today": [
    {{"desc": "这条新闻的中文解读，约100字"}},
    ...
  ],
  "weekly": [
    {{"desc": "这条新闻的中文解读，约100字"}},
    ...
  ]
}}
"""

    system_prompt = "You are a tech news curator. Output ONLY valid JSON. Do NOT use <think> or </think> tags. Do NOT use markdown fences."

    payload = {
        "model": llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 3000,
        "temperature": 0.1,
    }

    if "MiniMax" in llm_model or "minimax" in llm_model.lower():
        payload["skip"] = ["think"]

    api_url = base_url + "/chat/completions"

    import time as _time

    last_err = None
    for attempt in range(1, retries + 1):
        if attempt > 1:
            print(f"   LLM 解读失败，{retry_delay}s 后重试 ({attempt}/{retries})...", file=sys.stderr)
            _time.sleep(retry_delay)
        try:
            resp = requests.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=90,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            if not raw:
                raise ValueError("Empty content from API")

            after = extract_json_from_response(raw)
            if after.startswith("```"):
                for part in after.split("```"):
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("{"):
                        after = part
                        break

            return json.loads(after)

        except Exception as e:
            last_err = e
            print(f"LLM summarize failed (attempt {attempt}): {e}", file=sys.stderr)

    print(f"LLM summarize failed after {retries} attempts: {last_err}", file=sys.stderr)
    return None


def build_card(today_items, weekly_items, today_desc, weekly_desc, summary_failed=False):
    today_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y年%m月%d日")

    # 解读失败时在头部加提示
    notify_elements = []
    if summary_failed:
        notify_elements.append({
            "tag": "markdown",
            "content": "⚠️ 本次 AI 解读生成失败，以下仅展示标题与链接。"
        })
        notify_elements.append({"tag": "hr"})

    def fmt_item(item, i, desc):
        title = item["title"]
        url = item["url"] or f"https://news.ycombinator.com/item?id={item['objectID']}"
        points = item["points"]
        author = item["author"]
        ts = item["created_at"]
        title_link = f"[{title}]({url})"
        desc_text = f"\n   💬 {desc}" if desc else ""
        return (
            f"**{i}.** {title_link}\n"
            f"   🔥 {points} pts · 👤 {author} · 🕐 {ts}{desc_text}"
        )

    today_lines = []
    if today_items:
        for i, item in enumerate(today_items, 1):
            desc = today_desc[i - 1]["desc"] if today_desc and i <= len(today_desc) else ""
            today_lines.append(fmt_item(item, i, desc))
    else:
        today_lines.append("_今日暂无新增热门条目_")

    weekly_lines = []
    for i, item in enumerate(weekly_items, 1):
        desc = weekly_desc[i - 1]["desc"] if weekly_desc and i <= len(weekly_desc) else ""
        weekly_lines.append(fmt_item(item, i, desc))

    elements = list(notify_elements)
    elements += [
        {"tag": "markdown", "content": f"📰 **Hacker News 今日 Top**（{today_str}）"},
        {"tag": "markdown", "content": "\n\n─────────\n\n".join(today_lines)},
        {"tag": "hr"},
        {"tag": "markdown", "content": f"📊 **本周 HN Top 15**"},
        {"tag": "markdown", "content": "\n\n─────────\n\n".join(weekly_lines)},
        {"tag": "note", "elements": [
            {"tag": "plain_text", "content": "由 ArkClaw 自动生成 · 数据来源：news.ycombinator.com"}
        ]},
    ]

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"📰 Hacker News 早报 {today_str}"},
            "template": "orange",
        },
        "elements": elements,
    }


def send_card(token, receive_id, card):
    payload = json.dumps({
        "receive_id": receive_id,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    })
    r = subprocess.run([
        "curl", "-s", "-X", "POST",
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
        "-H", f"Authorization: Bearer {token}",
        "-H", "Content-Type: application/json",
        "-d", payload,
    ], capture_output=True, text=True)
    try:
        resp = json.loads(r.stdout)
    except:
        print(f"响应解析失败: {r.stdout[:200]}", file=sys.stderr)
        return False
    if resp.get("code") in (0, None):
        print("✅ 发送成功！")
        return True
    print(f"发送失败: {resp}", file=sys.stderr)
    return False


def main():
    print("📰 抓取 Hacker News 今日 Top...")
    today = fetch_hn_today(20)
    print(f"   今日: {len(today)} 条")

    print("📊 抓取 Hacker News 本周 Top...")
    weekly = fetch_hn_weekly(50)
    print(f"   本周: {len(weekly)} 条")

    print("💾 保存原始数据...")
    filepath = save_raw(today, weekly)

    # 加载配置
    config = get_config()
    feishu = config["channels"]["feishu"]
    receive_id = "<FEISHU_OPEN_ID>"

    primary = config["agents"]["defaults"]["model"]["primary"]
    if "/" in primary:
        provider_name, llm_model = primary.split("/", 1)
    else:
        provider_name, llm_model = "custom", primary

    providers = config["models"]["providers"]
    if provider_name in providers:
        p = providers[provider_name]
    else:
        p = providers.get("custom", {})
    api_key = p["apiKey"]
    base_url = p["baseUrl"]

    print("🤖 LLM 生成中文解读...")
    result = llm_summarize(filepath, api_key, base_url, llm_model)

    summary_failed = result is None
    today_desc = result.get("today", []) if result else []
    weekly_desc = result.get("weekly", []) if result else []

    print(f"   今日解读: {len(today_desc)} 条, 本周解读: {len(weekly_desc)} 条")
    if summary_failed:
        print("   ⚠️ 解读生成失败，将在卡片中加入提示（仅展示标题与链接）", file=sys.stderr)

    token = get_token(feishu["appId"], feishu["appSecret"])
    card = build_card(today[:10], weekly[:15], today_desc, weekly_desc, summary_failed=summary_failed)
    send_card(token, receive_id, card)


if __name__ == "__main__":
    main()