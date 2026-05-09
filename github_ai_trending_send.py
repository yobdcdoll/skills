#!/usr/bin/env python3
"""
GitHub AI Trending 日报 - 飞书卡片发送脚本（Markdown版本）
"""
import json
import sys
import subprocess
import argparse
from datetime import datetime


def get_config():
    with open("/root/.openclaw/openclaw.json") as f:
        return json.load(f)


def get_token(app_id, app_secret):
    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"app_id": app_id, "app_secret": app_secret})
    ], capture_output=True, text=True)
    resp = json.loads(result.stdout)
    return resp["tenant_access_token"]


def build_card(daily_items, weekly_items):
    """构建飞书互动卡片（Markdown 表格）"""

    def make_md_table(title, items):
        header = f"**{title}**\n\n"
        rows = []
        for i, item in enumerate(items, 1):
            name = f'[{item["project"]}]({item["url"]})'
            desc = item["desc"][:80] + "..." if len(item["desc"]) > 80 else item["desc"]
            rows.append(f"| {i} | {name} | ⭐ {item['stars']} | {desc} |")
        col_header = "| # | 项目 | Stars | 简介 |"
        col_sep = "|---|---|---|---|"
        return header + col_header + "\n" + col_sep + "\n" + "\n".join(rows)

    elements = [
        {"tag": "markdown", "content": "## 📈 GitHub AI Trending 日报"},
        {"tag": "markdown", "content": f"📅 {datetime.now().strftime('%Y-%m-%d')}"},
        {"tag": "hr"},
        {"tag": "markdown", "content": "### 🎯 今日热门 AI 项目 Top5"},
        {"tag": "markdown", "content": make_md_table("今日 Top5", daily_items)},
        {"tag": "hr"},
        {"tag": "markdown", "content": "### 📊 本周热门 AI 项目 Top10"},
        {"tag": "markdown", "content": make_md_table("本周 Top10", weekly_items)},
    ]

    return {
        "msg_type": "interactive",
        "content": json.dumps({
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "📈 GitHub AI Trending 日报"},
                "template": "blue"
            },
            "elements": elements
        }, ensure_ascii=False)
    }


def send_card(token, receive_id, card_content):
    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
        "-H", f"Authorization: Bearer {token}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": card_content
        })
    ], capture_output=True, text=True)
    resp = json.loads(result.stdout)
    if resp.get("code") != 0:
        print(f"发送失败: {resp}", file=sys.stderr)
        sys.exit(1)
    print("发送成功！")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="发送 GitHub AI Trending 飞书卡片")
    parser.add_argument("--daily", required=True)
    parser.add_argument("--weekly", required=True)
    args = parser.parse_args()

    config = get_config()
    feishu = config["channels"]["feishu"]
    app_id = feishu["appId"]
    app_secret = feishu["appSecret"]
    receive_id = "<FEISHU_OPEN_ID>"

    daily_items = json.loads(args.daily)
    weekly_items = json.loads(args.weekly)

    token = get_token(app_id, app_secret)
    card = build_card(daily_items, weekly_items)
    send_card(token, receive_id, card["content"])
