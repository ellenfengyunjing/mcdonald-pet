#!/usr/bin/env python3
"""把构建好的桌宠安装进 Codex，并修好「选了却不显示」的开关。

Codex 桌面版把桌宠叫 avatar overlay，有两个独立的坑：
  1. 桌宠目录 ~/.codex/pets/<id>/ 里要有 pet.json + spritesheet
  2. 全局状态 ~/.codex/.codex-global-state.json 里的
     electron-avatar-overlay-open 必须为 true —— 这个是浮窗总开关，
     为 false 时哪怕选对了桌宠也什么都不显示。

用法:
    python tools/install_codex.py                 # 安装 + 打开浮窗开关
    python tools/install_codex.py --check-only    # 只体检，不写文件
    python tools/install_codex.py --no-toggle     # 只装文件，不动开关

注意：改全局状态前必须完全退出 Codex，否则运行中的进程会把改动覆盖回去。
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

STATE_KEY = "electron-avatar-overlay-open"


def codex_home():
    return os.path.expanduser("~/.codex")


def is_codex_running():
    try:
        import subprocess
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq codex.exe"],
                           capture_output=True, text=True, errors="ignore")
        return "codex.exe" in r.stdout.lower()
    except Exception:
        return False


def read_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write_json(p, data):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, p)


def install(cfg, root, toggle=True, dry=False, with_webp=False):
    home = codex_home()
    target = os.path.expanduser(cfg["install"]["target"])
    src_png = os.path.join(root, cfg["output"]["dir"], cfg["output"]["png"])

    if not os.path.isfile(src_png):
        print(f"✗ 找不到图集 {src_png}，先跑 tools/build_spritesheet.py")
        return False

    print(f"安装目标: {target}")
    if dry:
        print("  （check-only 模式，未写入）")
    else:
        os.makedirs(target, exist_ok=True)
        shutil.copy2(src_png, os.path.join(target, cfg["install"]["spritesheetPath"]))
        # 默认只放 PNG：Codex 内置桌宠就是单 PNG 单 pet.json，多放一个 webp 反而可能
        # 被优先加载而踩到别的分支。需要 webp 时加 --with-webp。
        stale_webp = os.path.join(target, "spritesheet.webp")
        if os.path.isfile(stale_webp) and not with_webp:
            os.remove(stale_webp)
            print("  - 移除旧的 spritesheet.webp（避免优先加载）")
        if with_webp:
            webp = os.path.join(root, cfg["output"]["dir"], cfg["output"].get("webp", ""))
            if os.path.isfile(webp):
                shutil.copy2(webp, os.path.join(target, os.path.basename(webp)))
        pet_json = {
            "spritesheetPath": cfg["install"]["spritesheetPath"],
            "description": cfg["description"],
            "displayName": cfg["displayName"],
            "id": cfg["id"],
        }
        write_json(os.path.join(target, "pet.json"), pet_json)
        print(f"  ✓ pet.json + {os.path.basename(src_png)}  "
              f"({os.path.getsize(src_png)/1024:.0f} KB)")

    # 浮窗总开关
    state_path = os.path.join(home, ".codex-global-state.json")
    if not toggle:
        return True
    if not os.path.isfile(state_path):
        print("  ! 未找到全局状态文件，跳过开关修复")
        return True

    state = read_json(state_path)
    cur = state.get(STATE_KEY)
    print(f"  浮窗开关 {STATE_KEY} 当前 = {cur}")
    if cur is True:
        print("  ✓ 浮窗已是开启状态")
        return True
    if dry:
        print("  → 需要改成 true（本次未写入）")
        return True
    bak = os.path.join(home, f".codex-global-state.json.bak-petinstall-"
                             f"{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(state_path, bak)
    state[STATE_KEY] = True
    write_json(state_path, state)
    print(f"  ✓ 已设为 true（备份 {os.path.basename(bak)}）")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(ROOT, "pet.json"))
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--no-toggle", action="store_true")
    ap.add_argument("--with-webp", action="store_true")
    args = ap.parse_args()

    cfg = read_json(args.config)
    print(f"桌宠: {cfg['displayName']} ({cfg['id']})")

    if is_codex_running():
        print("⚠ 检测到 Codex 正在运行。运行中的 Codex 会在退出时覆盖全局状态，")
        print("  开关修改不会生效。请完全退出 Codex（托盘图标 → Quit）后重跑本脚本。")

    ok = install(cfg, ROOT, toggle=not args.no_toggle, dry=args.check_only,
                 with_webp=args.with_webp)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
