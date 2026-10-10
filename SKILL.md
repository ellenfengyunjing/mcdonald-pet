---
name: mcd-cat-pet
description: 麦当劳点餐桌宠「麦麦猫」——WorkBuddy 里的麦当劳 MCP 可视化互动桌宠。用户在 WorkBuddy 对话中用麦当劳 MCP 点餐、或手动投喂 12 道真实菜单时，猫咪实时吃掉对应餐品并自动记账（卡路里/花费，数据来自 list-nutrition-foods 官方营养表）；可投喂/睡觉打呼/双击切换动作/空闲自动循环。也可跑成桌面悬浮桌宠或 Codex 挂件。触发词：麦麦猫、桌宠、麦当劳猫、点餐动画、投喂猫咪、喂猫、猫咪记账、麦当劳桌宠、mcd pet。
---

# 麦麦猫 · 麦当劳 MCP 点餐桌宠（mcd-cat-pet）

一只住在 WorkBuddy 里的猫：**你点什么，它就吃什么；吃多少，记多少账——卡路里和花费全部来自麦当劳 MCP 真实数据，一个数字都不编。**

## 在 WorkBuddy 里怎么用（主形态）

**入口就是对话本身。** 用户说「投喂麦麦猫」「让猫吃个巨无霸」「猫睡了吧」「看看猫今天吃了多少」，Agent 识别意图后执行：

### 工作流 A：手动投喂（最常用）

1. 用户表达投喂意图（点某道菜 / 随便来点吃的 / 看菜单）
2. Agent 用 `present_files` 打开 `index.html`（WorkBuddy 预览面板内联渲染，可直接点击交互）
3. 交互（悬浮窗/网页统一）：**单击小猫** → 猫左右两侧弹出「🍗 投喂」「💤 睡觉」按钮；点「投喂」→ 猫下方展开 12 道餐品真实图案托盘（名称/编码/价格来自 `query-meals`，热量来自 `list-nutrition-foods`）→ 点图案投喂，食物贴嘴越吃越小；**顶部消息框**只在切换/投喂/来单时出现（框宽随文字自适应，休闲时隐藏），**底部记账框**投喂后显示「本次 kcal·金额 ｜ 累计 餐数·kcal·金额」、回休闲后自动收起（同字体同框式，与猫等间距）
4. 吃完自动「满足」→ 眯一会儿 → 回静坐；**双击**切换动作；空闲时自动循环（静坐→遛弯→扑向你→打盹）

### 工作流 B：MCP 点餐联动（参赛核心卖点）

1. 用户说「帮我点一份麦辣鸡腿汉堡套餐」「来个中薯条」
2. Agent 走完整 MCP 链路：
   `query-nearby-stores` → `query-meals`（拿真实商品编码/价格）→ `calculate-price` → 用户确认 → `create-order`
3. **下单成功后必须执行**（这是本 Skill 的联动心跳）：
   ```bash
   python tools/order_hook.py --code 1440   # 自动查 menu_map.json 补全名称/价格/热量
   ```
4. 猫 2 秒内开吃对应餐品，弹「餐名 · ¥价格 · kcal」，吃完自动休息。睡梦中来单会被香味叫醒
5. 用户问「猫今天吃了多少」→ Agent 读 `McdPet.stats()` 报数：几餐、多少 kcal、花多少钱（数据全程 MCP 真实值）

### 工作流 C：查账/营养咨询

用户问热量 → Agent 调 `list-nutrition-foods` 返回官方营养表（160 个餐品的能量/蛋白/脂肪/碳水/钠/钙），结合猫的记账给参考。

## 数据真实性声明（参赛答辩用）

| 数据 | 来源 | 口径 |
|---|---|---|
| 12 道菜名称/编码/价格 | `query-meals`（门店 1420257） | MCP 实时返回，价格可能随活动浮动 |
| 12 道菜 kcal | `list-nutrition-foods` 官方营养表 | 2026-10-10 拉取快照，标注在 menu_map.json 的 nutritionSource |
| 12 个食物道具图 | 原创生成的玩具质感插画 | 非麦当劳官方素材，规避版权风险 |

**设计原则：一个数字都不编。** 菜名/编码/价格/热量全部可溯源到 MCP 调用记录。

## 四种跑法

1. **WorkBuddy 对话内联**（主形态）— Agent `present_files` 打开 index.html，预览面板直接交互
2. **桌面悬浮桌宠（WorkBuddy & Codex 通用）** — `python tools/desktop_pet.py`，无边框透明置顶可拖动（tkinter 版，无需 WebView2；单实例锁 8799）。交互与网页版完全一致：单击=左右投喂/睡觉按钮、投喂=12 餐品图案托盘、双击=切换动作、顶部状态框+底部记账框。位置持久化 `~/.codex/pets/mcd-maimai/desktop_pet_pos.json`，WorkBuddy 和 Codex 两边跑的是同一只猫、同一套交互
3. **Codex 桌面桌宠** — 装进 `~/.codex/pets/mcd-maimai/`，选择器选「麦麦猫」
4. **独立网页** — 双击 index.html 或 `python tools/order_server.py --open`

## 目录

```
mcd-cat-pet/
├── pet.json              ★ 桌宠源配置：换形象/换动作/换行序改这里
├── menu_map.json         ★ 麦当劳真实菜单 → 动画道具映射（含编码+kcal+nutritionSource）
├── index.html            网页桌宠（Canvas 精灵动画 + 状态机 + localStorage 存档 + MCP 事件轮询）
├── assets/
│   ├── frames/<state>/   网页版五状态帧：idle/eating/drinking/happy/sleeping
│   └── food/<id>.png     12 个透明底食物道具
├── run-codex/frames/     Codex 九行帧（含镜像派生的 running-left）
├── dist/                 构建产物：spritesheet.png / .webp
├── qa/                   质检拼版与动图预览
└── tools/                见下表
```

| 脚本 | 作用 |
|---|---|
| `order_server.py` | 点餐桥：托管网页 + 订单事件接口（`--open` 自动开浏览器） |
| `order_hook.py` | MCP 下单成功后调用，把订单推给点餐桥（断线自动落盘补发） |
| `desktop_pet.py` | 桌面悬浮桌宠：tkinter+PIL 无边框透明置顶小窗，全交互（单击侧边按钮+餐品图案托盘+顶部状态框+底部记账框；用系统 Python 3.11 跑；`desktop_pet_webview.py` 是 pywebview 备用版） |
| `build_spritesheet.py` | 帧目录 → Codex 契约图集（体积优化 + 契约自检 + 自动清蓝/青残渣） |
| `despill_blue.py` | 蓝/青 spill + 键控 dropout 像素清理（`--check` 只统计） |
| `install_codex.py` | 装进 `~/.codex/pets/`，并修好浮窗总开关；`--check-only` 体检 |
| `slice_codex.py` | Codex 条带 → 透明帧（支持模型画成 2×N 网格） |
| `slice_strips.py` | 网页版切帧（帧数自适应、统一取行、去杂点） |
| `process_food.py` | 食物道具边框洪泛抠底 |
| `grab_latest.py` | 按 mtime 抓取生图产出（并发会串位，必须串行） |

## WorkBuddy Agent 使用规则

1. 识别到投喂/睡觉/切换动作意图 → `present_files` 打开 index.html 并告知按钮位置
2. 用麦当劳 MCP 下单成功 → **立即跑 `order_hook.py`**（写进 ~/.codex/AGENTS.md 与项目 AGENTS.md 的全局规则）
3. 用户问记账 → 若页面在预览面板打开，指导用户看底部统计；或 Agent 口头播报 McdPet.stats()
4. 点餐桥（order_server.py）未启动时先启动：`python tools/order_server.py`（后台）
5. 猫的存档在 localStorage（预览面板内持久），reset 可清零

## 与麦当劳 MCP 联动链路

```
query-nearby-stores → query-meals → calculate-price → create-order → query-order
                                                            ↓
                                    python tools/order_hook.py --code <编码>
                                                            ↓
                            order_server.py（本地点餐桥）→ 桌宠 2 秒内开吃
```

`onOrdered` 三层兜底：精确匹配 → 编码匹配 → 关键词猜类型（饮品词走 drinking，其余走 eating + emoji）。**命中不到也不会静默失败。**

网页侧兜底 API（无服务器时直接调用）：

```js
McdPet.onOrdered("麦辣鸡腿汉堡")   // 或传编码 "1440"，或传对象 {name, price, kcal}
McdPet.stats()                     // {kcal, cost, meals, fat, log[]}
McdPet.feed(id) / .sleep() / .reset()
```

## 安装到 Codex（通用三步）

```bash
python tools/build_spritesheet.py    # 1. 构建图集
python tools/install_codex.py        # 2. 安装 + 修开关
# 3. 完全退出 Codex 再重开 → 桌宠选择器选「麦麦猫」
```

**选了却看不到？** Codex 浮窗总开关 `electron-avatar-overlay-open`（在 `~/.codex/.codex-global-state.json`）必须是 true。安装脚本自动修，但必须先完全退出 Codex。详见 TROUBLESHOOTING.md。

## Codex 九行契约（行序固定）

| 行 | 状态 | 动作 |
|---|---|---|
| 0 | idle | 呼吸眨眼 |
| 1 | running-right | 向右小跑去上班 |
| 2 | running-left | 向左小跑（由 row1 镜像） |
| 3 | waving | 举爪招手迎客 |
| 4 | jumping | 蹲跳接汉堡 |
| 5 | failed | 耷耳朵委屈 |
| 6 | waiting | 双爪合十讨食 |
| 7 | running | **抱汉堡埋头苦干**（Codex 干活时的默认动作） |
| 8 | review | 歪头审视 |

画布 1536×1872（8 列 × 9 行，格 192×208），RGBA PNG，透明区 RGB 必须为 0。

## 换成你自己的宠物

1. 帧按 `assets/frames-<主题>/<状态>/f00.png…` 放好
2. 改 `pet.json` 的 `dir` / `displayName` / `description`（`mirror: true` 自动生成左右反向行）
3. `python tools/build_spritesheet.py && python tools/install_codex.py`

## 新增动画 / 食物的踩坑清单

1. 生图 **quality 用 `medium`** —— `high` 经常限流，medium 走另一个模型不受影响
2. **一次只发一个生图请求** —— 并发会让多张图串到同一目录甚至互相覆盖；每生成一张立刻 `python tools/grab_latest.py <id> "assets/food/<id>.png"` 归位
3. 模型常把「8 帧单行」画成 5–6 帧，甚至画成 **2×N 网格** —— 切帧器已做行带检测
4. **白底条带直接判废** —— 猫的白胸白爪会跟白底连通，抠底会把白毛一起吃掉，必须重生成成绿底/蓝底
5. `background:"transparent"` 参数实测无效，产出是不透明浅底 —— 必须跑 `process_food.py` 抠底
6. 生成图右下角可能有工具水印 —— 在纯背景区用色键色矩形盖掉

## 合规红线（改提示词/文案前必读）

- 热量**只做记录与可视化**，禁止输出减脂建议、健康评价或「少吃更健康」类话术
- kcal 数据来自 `list-nutrition-foods` 官方营养表快照，页面标注「营养参考值，以门店实际为准」
- 交互只保留「投喂」「睡觉休息」两个主动动作 + 双击切换 + 自动闲逛循环，全部是拟猫行为的可爱化表达，无排泄物等不雅元素
- 价格以 MCP 实时返回为准，代码里的是快照
- 不使用麦当劳官方图片素材，食物道具为原创生成的玩具质感插画

## 已知限制

- 网页版「变胖」用横向缩放近似（每级 +4.5%），专属胖猫帧在 P2 路线图
- WorkBuddy 没有 Codex 那样的常驻挂件机制，对话内联是随对话流出现（桌面悬浮窗补足常驻需求）
- Codex 桌宠改帧后需要「完全退出 → 重开」才生效，热重载不支持
