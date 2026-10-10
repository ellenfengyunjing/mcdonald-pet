# WorkBuddy 联动说明

> 本文件说明本项目如何在腾讯 WorkBuddy 智能体中被真实使用，用于参与 WorkBuddy 专项奖励。

---

## 一、WorkBuddy 在本项目中做了什么

这个项目不是「先写好代码再交给 WorkBuddy 上传」——**整个资产生产链路是在 WorkBuddy 会话里跑出来的**。

### 1. 需求澄清与方案收敛

用户提出两个参赛思路（模拟点餐+卡路里 / 卡通猫咪桌宠）。WorkBuddy 抓取并精读比赛仓库规则、扫描排行榜与生态现状后，给出评估报告：思路一存在「主动降级 MCP 真实能力」和「方向撞车」两个硬伤，思路二是场上空白位，建议融合。

### 2. 生图编排（资产生产）

桌宠的全部视觉资产由 WorkBuddy 调用图像生成模型产出，共 20+ 张：

- 基础形象（1 张，以用户提供的自家猫咪照片为参考）
- Codex 九动画条带（8 条，其中 1 条返工）
- 网页版六状态条带（6 条）
- 食物道具（12 个）

WorkBuddy 在其中承担了**质量把关**工作，而不只是调接口：

- 发现模型把「8 帧单行」画成 6 帧 → 改写切帧器做帧数自适应
- 发现模型把单行画成 2×N 网格 → 切帧器增加行带检测
- 发现白底条带会连带抠掉猫的白胸白毛 → 该条带判废并重生成
- 发现猫爪附近残留色键蓝斑 → 抠图规则增加「蓝色主导像素强制透明」
- 发现跳跃弧线不明显、帧间大小不一 → 重生成并加「尺寸恒定、只改纵向位置」约束
- 发现并发生图会串位（4 张只落 2 张）→ 改为串行 + 按修改时间归位

### 3. 工程管线（确定性处理）

WorkBuddy 编写并迭代了 6 个 Python 脚本，把「模型产出」变成「可用资产」：

| 脚本 | 解决的问题 |
|---|---|
| `slice_codex.py` | 条带 → 透明帧；支持多行网格、单帧基准缩放、保留跳跃弧线 |
| `slice_strips.py` | 网页版切帧；帧数自适应、统一取景、去杂点 |
| `process_food.py` | 食物道具边框洪泛抠底（`background:transparent` 参数实测无效） |
| `grab_latest.py` | 生图回传路径不可靠，改为按 mtime 抓取归位 |
| `build_spritesheet.py` | 帧目录 → Codex 契约图集，含体积优化与契约自检 |
| `install_codex.py` | 装进 Codex 并修好浮窗总开关 |

### 4. 交付物生产

网页桌宠 `index.html`（Canvas 精灵动画状态机 + 食物叠加 + 存档）、Skill 文档、以及本套参赛文档，均由 WorkBuddy 产出。

---

## 二、在 WorkBuddy 里怎么用这个项目

### 作为 Skill 被调用

本项目已封装为 WorkBuddy Skill，存放于 `~/.workbuddy/skills/mcd-cat-pet/`。

**触发词**：麦麦猫 / 麦当劳桌宠 / 猫吃麦当劳 / 桌宠 / Codex 桌宠

**典型对话**：

```
用户：我用麦当劳 MCP 点了个巨无霸，让猫吃一下
  → Skill 加载 → 渲染对话内桌宠 → McdPet.onOrdered("巨无霸")
  → 猫啃巨无霸，记账 +550 kcal / +¥26

用户：把我的猫装进 Codex
  → 跑 build_spritesheet.py + install_codex.py
  → 提示完全退出 Codex 后重开并在选择器里选「麦麦猫」

用户：我想换成我家的狗
  → 改 pet.json 的 dir / displayName / description
  → 重新生成帧 → 重建图集 → 重装
```

### 对话内联桌宠

WorkBuddy 会话里可直接渲染可交互桌宠（读 `assets/` 绝对路径），点按钮即播动画。它不是全局浮窗，随对话流出现——这是 WorkBuddy 与 Codex 在桌宠机制上的差异：Codex 有常驻挂件，WorkBuddy 目前是会话内联。

---

## 三、真实调用的 MCP 能力（在 WorkBuddy 会话内）

以下调用在 WorkBuddy 会话中真实发生，用于把桌宠与麦当劳真实数据打通：

- `query-nearby-stores` → 深圳八卦岭周边 5 家门店
- `query-meals` → **桌宠 12 个道具的名称/编码/价格全部来自这次返回**
- `query-store-coupons` / `available-coupons` / `auto-bind-coupons` / `query-my-coupons`
- `campaign-calendar`

调用链路由 WorkBuddy 编排，桌宠负责呈现结果。详见 [MCP_INTEGRATION.md](MCP_INTEGRATION.md)。

---

## 四、WorkBuddy 带来的实际价值

1. **把 20+ 次生图的废片率压到可接受**：纯手动调生图，一致性、帧数、布局每一项都会翻车；有 Agent 做程序化质检（覆盖率检测、蓝残留检测、帧间尺寸检测）才能批量产出可用资产。
2. **打通「模型产出 → 工程资产」的断层**：生图模型给的是一张 PNG，桌宠要的是带 alpha 的等尺寸精灵帧。中间的切片、抠底、统一取景、体积优化全靠脚本管线，这一步是本项目工作量的大头。
3. **排查 Codex 桌宠不显示**：WorkBuddy 直接读取 Codex 的全局状态文件，定位到 `electron-avatar-overlay-open` 这个浮窗总开关，而不是靠猜。

---

## 五、复现方式

在 WorkBuddy 中打开本项目目录，直接说：

- 「重建桌宠图集」→ 跑 `tools/build_spritesheet.py`
- 「装到 Codex」→ 跑 `tools/install_codex.py`
- 「检查为什么桌宠不显示」→ 跑 `tools/install_codex.py --check-only`
- 「加一个新餐品」→ 生图 → 存 `assets/food/<id>.png` → 在 `menu_map.json` 和 `index.html` 的 MENU 里登记
