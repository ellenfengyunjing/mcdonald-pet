#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""slice_codex.py — 把 run-codex/decoded 的条带切成透明帧，并镜像派生 running-left。

v2 改进：
  1. 支持多行网格（模型常把 12 帧画成 2 行 x 6 列）
  2. 缩放基准改为"单帧最大 bbox"而非"全状态并集"，
     避免跳跃/小跑的纵向位移把整行猫撑小
  3. 帧内保留相对纵向偏移（保住跳跃弧线），横向按各自中心对齐
"""
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from slice_strips import key_out, largest_component

CODEX_ORDER = ["idle", "running-right", "running-left", "waving",
               "jumping", "failed", "waiting", "running", "review"]
MAX_FRAMES = {"running-right": 8, "running-left": 8, "failed": 8}
FRAMES = os.path.join(ROOT, "run-codex", "frames")
DECODED = os.path.join(ROOT, "run-codex", "decoded")

CELL_W, CELL_H = 192, 208
FIT = 0.92
PAD = 2


def runs_1d(frac, thresh, min_len):
    out, s = [], None
    for i, v in enumerate(frac > thresh):
        if v and s is None:
            s = i
        elif not v and s is not None:
            if i - s >= min_len:
                out.append((s, i))
            s = None
    if s is not None and len(frac) - s >= min_len:
        out.append((s, len(frac)))
    return out


def subample(idxs, n):
    """均匀抽样 n 个索引，保持时序节奏。"""
    if len(idxs) <= n:
        return idxs
    return [idxs[round(i * (len(idxs) - 1) / (n - 1))] for i in range(n)]


def slice_strip2(path, state, tol=75):
    im = Image.open(path).convert("RGB")
    arr = np.asarray(im).astype(int)
    h, w, _ = arr.shape
    bg = arr[3, 3]
    dist = np.sqrt(((arr - bg) ** 2).sum(axis=2))
    mask = dist < tol

    rowf = (~mask).mean(axis=1)
    row_bands = runs_1d(rowf, 0.04, 100)
    if not row_bands:
        raise RuntimeError(f"{state}: 未检测到内容行")

    cells = []
    cell_bands = []
    for bi, (ry0, ry1) in enumerate(row_bands):
        sm = mask[ry0:ry1]
        colf = (~sm).mean(axis=0)
        for (cx0, cx1) in runs_1d(colf, 0.12, 60):
            cells.append(im.crop((cx0, ry0, cx1, ry1)))
            cell_bands.append(bi)
    if not cells:
        raise RuntimeError(f"{state}: 未检测到帧")
    print(f"  [{state}] 行带 {len(row_bands)} 个, 原始帧 {len(cells)}")

    # 抽样到目标帧数
    keep = subample(list(range(len(cells))), MAX_FRAMES.get(state, 6))
    if len(keep) < len(cells):
        print(f"  [{state}] {len(cells)} -> 抽样 {len(keep)} 帧 {keep}")
    cells = [cells[i] for i in keep]
    cell_bands = [cell_bands[i] for i in keep]

    # 抠底 + 去杂点 + bbox
    keyed, boxes = [], []
    for cell in cells:
        rgba = key_out(cell, bg, tol)
        al = np.asarray(rgba.split()[-1])
        am = al > 40
        if am.any():
            keep_m = largest_component(am)
            al2 = np.where(keep_m, al, 0).astype(np.uint8)
            rgba.putalpha(Image.fromarray(al2, "L"))
            ys, xs = np.where(keep_m)
            boxes.append((xs.min(), ys.min(), xs.max(), ys.max()))
        else:
            boxes.append((0, 0, 1, 1))
        keyed.append(rgba)

    # 每个行带的最低帧底 = 该行带基线（用于保留跳跃弧线等相对高度）
    band_baseline = {}
    for bi, (x0, y0, x1, y1) in zip(cell_bands, boxes):
        band_baseline[bi] = max(band_baseline.get(bi, 0), y1)

    max_bw = max(b[2] - b[0] + 1 for b in boxes)
    max_bh = max(b[3] - b[1] + 1 for b in boxes)
    s = min(CELL_W * FIT / max_bw, CELL_H * FIT / max_bh)
    print(f"  [{state}] 单帧最大 {max_bw}x{max_bh}, scale={s:.3f}")

    out_dir = os.path.join(FRAMES, state)
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.endswith(".png"):
            os.remove(os.path.join(out_dir, f))

    for i, (rgba, (x0, y0, x1, y1)) in enumerate(zip(keyed, boxes)):
        crop = rgba.crop((max(0, x0 - PAD), max(0, y0 - PAD),
                          min(rgba.width, x1 + 1 + PAD), min(rgba.height, y1 + 1 + PAD)))
        fw = max(1, int(round(crop.width * s)))
        fh = max(1, int(round(crop.height * s)))
        crop = crop.resize((fw, fh), Image.LANCZOS)
        # 纵向：以所在行带基线为地面，保留相对高度（跳跃弧线）
        dy_s = int(round((band_baseline[cell_bands[i]] - y1) * s))
        oy = CELL_H - PAD - fh - dy_s
        oy = max(2, min(oy, CELL_H - fh - 2))
        canvas = Image.new("RGBA", (CELL_W, CELL_H), (0, 0, 0, 0))
        canvas.alpha_composite(crop, ((CELL_W - fw) // 2, oy))
        canvas.save(os.path.join(out_dir, f"f{i:02d}.png"))

    n = len(keyed)
    meta = {"state": state, "frame_count": n,
            "source": os.path.relpath(path, ROOT), "cell": [CELL_W, CELL_H],
            "content_size": [int(max_bw * s), int(max_bh * s)]}
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return meta


def mirror_running_left():
    src = os.path.join(FRAMES, "running-right")
    dst = os.path.join(FRAMES, "running-left")
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(dst):
        if f.endswith(".png"):
            os.remove(os.path.join(dst, f))
    files = sorted(f for f in os.listdir(src) if f.startswith("f") and f.endswith(".png"))
    for f in files:
        Image.open(os.path.join(src, f)).transpose(
            Image.FLIP_LEFT_RIGHT).save(os.path.join(dst, f))
    print(f"  running-left: 由 running-right 镜像 {len(files)} 帧")
    return len(files)


def main():
    os.makedirs(FRAMES, exist_ok=True)
    metas = {}
    for st in CODEX_ORDER:
        if st == "running-left":
            continue
        p = os.path.join(DECODED, f"{st}.png")
        if not os.path.exists(p):
            print(f"  [{st}] 跳过（无条带）")
            continue
        metas[st] = slice_strip2(p, st)
    n = mirror_running_left()
    m = dict(metas["running-right"]); m["state"] = "running-left"
    m["source"] = "mirrored from running-right"
    m["frame_count"] = n
    json.dump(m, open(os.path.join(FRAMES, "running-left", "meta.json"), "w",
                      encoding="utf-8"), ensure_ascii=False, indent=2)
    metas["running-left"] = m
    json.dump(metas, open(os.path.join(FRAMES, "_slice_index.json"), "w",
                          encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\nCodex 切片完成:", {k: v["frame_count"] for k, v in metas.items()})


if __name__ == "__main__":
    main()
