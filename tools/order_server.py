#!/usr/bin/env python3
"""麦麦猫点餐事件桥 —— 本地小服务（仅标准库）。

作用：Codex 里用麦当劳 MCP 点单成功后，order_hook.py 把订单推到这里，
浏览器里打开的麦麦猫（http://127.0.0.1:8787/）会在 2 秒内收到事件：
猫跑过来吃你点的那道菜 + 弹卡路里/价格提示 + 吃完睡午觉。

接口：
    GET  /                    → 麦麦猫网页（index.html + assets 静态托管）
    POST /api/order           → JSON {name, code?, price?, kcal?, type?} 推送点单事件
    GET  /api/events?after=N  → 拉取 id > N 的事件（网页每 2s 轮询）

断线兜底：服务没开时 order_hook 会把订单落盘到
    ~/.codex/pets/mcd-maimai/orders_pending.jsonl
本服务启动时自动读取补发，然后清空该文件 —— 订单永不丢。

用法：
    python tools/order_server.py           # 启动（默认端口 8787）
    python tools/order_server.py --port 9000
    python tools/order_server.py --open    # 启动并打开浏览器
"""

import argparse
import json
import os
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PENDING = os.path.join(os.path.expanduser("~/.codex/pets/mcd-maimai"), "orders_pending.jsonl")
MAX_EVENTS = 50          # 内存里只保留最近 50 条
MAX_AGE_S = 3600         # 且只保留 1 小时内的事件（防止新开页面重放一整天的订单）

_lock = threading.Lock()
_events = []      # [{id(ms时间戳), ts, name, code, price, kcal, type}]
_seq = 0


def _new_id():
    global _seq
    _seq += 1
    return int(time.time() * 1000) * 100 + _seq % 100


def _prune():
    """按数量与时间双重裁剪（调用方需持有 _lock）。"""
    global _events
    cutoff = (time.time() - MAX_AGE_S) * 1000 * 100
    _events = [e for e in _events if e["id"] >= cutoff][-MAX_EVENTS:]


def load_pending():
    """把 hook 断线期间落盘的订单补进事件队列。"""
    if not os.path.isfile(PENDING):
        return 0
    n = 0
    try:
        with open(PENDING, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                e["id"] = _new_id()
                e.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
                e["replayed"] = True
                with _lock:
                    _events.append(e)
                n += 1
        os.remove(PENDING)
    except OSError:
        pass
    return n


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):  # 静默静态资源日志
        if "/api/" in (args[0] if args else ""):
            sys.stderr.write("[order_server] %s\n" % (fmt % args))

    # ---- API ----
    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/events":
            after = int(parse_qs(u.query).get("after", ["0"])[0])
            with _lock:
                evs = [e for e in _events if e["id"] > after]
            self._json({"events": evs})
            return
        if u.path == "/api/ping":
            self._json({"ok": True, "events": len(_events)})
            return
        super().do_GET()

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/order":
            self._json({"ok": False, "error": "unknown endpoint"}, 404)
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json({"ok": False, "error": "bad json"}, 400)
            return
        if not str(data.get("name", "")).strip():
            self._json({"ok": False, "error": "name required"}, 400)
            return
        e = {"id": _new_id(), "ts": datetime.now().isoformat(timespec="seconds"),
             "name": data.get("name"), "code": str(data.get("code", "")),
             "price": float(data.get("price", 0) or 0),
             "kcal": float(data.get("kcal", 0) or 0),
             "type": data.get("type", "eat")}
        with _lock:
            _events.append(e)
            _prune()
        print(f"[order_server] + 订单: {e['name']} ¥{e['price']} {e['kcal']}kcal")
        self._json({"ok": True, "id": e["id"]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--open", action="store_true", help="启动后打开浏览器")
    args = ap.parse_args()

    n = load_pending()
    if n:
        print(f"[order_server] 补发离线订单 {n} 条")

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"[order_server] 麦麦猫在线：{url}  （Ctrl+C 停止）")
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[order_server] bye")


if __name__ == "__main__":
    main()
