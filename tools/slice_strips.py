#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
slice_strips.py — 把 ImageGen 生成的横排动画条带切成透明 PNG 帧序列。

相比 hatch-pet 的固定 N 帧切法，这里做了三处容错：
  1. 自动检测实际帧数（6/8/10 都能切），不要求模型严格按帧数输出
  2. 自动裁掉黑边 / 参考线残留：只取内容 bbox，且同一 state 内所有帧共用同一取景框
  3. 抠蓝底 + 连通域去杂点（水印残留、悬浮噪点）

输出：
  assets/frames/<state>/f00.png ... fNN.png   (RGBA, 统一尺寸)
  assets/frames/<state>/meta.json
"""

import json
import os
import sys
from collections import deque

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "assets", "frames")

# 每个 state 的取景框缩放：内容占 cell 的比例
FIT = 0.92
CELL_W, CELL_H = 192, 208


def bg_mask(arr, bg, tol):
    d = np.sqrt(((arr.astype(int) - bg) ** 2).sum(axis=2))
    return d < tol


def find_frame_runs(colfrac, min_width=60, thresh=0.15):
    """把列投影切成一个个帧区间。colfrac[i] = 第 i 列非背景像素占比。

    阈值 0.15 是实测出来的：帧内内容列占比约 23-36%，帧间隙约 2-9%，
    用 0.02 这种"绝对干净"的阈值会把相邻帧连成一片（模型经常留很窄的缝）。
    """
    w = len(colfrac)
    content = colfrac > thresh
    runs, start = [], None
    for x in range(w):
        if content[x] and start is None:
            start = x
        elif not content[x] and start is not None:
            if x - start >= min_width:
                runs.append((start, x))
            start = None
    if start is not None and w - start >= min_width:
        runs.append((start, w))
    return runs


def largest_component(mask):
    """保留最大连通域，去掉水印/噪点等悬浮杂质。mask: bool array"""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    best = None
    best_size = 0
    for y in range(h):
        for x in range(w):
            if mask[y, x] and not seen[y, x]:
                # BFS
                comp = np.zeros_like(mask, dtype=bool)
                q = deque([(y, x)])
                seen[y, x] = True
                size = 0
                while q:
                    cy, cx = q.popleft()
                    comp[cy, cx] = True
                    size += 1
                    for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            q.append((ny, nx))
                if size > best_size:
                    best_size = size
                    best = comp
    return best if best is not None else mask


def key_out(cell_rgb, bg, tol=70, feather=18):
    """抠掉色键背景，返回 RGBA。边缘做 alpha 羽化，避免色边。
    额外规则：与背景同通道主导的像素（即色键及其暗部/阴影变体）强制透明，
    防止主体附近残留半透明色键斑块。蓝底用蓝色规则、绿底用绿色规则，自动判断。"""
    a = np.asarray(cell_rgb).astype(int)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    dist = np.sqrt(((a - bg) ** 2).sum(axis=2))
    alpha = np.clip((dist - (tol - feather)) / feather, 0, 1) * 255
    br, bgc, bb = bg
    if bb - max(br, bgc) > 60:                 # 蓝底
        dom = b - np.maximum(r, g)
    elif bgc - max(br, bb) > 60:               # 绿底
        dom = g - np.maximum(r, b)
    elif br - max(bgc, bb) > 60:               # 红底
        dom = r - np.maximum(g, b)
    else:
        dom = None
    if dom is not None:
        alpha = np.where(dom > 45, 0, alpha)
    alpha = alpha.astype(np.uint8)
    rgba = np.dstack([a.astype(np.uint8), alpha])
    return Image.fromarray(rgba, "RGBA")


def slice_strip(path, state, tol=70, padding=2):
    im = Image.open(path).convert("RGB")
    arr = np.asarray(im).astype(int)
    h, w, _ = arr.shape
    bg = arr[2, 2]

    m = bg_mask(arr, bg, tol)
    colfrac = (~m).mean(axis=0)
    runs = find_frame_runs(colfrac)

    # 兜底：帧粘连或误判时，按内容横向范围等分成 6 格
    if not (3 <= len(runs) <= 12):
        xs = np.where(colfrac > 0.05)[0]
        x0, x1 = (xs.min(), xs.max()) if len(xs) else (0, w)
        n_fb = 6
        step = (x1 - x0) / n_fb
        runs = [(int(x0 + i * step), int(x0 + (i + 1) * step)) for i in range(n_fb)]
        print(f"  [{state}] 帧检测异常（{len(runs) if runs else 0} 段），改为 {n_fb} 等分兜底")

    n = len(runs)
    print(f"  [{state}] 检测到 {n} 帧, 区间 {runs[0]} .. {runs[-1]}")

    # 第 1 步：每帧内的内容 bbox（局部坐标）
    boxes = []
    cells = []
    for (x0, x1) in runs:
        cell = im.crop((x0, 0, x1, h))
        carr = np.asarray(cell).astype(int)
        cm = ~bg_mask(carr, bg, tol)
        # 去杂点后再算 bbox，避免水印残留撑大取景框
        cm = largest_component(cm)
        ys, xs = np.where(cm)
        if len(ys) == 0:
            continue
        boxes.append((xs.min(), ys.min(), xs.max(), ys.max()))
        cells.append(cell)

    if not boxes:
        raise RuntimeError(f"{state}: 所有帧都为空")

    # 第 2 步：同一 state 共用取景框（=所有帧 bbox 的并集），保证帧间不抖
    ux0 = min(b[0] for b in boxes)
    uy0 = min(b[1] for b in boxes)
    ux1 = max(b[2] for b in boxes)
    uy1 = max(b[3] for b in boxes)
    print(f"  [{state}] 统一取景框 x{ux0}-{ux1} y{uy0}-{uy1}")

    out_dir = os.path.join(OUT_DIR, state)
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.endswith(".png"):
            os.remove(os.path.join(out_dir, f))

    frames = []
    for i, cell in enumerate(cells):
        cw = cell.width
        x0 = max(0, ux0 - padding)
        y0 = max(0, uy0 - padding)
        x1 = min(cw, ux1 + padding)
        y1 = min(cell.height, uy1 + padding)
        cropped = cell.crop((x0, y0, x1, y1))
        rgba = key_out(cropped, bg, tol)
        # 二次去杂点：alpha 图上的小连通域
        al = np.asarray(rgba.split()[-1])
        am = al > 40
        if am.any():
            keep = largest_component(am)
            al2 = np.where(keep, al, 0).astype(np.uint8)
            rgba.putalpha(Image.fromarray(al2, "L"))
        frames.append(rgba)

    # 第 3 步：统一缩放到 cell
    bw = ux1 - ux0 + 2 * padding
    bh = uy1 - uy0 + 2 * padding
    scale = min(CELL_W * FIT / bw, CELL_H * FIT / bh)
    tw, th = max(1, int(round(bw * scale))), max(1, int(round(bh * scale)))
    sized = [fr.resize((tw, th), Image.LANCZOS) for fr in frames]

    canvas = []
    for fr in sized:
        c = Image.new("RGBA", (CELL_W, CELL_H), (0, 0, 0, 0))
        ox = (CELL_W - tw) // 2
        oy = CELL_H - th          # 底对齐，脚踩基线
        c.alpha_composite(fr, (ox, oy))
        canvas.append(c)

    for i, c in enumerate(canvas):
        c.save(os.path.join(out_dir, f"f{i:02d}.png"))

    meta = {
        "state": state,
        "frame_count": len(canvas),
        "source": os.path.relpath(path, ROOT),
        "cell": [CELL_W, CELL_H],
        "content_size": [tw, th],
        "union_box": [int(ux0), int(uy0), int(ux1), int(uy1)],
        "baseline_offset": int(CELL_H - th),
    }
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return meta


def main():
    cfg_path = os.path.join(ROOT, "tools", "strip_sources.json")
    if not os.path.exists(cfg_path):
        print("缺少 tools/strip_sources.json", file=sys.stderr)
        return 1
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    out_metas = {}
    for state, rel in cfg.items():
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            print(f"  [{state}] 跳过（文件不存在: {rel}）")
            continue
        out_metas[state] = slice_strip(p, state)

    os.makedirs(OUT_DIR, exist_ok=True)
    json.dump(out_metas, open(os.path.join(OUT_DIR, "_slice_index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("\n切片完成:", {k: v["frame_count"] for k, v in out_metas.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
