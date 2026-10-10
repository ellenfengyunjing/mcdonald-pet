#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
process_food.py — 食物道具后处理：从 generated/ 原始图重做，输出透明 PNG。

ImageGen 的 background:"transparent" 参数实测不生效（返回不透明浅色底），
所以这里统一做「边框洪泛抠底」：以四条边的中位色为种子，按容差区域生长，
把连通到边框的背景整片抠掉，再裁边压缩到 256px。

用法: python tools/process_food.py
"""
import json
import os
import sys
from collections import deque

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "generated")
OUT = os.path.join(ROOT, "assets", "food")
TARGET = 256
TOL = 42          # 区域生长容差（RGB 欧氏距离）
FEATHER = 20      # 边缘羽化带宽度

# food id -> generated/ 下的原始文件名（由 grab_latest 记录）
SOURCES = {
    "bigmac":     "Create_a_single_food_prop_spri_2026-10-09T08-16-43.png",
    "mccrispy":   "Create_a_single_food_prop_spri_2026-10-09T08-17-16.png",
    "grilled":    "Create_a_single_food_prop_spri_2026-10-09T08-17-44.png",
    "dblcheese":  "Create_a_single_food_prop_spri_2026-10-09T08-18-15.png",
    "mcnuggets5": "Create_a_single_food_prop_spri_2026-10-09T08-18-46.png",
    "fries-m":    "Create_a_single_food_prop_spri_2026-10-09T08-19-18.png",
    "mcflurry":   "Create_a_single_food_prop_spri_2026-10-09T08-19-47.png",
    "cone":       "Create_a_single_food_prop_spri_2026-10-09T08-20-17.png",
    "taropie":    "Create_a_single_food_prop_spri_2026-10-09T08-20-46.png",
    "corn":       "Create_a_single_food_prop_spri_2026-10-09T08-21-16.png",
    "coke-m":     "Create_a_single_food_prop_spri_2026-10-09T08-21-45.png",
    "coffee-m":   "Create_a_single_food_prop_spri_2026-10-09T08-22-16.png",
}


def flood_bg(arr, tol):
    """从四条边做区域生长，返回背景布尔掩码。"""
    h, w, _ = arr.shape
    border = np.concatenate([
        arr[0, :], arr[h - 1, :], arr[:, 0], arr[:, w - 1]
    ], axis=0)
    seed = np.median(border, axis=0)
    dist = np.sqrt(((arr.astype(int) - seed) ** 2).sum(axis=2))
    visited = np.zeros((h, w), dtype=bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if not visited[y, x] and dist[y, x] < tol:
                visited[y, x] = True; q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if not visited[y, x] and dist[y, x] < tol:
                visited[y, x] = True; q.append((y, x))
    while q:
        cy, cx = q.popleft()
        for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and dist[ny, nx] < tol:
                visited[ny, nx] = True; q.append((ny, nx))
    return visited, dist


def largest_component(mask):
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    best, best_size = None, 0
    for y in range(h):
        for x in range(w):
            if mask[y, x] and not seen[y, x]:
                comp = np.zeros_like(mask, dtype=bool)
                q = deque([(y, x)]); seen[y, x] = True; size = 0
                while q:
                    cy, cx = q.popleft(); comp[cy, cx] = True; size += 1
                    for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True; q.append((ny, nx))
                if size > best_size:
                    best, best_size = comp, size
    return best if best is not None else mask


def process(food_id, fn):
    p = os.path.join(GEN, fn)
    if not os.path.exists(p):
        print(f"  {food_id}: 缺原图 {fn}")
        return False
    im = Image.open(p).convert("RGB")
    arr = np.asarray(im).astype(int)
    bgmask, dist = flood_bg(arr, TOL)
    # 羽化：距离越大越不透明
    alpha = np.clip((dist - TOL) / FEATHER, 0, 1)
    alpha = np.where(bgmask, 0, alpha)
    alpha = (alpha * 255).astype(np.uint8)
    rgba = np.dstack([arr.astype(np.uint8), alpha])
    out = Image.fromarray(rgba, "RGBA")

    # 去悬浮杂点
    am = np.asarray(out.split()[-1]) > 40
    if am.any():
        keep = largest_component(am)
        al = np.where(keep, np.asarray(out.split()[-1]), 0).astype(np.uint8)
        out.putalpha(Image.fromarray(al, "L"))

    al = np.asarray(out.split()[-1])
    ys, xs = np.where(al > 25)
    if len(xs) == 0:
        print(f"  {food_id}: 抠空了！")
        return False
    crop = out.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    sc = min(TARGET / crop.width, TARGET / crop.height)
    crop = crop.resize((max(1, int(crop.width * sc)), max(1, int(crop.height * sc))), Image.LANCZOS)
    os.makedirs(OUT, exist_ok=True)
    crop.save(os.path.join(OUT, f"{food_id}.png"))
    trans = float((np.asarray(crop.split()[-1]) < 16).mean())
    print(f"  {food_id:11s} {crop.size[0]}x{crop.size[1]}  透明占比 {trans:.0%}"
          + ("  ⚠️ 抠底不足" if trans < 0.25 else ""))
    return True


def main():
    ok = 0
    for fid, fn in SOURCES.items():
        if process(fid, fn):
            ok += 1
    print(f"\n完成 {ok}/{len(SOURCES)}")
    return 0 if ok == len(SOURCES) else 1


if __name__ == "__main__":
    sys.exit(main())
