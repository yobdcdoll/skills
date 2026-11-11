#!/usr/bin/env python3
"""
Hacker News 每日早报。

抓取 Hacker News -> 可选 LLM 生成中文解读 -> 输出 Markdown 或 JSON。

脚本只负责取数和整理，不包含任何发送逻辑，也不读取 OpenClaw 配置；
发到哪个渠道、发给谁，由调用方（OpenClaw 或其他 agent）决定。

用法:
    python3 hackernews_daily.py
    python3 hackernews_daily.py --format json
    python3 hackernews_daily.py --output /tmp/hn.md
    LLM_API_KEY=... LLM_BASE_URL=... LLM_MODEL=... \
        python3 hackernews_daily.py

环境变量:
    LLM_API_KEY   OpenAI 兼容接口的 API key；三项齐全时才启用 AI 解读
    LLM_BASE_URL  接口地址，例如 https://api.openai.com/v1
    LLM_MODEL     模型名，例如 gpt-4o-mini
    OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL  作为 LLM_* 的回退
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import requests

TZ_BEIJING = timezone(timedelta(hours=8))
HN_ITEM_URL = "https://news.ycombinator.com/item?id={object_id}"
SOURCE_URL = "https://news.ycombinator.com"

DEFAULT_TODAY = 10
DEFAULT_WEEKLY = 15


def fetch_hn_today(limit=20):
    """抓取今日 HN Top（北京时间当天）。"""
    url = "https://hn.algolia.com/api/v1/search"
    resp = requests.get(
        url, params={"tags": "front_page", "hitsPerPage": limit}, timeout=30
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", [])

    now_bj = datetime.now(TZ_BEIJING)
    today_start = now_bj.replace(hour=0, minute=0, second=0, microsecond=0)

    items = []
    for hit in hits:
        created_at = hit.get("created_at", "")
        if not created_at:
            continue
        moment = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(
            TZ_BEIJING
        )
        if moment >= today_start:
            object_id = hit.get("objectID", "")
            items.append(
                {
                    "title": hit.get("title", ""),
                    "url": hit.get("url", "") or HN_ITEM_URL.format(object_id=object_id),
                    "points": hit.get("points", 0),
                    "author": hit.get("author", ""),
                    "created_at": moment.strftime("%Y-%m-%d %H:%M"),
                    "object_id": object_id,
                }
            )

    return sorted(items, key=lambda item: -item["points"])


def fetch_hn_weekly(limit=50):
    """抓取本周 HN Top（最近 7 天）。"""
    now_bj = datetime.now(TZ_BEIJING)
    week_ago_ts = int((now_bj - timedelta(days=7)).timestamp())

    url = "https://hn.algolia.com/api/v1/search"
    resp = requests.get(
        url,
        params={
            "tags": "front_page",
            "hitsPerPage": limit,
            "numericFilters": f"created_at_i>{week_ago_ts}",
        },
        timeout=30,
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", [])

    items = []
    for hit in hits:
        created_at = hit.get("created_at", "")
        if not created_at:
            continue
        moment = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(
            TZ_BEIJING
        )
        object_id = hit.get("objectID", "")
        items.append(
            {
                "title": hit.get("title", ""),
                "url": hit.get("url", "") or HN_ITEM_URL.format(object_id=object_id),
                "points": hit.get("points", 0),
                "author": hit.get("author", ""),
                "created_at": moment.strftime("%Y-%m-%d %H:%M"),
                "object_id": object_id,
            }
        )

    return sorted(items, key=lambda item: -item["points"])


def extract_json_from_response(raw):
    """从 LLM 响应中提取 JSON，容忍 think 标签和 markdown 代码围栏。"""
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)

    json_start = cleaned.find("{")
    if json_start == -1:
        raise ValueError("响应中没有 JSON 对象: " + repr(raw[:200]))

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


def llm_call(prompt, api_key, base_url, model, retries=3, retry_delay=5, max_tokens=8000, timeout=120):
    """调用 LLM 一次（带重试），返回清洗后的文本；失败返回 None。"""
    system_prompt = (
        "You are a tech news curator. Output ONLY valid JSON. "
        "Do NOT use <think> or </think> tags. Do NOT use markdown fences."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }
    if "minimax" in model.lower():
        payload["skip"] = ["think"]

    api_url = base_url.rstrip("/") + "/chat/completions"

    import time

    last_error = None
    for attempt in range(1, retries + 1):
        if attempt > 1:
            print(
                f"   LLM 调用失败，{retry_delay}s 后重试 ({attempt}/{retries})...",
                file=sys.stderr,
            )
            time.sleep(retry_delay)
        try:
            resp = requests.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            if not raw:
                raise ValueError("LLM 返回了空内容")

            cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            if cleaned.startswith("```"):
                for part in cleaned.split("```"):
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("[") or part.startswith("{"):
                        cleaned = part
                        break
            return cleaned
        except Exception as exc:
            last_error = exc
            print(f"LLM call failed (attempt {attempt}): {exc}", file=sys.stderr)

    print(f"LLM call failed after {retries} attempts: {last_error}", file=sys.stderr)
    return None


def parse_desc_list(raw):
    """把 LLM 输出解析成 [{'desc': ...}]，容忍 JSON 被截断。"""
    if not raw:
        return None

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, list):
                    data = value
                    break
        if isinstance(data, list):
            out = []
            for item in data:
                if isinstance(item, dict):
                    out.append({"desc": item.get("desc", "")})
                elif isinstance(item, str):
                    out.append({"desc": item})
            if out:
                return out
    except Exception:
        pass

    salvaged = []
    for match in re.finditer(r'\{\s*"desc"\s*:\s*"(?:[^"\\]|\\.)*"\s*\}', raw):
        try:
            salvaged.append(json.loads(match.group(0)))
        except Exception:
            pass
    if salvaged:
        print(
            f"   ⚠️ JSON 被截断，已抢救出 {len(salvaged)} 条完整解读",
            file=sys.stderr,
        )
        return salvaged

    return None


def llm_summarize_section(
    items,
    section_name,
    api_key,
    base_url,
    model,
    retries=3,
    retry_delay=5,
    max_tokens=8000,
    timeout=120,
):
    """对单个板块生成中文解读，输出扁平 JSON 数组；失败返回 None。"""
    if not items:
        return []

    lines = []
    for index, item in enumerate(items, 1):
        lines.append(
            f"{index}. {item['title']} | {item['url']} | "
            f"{item['points']} pts | {item['author']} | {item['created_at']}"
        )

    prompt = f"""以下是从 Hacker News 抓取的{section_name}，请为每条生成约100字的中文解读，说明该新闻的背景、意义或值得关注的点。

{chr(10).join(lines)}

Output ONLY a valid JSON array, 条目顺序与上面一一对应，格式如下（不要输出任何其他内容）：
[
  {{"desc": "第1条的中文解读，约100字"}},
  {{"desc": "第2条的中文解读，约100字"}}
]
"""
    raw = llm_call(
        prompt,
        api_key,
        base_url,
        model,
        retries,
        retry_delay,
        max_tokens,
        timeout,
    )
    return parse_desc_list(raw)


def fmt_item(item, index, desc):
    lines = [
        f"**{index}.** [{item['title']}]({item['url']})",
        f"   🔥 {item['points']} pts · 👤 {item['author']} · 🕐 {item['created_at']}",
    ]
    if desc:
        lines.append(f"   💬 {desc}")
    return "\n".join(lines)


def render_markdown(today, weekly, today_desc, weekly_desc, summary_attempted, summary_failed):
    now_bj = datetime.now(TZ_BEIJING)
    date_text = now_bj.strftime("%Y年%m月%d日")

    parts = []
    if summary_attempted and summary_failed:
        parts += ["⚠️ 本次 AI 解读生成失败，以下仅展示标题与链接。", "", "---", ""]

    parts.append(f"📰 **Hacker News 今日 Top**（{date_text}）")
    parts.append("")
    if today:
        blocks = []
        for index, item in enumerate(today, 1):
            desc = ""
            if today_desc and index <= len(today_desc):
                desc = today_desc[index - 1].get("desc", "")
            blocks.append(fmt_item(item, index, desc))
        parts.append("\n\n─────────\n\n".join(blocks))
    else:
        parts.append("_今日暂无新增热门条目_")

    parts += ["", "---", "", "📊 **本周 HN Top**", ""]
    if weekly:
        blocks = []
        for index, item in enumerate(weekly, 1):
            desc = ""
            if weekly_desc and index <= len(weekly_desc):
                desc = weekly_desc[index - 1].get("desc", "")
            blocks.append(fmt_item(item, index, desc))
        parts.append("\n\n─────────\n\n".join(blocks))
    else:
        parts.append("_本周暂无热门条目_")

    parts += ["", "---", "", "数据来源：news.ycombinator.com"]
    return "\n".join(parts)


def render_json(today, weekly, today_desc, weekly_desc, summary_generated, summary_attempted):
    def merge(items, descs):
        merged = []
        for index, item in enumerate(items):
            entry = dict(item)
            entry["desc"] = (
                descs[index].get("desc", "")
                if descs and index < len(descs)
                else ""
            )
            merged.append(entry)
        return merged

    return json.dumps(
        {
            "generated_at": datetime.now(TZ_BEIJING).isoformat(timespec="seconds"),
            "source": SOURCE_URL,
            "summary_attempted": summary_attempted,
            "summary_generated": summary_generated,
            "today": merge(today, today_desc),
            "weekly": merge(weekly, weekly_desc),
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
        description="抓取 Hacker News 并输出中文早报（不发送）"
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="输出格式（默认 markdown）",
    )
    parser.add_argument("--output", help="输出文件路径；不指定则写到 stdout")
    parser.add_argument(
        "--today-limit", type=int, default=DEFAULT_TODAY, help="今日条目数（默认 10）"
    )
    parser.add_argument(
        "--weekly-limit", type=int, default=DEFAULT_WEEKLY, help="本周条目数（默认 15）"
    )
    parser.add_argument(
        "--fetch-today", type=int, default=20, help="今日抓取条数（默认 20）"
    )
    parser.add_argument(
        "--fetch-weekly", type=int, default=50, help="本周抓取条数（默认 50）"
    )
    parser.add_argument("--no-llm", action="store_true", help="跳过 LLM 解读")
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
    parser.add_argument("--timeout", type=int, default=120, help="LLM 请求超时秒数")
    parser.add_argument("--max-tokens", type=int, default=8000, help="LLM 最大输出 token")
    parser.add_argument(
        "--fail-on-llm-error",
        action="store_true",
        help="LLM 解读失败时以非零状态退出（默认仅省略解读）",
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
            "未提供完整的 LLM 配置（LLM_API_KEY / LLM_BASE_URL / LLM_MODEL），跳过 AI 解读。",
            file=sys.stderr,
        )

    print("抓取 Hacker News 今日 Top...", file=sys.stderr)
    try:
        today_all = fetch_hn_today(args.fetch_today)
        print(f"  今日: {len(today_all)} 条", file=sys.stderr)

        print("抓取 Hacker News 本周 Top...", file=sys.stderr)
        weekly_all = fetch_hn_weekly(args.fetch_weekly)
        print(f"  本周: {len(weekly_all)} 条", file=sys.stderr)
    except Exception as exc:
        print(f"抓取失败: {exc}", file=sys.stderr)
        return 1

    today = today_all[: args.today_limit]
    weekly = weekly_all[: args.weekly_limit]

    today_desc = []
    weekly_desc = []
    summary_attempted = use_llm
    summary_failed = False

    if use_llm:
        print("LLM 生成中文解读（今日 / 本周分别调用）...", file=sys.stderr)
        today_desc = llm_summarize_section(
            today,
            "今日 Top 新闻",
            api_key,
            base_url,
            model,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
        )
        weekly_desc = llm_summarize_section(
            weekly,
            "本周 Top 新闻",
            api_key,
            base_url,
            model,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
        )

        if today_desc is None:
            today_desc = []
        if weekly_desc is None:
            weekly_desc = []

        summary_failed = not today_desc and not weekly_desc
        print(
            f"  今日解读: {len(today_desc)} 条, 本周解读: {len(weekly_desc)} 条",
            file=sys.stderr,
        )
        if summary_failed:
            print("  ⚠️ 解读生成失败，仅输出标题与链接", file=sys.stderr)
            if args.fail_on_llm_error:
                return 2
        elif len(today_desc) < len(today) or len(weekly_desc) < len(weekly):
            print("  ⚠️ 部分解读缺失，已输出已有部分", file=sys.stderr)

    summary_generated = bool(today_desc or weekly_desc)

    if args.format == "json":
        text = render_json(
            today,
            weekly,
            today_desc,
            weekly_desc,
            summary_generated,
            summary_attempted,
        )
    else:
        text = render_markdown(
            today,
            weekly,
            today_desc,
            weekly_desc,
            summary_attempted,
            summary_failed,
        )

    write_output(text, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
