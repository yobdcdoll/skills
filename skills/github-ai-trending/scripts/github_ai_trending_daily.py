#!/usr/bin/env python3
"""
GitHub AI Trending 日报。

抓取 GitHub Trending -> 可选 LLM 过滤 AI 项目 -> 输出 Markdown 或 JSON。

脚本只负责取数和过滤，不包含任何发送逻辑，也不读取 OpenClaw 配置；
发到哪个渠道、发给谁，由调用方（OpenClaw 或其他 agent）决定。

用法:
    python3 scripts/github_ai_trending_daily.py
    python3 scripts/github_ai_trending_daily.py --format json
    python3 scripts/github_ai_trending_daily.py --output /tmp/trending.md
    LLM_API_KEY=... LLM_BASE_URL=... LLM_MODEL=... \
        python3 scripts/github_ai_trending_daily.py

环境变量:
    LLM_API_KEY   OpenAI 兼容接口的 API key；三项齐全时才启用 AI 过滤
    LLM_BASE_URL  接口地址，例如 https://api.openai.com/v1
    LLM_MODEL     模型名，例如 gpt-4o-mini
    OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL  作为 LLM_* 的回退
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from html.parser import HTMLParser

import requests

DAILY_URL = "https://github.com/trending"
WEEKLY_URL = "https://github.com/trending?since=weekly"

DEFAULT_DAILY = 10
DEFAULT_WEEKLY = 10


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
            self.current_item = {
                "name": "",
                "url": "",
                "stars": "0",
                "desc": "",
                "_raw": "",
                "period": "",
                "period_label": "",
            }
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
                match = re.search(
                    r"([\d,.]+)\s+stars\s+(today|this week)",
                    self.current_item.get("_raw", ""),
                )
                if match:
                    self.current_item["period"] = match.group(1).replace(",", "")
                    self.current_item["period_label"] = match.group(2)
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
                    match = re.match(r"([\d.]+)", text)
                    self.current_item["stars"] = match.group(1) if match else "0"
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
    """抓取一页 GitHub Trending。"""
    resp = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://github.com/",
        },
    )
    resp.raise_for_status()
    parser = TrendingParser()
    parser.feed(resp.text)
    return parser.items


def extract_json_from_response(raw):
    """从 LLM 响应中提取 JSON，容忍 think 标签和 markdown 代码围栏。"""
    cleaned = re.sub(r"<thinking>[\s\S]*?</thinking>", "", raw, flags=re.IGNORECASE)
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\[癢[\s\S]*?\]癢", "", cleaned)
    cleaned = re.sub(r"\[\[[\s\S]*?\]\]", "", cleaned)

    json_start = cleaned.rfind("{")
    if json_start == -1:
        raise ValueError("响应中没有 JSON 对象: " + repr(raw[:300]))

    after = cleaned[json_start:]

    try:
        json.loads(after)
        return after.strip()
    except Exception:
        pass

    depth = 0
    for i, ch in enumerate(after):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return after[: i + 1].strip()

    raise ValueError("无法匹配 JSON 括号: " + repr(after[:200]))


def llm_filter_both(daily, weekly, api_key, base_url, model, timeout=90, max_tokens=16000):
    """一次调用 LLM，返回两个列表中的 AI 相关仓库。失败时抛异常。"""
    if not daily and not weekly:
        return [], []

    def make_list_section(label, repos):
        lines = [f"{label}:"]
        for i, repo in enumerate(repos, 1):
            desc = repo["desc"][:150].strip() if repo["desc"] else "(no desc)"
            lines.append(f"  {i}. {repo['name']} - {desc}")
        return "\n".join(lines)

    prompt = (
        "You are an AI/ML expert. For each repo below, determine if it is AI/ML/LLM-related.\n\n"
        f"{make_list_section('DAILY_REPOS', daily)}\n\n"
        f"{make_list_section('WEEKLY_REPOS', weekly)}\n\n"
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

    api_url = base_url.rstrip("/") + "/chat/completions"

    try:
        resp = requests.post(
            api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.1,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        raw_content = resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"LLM 请求失败: {exc}") from exc

    if not raw_content:
        raise RuntimeError("LLM 返回了空内容")

    after = extract_json_from_response(raw_content)

    try:
        result = json.loads(after)
    except Exception as exc:
        raise RuntimeError(f"无法解析 LLM 输出: {exc}; 原始内容: {raw_content[:300]!r}") from exc

    daily_indices = result.get("daily_ai_repos", [])
    weekly_indices = result.get("weekly_ai_repos", [])

    daily_ai = [daily[i - 1] for i in daily_indices if isinstance(i, int) and 1 <= i <= len(daily)]
    weekly_ai = [weekly[i - 1] for i in weekly_indices if isinstance(i, int) and 1 <= i <= len(weekly)]
    return daily_ai, weekly_ai


def to_num(value):
    """把 '32,314' / '3.4k' 之类转成数字，失败返回 0。"""
    try:
        text = str(value).replace(",", "").strip()
        if not text:
            return 0
        return float(text) if "." in text else int(text)
    except Exception:
        return 0


def fmt_stars(value):
    try:
        text = str(value).replace(",", "")
        number = float(text) if "." in text else int(text)
        if number >= 1000:
            return f"{number / 1000:.1f}k"
        return str(int(number))
    except Exception:
        return str(value)


def rank_items(items, limit):
    """按本期新增星降序；没有新增星数据时回退到累计星。"""
    has_period = any(item.get("period") for item in items)
    key = "period" if has_period else "stars"
    ranked = sorted(items, key=lambda item: to_num(item.get(key)), reverse=True)[:limit]
    return [
        {**item, "rank": index}
        for index, item in enumerate(ranked, 1)
    ], has_period


def ranked_markdown(title, items, period_word):
    lines = [f"**{title}**", ""]
    for item in items:
        head = (
            f"**{item['rank']}.** [{item['name']}]({item['url']})"
            f"  ⭐ {fmt_stars(item['stars'])}"
        )
        if item.get("period"):
            head += f" ｜ 🔺 {period_word} +{fmt_stars(item['period'])}"
        lines.append(head)

        desc = (item.get("desc") or "").replace("\n", " ").strip()[:100]
        if desc:
            lines.append(f"   {desc}")
        lines.append("")
    return "\n".join(lines).rstrip()


def render_markdown(daily, weekly, daily_period, weekly_period, daily_limit, weekly_limit, now):
    daily_sort = "按今日新增 ⭐ 排序" if daily_period else "按总 ⭐ 排序"
    weekly_sort = "按本周新增 ⭐ 排序" if weekly_period else "按总 ⭐ 排序"

    parts = [
        f"📈 **GitHub AI Trending 日报**（{now}）",
        "",
        ranked_markdown(f"🎯 今日热门 AI 项目 Top{daily_limit}（{daily_sort}）", daily, "今日"),
        "",
        "---",
        "",
        ranked_markdown(f"📊 本周热门 AI 项目 Top{weekly_limit}（{weekly_sort}）", weekly, "本周"),
        "",
        "---",
        "",
        "⭐=累计星 ｜ 🔺=本期新增星（排序依据）",
        "数据来源：github.com/trending",
    ]
    return "\n".join(parts)


def render_json(daily, weekly, daily_period, weekly_period, llm_filtered, fallback):
    return json.dumps(
        {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source": DAILY_URL,
            "llm_filtered": llm_filtered,
            "fallback_to_all": fallback,
            "daily": {
                "sort": "period" if daily_period else "stars",
                "items": daily,
            },
            "weekly": {
                "sort": "period" if weekly_period else "stars",
                "items": weekly,
            },
        },
        ensure_ascii=False,
        indent=2,
    )


def default_env(*names):
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="抓取 GitHub Trending 并输出 AI 项目日报（不发送）"
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="输出格式（默认 markdown）",
    )
    parser.add_argument("--output", help="输出文件路径；不指定则写到 stdout")
    parser.add_argument(
        "--top-daily", type=int, default=DEFAULT_DAILY, help="今日条目数（默认 10）"
    )
    parser.add_argument(
        "--top-weekly", type=int, default=DEFAULT_WEEKLY, help="本周条目数（默认 10）"
    )
    parser.add_argument("--no-llm", action="store_true", help="跳过 LLM 过滤")
    parser.add_argument(
        "--api-key",
        default=default_env("LLM_API_KEY", "OPENAI_API_KEY"),
        help="LLM API key（默认读 LLM_API_KEY / OPENAI_API_KEY）",
    )
    parser.add_argument(
        "--base-url",
        default=default_env("LLM_BASE_URL", "OPENAI_BASE_URL"),
        help="OpenAI 兼容接口地址（默认读 LLM_BASE_URL / OPENAI_BASE_URL）",
    )
    parser.add_argument(
        "--model",
        default=default_env("LLM_MODEL", "OPENAI_MODEL"),
        help="模型名（默认读 LLM_MODEL / OPENAI_MODEL）",
    )
    parser.add_argument("--timeout", type=int, default=90, help="LLM 请求超时秒数")
    parser.add_argument("--max-tokens", type=int, default=16000, help="LLM 最大输出 token")
    parser.add_argument(
        "--fail-on-llm-error",
        action="store_true",
        help="LLM 过滤失败时以非零状态退出（默认回退为全部热门仓库）",
    )
    return parser.parse_args(argv)


def write_output(text, output):
    text = text.rstrip() + "\n"
    if output:
        with open(output, "w", encoding="utf-8") as file:
            file.write(text)
        print(f"已写入 {output}", file=sys.stderr)
    else:
        sys.stdout.write(text)


def main(argv=None):
    args = parse_args(argv)
    api_key = (args.api_key or "").strip()
    base_url = (args.base_url or "").strip()
    model = (args.model or "").strip()

    use_llm = not args.no_llm and bool(api_key and base_url and model)
    if not args.no_llm and not use_llm:
        print(
            "未提供完整的 LLM 配置（LLM_API_KEY / LLM_BASE_URL / LLM_MODEL），跳过 AI 过滤。",
            file=sys.stderr,
        )

    print("抓取 GitHub Trending（每日）...", file=sys.stderr)
    try:
        daily_all = fetch_trending(DAILY_URL)
        print(f"  每日: {len(daily_all)} 个仓库", file=sys.stderr)

        print("抓取 GitHub Trending（每周）...", file=sys.stderr)
        weekly_all = fetch_trending(WEEKLY_URL)
        print(f"  每周: {len(weekly_all)} 个仓库", file=sys.stderr)
    except Exception as exc:
        print(f"抓取失败: {exc}", file=sys.stderr)
        return 1

    daily_pool, weekly_pool = daily_all, weekly_all
    llm_filtered = False

    if use_llm:
        print("LLM 过滤 AI 项目...", file=sys.stderr)
        try:
            daily_pool, weekly_pool = llm_filter_both(
                daily_all,
                weekly_all,
                api_key,
                base_url,
                model,
                timeout=args.timeout,
                max_tokens=args.max_tokens,
            )
            llm_filtered = True
            print(
                f"  LLM 过滤: 每日 {len(daily_pool)} 个, 每周 {len(weekly_pool)} 个",
                file=sys.stderr,
            )
        except Exception as exc:
            print(f"LLM 过滤失败: {exc}", file=sys.stderr)
            if args.fail_on_llm_error:
                return 2
            print("  回退为全部热门仓库", file=sys.stderr)

    daily, daily_period = rank_items(daily_pool, args.top_daily)
    weekly, weekly_period = rank_items(weekly_pool, args.top_weekly)

    fallback = False
    if not daily and not weekly:
        print("未找到 AI 项目，回退为全部热门仓库", file=sys.stderr)
        daily, daily_period = rank_items(daily_all, args.top_daily)
        weekly, weekly_period = rank_items(weekly_all, args.top_weekly)
        fallback = True

    if args.format == "json":
        text = render_json(
            daily, weekly, daily_period, weekly_period, llm_filtered, fallback
        )
    else:
        now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        text = render_markdown(
            daily,
            weekly,
            daily_period,
            weekly_period,
            args.top_daily,
            args.top_weekly,
            now,
        )

    write_output(text, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
