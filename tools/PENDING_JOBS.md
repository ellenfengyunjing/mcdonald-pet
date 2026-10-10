# 麦麦猫 · 待生成任务手册（生图配额恢复后执行）

> 背景：2026-10-09 15:52 ImageGen 触发 429 限流，**20:42 UTC+8 重置**。
> 已完成：`base`（基础形象）、`idle`、`eating`（各 6 帧，已切片）。
> 本手册包含全部剩余提示词，逐条喂给 ImageGen 即可。

## 执行流程（每生成一条）

1. 用下方提示词调 ImageGen（参数：`size:"1536x1024"`, `quality:"high"`, `input_fidelity:"high"`，
   `image1=run/references/canonical-base.png`, `image2=run/references/layout-guides/<state>.png`,
   `image3=run/references/reference-01.png`, `output_dir=generated/`）
2. 视觉 QA：帧数（6 或 8 都行）、身份一致、无食物入画、无参考线残留
3. 把文件路径登记进 `tools/strip_sources.json`（state → 相对路径）
4. 重跑 `python tools/slice_strips.py` —— 自动切片+抠蓝底+去杂点，帧数自适应
5. 刷新 `index.html` 确认新动画出现

## 一、剩余动画条带（P0 四条）

### drinking（喝东西）

```text
Create one horizontal animation strip for pet `mcd-maimai`, state `drinking`.

Use the attached canonical base for identity. Use the attached layout guide only for slot count, spacing, centering, and padding; do not draw the guide.

Output exactly 6 full-body frames in one left-to-right row on flat pure blue #0000FF. Treat the row as 6 invisible equal-width slots: one centered complete pose per slot, evenly spaced, with no overlap, clipping, empty slots, labels, or borders.

Identity: same pet in every frame: a chunky orange-and-white tabby cat in a tiny red Santa hat. Preserve silhouette, face, proportions, markings, palette, material, style from the canonical base.
Style: glossy vinyl 3D toy figure look with soft baked-in shading and no cast shadows; chubby rounded proportions; big round amber eyes.
Animation continuity: keep apparent pet scale and baseline stable within the row.

State action: Generic drinking loop with NO cup, straw or liquid visible anywhere: the head tilts slightly downward-forward toward an invisible spout just in front of the mouth, tongue laps repeatedly, throat swallows, then a brief satisfied pause with eyes closing halfway. Head anchor position must stay consistent across all frames so a cup sprite can be overlaid at the mouth during playback.

State requirements:
- CRITICAL: absolutely NO cup, no straw, no can, no liquid, no splash anywhere in any frame.
- Keep the head angle and mouth anchor position consistent across all frames.
- Show drinking through tongue lapping, throat swallowing and a satisfied pause only.
- No detached effects, no sparkle, no motion marks, no hearts.

Clean extraction: crisp opaque edges, safe padding, no scenery, text, guide marks, checkerboard, shadows, glows, motion blur, dust, detached effects, stray pixels, or chroma-key colors inside the pet.
```

### sleeping（打呼睡觉）

```text
Create one horizontal animation strip for pet `mcd-maimai`, state `sleeping`.

Use the attached canonical base for identity. Use the attached layout guide only for slot count, spacing, centering, and padding; do not draw the guide.

Output exactly 6 full-body frames in one left-to-right row on flat pure blue #0000FF. Treat the row as 6 invisible equal-width slots: one centered complete pose per slot, evenly spaced, with no overlap, clipping, empty slots, labels, or borders.

Identity: same pet in every frame: a chunky orange-and-white tabby cat in a tiny red Santa hat. Preserve silhouette, face, proportions, markings, palette, material, style from the canonical base.
Style: glossy vinyl 3D toy figure look with soft baked-in shading and no cast shadows; chubby rounded proportions; big round amber eyes.
Animation continuity: keep apparent pet scale and baseline stable within the row.

State action: Cozy napping loop: the cat sits with body slightly slumped and rounded, eyes fully closed, a stretch of the front paws extending forward then tucking back, slow deep breathing with the chest and belly rising and falling, tiny head nods, and the mouth opening slightly in a sleepy yawn in one middle frame. The Santa hat may tilt slightly but must never fall off.

State requirements:
- Eyes stay fully closed in every frame; do not open them.
- Breathing motion must be visible and gentle: chest and belly rise and fall across the frames.
- Include one slow paw stretch and one small yawn; everything else stays curled and still.
- No Z letters, no bubbles, no musical notes, no detached effects, no props.

Clean extraction: crisp opaque edges, safe padding, no scenery, text, guide marks, checkerboard, shadows, glows, motion blur, dust, detached effects, stray pixels, or chroma-key colors inside the pet.
```

### litter（上厕所埋猫砂）

```text
Create one horizontal animation strip for pet `mcd-maimai`, state `litter`.

Use the attached canonical base for identity. Use the attached layout guide only for slot count, spacing, centering, and padding; do not draw the guide.

Output exactly 6 full-body frames in one left-to-right row on flat pure blue #0000FF. Treat the row as 6 invisible equal-width slots: one centered complete pose per slot, evenly spaced, with no overlap, clipping, empty slots, labels, or borders.

Identity: same pet in every frame: a chunky orange-and-white tabby cat in a tiny red Santa hat. Preserve silhouette, face, proportions, markings, palette, material, style from the canonical base.
Style: glossy vinyl 3D toy figure look with soft baked-in shading and no cast shadows; chubby rounded proportions; big round amber eyes.
Animation continuity: keep apparent pet scale and baseline stable within the row.

State action: Innocent burying pantomime performed on an invisible spot on the ground: the cat crouches, then makes alternating digging motions with one front paw sweeping sideways across the ground, glances around with a slightly guilty look, then gives a final satisfied pat and sits back upright, ending with a small proud blink.

State requirements:
- CRITICAL: absolutely NO litter box, no sand, no soil, no waste, no poop, no puddle anywhere in any frame. The cat digs at an empty invisible ground spot.
- Keep the digging motions readable: clear paw sweep with body weight shifting.
- The guilty glance (looking left and right) must appear in exactly one frame.
- End the loop back in a normal sitting pose similar to the first frame.
- No detached effects, no dust clouds, no sparkles.

Clean extraction: crisp opaque edges, safe padding, no scenery, text, guide marks, checkerboard, shadows, glows, motion blur, dust, detached effects, stray pixels, or chroma-key colors inside the pet.
```

### happy（满足）

```text
Create one horizontal animation strip for pet `mcd-maimai`, state `happy`.

Use the attached canonical base for identity. Use the attached layout guide only for slot count, spacing, centering, and padding; do not draw the guide.

Output exactly 6 full-body frames in one left-to-right row on flat pure blue #0000FF. Treat the row as 6 invisible equal-width slots: one centered complete pose per slot, evenly spaced, with no overlap, clipping, empty slots, labels, or borders.

Identity: same pet in every frame: a chunky orange-and-white tabby cat in a tiny red Santa hat. Preserve silhouette, face, proportions, markings, palette, material, style from the canonical base.
Style: glossy vinyl 3D toy figure look with soft baked-in shading and no cast shadows; chubby rounded proportions; big round amber eyes.
Animation continuity: keep apparent pet scale and baseline stable within the row.

State action: Short satisfied celebration after a meal: the cat sits up a little taller, closes its eyes happily with cheeks pushed up, does one small contented wiggle of the shoulders, licks its lips with a tiny tongue flick, and puffs its chest proudly, ending in a calm content sit.

State requirements:
- Keep the pet seated in place; no jumping, no standing, no walking.
- Show happiness through closed happy eyes, lip licking, chest puff and a small wiggle only.
- No hearts, no sparkles, no music notes, no detached effects, no props.

Clean extraction: crisp opaque edges, safe padding, no scenery, text, guide marks, checkerboard, shadows, glows, motion blur, dust, detached effects, stray pixels, or chroma-key colors inside the pet.
```

### （可选）sad / running-right / running-left

模板同上，动作描述替换为：
- `sad`：ears slightly flattened, head lowered, eyes looking up with a pleading gaze, tail drooping and giving one slow flick, small head shake. （P2，可不做）
- `running-right` / `running-left`：fast trot to the right/left, legs cycling, body leaning into the run, ears pressed back slightly. （P2，可不做）

## 二、食物道具（12 个，透明背景）

> 道具不用色键，直接 `background:"transparent"`。每张单独生成。
> 通用模板（替换 `{食物}` 与 `image1` 可不带）：

```text
Create a single food prop sprite on a fully transparent background: {食物描述}.

Style: glossy vinyl 3D toy figure look matching a chubby orange-and-white cartoon cat mascot — smooth rounded forms, soft baked-in shading, no cast shadows, saturated appetizing colors, crisp clean silhouette.

Composition: single item centered, three-quarter front view slightly tilted, occupying about 70% of the frame, no plate, no hands, no table, no background elements, no text, no watermark, no drop shadow onto background.

Edge quality: crisp opaque edges with clean alpha, no halo, no stray semi-transparent pixels around the silhouette.
```

12 张的具体替换（size 用 `1024x1024`，无参考图纯文生图）：

| id | 文件名 | 食物描述 |
|---|---|---|
| bigmac | `assets/food/bigmac.png` | a classic double-decker sesame bun hamburger with two beef patties, melted cheese, lettuce and sauce |
| mccrispy | `assets/food/mccrispy.png` | a crispy fried chicken sandwich burger with lettuce on a sesame bun |
| grilled | `assets/food/grilled.png` | a grilled chicken sandwich burger with lettuce on a plain bun |
| dblcheese | `assets/food/dblcheese.png` | a double cheeseburger with two beef patties and two slices of melted cheese on a sesame bun |
| mcnuggets5 | `assets/food/mcnuggets5.png` | a small open red paper box holding five golden crispy chicken nuggets |
| fries-m | `assets/food/fries-m.png` | a red paper fry carton filled with golden french fries |
| mcflurry | `assets/food/mcflurry.png` | a clear plastic cup of swirled soft-serve ice cream mixed with cookie crumbs, topped with a small spoon |
| cone | `assets/food/cone.png` | a soft-serve ice cream cone with a perfectly swirled white peak on a golden wafer cone |
| taropie | `assets/food/taropie.png` | a golden crispy fried turnover pie with crimped edges, purple taro filling peeking from the seam |
| corn | `assets/food/corn.png` | a clear cup of sweet corn kernels with a tiny spoon |
| coke-m | `assets/food/coke-m.png` | a paper cup of fizzy cola with a lid and a striped straw, condensation droplets on the cup |
| coffee-m | `assets/food/coffee-m.png` | a paper cup of latte coffee with a lid and a brown heat sleeve, small steam wisps |

道具生成后无需切片，直接放入 `assets/food/<id>.png`，刷新页面即生效。

## 三、P0 之外的扩展（后续再说）

- sad / running-left / running-right 动画
- 更多食物道具（早餐系列、派系列全口味、脆汁鸡…）
- 猫咪体型随 fat 值换专属「胖猫」基础帧（当前用 CSS 缩放近似）
