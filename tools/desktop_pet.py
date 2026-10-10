#!/usr/bin/env python3
"""麦麦猫 · 桌面悬浮桌宠（tkinter 版，不依赖 WebView2，稳定不白屏）。

WorkBuddy 悬浮窗版与 Codex 桌宠版共用本程序（同一套资产/状态机/交互），
位置持久化在 ~/.codex/pets/mcd-maimai/，两边体验完全一致。

交互（与网页版 index.html 完全统一）：
  - 单击小猫        → 猫左右两侧弹出「🍗 投喂」「💤 睡觉」按钮
  - 点「投喂」      → 猫下方展开 12 道餐品真实图案托盘，点图案即投喂
  - 选择餐品        → 播放吃对应食物动画（食物贴嘴、越吃越小），
                      吃完自动满足→打盹→恢复休闲；底部框显示本次+累计 kcal/金额
  - 点「睡觉」      → 打呼睡觉（Zzz），再点小猫或双击叫醒
  - 双击小猫        → 手动切换状态：静坐→走来走去→扑向你→休息
  - 无人操作        → 自动循环同上（休闲状态自动切换）
  - MCP 点餐联动    → Codex/WorkBuddy 用麦当劳 MCP 下单后 order_hook.py 推送，
                      本桌宠轮询 127.0.0.1:8787/api/events，自动识别餐品开吃并记账

文字可读性（用户规范 2026-10-10 v2）：
  - 顶部框：只在有动作时出现（切换状态/投喂/MCP 来单的临时消息），
    框宽随文字自适应；休闲状态下不显示，只留猫本体
  - 底部框：只在投喂后出现（本次+累计 kcal/金额），回休闲几秒后自动隐藏
  - 顶部/底部框与猫的间距一致（BOX_GAP），字体一致（Microsoft YaHei 10 bold）

数据真实性：餐品名/编码/价格来自 MCP query-meals（menu_map.json），
热量来自 MCP list-nutrition-foods 官方营养表，严禁捏造。

技术：
  - tkinter + PIL(ImageTk)：PIL 负责帧合成（翻面/胖度缩放/食物叠加），
    tkinter 负责透明置顶窗（transparentcolor）；所有 UI 元素画在 Canvas 上
  - 用系统 Python 3.11 运行（托管 3.13 未编译 tkinter）：
      C:\\Users\\<user>\\AppData\\Local\\Programs\\Python\\Python311\\python.exe
  - 单实例：独占 127.0.0.1:8799

用法：
    python tools/desktop_pet.py                 # 启动桌面悬浮桌宠
    python tools/desktop_pet.py --x 900 --y 500 # 指定初始位置
    python tools/desktop_pet.py --selftest out.json  # 渲染+投喂自检后退出
"""

import argparse
import json
import os
import queue
import socket
import sys
import threading
import time
import urllib.request
import urllib.error

from PIL import Image, ImageTk, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PET_HOME = os.path.join(os.path.expanduser("~"), ".codex", "pets", "mcd-maimai")
POS_FILE = os.path.join(PET_HOME, "desktop_pet_pos.json")
MENU_FILE = os.path.join(ROOT, "menu_map.json")

CELL_W, CELL_H = 192, 208
CANVAS_W, CANVAS_H = 360, 424
CAT_BOTTOM = 252                     # 猫脚站的 y
CAT_SCALE = 0.82
MAGIC = "#010203"                    # 透明键色
LOCK_PORT = 8799
BRIDGE = "http://127.0.0.1:8787"

# ---- 文字规范（顶部/底部统一）----
BOX_W = 328                          # 两个框同宽
BOX_H = 26                           # 同高
BOX_GAP = 14                         # 框与猫的垂直间距（上/下一致）
FONT_TXT = ("Microsoft YaHei", 10, "bold")
COL_BOX_FILL = "#14102a"             # 黑底
COL_BOX_LINE = "#ffb84d"             # 金色描边
COL_TXT = "#ffffff"                  # 白字

SHORT_NAME = {
    "麦辣鸡腿汉堡": "麦辣堡", "板烧鸡腿堡": "板烧堡", "双层吉士汉堡": "吉士堡",
    "经典麦旋风": "麦旋风", "圆筒冰淇淋": "圆筒", "麦咖啡™奶铁": "奶铁",
}

FRAME_COUNTS = {
    "idle": 6, "eating": 6, "drinking": 5, "happy": 5, "sleeping": 6,
    "waving": 4, "jumping": 5, "running": 5, "waiting": 5, "review": 5, "failed": 6,
}
STATES = {
    "idle":     {"fps": 5, "label": "静坐发呆"},
    "eating":   {"fps": 6, "label": "干饭中", "overlay": (0.58, 0.50, 64)},   # 嘴部锚点
    "drinking": {"fps": 6, "label": "喝东西", "overlay": (0.58, 0.48, 58)},
    "happy":    {"fps": 6, "label": "满足"},
    "sleeping": {"fps": 4, "label": "打呼睡觉", "zzz": True},
    "waving":   {"fps": 6, "label": "招手"},
    "jumping":  {"fps": 7, "label": "扑向你"},
    "running":  {"fps": 8, "label": "走来走去", "walk": True},
    "waiting":  {"fps": 5, "label": "眼巴巴"},
    "review":   {"fps": 5, "label": "歪头打量"},
    "failed":   {"fps": 5, "label": "委屈"},
}
ASSET_STATES = {"idle", "eating", "drinking", "happy", "sleeping"}   # assets/frames，其余 run-codex/frames
CYCLE = ["sit", "walk", "pounce", "rest"]


def frame_dir(state):
    sub = "assets/frames" if state in ASSET_STATES else "run-codex/frames"
    return os.path.join(ROOT, sub, state)


def load_frames():
    frames = {}
    for st, n in FRAME_COUNTS.items():
        lst = []
        d = frame_dir(st)
        for i in range(n):
            p = os.path.join(d, "f%02d.png" % i)
            if os.path.exists(p):
                try:
                    lst.append(Image.open(p).convert("RGBA"))
                except OSError:
                    pass
        frames[st] = lst
    return frames


def load_menu():
    try:
        with open(MENU_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return [{
            "id": v.get("food") or v.get("code"),
            "code": str(v.get("code") or ""),
            "name": v.get("name", ""),
            "emo": v.get("emo", "🍽️"),
            "kcal": v.get("kcal", 0),
            "price": v.get("price", 0),
            "type": v.get("type", "eat"),
        } for v in d.get("mappings", [])]
    except (OSError, ValueError):
        return []


def load_food_images(menu):
    imgs = {}
    for m in menu:
        p = os.path.join(ROOT, "assets", "food", "%s.png" % m["id"])
        if os.path.exists(p):
            try:
                imgs[m["id"]] = Image.open(p).convert("RGBA")
            except OSError:
                pass
    return imgs


def load_pos(default=(120, 120)):
    try:
        with open(POS_FILE, encoding="utf-8") as f:
            d = json.load(f)
            return int(d.get("x", default[0])), int(d.get("y", default[1]))
    except (OSError, ValueError):
        return default


def save_pos(x, y):
    try:
        os.makedirs(PET_HOME, exist_ok=True)
        with open(POS_FILE, "w", encoding="utf-8") as f:
            json.dump({"x": int(x), "y": int(y)}, f)
    except OSError:
        pass


def acquire_singleton():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        s.listen(1)
        return s
    except OSError:
        s.close()
        return None


# ---------------- 桌宠本体 ----------------
class McdPet:
    def __init__(self, root, x, y):
        import tkinter as tk
        import tkinter.font as tkfont

        self.tk = tk
        self.root = root
        self.menu_list = load_menu()
        self.frames = load_frames()
        self.food_imgs = load_food_images(self.menu_list)
        self.avail = {st: bool(fs) for st, fs in self.frames.items()}

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", MAGIC)
        self.root.resizable(False, False)
        self.root.geometry("+%d+%d" % (x, y))
        self.root.configure(bg=MAGIC)

        self.canvas = tk.Canvas(root, width=CANVAS_W, height=CANVAS_H,
                                bg=MAGIC, highlightthickness=0, bd=0)
        self.canvas.pack()

        # 状态
        self.cur = "idle"
        self.fi = 0
        self.ft = 0.0
        self.eat_tick = 0
        self.facing = 1
        self.px = 0.5                     # 0..1 舞台水平位置
        self.walk_target = None
        self.overlay_food = None
        self.seq_timer = None
        self.user_hold = False
        self.cycle_idx = 0
        self.auto_idx = 0
        self.ambient_after = None
        self.stats = {"kcal": 0, "cost": 0.0, "meals": 0, "fat": 0.0, "log": []}
        self.last_meal = None             # 本次投喂 {"name","kcal","price"}
        self.botbox_visible = False       # 底部记账框：投喂后才出现
        self._botbox_hide_after = None
        self.zzz = []                     # [x, y, alpha, size, canvas_id]
        self.top_msg = None               # 顶部框临时消息（None=不显示）
        self.bubble_timer = None
        self._click_after = None
        self._font = tkfont.Font(font=FONT_TXT)   # 用于测量文字宽度，框宽自适应
        self._photo = None
        self._tray_photos = {}            # PhotoImage 引用防回收
        self._drag_off = None
        self._press_pos = None

        # 事件
        c = self.canvas
        c.bind("<Button-1>", self.on_press)
        c.bind("<B1-Motion>", self.on_drag)
        c.bind("<ButtonRelease-1>", self.on_release)
        c.bind("<Double-Button-1>", self.on_double)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        # MCP 点餐轮询
        self.evt_queue = queue.Queue()
        self.last_evt_id = 0
        self.evt_booted = False
        threading.Thread(target=self.poll_events, daemon=True).start()
        self.root.after(200, self.drain_events)

        self.set_state("idle")
        self.schedule_ambient(6000)
        self.bubble("单击我开饭 · 双击换动作", 3200)
        self.refresh_topbox()
        self.refresh_botbox()
        self.tick()

    # ---------- 几何 ----------
    def cat_top(self):
        fat = min(self.stats["fat"], 6)
        dh = CELL_H * (1 + fat * 0.018) * CAT_SCALE
        return CAT_BOTTOM - dh

    def cat_cx(self):
        fat = min(self.stats["fat"], 6)
        dw = CELL_W * (1 + fat * 0.045) * CAT_SCALE
        return self.px * (CANVAS_W - dw) + dw / 2

    # ---------- 圆角框 ----------
    def _rrect(self, x1, y1, x2, y2, r, tags, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.canvas.create_polygon(pts, smooth=True, tags=tags, **kw)

    # ---------- 状态机 ----------
    def set_state(self, st):
        if not self.avail.get(st):
            st = "idle"
        self.clear_seq()
        self.cur = st
        self.fi = 0
        self.ft = 0.0
        self.eat_tick = 0
        self.walk_target = None
        self.refresh_topbox()

    def clear_seq(self):
        if self.seq_timer:
            try:
                self.root.after_cancel(self.seq_timer)
            except Exception:
                pass
            self.seq_timer = None

    def play_for(self, st, dur, done):
        self.set_state(st)
        self.seq_timer = self.root.after(int(dur * 1000), done)

    def run_cycle_step(self, manual):
        """manual=True（双击/按钮）才出顶部文字；自动闲逛保持安静，休闲时只留猫。"""
        step = CYCLE[self.cycle_idx]
        if step == "sit":
            self.set_state("idle")
            if manual:
                self.bubble("（安静坐好）")
                self.hold_then_release(3)
        elif step == "walk" and self.avail.get("running"):
            self.walk_target = self.px + 0.30 if self.px < 0.5 else self.px - 0.30
            self.walk_target = min(max(self.walk_target, 0.08), 0.92)
            self.set_state("running")
            if manual:
                self.bubble("溜达溜达~", 1500)
                self.hold_then_release(6)
        elif step == "pounce" and self.avail.get("jumping"):
            self.set_state("jumping")
            if manual:
                self.bubble("噗！扑向你~", 1500)
                self.hold_then_release(4)
            self.play_for("jumping", 1.8, lambda: self.set_state("idle") if not self.user_hold else None)
        elif step == "rest":
            self.nap(8 if manual else 5, "Zzz… 休息一下" if manual else "")
        else:
            self.set_state("idle")
            self.user_hold = False
            self.schedule_ambient(4000)

    def hold_then_release(self, sec):
        def _rel():
            if self.cur == "idle":
                self.user_hold = False
                self.schedule_ambient(5000)
        self.root.after(int(sec * 1000), _rel)

    def schedule_ambient(self, ms=None):
        if self.ambient_after:
            try:
                self.root.after_cancel(self.ambient_after)
            except Exception:
                pass
        self.ambient_after = self.root.after(ms or int(6000 + (time.time() * 1000) % 7000),
                                             self.do_ambient)

    def do_ambient(self):
        if self.user_hold or self.cur != "idle":
            self.schedule_ambient(4000)
            return
        step = CYCLE[self.auto_idx % len(CYCLE)]
        self.auto_idx += 1
        if step == "sit":
            self.schedule_ambient(5000)
        else:
            self.run_cycle_step(False)
            self.schedule_ambient(9000)

    # ---------- 投喂 / 睡觉 ----------
    def feed(self, food_id, src=""):
        m = next((x for x in self.menu_list if x["id"] == food_id), None)
        if not m:
            return
        self.hide_panels(keep_hold=True)
        self.user_hold = True
        self.stats["meals"] += 1
        self.stats["kcal"] += m["kcal"]
        self.stats["cost"] += m["price"]
        self.stats["fat"] = min(6, self.stats["fat"] + (0.5 if m["type"] == "drink" else 1))
        self.stats["log"].append({"name": m["name"], "kcal": m["kcal"], "price": m["price"], "src": src})
        self.last_meal = {"name": m["name"], "kcal": m["kcal"], "price": m["price"]}
        self.overlay_food = m
        # 底部记账框：投喂后才出现，回休闲数秒后自动隐藏
        if self._botbox_hide_after:
            try:
                self.root.after_cancel(self._botbox_hide_after)
            except Exception:
                pass
            self._botbox_hide_after = None
        self.botbox_visible = True
        self.set_state("drinking" if m["type"] == "drink" else "eating")
        self.bubble("嗷呜~ %s！" % m["name"])
        self.show_meal_card(m)
        self.refresh_botbox()
        self.play_for(self.cur, 3.2, self.after_meal_rest)

    def after_meal_rest(self):
        self.overlay_food = None
        if not self.avail.get("happy"):
            self.set_state("idle")
            self.user_hold = False
            self.schedule_ambient(3000)
            return
        self.set_state("happy")
        self.bubble("吃饱了…眯一会儿", 2400)
        self.seq_timer = self.root.after(1400, lambda: self.nap(6, "Zzz… 吃饱就睡，猫生赢家"))

    def nap(self, dur, msg=""):
        if not self.avail.get("sleeping"):
            self.set_state("idle")
            self.user_hold = False
            self.schedule_ambient(3000)
            return
        self.overlay_food = None
        self.set_state("sleeping")
        if msg:
            self.bubble(msg, 2400)
        if dur > 0:
            self.seq_timer = self.root.after(int(dur * 1000), self.wake_up)

    def wake_up(self):
        if self.cur != "sleeping":
            return
        self.zzz = []
        self.user_hold = False
        if self.avail.get("happy"):
            self.play_for("happy", 1.2, lambda: self.set_state("idle"))
        else:
            self.set_state("idle")
        self.bubble("喵呜…睡饱了")
        # 回休闲后 6 秒收起底部记账框，保持画面干净
        if self._botbox_hide_after:
            try:
                self.root.after_cancel(self._botbox_hide_after)
            except Exception:
                pass
        self._botbox_hide_after = self.root.after(6000, self._hide_botbox)
        self.schedule_ambient(6000)

    # ---------- 交互：单击=侧边按钮面板 / 双击=切换状态 ----------
    def on_press(self, ev):
        self._press_pos = (ev.x_root, ev.y_root)
        self._drag_off = (ev.x_root - self.root.winfo_x(), ev.y_root - self.root.winfo_y())

    def on_drag(self, ev):
        if self._drag_off:
            self.root.geometry("+%d+%d" % (ev.x_root - self._drag_off[0],
                                           ev.y_root - self._drag_off[1]))

    def on_release(self, ev):
        moved = False
        if self._press_pos:
            moved = abs(ev.x_root - self._press_pos[0]) + abs(ev.y_root - self._press_pos[1]) > 6
        self._press_pos = None
        save_pos(self.root.winfo_x(), self.root.winfo_y())
        if moved:
            return
        self.handle_click(ev)

    def handle_click(self, ev):
        """单击命中检测：按钮 > 食物 > 猫 > 空白（收面板）。"""
        cv = self.canvas
        items = cv.find_overlapping(ev.x - 1, ev.y - 1, ev.x + 1, ev.y + 1)
        for it in reversed(items):                      # 上层元素优先
            tags = cv.gettags(it)
            if "btn-feed" in tags:
                self.toggle_tray()
                return
            if "btn-sleep" in tags:
                self.hide_panels()
                self.sleep_command()
                return
            for t in tags:
                if t.startswith("food-"):
                    self.hide_panels(keep_hold=True)
                    self.feed(t[5:])
                    return
            if "cat" in tags:
                if self.cur == "sleeping":
                    self.wake_up()
                    return
                if self._click_after:
                    try:
                        self.root.after_cancel(self._click_after)
                    except Exception:
                        pass
                self._click_after = self.root.after(280, self.toggle_side)
                return
            if "topbox" in tags or "botbox" in tags or "card" in tags:
                return                                   # 点框上不动作
        self.hide_panels()                               # 点空白收面板

    def toggle_side(self):
        self._click_after = None
        if self._side_shown():
            self.hide_panels()
            return
        self.hide_panels(keep_hold=True)
        self.user_hold = True                            # 面板打开期间暂停自动循环
        cx = self.cat_cx()
        cy = CAT_BOTTOM - 92
        cv = self.canvas
        # 左：投喂
        bx1, bx2 = int(cx - 176), int(cx - 90)
        self._rrect(bx1, cy - 17, bx2, cy + 17, 12, ("ui", "btn-feed"),
                    fill="#ffb84d", outline="#c9832a")
        cv.create_text((bx1 + bx2) / 2, cy, text="🍗 投喂", font=FONT_TXT,
                       fill="#3a2410", tags=("ui", "btn-feed"))
        # 右：睡觉
        bx1, bx2 = int(cx + 90), int(cx + 176)
        self._rrect(bx1, cy - 17, bx2, cy + 17, 12, ("ui", "btn-sleep"),
                    fill="#5ed694", outline="#2f9d67")
        cv.create_text((bx1 + bx2) / 2, cy, text="💤 睡觉", font=FONT_TXT,
                       fill="#0e3b24", tags=("ui", "btn-sleep"))
        self.bubble("想吃啥？点旁边按钮~", 1800)

    def _side_shown(self):
        return bool(self.canvas.find_withtag("btn-feed"))

    def toggle_tray(self):
        if self.canvas.find_withtag("tray"):
            self.canvas.delete("tray")
            return
        self.canvas.delete("tray")
        cv = self.canvas
        x0, y0 = (CANVAS_W - 6 * 52) / 2, 316
        # 标题行
        cv.create_text(CANVAS_W / 2, y0 - 12, text="🍗 今天吃点啥？点图案投喂（12 道真实菜单）",
                       font=("Microsoft YaHei", 9), fill="#a99fd0", tags=("tray", "tray-title"))
        for i, m in enumerate(self.menu_list):
            r, cidx = divmod(i, 6)
            cx = x0 + cidx * 52 + 26
            cy = y0 + r * 62 + 26
            tag = ("tray", "food-%s" % m["id"])
            self._rrect(cx - 24, cy - 24, cx + 24, cy + 24, 10, tag,
                        fill="#241c42", outline="#3d3168")
            im = self.food_imgs.get(m["id"])
            if im is not None:
                ph = ImageTk.PhotoImage(self._fit(im, 36))
                self._tray_photos[m["id"]] = ph
                cv.create_image(cx, cy - 2, image=ph, tags=tag)
            else:
                cv.create_text(cx, cy - 2, text=m["emo"], font=("Segoe UI Emoji", 15), tags=tag)
            nm = SHORT_NAME.get(m["name"], m["name"][:4])
            cv.create_text(cx, cy + 18, text=nm, font=("Microsoft YaHei", 8),
                           fill="#a99fd0", tags=tag)
            cv.tag_bind("food-%s" % m["id"], "<Enter>",
                        lambda e, m=m: self._tray_hint(m))
            cv.tag_bind("food-%s" % m["id"], "<Leave>",
                        lambda e: self._tray_hint(None))

    def _tray_hint(self, m):
        if not self.canvas.find_withtag("tray-title"):
            return
        txt = ("%s · %d kcal · ¥%.1f（MCP 官方数据）" % (m["name"], m["kcal"], m["price"])
               if m else "🍗 今天吃点啥？点图案投喂（12 道真实菜单）")
        self.canvas.itemconfigure("tray-title", text=txt)

    @staticmethod
    def _fit(im, box):
        w, h = im.size
        s = min(box / w, box / h)
        return im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)

    def hide_panels(self, keep_hold=False):
        if self._click_after:
            try:
                self.root.after_cancel(self._click_after)
            except Exception:
                pass
            self._click_after = None
        self.canvas.delete("ui")
        self.canvas.delete("tray")
        if not keep_hold and self.cur == "idle" and self.user_hold:
            self.user_hold = False
            self.schedule_ambient(4000)

    def on_double(self, ev):
        if self._click_after:
            try:
                self.root.after_cancel(self._click_after)
            except Exception:
                pass
            self._click_after = None
        self.hide_panels(keep_hold=True)
        self.user_hold = True
        if self.cur == "sleeping":
            self.cycle_idx = 0
            self.wake_up()
            return
        self.cycle_idx = (self.cycle_idx + 1) % len(CYCLE)
        self.run_cycle_step(True)

    def sleep_command(self):
        if self.cur == "sleeping":
            self.wake_up()
            return
        self.user_hold = True
        self.nap(0, "Zzz… 打呼中，单击/双击叫我醒")

    # ---------- 事件轮询（MCP 点餐桥） ----------
    def poll_events(self):
        while True:
            try:
                with urllib.request.urlopen(BRIDGE + "/api/events?after=%d" % self.last_evt_id,
                                            timeout=4) as r:
                    data = json.loads(r.read().decode("utf-8"))
                evs = data.get("events") or []
                if evs:
                    self.evt_queue.put(evs)
            except (urllib.error.URLError, OSError, ValueError):
                pass
            time.sleep(2)

    def drain_events(self):
        try:
            while True:
                evs = self.evt_queue.get_nowait()
                if not self.evt_booted:
                    self.evt_booted = True
                    self.last_evt_id = evs[-1]["id"]
                    continue
                for ev in evs:
                    if ev.get("id", 0) > self.last_evt_id:
                        self.last_evt_id = ev["id"]
                        self.on_ordered(ev)
        except queue.Empty:
            pass
        self.root.after(300, self.drain_events)

    def on_ordered(self, ev):
        q = str(ev.get("name", "")).strip()
        if not q:
            return
        if self.cur == "sleeping":
            self.zzz = []
        m = None
        if ev.get("code"):
            m = next((x for x in self.menu_list if x["code"] == str(ev["code"])), None)
        if not m:
            m = next((x for x in self.menu_list if x["name"] == q), None)
        if not m:
            m = next((x for x in self.menu_list if x["name"] in q or q in x["name"]), None)
        if not m:
            m = {"id": "__tmp_%d" % int(time.time() * 1000), "code": "", "name": q,
                 "emo": "🍽️", "kcal": ev.get("kcal", 0), "price": ev.get("price", 0),
                 "type": ev.get("type", "eat")}
            self.menu_list.append(m)
        self.root.after(0, lambda: self.toast_and_feed(m))

    def toast_and_feed(self, m):
        if self.cur == "sleeping":
            self.bubble("闻到麦当劳的香味，惊醒！", 2000)
        else:
            self.bubble("📩 麦当劳来单啦：%s · ¥%s" % (m["name"], m["price"]), 4200)
        self.feed(m["id"], src="mcp-order")

    # ---------- 绘制 ----------
    def composite(self):
        conf = STATES[self.cur]
        fs = self.frames.get(self.cur) or self.frames["idle"]
        if not fs:
            return None
        img = fs[min(self.fi, len(fs) - 1)].copy()
        if self.facing < 0:
            img = ImageOps.mirror(img)
        fat = min(self.stats["fat"], 6)
        sx = 1 + fat * 0.045
        sy = 1 + fat * 0.018
        if abs(sx - 1) > 0.01:
            img = img.resize((int(CELL_W * sx * CAT_SCALE), int(CELL_H * sy * CAT_SCALE)), Image.LANCZOS)
        else:
            img = img.resize((int(CELL_W * CAT_SCALE), int(CELL_H * CAT_SCALE)), Image.LANCZOS)

        # 食物叠加（嘴部锚点 + 越吃越小）
        if self.cur in ("eating", "drinking") and self.overlay_food:
            ovx, ovy, ovsize = conf["overlay"]
            prog = min(1.0, self.eat_tick / max(1, len(fs) * 2))
            bite = (1 - prog * 0.55) if self.cur == "eating" else (1 - prog * 0.35)
            alpha = (max(0.25, 1 - prog * 0.65) if self.cur == "eating"
                     else max(0.40, 1 - prog * 0.50))
            size = int(ovsize * bite)
            fim = self.food_imgs.get(self.overlay_food["id"])
            if fim is None:
                fim = self._emoji_fallback(self.overlay_food["emo"], size)
            if fim:
                f = fim.resize((size, size), Image.LANCZOS)
                if f.mode != "RGBA":
                    f = f.convert("RGBA")
                a = f.getchannel("A").point(lambda v: int(v * alpha))
                f.putalpha(a)
                w, h = img.size
                ox = int((ovx - 0.5) * w)
                oy = int((1 - ovy) * h)
                img.alpha_composite(f, (ox - size // 2, oy - size // 2))
        return img

    def _emoji_fallback(self, emo, size):
        try:
            from PIL import ImageDraw, ImageFont
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            font = ImageFont.truetype("seguiemj.ttf", int(size * 0.8))
            d.text((size / 2, size / 2), emo, font=font, anchor="mm")
            return img
        except Exception:
            return None

    def tick(self):
        conf = STATES[self.cur]
        fs = self.frames.get(self.cur) or self.frames["idle"]
        dt = 1.0 / 30
        if fs:
            self.ft += dt
            spf = 1.0 / (conf.get("fps") or 5)
            while self.ft >= spf:
                self.ft -= spf
                self.fi += 1
                if self.fi >= len(fs):
                    self.fi = 0
                self.eat_tick = self.eat_tick + 1 if self.cur in ("eating", "drinking") else 0

        # 走路推进
        if self.cur == "running" and self.walk_target is not None:
            speed = 0.22 * dt * 30
            d = self.walk_target - self.px
            if abs(d) <= speed / 30 * 3:
                self.px = self.walk_target
                self.walk_target = None
                if not self.user_hold:
                    self.set_state("idle")
            else:
                self.px += 0.02 if d > 0 else -0.02
                self.facing = 1 if d >= 0 else -1

        self.render()
        self.root.after(33, self.tick)

    def render(self):
        conf = STATES[self.cur]
        img = self.composite()
        cv = self.canvas
        cv.delete("cat")
        if img is None:
            return
        self._photo = ImageTk.PhotoImage(img)
        w, h = img.size
        bob = 0
        t = time.time() * 1000
        if self.cur == "idle":
            bob = 2 * (1 if int(t / 300) % 2 else -1)
        elif self.cur == "jumping":
            bob = -20 * abs((t % 600) / 600 - 0.5) * 2
        elif self.cur == "running":
            bob = 3 * (1 if int(t / 60) % 2 else -1)
        cx = self.px * (CANVAS_W - w) + w / 2
        cv.create_image(cx, CAT_BOTTOM + bob, image=self._photo, anchor="s", tags="cat")

        # Zzz 粒子
        if conf.get("zzz") and self.cur == "sleeping" and int(t / 700) % 2 == 0 and len(self.zzz) < 6:
            self.zzz.append([cx + 30, CAT_BOTTOM - h * 0.8, 1.0, 13])
        for z in self.zzz[:]:
            z[1] -= 1.2
            z[0] += 0.6
            z[2] -= 0.02
            if z[2] <= 0:
                self.zzz.remove(z)
        cv.delete("zzz")
        for z in self.zzz:
            cv.create_text(z[0], z[1], text="Z", font=("Segoe UI", int(z[3]), "bold"),
                           fill="#c8beff", tags="zzz")

    # ---------- 顶部消息框 / 底部记账框（随文字自适应宽度；无动作时不显示） ----------
    def _adaptive_box(self, tags, txt, y2):
        """按文字宽度画圆角框+居中文字，返回实际框高；过长自动换行。"""
        cv = self.canvas
        maxw = CANVAS_W - 14
        tw = self._font.measure(txt)
        lines = 1 if tw <= maxw - 24 else 2
        w = min(tw + 28, maxw)
        h = BOX_H + (15 if lines > 1 else 0)
        y1 = y2 - h
        x1 = (CANVAS_W - w) / 2
        x2 = x1 + w
        self._rrect(x1, y1, x2, y2, 12, (tags,), fill=COL_BOX_FILL, outline=COL_BOX_LINE)
        cv.create_text(CANVAS_W / 2, (y1 + y2) / 2, text=txt, font=FONT_TXT,
                       fill=COL_TXT, tags=(tags,),
                       width=(w - 20) if lines > 1 else 0, justify="center")
        return h

    def refresh_topbox(self):
        cv = self.canvas
        cv.delete("topbox")
        if not self.top_msg:                     # 休闲状态：不显示顶部文字
            return
        self._adaptive_box("topbox", self.top_msg, int(self.cat_top()) - BOX_GAP)

    def _botbox_text(self):
        if self.last_meal:
            return ("本次 %dkcal·¥%.1f ｜ 累计 %d餐·%dkcal·¥%.1f"
                    % (self.last_meal["kcal"], self.last_meal["price"],
                       self.stats["meals"], self.stats["kcal"], self.stats["cost"]))
        return ""

    def refresh_botbox(self):
        cv = self.canvas
        cv.delete("botbox")
        self._bot_text = ""
        if not (self.botbox_visible and self.last_meal):   # 没投喂过：不显示
            return
        txt = self._botbox_text()
        self._bot_text = txt
        self._adaptive_box("botbox", txt, CAT_BOTTOM + BOX_GAP + BOX_H)

    def _hide_botbox(self):
        self.botbox_visible = False
        self.refresh_botbox()

    # ---------- 右侧详情卡（投喂旁显 4.5s） ----------
    def show_meal_card(self, m):
        cv = self.canvas
        for i in self.card_ids:
            try:
                cv.delete(i)
            except Exception:
                pass
        self.card_ids = []
        x1, y1 = CANVAS_W - 150, 60
        self.card_ids.append(self._rrect(x1, y1, x1 + 146, y1 + 58, 10, ("card",),
                                         fill="#181030", outline="#ffb84d"))
        self.card_ids.append(cv.create_text(x1 + 73, y1 + 12, font=("Microsoft YaHei", 10, "bold"),
                                            fill="#ffffff", text="%s %s" % (m["emo"], m["name"]), tags=("card",)))
        self.card_ids.append(cv.create_text(x1 + 73, y1 + 30, font=("Microsoft YaHei", 9),
                                            fill="#a99fd0", text="摄入  %d kcal（MCP 营养表）" % m["kcal"], tags=("card",)))
        self.card_ids.append(cv.create_text(x1 + 73, y1 + 46, font=("Microsoft YaHei", 9),
                                            fill="#a99fd0", text="消费  ¥%.1f" % m["price"], tags=("card",)))
        if self.card_timer:
            try:
                self.root.after_cancel(self.card_timer)
            except Exception:
                pass
        self.card_timer = self.root.after(4500, self._clear_card)

    card_ids = []
    card_timer = None

    def _clear_card(self):
        for i in self.card_ids:
            try:
                self.canvas.delete(i)
            except Exception:
                pass
        self.card_ids = []

    # ---------- 顶部框消息（气泡） ----------
    def bubble(self, txt, ms=2200):
        self.top_msg = txt
        self.refresh_topbox()
        if self.bubble_timer:
            try:
                self.root.after_cancel(self.bubble_timer)
            except Exception:
                pass
        self.bubble_timer = self.root.after(ms, self._clear_bubble)

    def _clear_bubble(self):
        self.top_msg = None
        self.refresh_topbox()

    # ---------- 自检 ----------
    def selftest(self, out_path):
        def step1():
            self.feed(next((m["id"] for m in self.menu_list if "巨无霸" in m["name"]), self.menu_list[0]["id"]),
                      src="selftest")

        def step2():
            self.bubble("自检：顶部消息框随文字自适应", 8000)
            img = self.composite()
            rgba = img.convert("RGBA")
            px = rgba.load()
            w, h = rgba.size
            vis = orange = blue = 0
            for yy in range(0, h, 2):
                for xx in range(0, w, 2):
                    r, g, b, a = px[xx, yy]
                    if a < 20:
                        continue
                    vis += 1
                    if r > 120 and 60 < g < 210 and b < 100:
                        orange += 1
                    if b > 140 and b > r + 40 and g > r:
                        blue += 1
            res = {
                "render": {"vis": vis * 4, "orange": orange * 4, "blue": blue * 4, "total": w * h},
                "state": self.cur,
                "topbox": self.top_msg or "",
                "botbox": self._botbox_text() if self.botbox_visible else "",
                "stats": json.loads(json.dumps(self.stats)),
            }
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=2)
            print("[selftest] 完成", flush=True)
            self.quit()

        self.root.after(2500, step1)
        self.root.after(4800, step2)

    def quit(self):
        try:
            save_pos(self.root.winfo_x(), self.root.winfo_y())
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=ROOT, help="mcd-cat-pet 项目根目录")
    ap.add_argument("--x", type=int, default=None)
    ap.add_argument("--y", type=int, default=None)
    ap.add_argument("--selftest", default=None, help="自检：渲染+投喂，结果写该 JSON 后退出")
    args = ap.parse_args()

    lock = acquire_singleton()
    if lock is None:
        print("[desktop_pet] 麦麦猫已经在桌面上了（单实例），跳过重复启动。")
        return 0

    import tkinter as tk
    px, py = load_pos()
    if args.x is not None:
        px = args.x
    if args.y is not None:
        py = args.y

    root = tk.Tk()
    root.withdraw()
    pet = McdPet(root, px, py)
    if args.selftest:
        pet.selftest(os.path.abspath(args.selftest))
    root.deiconify()
    print("[desktop_pet] 麦麦猫桌面悬浮桌宠启动：单击=投喂/睡觉按钮 · 双击=换动作 · 按住拖动")
    root.mainloop()
    try:
        lock.close()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
