#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grab_latest.py — ImageGen 回传的 localPath 在并发调用时会串位，
本脚本按 mtime 找到最近生成的那张图，另存为确定文件名。

用法: python tools/grab_latest.py <state>
  → 输出 generated/strip_<state>.png
"""
import os
import shutil
import sys
import time
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES = [
    os.path.join(ROOT, "generated"),
    os.path.join(ROOT, "assets", "food", "_tmp"),
    r"D:\Ellen工作资料\AI项目\workbuddy\workbuddy-data\blobs",
]


def walk_files(base):
    out = []
    for dp, _, fns in os.walk(base):
        for fn in fns:
            if fn.lower().endswith(".png"):
                p = os.path.join(dp, fn)
                try:
                    out.append((os.path.getmtime(p), p))
                except OSError:
                    pass
    return out


def main():
    if len(sys.argv) < 2:
        print("用法: python tools/grab_latest.py <state>", file=sys.stderr)
        return 1
    state = sys.argv[1]
    now = time.time()
    pool = []
    for c in CANDIDATES:
        if os.path.isdir(c):
            pool += walk_files(c)
    # 只看 15 分钟内生成的
    pool = [(t, p) for t, p in pool if now - t < 900]
    if not pool:
        print("未找到近期生成的图片", file=sys.stderr)
        return 1
    pool.sort(key=lambda x: x[0])
    t, p = pool[-1]
    try:
        im = Image.open(p)
        im.load()
        size = im.size
    except Exception as e:
        print("无法读取:", p, e, file=sys.stderr)
        return 1
    if len(sys.argv) >= 3:
        out = os.path.join(ROOT, sys.argv[2])
    else:
        out = os.path.join(ROOT, "generated", f"strip_{state}.png")
    shutil.copy2(p, out)
    print(f"{state}: {p} ({size[0]}x{size[1]}) -> {os.path.relpath(out, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
