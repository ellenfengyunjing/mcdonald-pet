# MCP 集成说明

> 本文件说明本项目实际使用了麦当劳 MCP 的哪些 Server / Tool、调用流程是什么、以及它带来了什么业务价值。
> 所有调用均为真实调用，记录于 2026-10-09。

---

## 一、使用的 MCP Server

| 项 | 值 |
|---|---|
| Server | `mcd-order`（麦当劳官方 MCP） |
| 传输 | `streamablehttp` |
| 端点 | `https://mcp.mcd.cn` |
| 认证 | `Authorization: Bearer ${MCD_MCP_TOKEN}`（环境变量注入，见 `mcp-config.example.json`） |
| Token 申请 | https://open.mcd.cn/mcp/doc |

---

## 二、实际调用的 Tool

### 已真实调用（本项目开发过程中）

| Tool | 调用目的 | 真实结果 |
|---|---|---|
| `query-nearby-stores` | 定位门店 | 深圳八卦岭周边 5 家门店，取到 `storeCode`（如八卦二路 `1420257`，24 小时营业） |
| `query-meals` | 拉取真实菜单 | 拿到门店全量餐品的 `code` / `name` / `currentPrice`，**桌宠的 12 个道具与价格全部来自这次返回** |
| `query-store-coupons` | 查门店可用券 | 5 家门店一致，两张新人专享 7 折券 |
| `available-coupons` | 查可领券 | 麦麦省 9 张（麦旋风任选 / 薯薯任选 / 9.9 冰美式 …） |
| `auto-bind-coupons` | 一键领券 | 9 张全部领取成功，0 失败 |
| `query-my-coupons` | 核销卡包 | 卡包 10 张可用，含有效期与适用时段 |
| `campaign-calendar` | 活动日历 | 10 月全国活动（韩式蘸酱上新 / G-DRAGON 联名 / 9.9 早餐两件套 …） |
| `now-time-info` | 对齐服务端时间 | 用于判断券的可用时段 |

### 桌宠联动链路中使用的 Tool

| Tool | 在链路中的角色 |
|---|---|
| `query-nearby-stores` | 第 1 步：确定门店，拿到 `storeCode` |
| `query-meals` | 第 2 步：拿到商品 `code` / `name` / 价格，喂给桌宠的菜单映射 |
| `calculate-price` | 第 3 步：算价，对比用券前后 |
| `create-order` | 第 4 步：下单（**必须经用户二次确认，本项目不代下单**） |
| `query-order` | 第 5 步：查订单状态，确认后触发桌宠进食 |

---

## 三、调用流程

```text
┌─────────────── Agent（WorkBuddy / Codex）编排 ───────────────┐

  用户："帮我点一份麦辣鸡腿汉堡，八卦二路那家"
        │
        ▼
  ① query-nearby-stores  ──► storeCode = 1420257
        │
        ▼
  ② query-meals          ──► code=1440  name="麦辣鸡腿汉堡"  price=22.5
        │                      └─► 与 menu_map.json 比对，命中道具 mccrispy
        ▼
  ③ calculate-price      ──► 原价 / 用券价 两个数字
        │
        ▼
  ④ 【人工确认卡点】把门店、餐品、用券、实付金额列给用户
        │  用户说"确认下单"
        ▼
  ⑤ create-order         ──► 生成订单 + 支付链接（用户自己在 App 付）
        │
        ▼
  ⑥ query-order          ──► 确认订单状态
        │
        ▼
  ⑦ python tools/order_hook.py --code 1440
        │                     └─► 查 menu_map.json 补全价格/热量
        │                         POST http://127.0.0.1:8787/api/order
        │                         （点餐桥没开 → 落盘 pending，下次启动补发）
        ▼
┌──────── 呈现层（网页桌宠，2 秒轮询事件）────────┐
│  猫开始啃麦辣鸡腿汉堡 + 弹「¥22.5 · 485 kcal」   │
│  吃完满足抹嘴 → 自己眯一会儿 → 回到闲逛           │
└──────────────────────────────────────────────────┘
```

### 一个重要的诚实说明

**桌宠本身不直接连接 MCP。** 它是渲染层：浏览器页面和 Codex 桌面挂件都拿不到 MCP 凭据，也不该拿。

真实的调用关系是：**Agent 编排 MCP，点餐桥传递事件，桌宠呈现结果**。Agent 拿到 `create-order` 成功回执后，调用 `tools/order_hook.py` 把订单推给本地点餐桥（`tools/order_server.py`），网页桌宠轮询到事件后把结果"演"出来。

这不是绕过 MCP 做假点餐 —— 恰恰相反：

- 菜单数据来自 `query-meals` 真实返回，商品编码可回查
- 下单走真实 `create-order`，真实支付，不模拟
- 桌宠只是把「下单成功」这件过去只有一行 JSON 回执的事，变成看得见的反馈

### 点餐桥的技术细节

- `order_server.py`（纯标准库）：托管网页 + `POST /api/order` + `GET /api/events?after=N`；事件 ID 用毫秒时间戳保证单调，内存只留最近 50 条 / 1 小时内
- `order_hook.py`：`--code` 自动查 `menu_map.json` 补全；服务没开就落盘 `~/.codex/pets/mcd-maimai/orders_pending.jsonl`，服务启动时自动补发
- 页面游标持久化（localStorage）：刷新页面不重放旧订单，首次访问快进到最新事件（不补吃历史）
- 无浏览器 / 无 Python 时，`McdPet.onOrdered(name)` 的页面直调 API 依然可用

---

## 四、菜单映射的真实依据

`menu_map.json` 里的 12 条映射，全部来自 `query-meals`（`storeCode=1420257`，`orderType=1`，`beType=1`）的真实返回字段：

| 商品编码 | MCP 返回的名称 | MCP 返回的价格 | 桌宠道具 | 动画 |
|---|---|---|---|---|
| `1100` | 巨无霸 | ¥26.0 | `bigmac` | eating |
| `1440` | 麦辣鸡腿汉堡 | ¥22.5 | `mccrispy` | eating |
| `1406` | 板烧鸡腿堡 | ¥23.5 | `grilled` | eating |
| `1120` | 双层吉士汉堡 | ¥23.0 | `dblcheese` | eating |
| `1401` | 麦乐鸡 | ¥14.0 | `mcnuggets5` | eating |
| `4810` | 薯条 | ¥14.5 | `fries-m` | eating |
| `9900008754` | 经典麦旋风 | ¥15.5 | `mcflurry` | eating |
| `515837` | 圆筒冰淇淋 | ¥5.0 | `cone` | eating |
| `9900008752` | 派 | ¥8.0 | `taropie` | eating |
| `4437` | 玉米杯 | ¥13.0 | `corn` | eating |
| `9900008751` | 可乐 | ¥9.5 | `coke-m` | drinking |
| `507409` | 麦咖啡™奶铁 | ¥13.9 | `coffee-m` | drinking |

> kcal 列来自麦当劳 MCP `list-nutrition-foods` 官方营养表快照（2026-10-10），来源与拉取日期已标注在 `menu_map.json` 的 nutritionSource 字段，仅用于趣味记账。

**未命中的餐品怎么办**：`onOrdered` 有关键词兜底（含「可乐/咖啡/奶铁/红茶/果汁…」等饮品词走喝动画，其余走吃动画 + emoji 占位）。所以门店上新了新餐品，猫也不会哑掉。

---

## 五、业务价值

**1. 给下单这件事补上「反馈层」。**
MCP 让点餐变成几行 JSON。对开发者这是效率，对使用者却是「我点了个寂寞」——没有小票、没有包装袋、没有任何实体反馈。桌宠把这个缺口补上：你点了什么，有个东西真的替你吃掉它。

**2. 把冷数据变成情绪触点。**
`query-meals` 返回的是 `{"code":"1440","name":"麦辣鸡腿汉堡","currentPrice":"22.5"}`。同样的数据，一个是表格里的一行，一个是一只猫抱着汉堡啃。后者才是会被截图转发的那个。

**3. 降低 MCP 的调试枯燥感。**
接 MCP 的过程是反复调 `query-meals` / `calculate-price` 看 JSON。有个活物在旁边同步反应（你在算价它就在等、任务失败它就耷耳朵），长时间调试的心理成本明显不同。

**4. 给麦当劳 MCP 生态提供「呈现层」的范例。**
现有麦当劳 MCP 项目几乎全是工具型：查门店、算价、下单、算热量。缺少把 MCP 结果**可视化、人格化**的那一层。本项目证明这一层可以很轻（一个 HTML + 一批精灵帧）但很有存在感。

---

## 六、合规与边界

- 不代用户下单、不代支付。`create-order` 必须由用户二次确认，支付在麦当劳 App 完成。
- 不使用、不转存麦当劳官方商品图片，食物道具为原创生成的 3D 玩具质感插画。
- 只使用 MCP 公开返回的字段，不做逆向、不爬取、不绕过限流。
- 热量数字来自 MCP 官方营养表快照，不提供任何饮食指导（详见 `CONTEST_DECLARATION.md`）。
