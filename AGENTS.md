# Agent 使用说明（Codex / WorkBuddy）

## 桌宠交互（Codex 与 WorkBuddy 完全一致）

Codex 侧要展示可交互桌宠时，直接拉起桌面悬浮窗（与 WorkBuddy 同一程序）：

```bash
python tools/desktop_pet.py    # tkinter 版，系统 Python 3.11；单实例锁 8799
```

- **单击小猫** → 左右两侧弹出「🍗 投喂」「💤 睡觉」按钮；点投喂 → 猫下方展开 12 道餐品真实图案托盘，点图案即吃（顶部状态框 + 底部本次/累计 kcal·金额记账框）
- **双击小猫** → 切换动作（静坐→走来走去→扑向你→休息）；无人操作时自动循环
- Codex 原生挂件（`~/.codex/pets/mcd-maimai/`）只负责形象展示，全部交互由上述悬浮窗承载；`pet.json` 契约不变

## 麦当劳 MCP 点餐联动

本仓库的桌宠「麦麦猫」需要 Agent 编排 MCP。当你在本项目中使用麦当劳 MCP（`mcd-order`）**下单成功**后：

```bash
python tools/order_hook.py --code "<商品编码>"        # 自动查 menu_map.json 补全
# 或：python tools/order_hook.py --name "餐品名" --price 22.5 --kcal 570
```

- 只在下单成功后调用一次；查菜单/查券/算价等只读操作不要调用。
- 点餐桥未启动时订单会暂存补发，命令不会失败，无需重试。
- 展示网页：`python tools/order_server.py --open`（http://127.0.0.1:8787/）。

## 修改形象 / 动画后

```bash
python tools/build_spritesheet.py    # 构建图集（已内置蓝/青残渣清理）
python tools/install_codex.py        # 安装进 Codex（需先完全退出 Codex）
python tools/despill_blue.py --check # 手动检查残留（正常应为 0）
```
