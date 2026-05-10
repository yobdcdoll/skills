#!/usr/bin/env python3
"""
GitHub AI Trending 日报 - Playwright 抓取 -> LLM 过滤（一次调用） -> 飞书卡片
"""
import asyncio
import json
import subprocess
import sys
import requests
from datetime import datetime
from playwright.async_api import async_playwright


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
    """从 LLM 响应内容中提取 JSON，用 brace counting 找配对的 {}"""
    json_start = raw.rfind('{')
    if json_start == -1:
        raise ValueError("No '{' found in response: " + repr(raw[:200]))

    after = raw[json_start:]

    # Try direct parse first
    try:
        json.loads(after)
        return after.strip()
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


def llm_filter_both(daily, weekly, api_key, base_url, llm_model):
    """一次 LLM 调用同时过滤每日+每周两个批次"""
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
                "max_tokens": 2000,
                "temperature": 0.1,
            },
            timeout=90,
        )
        resp.raise_for_status()

        # 正确方式：从 resp.json() 的嵌套结构里取 content
        raw_content = resp.json()["choices"][0]["message"]["content"]
        if not raw_content:
            raise ValueError("Empty content from API")

        after = extract_json_from_response(raw_content)

        # Strip markdown code fences
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


async def fetch_trending(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        items = await page.evaluate("""
() => {
    const articles = document.querySelectorAll("article.Box-row");
    const results = [];
    articles.forEach(el => {
        const h2 = el.querySelector("h2");
        if (!h2) return;
        const a = h2.querySelector("a");
        if (!a) return;
        let name = a.textContent.trim().replace(/\\s+/g, " ");
        let url = "https://github.com" + a.getAttribute("href");
        if (url.includes("/sponsors/")) return;
        const starsEl = el.querySelector("a[href*='/stargazers']");
        let stars = "0";
        if (starsEl) {
            const m = starsEl.textContent.trim().replace(/,/g,"").match(/([\\d.]+)/);
            stars = m ? m[1] : "0";
        }
        const descEl = el.querySelector("p");
        const desc = descEl ? descEl.textContent.trim() : "";
        results.push({name, url, stars, desc});
    });
    return results;
}
        """)
        await browser.close()
        return items


def topk(items, n=5):
    def sk(x):
        try:
            v = x["stars"]
            return float(v) if "." in v else int(v)
        except:
            return 0
    return sorted(items, key=sk, reverse=True)[:n]


def fmt_stars(s):
    try:
        v = float(s) if "." in s else int(s)
        if v >= 1000:
            return f"{v/1000:.1f}k"
        return str(int(v))
    except:
        return s


def ranked_list(title, items, n=5):
    top = topk(items, n)
    lines = [f"**{title}**", ""]
    for i, x in enumerate(top, 1):
        s = fmt_stars(x["stars"])
        name_link = f'[{x["name"]}]({x["url"]})'
        desc = x["desc"][:100].replace("\n", " ").strip()
        lines.append(f"**{i}.** {name_link}  ⭐ {s}")
        lines.append(f"   {desc}")
        lines.append("")
    return {"tag": "markdown", "content": "\n".join(lines)}


def build_card(daily_top, weekly_top):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    elements = [
        {"tag": "markdown", "content": f"📈 **GitHub AI Trending 日报**（{now}）"},
        ranked_list("🎯 今日热门 AI 项目 Top5", daily_top, 5),
        {"tag": "hr"},
        ranked_list("📊 本周热门 AI 项目 Top10", weekly_top, 10),
        {"tag": "note", "elements": [
            {"tag": "plain_text", "content": "由 ArkClaw 自动生成 · 数据来源：github.com/trending"}
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


async def main_async():
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
    daily = await fetch_trending("https://github.com/trending")
    print(f"   每日: {len(daily)} repos")

    print("🌐 抓取 GitHub Trending（每周）...")
    weekly = await fetch_trending("https://github.com/trending?since=weekly")
    print(f"   每周: {len(weekly)} repos")

    print("🤖 LLM 过滤 AI 项目（一次调用）...")
    daily_ai, weekly_ai = llm_filter_both(daily, weekly, api_key, base_url, llm_model)
    print(f"   LLM 过滤: 每日 {len(daily_ai)} 个, 每周 {len(weekly_ai)} 个")

    daily_top = topk(daily_ai, 5)
    weekly_top = topk(weekly_ai, 10)
    print(f"🏆 每日: {', '.join(x['name'] for x in daily_top)}")
    print(f"🏆 每周: {', '.join(x['name'] for x in weekly_top)}")

    if not daily_top and not weekly_top:
        print("⚠️ 未找到AI项目，使用全部热门备选")
        daily_top = topk(daily, 5)
        weekly_top = topk(weekly, 10)

    token = get_token(feishu["appId"], feishu["appSecret"])
    card = build_card(daily_top, weekly_top)
    send_card(token, receive_id, card)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
