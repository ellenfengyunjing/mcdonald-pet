#!/usr/bin/env python3
"""麦麦猫 · 桌面悬浮桌宠（真正的桌面宠物，不是网页）。

用 pywebview + Edge WebView2 开一个无边框、透明、置顶、可拖动的小窗，
复用 mcd-cat-pet 的全部动画资产与状态机（assets/ + run-codex/frames/）。

交互（与悬浮桌宠语义一致）：
  - 平时（无操作）   → 自动循环：静坐 → 走来走去 → 扑向你 → 休息打盹
  - 双击小猫        → 手动按同样顺序切换状态（睡着时双击 = 叫醒）
  - 单击小猫        → 弹出小菜单：🍗 投喂（12 道真实菜单）/ 💤 睡觉休息
  - MCP 点餐联动    → Codex 用麦当劳 MCP 下单成功后 order_hook.py 推送，
                      本桌宠内置 HTTP 轮询（同源 /api/events），自动开吃

技术：
  - 帧来源与 index.html 完全一致（相对路径），双击 mcd-cat-pet 目录运行最稳
  - 若从别处启动，用 --root 指定 mcd-cat-pet 项目目录
  - 悬浮窗位置持久化到 ~/.codex/pets/mcd-maimai/desktop_pet_pos.json

用法：
    python tools/desktop_pet.py                 # 启动桌面悬浮桌宠
    python tools/desktop_pet.py --root <目录>   # 指定 mcd-cat-pet 目录
    python tools/desktop_pet.py --x 900 --y 500 # 指定初始位置
"""

import argparse
import atexit
import errno
import glob
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import uuid
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PET_HOME = os.path.join(os.path.expanduser("~/.codex/pets/mcd-maimai"))
POS_FILE = os.path.join(PET_HOME, "desktop_pet_pos.json")
MENU_FILE = os.path.join(ROOT, "menu_map.json")

# ---------- 点餐桥事件轮询（与网页版同一套接口，order_hook.py 推送） ----------
BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8787

# ---------- 单实例：只允许一只麦麦猫在桌面上 ----------
LOCK_PORT = 8799


def acquire_singleton():
    """用 127.0.0.1:8799 独占 bind 做单实例锁，返回 socket（保持引用直到进程退出）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        s.listen(1)
        return s
    except OSError as e:
        s.close()
        return None


# ---------- 自检：页面内读 canvas 像素（GDI 截屏抓不到透明窗，只能页内自检） ----------
# 注意：不要用 pywebview 的 evaluate_js 做自检 —— 6.2.1 在 url 模式下注入线程
# 永远不 set _pywebviewready，evaluate_js 会死等 20s 报 'Main window failed to start'。
# 因此自检由页面自身执行（?selftest=1），结果 POST 回本地资产服务器落盘。
SELFTEST_JS = r"""
if(/[?&]selftest=1/.test(location.search)){
  window.onerror = function(msg, src, line){
    try{ fetch('/selftest', { method:'POST', body: JSON.stringify({ pageError: String(msg) + ' @line ' + line }) }); }catch(e){}
    return false;
  };
  fetch('/selftest', { method:'POST', body: JSON.stringify({ boot: location.search }) }).catch(function(){});
  window.__petPixels = function(){
    const cv = document.getElementById('cv'), c = cv.getContext('2d');
    const d = c.getImageData(0, 0, cv.width, cv.height).data;
    let vis = 0, orange = 0, blue = 0;
    for(let i = 0; i < d.length; i += 4){
      const a = d[i+3]; if(a < 20) continue;
      vis++;
      const r = d[i], g = d[i+1], b = d[i+2];
      if(r > 120 && g > 60 && g < 210 && b < 100) orange++;   // 橘猫毛色
      if(b > 140 && b > r + 40 && g > r) blue++;               // 抠图蓝边残留
    }
    return { vis, orange, blue, total: cv.width * cv.height };
  };
  setTimeout(function(){
    const out = { render: window.__petPixels() };
    try{ window.McdPet.onOrdered({ name: '巨无霸' }); }
    catch(e){ out.feedErr = String(e); }
    setTimeout(function(){
      out.render_eating = window.__petPixels();
      const mc = document.getElementById('meal-card');
      out.card = mc.className + ' :: ' + mc.innerText.replace(/\n/g, ' / ');
      out.stats = JSON.parse(JSON.stringify(stats));
      fetch('/selftest', { method: 'POST', body: JSON.stringify(out) });
    }, 1600);
  }, 3000);
}
"""


def _selftest_watcher(out_path, timeout=40):
    """后台等自检结果落盘，超时或成功都直接退出进程。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(out_path):
            time.sleep(0.5)
            break
        time.sleep(0.5)
    print("[selftest] 完成，退出。")
    os._exit(0)


def make_user_data_dir():
    """每个实例一个独立 WebView2 用户目录，避免多实例抢同一目录导致崩溃/白屏。"""
    base = os.path.join(tempfile.gettempdir(), "mcd-maimai-webview")
    os.makedirs(base, exist_ok=True)
    # 顺手清掉两天前的旧目录
    try:
        now = time.time()
        for d in glob.glob(os.path.join(base, "*")):
            if os.path.isdir(d) and now - os.path.getmtime(d) > 2 * 86400:
                shutil.rmtree(d, ignore_errors=True)
    except OSError:
        pass
    ud = os.path.join(base, uuid.uuid4().hex[:12])
    os.makedirs(ud, exist_ok=True)
    atexit.register(lambda: shutil.rmtree(ud, ignore_errors=True))
    return ud


def load_pos(default_x=120, default_y=120):
    try:
        with open(POS_FILE, encoding="utf-8") as f:
            d = json.load(f)
            return int(d.get("x", default_x)), int(d.get("y", default_y))
    except (OSError, ValueError):
        return default_x, default_y


def save_pos(x, y):
    try:
        os.makedirs(PET_HOME, exist_ok=True)
        with open(POS_FILE, "w", encoding="utf-8") as f:
            json.dump({"x": int(x), "y": int(y)}, f)
    except OSError:
        pass


def load_menu():
    """读 menu_map.json → 供 JS 注入（名称/价格/热量/编码与网页版一致）。"""
    try:
        with open(MENU_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


# ---------- 本地资产服务器：托管 pet.html + assets/（解决相对路径加载） ----------
def make_asset_server(root, port=0, selftest_sink=None):
    """起一个只绑 127.0.0.1 的静态服务器，返回 (server, base_url)。
    selftest_sink: 收到 POST /selftest 时回调 (json_str)。"""
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def log_message(self, fmt, *args):
            if selftest_sink is not None:      # 自检模式打印请求，便于定位页面是否加载
                try:
                    print("[selftest:http]", fmt % args)
                except Exception:
                    pass

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_POST(self):
            if self.path.split("?")[0] != "/selftest" or selftest_sink is None:
                self.send_response(404)
                self._cors()
                self.end_headers()
                return
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(n).decode("utf-8", "replace")
                selftest_sink(body)
                self.send_response(200)
                self._cors()
                self.end_headers()
                self.wfile.write(b"ok")
            except Exception:
                self.send_response(500)
                self._cors()
                self.end_headers()

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


PET_HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>麦麦猫</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{width:100%;height:100%;overflow:hidden;background:transparent;
    font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif;user-select:none}
  #stage{position:relative;width:100%;height:100%}
  canvas{display:block;width:100%;height:100%}
  .bubble{
    position:absolute;top:2px;left:50%;transform:translateX(-50%);
    background:#fff;color:#3a2c18;font-size:11px;font-weight:600;
    padding:4px 10px;border-radius:10px;white-space:nowrap;
    pointer-events:none;box-shadow:0 3px 8px rgba(0,0,0,.25);z-index:5;
    opacity:0;transition:opacity .2s;
  }
  .bubble.show{opacity:1}
  .toast{
    position:absolute;bottom:4px;left:50%;transform:translateX(-50%);
    background:rgba(20,12,40,.94);border:1px solid #ffb84d;color:#f3efff;
    font-size:11px;padding:5px 10px;border-radius:10px;white-space:nowrap;
    pointer-events:none;z-index:6;opacity:0;transition:opacity .25s;
  }
  .toast.show{opacity:1}
  .toast b{color:#ffb84d}
  /* 投喂旁显卡：这一餐摄入 kcal（MCP 官方营养表）+ 消费金额 */
  .meal-card{
    position:absolute;top:34%;right:-2px;background:rgba(24,16,48,.96);
    border:1px solid #ffb84d;border-radius:14px;padding:9px 12px;min-width:136px;
    z-index:7;pointer-events:none;opacity:0;transform:translateX(12px);
    transition:opacity .28s, transform .28s;box-shadow:0 8px 22px rgba(0,0,0,.45);
  }
  .meal-card.show{opacity:1;transform:translateX(0)}
  .mc-name{font-size:12px;font-weight:700;color:#fff;margin-bottom:5px;white-space:nowrap}
  .mc-row{display:flex;justify-content:space-between;gap:14px;font-size:11px;color:#a99fd0;line-height:1.65}
  .mc-row b{color:#ffb84d;font-size:12px}
  /* 单击弹出的小菜单（投喂/睡觉） */
  .menu{
    position:absolute;top:6px;right:6px;background:#241c42;border:1px solid #3d3168;
    border-radius:14px;padding:8px;display:none;z-index:8;
    box-shadow:0 10px 30px rgba(0,0,0,.5);
  }
  .menu.open{display:block}
  .menu .mi{
    display:flex;align-items:center;gap:6px;padding:7px 12px;border-radius:10px;
    color:#f3efff;font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap;
  }
  .menu .mi:hover{background:#3a2f66}
  .menu .sep{height:1px;background:#3d3168;margin:4px 6px}
  /* 投喂子菜单（12 道菜） */
  .food-list{display:none;position:absolute;right:calc(100% + 8px);top:0;
    background:#241c42;border:1px solid #3d3168;border-radius:14px;padding:8px;
    max-height:230px;overflow-y:auto;box-shadow:0 10px 30px rgba(0,0,0,.5);z-index:9}
  .food-list.open{display:block}
  .food{display:flex;align-items:center;gap:6px;padding:6px 10px;border-radius:8px;
    color:#f3efff;font-size:11px;cursor:pointer;white-space:nowrap}
  .food:hover{background:#3a2f66}
  .food img{width:22px;height:22px;object-fit:contain}
  .food .meta{color:#a99fd0;font-size:10px;margin-left:auto;padding-left:8px}
  /* 拖动把手（顶部细条） */
  #drag{
    position:absolute;top:0;left:0;right:0;height:14px;cursor:move;z-index:4;
    -webkit-app-region:drag;
  }
</style>
</head>
<body>
  <div id="stage">
    <div id="drag"></div>
    <canvas id="cv" width="420" height="420"></canvas>
    <div class="bubble" id="bubble"></div>
    <div class="toast" id="toast"></div>
    <div class="meal-card" id="meal-card"></div>
    <div class="menu" id="menu">
      <div class="mi" id="mi-feed">🍗 投喂</div>
      <div class="mi" id="mi-sleep">💤 睡觉休息</div>
      <div class="sep"></div>
      <div class="menu-hint" style="color:#a99fd0;font-size:10px;padding:2px 12px 4px">双击小猫切换动作</div>
      <div class="food-list" id="food-list"></div>
    </div>
  </div>
<script>
/* 与网页版同源的帧配置（相对路径基于 mcd-cat-pet 根目录） */
const CELL_W = 192, CELL_H = 208;
const FRAME_COUNTS = {
  idle: 6, eating: 6, drinking: 5, happy: 5, sleeping: 6,
  waving: 4, jumping: 5, running: 5, waiting: 5, review: 5, failed: 6,
};
const STATES = {
  idle:     { fps: 5, label: "静坐发呆" },
  eating:   { fps: 6, label: "干饭中", overlay: { x:.58, y:.50, size:64 } },   /* 锚点=嘴部 */
  drinking: { fps: 6, label: "喝东西", overlay: { x:.58, y:.48, size:58 } },
  happy:    { fps: 6, label: "满足" },
  sleeping: { fps: 4, label: "打呼睡觉", zzz: true },
  waving:   { fps: 6, label: "招手" },
  jumping:  { fps: 7, label: "扑向你" },
  running:  { fps: 8, label: "走来走去", walk: true },
  waiting:  { fps: 5, label: "眼巴巴" },
  review:   { fps: 5, label: "歪头打量" },
  failed:   { fps: 5, label: "委屈" },
};
const STATE_LABELS = Object.fromEntries(Object.entries(STATES).map(([k,v])=>[k,v.label]));
const FRAME_DIRS = { __proto__: null };
for(const st of Object.keys(FRAME_COUNTS))
  FRAME_DIRS[st] = (st in {idle:1,eating:1,drinking:1,happy:1,sleeping:1})
    ? `assets/frames/${st}` : `run-codex/frames/${st}`;

const MENU_URL = "menu_map.json";
let MENU = [];
async function loadMenu(){
  try{
    const r = await fetch(MENU_URL);
    const d = await r.json();
    MENU = (d.mappings || []).map(v => ({
      id: v.food || v.code, code: String(v.code || ""), name: v.name || "",
      emo: v.emo || "🍽️", kcal: v.kcal || 0, price: v.price || 0, type: v.type || "eat",
    }));
  }catch(e){ MENU = []; }
}

function loadImage(src){
  return new Promise(res => {
    const im = new Image();
    im.onload = () => res(im); im.onerror = () => res(null); im.src = src;
  });
}

const cv = document.getElementById("cv"), ctx = cv.getContext("2d");
const frames = {}, foodImgs = {}, avail = {};
let cur = "idle", fi = 0, ft = 0, last = 0, overlayFood = null;
let eatTick = 0;          /* 吃/喝推进帧数（食物被咬小的程度） */
let facing = 1, px = .5, walkTarget = null, zzz = [], seqTimer = null;
let userHold = false;
let stats = { kcal:0, cost:0, meals:0, fat:0, log:[] };

async function loadAssets(){
  const jobs = [];
  for(const [st, n] of Object.entries(FRAME_COUNTS)){
    frames[st] = [];
    for(let i = 0; i < n; i++){
      const nn = String(i).padStart(2, "0");
      jobs.push(loadImage(`${FRAME_DIRS[st]}/f${nn}.png`).then(im => { if(im) frames[st].push(im); }));
    }
  }
  for(const m of MENU){
    jobs.push(loadImage(`assets/food/${m.id}.png`).then(im => { foodImgs[m.id] = im; }));
  }
  await Promise.all(jobs);
  for(const st of Object.keys(STATES)) avail[st] = (frames[st] || []).length > 0;
}

function bubble(txt, ms = 2200){
  const b = document.getElementById("bubble"); b.textContent = txt; b.classList.add("show");
  clearTimeout(b.__t); b.__t = setTimeout(() => b.classList.remove("show"), ms);
}
function toast(html, ms = 4200){
  const el = document.getElementById("toast"); el.innerHTML = html; el.classList.add("show");
  clearTimeout(el.__t); el.__t = setTimeout(() => el.classList.remove("show"), ms);
}
function clearSeq(){ clearTimeout(seqTimer); seqTimer = null; }
function setState(st){
  if(!avail[st]) st = "idle";
  clearSeq(); cur = st; fi = 0; ft = 0; eatTick = 0; walkTarget = null;
}
function playFor(st, dur, done){
  setState(st);
  seqTimer = setTimeout(() => { seqTimer = null; done && done(); }, dur * 1000);
}

function draw(){
  const t = performance.now();
  const dt = Math.min((t - last) / 1000, .1); last = t;
  const conf = STATES[cur] || STATES.idle;
  const fs = frames[cur] && frames[cur].length ? frames[cur] : frames.idle;
  if(fs && fs.length){
    ft += dt; const spf = 1 / (conf.fps || 5);
    while(ft >= spf){
      ft -= spf; fi++; if(fi >= fs.length) fi = 0;
      eatTick = (cur === "eating" || cur === "drinking") ? eatTick + 1 : 0;
    }
  }
  if(cur === "running" && walkTarget !== null){
    const speed = .22, d = walkTarget - px;
    if(Math.abs(d) <= speed * dt){ px = walkTarget; walkTarget = null; }
    else px += Math.sign(d) * speed * dt;
    facing = d >= 0 ? 1 : -1;
    if(walkTarget === null && !userHold) setState("idle");
  }
  ctx.clearRect(0, 0, cv.width, cv.height);
  const S = Math.min(cv.width / CELL_W, (cv.height - 10) / CELL_H) * .92;
  const dw = CELL_W * S, dh = CELL_H * S;
  const cx = px * (cv.width - dw) + dw / 2;
  const baseY = cv.height - 18;
  const fat = Math.min(stats.fat, 6);
  const sx = 1 + fat * 0.045, sy = 1 + fat * 0.018;
  let bob = 0;
  if(cur === "idle") bob = Math.sin(t / 600) * 2;
  if(cur === "jumping") bob = -Math.abs(Math.sin(t / 300)) * 26;
  if(cur === "running") bob = Math.abs(Math.sin(t / 120)) * 4;
  ctx.save();
  ctx.translate(cx, baseY + bob);
  ctx.scale(facing * S * sx, S * sy);
  ctx.drawImage(fs[Math.min(fi, fs.length - 1)] || fs[0], -CELL_W / 2, -CELL_H);
  if((cur === "eating" || cur === "drinking") && overlayFood){
    const ov = STATES[cur].overlay;
    const prog = Math.min(1, eatTick / Math.max(1, fs.length * 2));
    const bite  = cur === "eating" ? (1 - prog * 0.55) : (1 - prog * 0.35);
    const alpha = cur === "eating" ? Math.max(0.25, 1 - prog * 0.65)
                                   : Math.max(0.40, 1 - prog * 0.50);
    const size = ov.size * bite * (1 + Math.sin(t / 120) * 0.04);
    const fim = foodImgs[overlayFood.id];
    const ox = (ov.x - .5) * CELL_W, oy = -(1 - ov.y) * CELL_H;
    ctx.globalAlpha = alpha;
    if(fim) ctx.drawImage(fim, ox - size / 2, oy - size / 2, size, size);
    else { ctx.font = `${size * .8}px serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(overlayFood.emo, ox, oy); }
    ctx.globalAlpha = 1;
  }
  ctx.restore();
  if(conf.zzz && cur === "sleeping"){
    if(!draw.__z || t - draw.__z > 700){
      draw.__z = t;
      zzz.push({ x: cx + 30 + Math.random()*10, y: baseY - dh * .78, a: 1, s: 12 + Math.random()*8 });
    }
  }
  zzz = zzz.filter(z => z.a > 0);
  for(const z of zzz){
    z.y -= dt * 26; z.x += dt * 12; z.a -= dt * .5;
    ctx.font = `600 ${z.s}px sans-serif`;
    ctx.fillStyle = `rgba(200,190,255,${Math.max(z.a,0)})`;
    ctx.textAlign = "center";
    ctx.fillText("Z", z.x, z.y);
  }
  requestAnimationFrame(draw);
}

/* ---------- 交互 ---------- */
const CYCLE = ["sit", "walk", "pounce", "rest"];
let cycleIdx = 0;
function runCycleStep(manual){
  const step = CYCLE[cycleIdx];
  if(step === "sit"){
    setState("idle"); bubble("（安静坐好）");
    if(manual) holdThenRelease(3);
  } else if(step === "walk" && avail.running){
    walkTarget = px < .5 ? .62 + Math.random() * .26 : .12 + Math.random() * .26;
    setState("running"); bubble("溜达溜达~", 1500);
    if(manual) holdThenRelease(6);
  } else if(step === "pounce" && avail.jumping){
    setState("jumping"); bubble("噗！扑向你~", 1500);
    playFor("jumping", 1.8, () => { if(!userHold) setState("idle"); });
    if(manual) holdThenRelease(4);
  } else if(step === "rest"){
    nap(manual ? 8 : 5, "Zzz… 休息一下");
  } else {
    setState("idle"); userHold = false; scheduleAmbient(4000);
  }
}
function holdThenRelease(sec){
  clearTimeout(holdThenRelease.__t);
  holdThenRelease.__t = setTimeout(() => {
    if(cur === "idle"){ userHold = false; scheduleAmbient(5000 + Math.random() * 5000); }
  }, sec * 1000);
}

function feed(id, opts = {}){
  const m = MENU.find(x => x.id === id); if(!m) return;
  userHold = true;
  stats.meals++; stats.kcal += m.kcal; stats.cost += m.price;
  stats.fat = Math.min(6, stats.fat + (m.type === "drink" ? 0.5 : 1));
  overlayFood = m;
  setState(m.type === "drink" ? "drinking" : "eating");
  bubble(`嗷呜~ ${m.name}！`);
  showMealCard(m);
  playFor(cur, 3.2, afterMealRest);
}
/* 旁显这一餐：摄入 kcal（来自麦当劳 MCP 官方营养表）+ 消费金额 */
function showMealCard(m){
  const mc = document.getElementById("meal-card"); if(!mc) return;
  mc.innerHTML =
    `<div class="mc-name">${m.emo || "🍽️"} ${m.name}</div>` +
    `<div class="mc-row"><span>摄入</span><b>${m.kcal} kcal</b></div>` +
    `<div class="mc-row"><span>消费</span><b>¥${Number(m.price || 0).toFixed(1)}</b></div>`;
  mc.classList.add("show");
  clearTimeout(window.__mcT);
  window.__mcT = setTimeout(() => mc.classList.remove("show"), 4500);
}
function afterMealRest(){
  overlayFood = null;
  if(!avail.happy){ setState("idle"); userHold = false; scheduleAmbient(3000); return; }
  setState("happy");
  bubble("吃饱了…眯一会儿", 2400);
  seqTimer = setTimeout(() => { seqTimer = null; nap(6, "Zzz… 吃饱就睡，猫生赢家"); }, 1400);
}
function nap(dur, msg){
  if(!avail.sleeping){ setState("idle"); userHold = false; scheduleAmbient(3000); return; }
  overlayFood = null;
  setState("sleeping");
  if(msg) bubble(msg, 2400);
  seqTimer = setTimeout(() => { seqTimer = null; wakeUp(); }, dur * 1000);
}
function wakeUp(){
  if(cur !== "sleeping") return;
  zzz = []; userHold = false;
  if(avail.happy) playFor("happy", 1.2, () => setState("idle"));
  else setState("idle");
  bubble("喵呜…睡饱了"); scheduleAmbient(6000);
}

/* 自动循环：静坐 → 走 → 扑 → 休息 */
let ambientTimer = null, autoIdx = 0;
function scheduleAmbient(ms){
  clearTimeout(ambientTimer);
  ambientTimer = setTimeout(doAmbient, ms || 6000 + Math.random() * 7000);
}
function doAmbient(){
  if(userHold || cur !== "idle"){ scheduleAmbient(4000); return; }
  const step = CYCLE[autoIdx % CYCLE.length];
  autoIdx++;
  if(step === "sit"){ scheduleAmbient(5000 + Math.random() * 5000); }
  else { runCycleStep(false); scheduleAmbient(9000 + Math.random() * 6000); }
}

/* 点击菜单 */
const menuEl = document.getElementById("menu");
const foodList = document.getElementById("food-list");
function toggleMenu(open){
  foodList.classList.remove("open");
  menuEl.classList.toggle("open", open);
}
document.getElementById("mi-feed").onclick = e => {
  e.stopPropagation();
  if(!foodList.childElementCount){
    foodList.innerHTML = MENU.map(m => `
      <div class="food" data-id="${m.id}">
        ${foodImgs[m.id] ? `<img src="assets/food/${m.id}.png">` : `<span>${m.emo}</span>`}
        <span>${m.name}</span><span class="meta">${m.kcal}kcal·¥${m.price}</span>
      </div>`).join("");
    foodList.querySelectorAll(".food").forEach(el =>
      el.onclick = ev => { ev.stopPropagation(); toggleMenu(false); feed(el.dataset.id); });
  }
  foodList.classList.toggle("open");
};
document.getElementById("mi-sleep").onclick = e => {
  e.stopPropagation(); toggleMenu(false);
  if(cur === "sleeping"){ wakeUp(); return; }
  userHold = true;
  nap(0 + 30*60, "Zzz… 点菜单「睡觉休息」叫醒");   /* 手动睡直到叫醒 */
};
document.addEventListener("click", e => {
  if(!menuEl.contains(e.target)) foodList.classList.remove("open");
  if(!menuEl.contains(e.target)) toggleMenu(false);
});
cv.addEventListener("click", () => {
  if(cur === "sleeping"){ wakeUp(); return; }
  toggleMenu(true);
});

/* 双击 = 切换动作 */
cv.addEventListener("dblclick", e => {
  e.preventDefault();
  toggleMenu(false);
  userHold = true;
  if(cur === "sleeping"){ cycleIdx = 0; wakeUp(); return; }
  cycleIdx = (cycleIdx + 1) % CYCLE.length;
  runCycleStep(true);
});

/* 对外 API（页面轮询到新订单时调用；也可通过 evaluate_js 手动触发） */
window.McdPet = {
  onOrdered(e){
    if(typeof e === "string") e = { name: e };
    const q = String(e.name || "").trim(); if(!q) return;
    if(cur === "sleeping"){ zzz = []; bubble("闻到麦当劳的香味，惊醒！", 2000); }
    let m = MENU.find(x => e.code && x.code === String(e.code))
         || MENU.find(x => x.name === q)
         || MENU.find(x => x.name.includes(q) || q.includes(x.name));
    if(!m){
      m = { id:"__tmp_"+Date.now(), name:q, emo:"🍽️", kcal:e.kcal||0, price:e.price||0, type: e.type || "eat" };
      MENU.push(m);
    }
    toast(`📩 <b>麦当劳来单啦</b>：${m.name} · ¥${m.price} · ${m.kcal} kcal<br>麦麦猫开吃！`);
    feed(m.id);
    return true;
  },
  stats(){ return JSON.parse(JSON.stringify(stats)); },
};

/* MCP 点餐联动：直接轮询点餐桥 /api/events（CORS 已放行） */
let lastEvtId = 0, evtBooted = false;
setInterval(async () => {
  try{
    const r = await fetch(`http://127.0.0.1:8787/api/events?after=${lastEvtId}`, {mode:"cors"});
    const j = await r.json();
    const evs = j.events || [];
    if(!evs.length) return;
    if(!evtBooted){                       // 首次：只快进游标，不重放历史订单
      evtBooted = true;
      lastEvtId = evs[evs.length - 1].id;
      return;
    }
    for(const ev of evs){
      if(ev.id > lastEvtId){ lastEvtId = ev.id; window.McdPet.onOrdered(ev); }
    }
  }catch(_){}
}, 2000);

loadMenu().then(() => loadAssets()).then(() => {
  setState("idle");
  scheduleAmbient(6000);
  requestAnimationFrame(t => { last = t; draw(); });
  bubble("单击投喂我 · 双击换动作", 3000);
});
</script>
<script>
""" + SELFTEST_JS + """
</script>
</body>
</html>
"""


def build_html(menu_map):
    """保留占位（菜单现在由页面 fetch menu_map.json，不再注入）。"""
    return PET_HTML


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=ROOT, help="mcd-cat-pet 项目根目录")
    ap.add_argument("--x", type=int, default=None, help="初始 X（默认读持久化位置）")
    ap.add_argument("--y", type=int, default=None, help="初始 Y")
    ap.add_argument("--selftest", default=None, help="自检：跑一遍渲染+投喂并把结果写到该 JSON 文件后退出")
    args = ap.parse_args()

    # 0) 单实例：已经有一只麦麦猫在桌面上就直接退出，不再开第二只
    lock = acquire_singleton()
    if lock is None:
        print("[desktop_pet] 麦麦猫已经在桌面上了（单实例），跳过重复启动。")
        return 0

    # 0.5) 每个实例独立 WebView2 用户目录（多实例抢目录会崩/白屏）
    user_data = make_user_data_dir()

    root = os.path.abspath(args.root)
    os.chdir(root)                       # 相对路径资产基于项目根

    # 1) 写 pet.html（页面自己 fetch menu_map.json）
    html = build_html(None)
    pet_html_path = os.path.join(root, "pet.html")
    with open(pet_html_path, "w", encoding="utf-8") as f:
        f.write(html)

    # 2) 本地资产服务器（相对路径 assets/... 可加载）
    selftest_mode = bool(args.selftest)
    sink = None
    if selftest_mode:
        def sink(body_str, _out=os.path.abspath(args.selftest)):
            try:
                with open(_out, "w", encoding="utf-8") as f:
                    f.write(body_str)
                print("[selftest] 结果已写入", _out)
            except OSError as e:
                print("[selftest] 写结果失败：", e)

    srv, base = make_asset_server(root, selftest_sink=sink)
    url = base + "pet.html" + ("?selftest=1" if selftest_mode else "")
    print(f"[desktop_pet] 资产服务: {base}")

    import webview

    if selftest_mode:
        threading.Thread(target=_selftest_watcher, args=(os.path.abspath(args.selftest),),
                         daemon=True).start()

    px, py = load_pos()
    if args.x is not None: px = args.x
    if args.y is not None: py = args.y

    window = webview.create_window(
        title="麦麦猫",
        url=url,
        width=260, height=300,
        x=px, y=py,
        resizable=False,
        fullscreen=False,
        frameless=True,                  # 无边框悬浮
        transparent=True,                # 透明背景
        on_top=True,                     # 置顶
        easy_drag=True,                  # pywebview 自带拖动
    )

    _last_pos = [px, py]

    def on_moved():
        try:
            _last_pos[0], _last_pos[1] = window.x, window.y
            save_pos(*_last_pos)
        except Exception:
            pass
    try:
        window.events.moved += on_moved
        # closing 时窗口还活着，能拿到位置；closed 时已销毁会报错
        window.events.closing += lambda: save_pos(*_last_pos)
    except Exception:
        pass

    print("[desktop_pet] 麦麦猫桌面悬浮桌宠启动：单击=投喂菜单 · 双击=切换动作 · 顶栏拖动")
    try:
        webview.start(gui="edgechromium", private_mode=True, storage_path=user_data, debug=False)
    except Exception as e:
        print(f"[desktop_pet] 启动失败：{e}")
        return 1
    finally:
        try:
            lock.close()
        except OSError:
            pass
        srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
