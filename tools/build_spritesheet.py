#!/usr/bin/env python3
"""通用桌宠图集构建器 —— 读 pet.json，把帧目录合成 Codex 契约图集。

用法:
    python tools/build_spritesheet.py                 # 构建 pet.json 描述的桌宠
    python tools/build_spritesheet.py --config X.json # 用另一份配置
    python tools/build_spritesheet.py --no-webp       # 只出 PNG

契约要点（与 Codex 内置桌宠实测一致）:
  * 画布 1536x1872 = 8 列 x 9 行，单元格 192x208
  * 行序固定：idle / running-right / running-left / waving / jumping / failed / waiting / running / review
  * 每行帧从 f00.png 起顺序排列，不足 8 帧的尾部留全透明
  * RGBA，透明区 RGB 必须为 0（否则部分渲染器会出黑边）
"""

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def collect_frames(d, mirror, max_frames):
    """读取一个动画行的所有帧，按顺序返回 RGBA 图。"""
    if not os.path.isdir(d):
        raise FileNotFoundError(f"帧目录不存在: {d}")
    files = sorted(
        f for f in os.listdir(d)
        if f.lower().endswith(".png") and not f.startswith("_")
    )
    if not files:
        raise RuntimeError(f"帧目录为空: {d}")
    if len(files) > max_frames:
        print(f"  ! {d} 有 {len(files)} 帧，超过上限 {max_frames}，截断")
        files = files[:max_frames]
    ims = [Image.open(os.path.join(d, f)).convert("RGBA") for f in files]
    if mirror:
        ims = [im.transpose(Image.FLIP_LEFT_RIGHT) for im in ims]
    return ims


def clean_alpha(im, low=10, high=245, rgb_step=1, alpha_step=1):
    """整理像素，让 PNG 压得动，同时不产生可见画质损失。

    1. 极淡的半透明噪点归零、极浓的拉满（抠图残留是 PNG 压不动的主因）
    2. 透明区 RGB 归零（避免非预乘渲染器出黑边）
    3. 可选轻量量化：默认 rgb_step=8 / alpha_step=16，
       3D 软阴影是连续渐变，PNG 对此极不友好；轻微阶跃后体积约减半，肉眼无差别。
    """
    a = np.asarray(im).astype(np.int16)
    al = a[:, :, 3]
    al = np.where(al <= low, 0, np.where(al >= high, 255, al))
    if alpha_step > 1:
        al = np.round(al / alpha_step) * alpha_step
    al = np.clip(al, 0, 255)
    if rgb_step > 1:
        a[:, :, :3] = np.round(a[:, :, :3] / rgb_step) * rgb_step
    a[:, :, 3] = al
    a[:, :, 0] = np.where(al == 0, 0, a[:, :, 0])
    a[:, :, 1] = np.where(al == 0, 0, a[:, :, 1])
    a[:, :, 2] = np.where(al == 0, 0, a[:, :, 2])
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def build(cfg, root, make_webp=True, rgb_step=8, alpha_step=16):
    ss = cfg["spritesheet"]
    cw, ch = ss["cell"]["width"], ss["cell"]["height"]
    cols, rows = ss["grid"]["columns"], ss["grid"]["rows"]
    atlas = Image.new("RGBA", (cols * cw, rows * ch), (0, 0, 0, 0))

    report = []
    print(f"构建图集 {cols}x{rows} 格，单元格 {cw}x{ch}")
    for spec in ss["rows"]:
        r = spec["row"]
        state = spec["state"]
        d = os.path.join(root, spec["dir"])
        ims = collect_frames(d, spec.get("mirror", False), spec.get("maxFrames", cols))
        for c, im in enumerate(ims):
            if c >= cols:
                break
            im = clean_alpha(im, rgb_step=rgb_step, alpha_step=alpha_step)
            if im.size != (cw, ch):
                # 居中贴入单元格（保持原比例，避免拉伸变形）
                canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
                w, h = im.size
                sc = min(cw / w, ch / h)
                if sc < 1:
                    im = im.resize((max(1, int(w * sc)), max(1, int(h * sc))), Image.LANCZOS)
                canvas.alpha_composite(im, ((cw - im.width) // 2, ch - im.height))
                im = canvas
            atlas.alpha_composite(im, (c * cw, r * ch))
        report.append({"row": r, "state": state, "frames": len(ims)})
        print(f"  row{r} {state:14s} {len(ims)} 帧  {'[镜像]' if spec.get('mirror') else ''}")

    out_dir = os.path.join(root, cfg["output"]["dir"])
    os.makedirs(out_dir, exist_ok=True)
    png_path = os.path.join(out_dir, cfg["output"]["png"])
    atlas.save(png_path, "PNG", optimize=True, compress_level=9)
    # 蓝/青残渣清理：rgb 量化可能让边缘像素重新越线，出图后立即收敛清理
    try:
        sys.path.insert(0, HERE)
        from despill_blue import process_image
        removed = 0
        for _ in range(6):
            n = process_image(png_path)
            if n == 0:
                break
            removed += n
        if removed:
            print(f"  已清理量化再生的蓝/青残渣 {removed} px")
    except Exception as e:
        print(f"  ! despill 步骤跳过: {e}")
    size_png = os.path.getsize(png_path)
    print(f"PNG  -> {png_path}  {atlas.size}  {size_png/1024:.0f} KB")

    webp_path = None
    if make_webp:
        webp_path = os.path.join(out_dir, cfg["output"]["webp"])
        try:
            atlas.save(webp_path, "WEBP", quality=92, method=6, exact=False)
            print(f"WEBP -> {webp_path}  {os.path.getsize(webp_path)/1024:.0f} KB")
        except Exception as e:
            print(f"WEBP 失败（可忽略）: {e}")
            webp_path = None

    return png_path, webp_path, report


def verify(path, cfg):
    """按契约自检图集：尺寸、行序占用、透明区 RGB。"""
    ss = cfg["spritesheet"]
    cw, ch = ss["cell"]["width"], ss["cell"]["height"]
    cols, rows = ss["grid"]["columns"], ss["grid"]["rows"]
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im).astype(int)
    ok = True
    if im.size != (cols * cw, rows * ch):
        print(f"  ✗ 尺寸应为 {cols*cw}x{rows*ch}，实际 {im.size}")
        ok = False
    al = a[:, :, 3]
    rgb = a[:, :, :3]
    leak = int((rgb[al == 0].max(axis=1) > 0).sum())
    if leak:
        print(f"  ✗ 透明区有 {leak} 个像素 RGB 非零（会出黑边）")
        ok = False
    for spec in ss["rows"]:
        r, state = spec["row"], spec["state"]
        filled = 0
        for c in range(cols):
            cell = al[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw]
            if (cell > 10).any():
                filled += 1
        if filled == 0:
            print(f"  ✗ row{r} {state} 全空")
            ok = False
    print("  自检：" + ("通过" if ok else "存在问题"))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(ROOT, "pet.json"))
    ap.add_argument("--no-webp", action="store_true")
    ap.add_argument("--lossless", action="store_true",
                    help="不量化，保留完整渐变（体积更大）")
    ap.add_argument("--rgb-step", type=int, default=8)
    ap.add_argument("--alpha-step", type=int, default=16)
    args = ap.parse_args()

    rgb_step = 1 if args.lossless else args.rgb_step
    alpha_step = 1 if args.lossless else args.alpha_step
    cfg = load_config(args.config)
    png, webp, report = build(cfg, ROOT, make_webp=not args.no_webp,
                              rgb_step=rgb_step, alpha_step=alpha_step)
    print("自检中…")
    verify(png, cfg)
    rep_path = os.path.join(ROOT, cfg["output"]["dir"], "build-report.json")
    with open(rep_path, "w", encoding="utf-8") as f:
        json.dump({"rows": report, "png": png, "webp": webp}, f, ensure_ascii=False, indent=2)
    print("构建完成")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"构建失败: {e}", file=sys.stderr)
        sys.exit(1)
