#!/usr/bin/env python3
"""Codex 点单钩子 —— 麦当劳 MCP 下单成功后由 Agent 调用，把订单推给麦麦猫。

用法（name 或 code 至少给一个，给 code 时自动查 menu_map.json 补全价格/热量）：
    python tools/order_hook.py --code 1100
    python tools/order_hook.py --name "麦辣鸡腿汉堡" --price 22.5 --kcal 570
    python tools/order_hook.py --name "可口可乐" --type drink

行为：
  1. 优先 POST 到本地点餐桥 http://127.0.0.1:8787/api/order（order_server.py）
  2. 服务没开 → 落盘到 ~/.codex/pets/mcd-maimai/orders_pending.jsonl，
     下次 order_server 启动时自动补发。订单永不丢。
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MENU_MAP = os.path.join(ROOT, "menu_map.json")
PENDING = os.path.join(os.path.expanduser("~/.codex/pets/mcd-maimai"), "orders_pending.jsonl")
SERVER = "http://127.0.0.1:8787/api/order"


def lookup(code=None, name=None):
    """从 menu_map.json 补全菜单信息。"""
    try:
        mm = json.load(open(MENU_MAP, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    for m in mm.get("mappings", []):
        if code and m.get("code") == str(code):
            return m
        if name and m.get("name") == name:
            return m
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", help="餐品名（如 巨无霸）")
    ap.add_argument("--code", help="商品编码（如 1100）")
    ap.add_argument("--price", type=float)
    ap.add_argument("--kcal", type=float)
    ap.add_argument("--type", choices=["eat", "drink"], default="eat")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()

    m = lookup(code=args.code, name=args.name)
    name = args.name or m.get("name") or ""
    if not name:
        print("✗ 需要 --name 或 --code（且能在 menu_map.json 命中）")
        sys.exit(1)
    payload = {
        "name": name,
        "code": str(args.code or m.get("code", "")),
        "price": args.price if args.price is not None else float(m.get("price", 0)),
        "kcal": args.kcal if args.kcal is not None else float(m.get("kcal", 0)),
        "type": args.type if args.type != "eat" else m.get("type", "eat"),
    }

    req = urllib.request.Request(
        SERVER.replace("8787", str(args.port)),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            resp = json.loads(r.read().decode("utf-8"))
        print(f"✓ 已推送给麦麦猫（事件 #{resp.get('id')}）：{name} ¥{payload['price']}")
    except Exception:
        os.makedirs(os.path.dirname(PENDING), exist_ok=True)
        with open(PENDING, "a", encoding="utf-8") as f:
            f.write(json.dumps({**payload, "ts": datetime.now().isoformat(timespec="seconds")},
                               ensure_ascii=False) + "\n")
        print(f"! 点餐桥未启动，订单已暂存待补发：{name}（启动 order_server.py 后生效）")


if __name__ == "__main__":
    main()
