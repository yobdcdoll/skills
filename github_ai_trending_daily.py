#!/usr/bin/env python3
"""
GitHub AI Trending 日报 - requests+html.parser 抓取 -> LLM 过滤（一次调用） -> 飞书卡片
"""
import asyncio
import json
import re
import subprocess
import sys
import requests
from datetime import datetime
from html.parser import HTMLParser


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


def extract_json_from_response(raw):
    """Extract JSON from LLM response, stripping think/analysis tags."""
    # Remove think/analyze blocks (various formats)
    cleaned = re.sub(r'<thinking>[\s\S]*?</thinking>', '', raw, flags=re.IGNORECASE)
    cleaned = re.sub(r'\[癢[\s\S]*?\]癢', '', cleaned)
    cleaned = re.sub(r'\[\[[\s\S]*?\]\]', '', cleaned)
    # Now look for JSON in the cleaned text
    json_start = cleaned.rfind('{')
    if json_start == -1:
        raise ValueError("No '{' found after stripping think tags in: " + repr(raw[:300]))

    after = cleaned[json_start:]
    try:
        json.loads(after)
        return after.strip()
    except Exception:
        pass

    # Brace counting: find matching }
    depth = 0
    for i, ch in enumerate(after):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return after[:i+1].strip()

    raise ValueError("Could not find matching } in: " + repr(after[:200]))


def llm_filter_both(daily, weekly, api_key, base_url, llm_model):
    if not daily and not weekly:
        return [], []

    def make_list_section(label, repos):
        lines = [f"{label}:"]
        for i, r in enumerate(repos, 1):
            desc = r["desc"][:150].strip() if r["desc"] else "(no desc)"
            lines.append(f"  {i}. {r['name']} - {desc}")
        return "\n".join(lines)

    daily_section = make_list_section("DAILY_REPOS", daily)
    weekly_section = make_list_section("WEEKLY_REPOS", weekly)

    prompt = (
        "You are an AI/ML expert. For each repo below, determine if it is AI/ML/LLM-related.\n\n"
        f"{daily_section}\n\n{weekly_section}\n\n"
        "Output ONLY valid JSON, no markdown, no explanation, no thinking tags:\n"
        '{"daily_ai_repos": [daily_index1, ...], "weekly_ai_repos": [weekly_index1, ...]}\n\n'
        "Rules:\n"
        "- Include if related to: LLMs, AI models, ML, deep learning, AI agents, chatbots, "
        "AI frameworks, AI SDKs, AI APIs, AI tools, generative AI, AI inference, fine-tuning, "
        "RLHF, vector DBs, RAG, embeddings, diffusion, AI coding assistants.\n"
        "- Exclude: qBittorrent, maigret (OSINT), chess engines, game emulators, hardware, "
        "CLI tools without AI, package managers.\n"
        "- Indexes are 1-based within each section separately.\n"
        "- Return empty list [] for a section if nothing qualifies."
    )

    api_url = base_url + "/chat/completions"

    try:
        resp = requests.post(
            api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": llm_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 16000,
                "temperature": 0.1,
            },
            timeout=90,
        )
        resp.raise_for_status()
        raw_content = resp.json()["choices"][0]["message"]["content"]
        if not raw_content:
            raise ValueError("Empty content from API")

        after = extract_json_from_response(raw_content)
        if after.startswith("```"):
            for part in after.split("```"):
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    after = part
                    break

        result = json.loads(after)
        daily_indices = result.get("daily_ai_repos", [])
        weekly_indices = result.get("weekly_ai_repos", [])

        daily_ai = [daily[i - 1] for i in daily_indices if 1 <= i <= len(daily)]
        weekly_ai = [weekly[i - 1] for i in weekly_indices if 1 <= i <= len(weekly)]

        return daily_ai, weekly_ai

    except Exception as e:
        print(f"LLM filter failed: {e}", file=sys.stderr)
        return [], []


class TrendingParser(HTMLParser):
    """Parse GitHub Trending HTML to extract repo info."""
    def __init__(self):
        super().__init__()
        self.in_article = False
        self.in_h2 = False
        self.in_a = False
        self.in_stars = False
        self.in_desc = False
        self.current_text = ""
        self.current_href = ""
        self.items = []
        self.current_item = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        href = attrs_dict.get("href", "")

        if tag == "article" and "Box-row" in cls:
            self.in_article = True
            self.current_item = {"name": "", "url": "", "stars": "0", "desc": "",
                                 "_raw": "", "period": "", "period_label": ""}
            return

        if not self.in_article:
            return

        if tag == "h2":
            self.in_h2 = True
            self.current_text = ""
        elif tag == "a":
            if self.in_h2:
                self.in_a = True
                self.current_href = href
                self.current_text = ""
            elif "stargazers" in href:
                self.in_stars = True
                self.current_text = ""
        elif tag == "p":
            if self.in_article and not self.in_h2:
                self.in_desc = True
                self.current_text = ""

    def handle_endtag(self, tag):
        if tag == "article" and self.in_article:
            if self.current_item and self.current_item.get("name"):
                # 解析「本期新增星」：X stars today / X stars this week
                mm = re.search(r"([\d,\.]+)\s+stars\s+(today|this week)",
                               self.current_item.get("_raw", ""))
                if mm:
                    self.current_item["period"] = mm.group(1).replace(",", "")
                    self.current_item["period_label"] = mm.group(2)
                self.current_item.pop("_raw", None)
                self.items.append(self.current_item)
            self.in_article = False
            self.current_item = None
        elif tag == "h2":
            self.in_h2 = False
        elif tag == "a":
            if self.in_a:
                self.in_a = False
                if self.current_item and self.current_text.strip():
                    name = re.sub(r"\s+", " ", self.current_text.strip())
                    url = "https://github.com" + self.current_href
                    if "/sponsors/" not in url:
                        self.current_item["name"] = name
                        self.current_item["url"] = url
            elif self.in_stars:
                self.in_stars = False
                if self.current_item:
                    text = self.current_text.strip().replace(",", "")
                    m = re.match(r"([\d.]+)", text)
                    self.current_item["stars"] = m.group(1) if m else "0"
        elif tag == "p" and self.in_desc:
            self.in_desc = False
            if self.current_item:
                self.current_item["desc"] = self.current_text.strip()

    def handle_data(self, data):
        if self.in_a or self.in_stars or self.in_desc or self.in_h2:
            self.current_text += data
        if self.in_article and self.current_item is not None:
            self.current_item["_raw"] = self.current_item.get("_raw", "") + data


def fetch_trending(url):
    """Sync fetch using requests + html.parser."""
    resp = requests.get(url, timeout=15, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://github.com/",
        "Cache-Control": "no-cache",
        "Upgrade-Insecure-Requests": "1",
    })
    resp.raise_for_status()
    parser = TrendingParser()
    parser.feed(resp.text)
    return parser.items


def to_num(s):
    """把 '32,314' / '3.4k' 之类转成数字，失败返回 0。"""
    try:
        s = str(s).replace(",", "").strip()
        if not s:
            return 0
        return float(s) if "." in s else int(s)
    except Exception:
        return 0


def topk(items, n=5):
    return sorted(items, key=lambda x: to_num(x.get("stars")), reverse=True)[:n]


def rank_items(items, n=10):
    """按「本期新增星」降序取前 n；若无任何 period 数据则回退按总星排序。
    返回 (ranked_list, has_period)。"""
    has_period = any(x.get("period") for x in items)
    if has_period:
        ranked = sorted(items, key=lambda x: to_num(x.get("period")), reverse=True)
    else:
        ranked = sorted(items, key=lambda x: to_num(x.get("stars")), reverse=True)
    return ranked[:n], has_period


def fmt_stars(s):
    try:
        s = str(s).replace(",", "")
        v = float(s) if "." in s else int(s)
        if v >= 1000:
            return f"{v/1000:.1f}k"
        return str(int(v))
    except:
        return str(s)


def ranked_list(title, items, n=10, period_word="今日"):
    """items 需已排好序；n 重新裁剪以防越界。"""
    top = items[:n]
    lines = [f"**{title}**", ""]
    for i, x in enumerate(top, 1):
        s = fmt_stars(x["stars"])
        name_link = f'[{x["name"]}]({x["url"]})'
        desc = x["desc"][:100].replace("\n", " ").strip()
        head = f"**{i}.** {name_link}  ⭐ {s}"
        if x.get("period"):
            head += f" ｜ 🔺 {period_word} +{fmt_stars(x['period'])}"
        lines.append(head)
        lines.append(f"   {desc}")
        lines.append("")
    return {"tag": "markdown", "content": "\n".join(lines)}


def build_card(daily_top, weekly_top, daily_period=True, weekly_period=True):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    daily_title = ("🎯 今日热门 AI 项目 Top10（按今日新增 ⭐ 排序）" if daily_period
                   else "🎯 今日热门 AI 项目 Top10（按总 ⭐ 排序）")
    weekly_title = ("📊 本周热门 AI 项目 Top10（按本周新增 ⭐ 排序）" if weekly_period
                    else "📊 本周热门 AI 项目 Top10（按总 ⭐ 排序）")
    elements = [
        {"tag": "markdown", "content": f"📈 **GitHub AI Trending 日报**（{now}）"},
        ranked_list(daily_title, daily_top, 10, "今日"),
        {"tag": "hr"},
        ranked_list(weekly_title, weekly_top, 10, "本周"),
        {"tag": "note", "elements": [
            {"tag": "plain_text", "content": "⭐=累计星 ｜ 🔺=本期新增星（排序依据）· 由 ArkClaw 自动生成 · 数据来源：github.com/trending"}
        ]},
    ]
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"📈 GitHub AI Trending 日报 {now}"},
            "template": "blue",
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


def main_async():
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

    print("🌐 抓取 GitHub Trending（每日）...")
    daily = fetch_trending("https://github.com/trending")
    print(f"   每日: {len(daily)} repos")

    print("🌐 抓取 GitHub Trending（每周）...")
    weekly = fetch_trending("https://github.com/trending?since=weekly")
    print(f"   每周: {len(weekly)} repos")

    print("🤖 LLM 过滤 AI 项目（一次调用）...")
    daily_ai, weekly_ai = llm_filter_both(daily, weekly, api_key, base_url, llm_model)
    print(f"   LLM 过滤: 每日 {len(daily_ai)} 个, 每周 {len(weekly_ai)} 个")

    daily_top, daily_period = rank_items(daily_ai, 10)
    weekly_top, weekly_period = rank_items(weekly_ai, 10)
    print(f"🏆 每日(按本期新增): {', '.join(x['name'] for x in daily_top)}")
    print(f"🏆 每周(按本期新增): {', '.join(x['name'] for x in weekly_top)}")
    if not daily_period:
        print("⚠️ 每日榜未解析到新增星，回退按总星排序")
    if not weekly_period:
        print("⚠️ 每周榜未解析到新增星，回退按总星排序")

    if not daily_top and not weekly_top:
        print("⚠️ 未找到AI项目，使用全部热门备选")
        daily_top, daily_period = rank_items(daily, 10)
        weekly_top, weekly_period = rank_items(weekly, 10)

    token = get_token(feishu["appId"], feishu["appSecret"])
    card = build_card(daily_top, weekly_top, daily_period, weekly_period)
    send_card(token, receive_id, card)


def main():
    main_async()


if __name__ == "__main__":
    main()