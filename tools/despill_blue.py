#!/usr/bin/env python3
"""蓝/青色残渣清理器 —— 去除抠图残留的 chroma-key 污染像素。

背景：源帧由蓝底（或彩底）图生成，抠图后抗锯齿边缘和部分笔触里
残留蓝/青色像素（猫脸上青绿色斑点）。本工具在源帧层面清理：

  1. 检测：a>0 且 b>r+25 且 b>g+15 且 (b-min(r,g))>30  （蓝/青主导）
  2. 低 alpha(<160) 边缘残渣 → 直接置透明
  3. 实心残渣 → 用周围干净像素迭代 inpaint（邻域均值填充）
  4. 光晕后处理：残渣周边轻微偏蓝的像素向邻域均值混合，消除过渡圈

安全边界（已验证）：本套素材的合法深色只有暖棕描边（r>g>b），
红色圣诞帽、橘白毛发均不会被误判；猫眼为深棕色，同样安全。

用法:
    python tools/despill_blue.py                     # 清理 pet.json 声明的全部帧源 + 食物
    python tools/despill_blue.py run-codex/frames/idle assets/food
    python tools/despill_blue.py --check             # 只统计不修改
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# ---------- 检测规则 ----------
def bad_mask(arr):
    """arr: HxWx4 → bool 掩码。两类污染：
    1. 蓝/青 spill：蓝主导（b>r+25 且 b>g+15）
    2. 键控 dropout：某通道为 0 但像素高亮且不透明
       （绿幕/品红/黄键残留，如 (0,255,0)/(248,0,248)/(255,255,0)），
       合法 3D 渲染不会有零通道高亮像素（描边是暖棕、帽红是 216,24,24）"""
    r = arr[:, :, 0].astype(np.int32)
    g = arr[:, :, 1].astype(np.int32)
    b = arr[:, :, 2].astype(np.int32)
    a = arr[:, :, 3].astype(np.int32)
    blue = (a > 0) & (b > r + 25) & (b > g + 15) & ((b - np.minimum(r, g)) > 30)
    mn = np.minimum(np.minimum(r, g), b)
    mx = np.maximum(np.maximum(r, g), b)
    dropout = (a > 0) & (mn == 0) & (mx >= 160)
    return blue | dropout


def inpaint(arr, mask):
    """迭代邻域均值填充 mask=True 的像素（8 邻域，逐圈扩散）。"""
    out = arr.copy()
    H, W = mask.shape
    remaining = mask.copy()
    for it in range(64):
        if not remaining.any():
            break
        fixed_any = False
        ys, xs = np.where(remaining)
        for y, x in zip(ys, xs):
            y0, y1 = max(0, y - 1), min(H, y + 2)
            x0, x1 = max(0, x - 1), min(W, x + 2)
            win_m = ~mask[y0:y1, x0:x1]
            win_a = arr[y0:y1, x0:x1, 3]
            good = win_m & (win_a >= 100)
            if not good.any():
                continue
            rgb = arr[y0:y1, x0:x1, :3][good].mean(axis=0)
            out[y, x, :3] = rgb.astype(np.uint8)
            # alpha：取邻域不透明度均值，保持软边过渡
            out[y, x, 3] = int(np.clip(arr[y0:y1, x0:x1, 3][good].mean(), 0, 255))
            remaining[y, x] = False
            fixed_any = True
        if not fixed_any:
            break  # 孤岛（周围全是残渣）下一轮 mask 扩展也救不了时放弃
    # 孤岛兜底：剩余的直接置透明（极少出现）
    if remaining.any():
        out[remaining, 3] = 0
    return out


def halo_pass(arr, was_bad):
    """对残渣周边 1px 内轻微偏蓝的像素做 60% 邻域均值混合，消光晕。"""
    out = arr.copy()
    H, W = was_bad.shape
    # 膨胀 1 圈
    dil = was_bad.copy()
    dil[1:, :] |= was_bad[:-1, :]
    dil[:-1, :] |= was_bad[1:, :]
    dil[:, 1:] |= was_bad[:, :-1]
    dil[:, :-1] |= was_bad[:, 1:]
    zone = dil & ~was_bad
    r = arr[:, :, 0].astype(np.int32)
    g = arr[:, :, 1].astype(np.int32)
    b = arr[:, :, 2].astype(np.int32)
    a = arr[:, :, 3]
    tinted = zone & (a >= 100) & (b > r + 8) & (b > g + 4)
    ys, xs = np.where(tinted)
    for y, x in zip(ys, xs):
        y0, y1 = max(0, y - 1), min(H, y + 2)
        x0, x1 = max(0, x - 1), min(W, x + 2)
        good = ~dil[y0:y1, x0:x1] & (arr[y0:y1, x0:x1, 3] >= 100)
        if not good.any():
            continue
        mean = arr[y0:y1, x0:x1, :3][good].mean(axis=0)
        mixed = (0.4 * arr[y, x, :3] + 0.6 * mean).astype(np.uint8)
        out[y, x, :3] = mixed
    return out


def process_image(path, check_only=False):
    im = Image.open(path).convert("RGBA")
    arr = np.asarray(im).astype(np.int16)
    n_total = 0
    if check_only:
        return int(bad_mask(arr).sum())
    # 收敛循环：inpaint/halo 可能让临界像素重新越线，反复清理直到归零
    for _ in range(6):
        m = bad_mask(arr)
        n = int(m.sum())
        if n == 0:
            break
        n_total += n
        solid = m & (arr[:, :, 3] >= 160)
        arr[m & ~solid, 3] = 0
        if solid.any():
            arr = inpaint(arr, solid).astype(np.int16)
            arr = halo_pass(arr, solid).astype(np.int16)
    if n_total:
        out = arr.astype(np.uint8)
        # 透明区 RGB 归零（部分渲染器会出黑边/紫边）
        out[:, :, 0] = np.where(out[:, :, 3] == 0, 0, out[:, :, 0])
        out[:, :, 1] = np.where(out[:, :, 3] == 0, 0, out[:, :, 1])
        out[:, :, 2] = np.where(out[:, :, 3] == 0, 0, out[:, :, 2])
        Image.fromarray(out, "RGBA").save(path, "PNG", optimize=True)
    return n_total


def frame_dirs_from_config(cfg_path):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    dirs = []
    for spec in cfg["spritesheet"]["rows"]:
        d = os.path.normpath(os.path.join(ROOT, spec["dir"]))
        if d not in dirs:
            dirs.append(d)
    return dirs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help="要清理的目录或文件（默认=pet.json 全部帧源 + assets）")
    ap.add_argument("--check", action="store_true", help="只统计，不修改")
    ap.add_argument("--config", default=os.path.join(ROOT, "pet.json"))
    args = ap.parse_args()

    if args.paths:
        targets = []
        for p in args.paths:
            p = os.path.normpath(p if os.path.isabs(p) else os.path.join(ROOT, p))
            if os.path.isdir(p):
                targets.extend(sorted(
                    os.path.join(p, f) for f in os.listdir(p)
                    if f.lower().endswith(".png")))
            else:
                targets.append(p)
    else:
        targets = []
        for d in frame_dirs_from_config(args.config):
            if os.path.isdir(d):
                targets.extend(sorted(
                    os.path.join(d, f) for f in os.listdir(d)
                    if f.lower().endswith(".png") and not f.startswith("_")))
            else:
                print(f"! 帧目录不存在: {d}")
        for sub in ("assets/frames", "assets/food"):
            base = os.path.join(ROOT, sub)
            if os.path.isdir(base):
                for root, _dirs, files in os.walk(base):
                    targets.extend(sorted(
                        os.path.join(root, f) for f in files
                        if f.lower().endswith(".png") and not f.startswith("_")))
        # 构建产物也纳入（量化 rgb_step=8 会让边缘像素偏移 ±4，可能重新越线）
        dist_png = os.path.join(ROOT, "dist", "spritesheet.png")
        if os.path.isfile(dist_png):
            targets.append(dist_png)

    total = 0
    touched = 0
    for p in targets:
        if not os.path.isfile(p):
            print(f"! 跳过（不存在）: {p}")
            continue
        n = process_image(p, check_only=args.check)
        if n:
            touched += 1
            total += n
            rel = os.path.relpath(p, ROOT)
            print(f"  {'[待清理]' if args.check else '[已清理]'} {rel}: {n} px")
    print(f"\n共 {total} 个蓝/青残渣像素，涉及 {touched} 个文件"
          + ("（check-only，未写入）" if args.check else ""))

    if not args.check and touched:
        bak = os.path.join(ROOT, "qa", f"despill_backup_{datetime.now():%Y%m%d-%H%M%S}.txt")
        os.makedirs(os.path.dirname(bak), exist_ok=True)
        with open(bak, "w", encoding="utf-8") as f:
            f.write("本次清理过的文件（如需回滚请从 git/备份恢复）:\n")
            f.write("\n".join(targets))
        print(f"清单: {bak}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"清理失败: {e}", file=sys.stderr)
        sys.exit(1)
