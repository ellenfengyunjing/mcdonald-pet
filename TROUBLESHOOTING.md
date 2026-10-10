# 桌宠不显示？按这个顺序查

> Codex 桌面版把桌宠叫 **avatar overlay**（头像浮窗）。它有两道独立的开关，
> 少任何一道都会出现「在列表里选到了，但屏幕上什么都没有」。

---

## 第 0 步：体检

```bash
python tools/install_codex.py --check-only
```

它会告诉你：安装目录在不在、图集在不在、浮窗开关是什么状态、Codex 是不是正在运行。

---

## 第 1 步：浮窗总开关（最常见的坑）

Codex 的全局状态文件 `~/.codex/.codex-global-state.json` 里有一个键：

```json
"electron-avatar-overlay-open": true
```

**它是 false 的时候，无论你选了哪个桌宠，屏幕上都不会出现任何东西。**

这个值只能通过下面两种方式改：

- 跑 `python tools/install_codex.py`（脚本会自动备份并改成 true）
- 在 Codex 界面里手动打开桌宠浮窗

⚠️ **必须先完全退出 Codex**（托盘图标 → Quit，不是关窗口）。
运行中的 Codex 会在退出时把内存里的状态写回磁盘，把你的修改覆盖掉。

验证是否生效：

```bash
python -c "
import json,os
d=json.load(open(os.path.expanduser('~/.codex/.codex-global-state.json'),encoding='utf-8'))
print('浮窗开关:', d.get('electron-avatar-overlay-open'))
"
```

---

## 第 2 步：确认 Codex 真的认到了这个桌宠

同一个文件里还有一个列表，激活过的桌宠会被记进来：

```json
"first-awake-pet-notification-avatar-ids": ["custom:chou-zhumi", "custom:mcd-maimai"]
```

**如果这里没有你的 id，说明 Codex 根本没扫到这个目录**，问题在文件本身；
**如果这里有你的 id，说明 Codex 认到了**，问题在渲染或窗口位置。

---

## 第 3 步：检查安装目录

```bash
ls -la ~/.codex/pets/mcd-maimai/
```

应该只有两个文件（跟 Codex 内置桌宠保持完全一致的结构）：

```text
pet.json
spritesheet.png
```

`pet.json` 长这样：

```json
{
  "spritesheetPath": "spritesheet.png",
  "description": "…",
  "displayName": "麦麦猫",
  "id": "custom:mcd-maimai"
}
```

**注意**：不要多放 `spritesheet.webp`。实测可用的桌宠目录都是「单 PNG + 单 pet.json」，
多一个 webp 可能被优先加载而走到别的分支。`install_codex.py` 默认会帮你删掉它。

---

## 第 4 步：检查图集是否符合契约

```bash
python tools/build_spritesheet.py   # 重新构建 + 自动自检
```

契约要求（与 Codex 内置桌宠实测对比得出）：

| 项 | 要求 |
|---|---|
| 画布 | 1536 × 1872（8 列 × 9 行） |
| 单元格 | 192 × 208 |
| 行序 | idle / running-right / running-left / waving / jumping / failed / waiting / running / review |
| 格式 | RGBA PNG，8 bit |
| 透明区 | RGB 必须为 0（否则部分渲染器会出黑边） |
| 空列 | 每行不足 8 帧的尾部留全透明，不要留垃圾数据 |

自检会逐行检查这些，不通过会明确告诉你哪一行有问题。

**体积**：原始图集可能到 2 MB 以上（3D 软阴影的连续渐变 PNG 压不动）。
`build_spritesheet.py` 默认做轻量量化（rgb_step=8 / alpha_step=16），压到约 1 MB，肉眼无损。
想要完整渐变可加 `--lossless`。

---

## 第 5 步：窗口跑到屏幕外了

如果浮窗开关是开的、Codex 也认到了，但仍然看不到，可能是窗口位置记录错了。

```bash
python -c "
import json,os
d=json.load(open(os.path.expanduser('~/.codex/.codex-global-state.json'),encoding='utf-8'))
b=d.get('electron-avatar-overlay-bounds',{})
print('位置:', b.get('x'), b.get('y'), '| 记录的显示器:', b.get('displayBounds'))
"
```

把输出的 `displayBounds` 和你实际的屏幕分辨率对一下。经常换外接显示器的人很容易踩这个：
记录里存的是 1280×720，实际屏幕是 2560×1440，浮窗就会被放到一个奇怪的位置。

**修复**：删掉 `electron-avatar-overlay-bounds` 这个键，让 Codex 下次启动用默认位置。

```bash
python -c "
import json,os,shutil
p=os.path.expanduser('~/.codex/.codex-global-state.json')
shutil.copy2(p,p+'.bak-bounds')
d=json.load(open(p,encoding='utf-8'))
d.pop('electron-avatar-overlay-bounds',None)
json.dump(d,open(p,'w',encoding='utf-8'),ensure_ascii=False)
print('已重置浮窗位置')
"
```

（同样要先完全退出 Codex。）

---

## 第 6 步：A/B 对照

如果以上都正常还是不显示，做一次对照实验，能一次锁定问题归属：

```bash
# 把已知能正常显示的桌宠图集，临时装到你的桌宠目录里
cp ~/.codex/pets/<已知可用的桌宠>/spritesheet.png ~/.codex/pets/mcd-maimai/spritesheet.png
```

重启 Codex：

- **看得到** → 问题在你的图集（回到第 4 步）
- **还是看不到** → 问题在 Codex 侧或配置（回到第 1、2 步）

---

## 第 7 步：还不行

- 完全退出 Codex 后**再重启两次**（有些版本第一次启动不会重载 pets 目录）
- 确认 Codex 版本：`~/.codex/` 下如果有 `pets/` 目录就说明这个版本支持自定义桌宠
- 换回内置桌宠试试，确认挂件功能本身没坏

---

## 附：改了帧之后怎么重新打包

```bash
python tools/slice_codex.py          # 新条带 → 透明帧（如有新动画）
python tools/build_spritesheet.py    # 帧 → 图集 + 自检
python tools/install_codex.py        # 装进 Codex（记得先退出 Codex）
```

## 桌面悬浮窗（2026-10-10 更新）

- **主方案改为 tkinter+PIL**（`tools/desktop_pet.py`），用系统 Python 3.11 运行
  （`C:/Users/<user>/AppData/Local/Programs/Python/Python311/python.exe`）。
  托管 Python 3.13 未编译 tkinter，跑不了；装 Pillow 后即可（3.11 自带 tkinter）。
- 原因：pywebview 6.2.1 + Edge WebView2 在本机不稳定——
  ① `private_mode=True` 且未指定 storage_path 时用户目录被即时回收 → WebView2 起不来（白屏）；
  ② url 模式下注入线程不 set `_pywebviewready` → `evaluate_js` 死等 20s 报 "Main window failed to start"；
  ③ 页面 JS 在窗口内时跑时不跑（疑似透明窗 Show/Hide hack 触发渲染挂起）。
- pywebview 版保留在 `tools/desktop_pet_webview.py`，修正了独立 user_data_dir + 单实例锁，但默认不再使用。
- tkinter 版：单实例锁 127.0.0.1:8799（重复启动自动退出）；位置持久化同旧版；
  `--selftest out.json` 可做无人值守验证（渲染像素统计 + 模拟投喂巨无霸）。
