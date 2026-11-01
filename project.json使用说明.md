# project.json 使用说明

> 一份配置驱动一条视频。`gen_draft.py` 只读这个文件，换一本书不用改代码。

---

## 快速开始

```bash
cd 05_输出结果/语音生成

python gen_draft.py --dry-run          # 先校验，不调接口、不建草稿
python gen_draft.py                    # 确认无误后真跑
python localize_draft.py <draft_id>    # 装到剪映后本地化（需先关剪映）
```

`gen_draft.py` 会自动往上找 `project.json`（同目录 → 上两级 → 当前目录），
也可以显式指定：`python gen_draft.py --project D:/新项目/project.json`。

---

## 字段全表

### 顶层

| 字段 | 必填 | 说明 |
|---|---|---|
| `book` | ✅ | 书名，仅用于日志和结果记录 |
| `draft_name` | | 草稿显示名，安装到剪映后本地化时用 |
| `canvas` | ✅ | `{"width":1080,"height":1920}`，竖屏固定 1080×1920 |
| `asset_base` | ✅* | 素材公网前缀。**素材写相对路径时必须有**；全部写绝对 URL 时可省 |
| `shots` | ✅ | 画面数组，见下 |
| `overlays` | | 叠加层数组（书名层 / 书封层等），见下 |
| `audios` | | 音频数组，见下 |
| `captions` | | 字幕配置，见下 |
| `output.result` | | 结果落盘路径，默认 `draft_result.json` |

### shots[]（画面）

| 字段 | 必填 | 说明 |
|---|---|---|
| `image` | ✅ | 素材路径。相对 project.json 所在目录，**或**完整 http(s) 地址 |
| `start` / `end` | ✅ | **秒**（可写小数）。写成 4 就是 4 秒，脚本自动转微秒 |
| `transition` | | 转场名，如 `"叠化"`。留空 `""` 表示无转场（最后一个镜头通常留空） |
| `transition_duration` | | 转场时长，**秒**，默认 0.5 |

### audios[]（音频）

| 字段 | 必填 | 说明 |
|---|---|---|
| `audio` | ✅ | 路径规则同 `image` |
| `start` / `end` | ✅ | 秒。多段音频**首尾相接**分配，不要留缝 |
| `volume` | | 0—1，默认 1.0 |

### captions（字幕）

| 字段 | 说明 |
|---|---|
| `source` | `timeline_json`（默认）/ `srt` / `inline` |
| `path` | 前两种模式下必填，相对 project.json 所在目录 |
| `items` | `source=inline` 时用，`[{start, end, text}]`，时间单位秒 |
| `style` | 透传给 `add_captions` 的样式参数，见下 |

**三种来源的适用场景**

| source | 什么时候用 |
|---|---|
| `timeline_json` | 有 TTS 时长清单（`语音时长清单.json`），**最常用**，时间最准 |
| `srt` | 只有字幕文件（剪映/第三方工具导出的 SRT） |
| `inline` | 手写字幕，条数少或需要逐条微调 |

`timeline_json` 兼容两种结构，自动识别：
- `{"segments":[{"lines":[{"abs_start_sec","abs_end_sec","text"}]}]}` ← 本项目 TTS 脚本产出
- `{"captions":[{"start","end","text"}]}`

**style 常用参数（本项目验证过的组合）**

```json
{
  "text_color": "#ffffff",
  "border_color": "#000000",
  "alignment": 1,
  "font": "SourceHanSansCN-Bold",
  "font_size": 20,
  "transform_y": -1240,
  "bold": true,
  "has_shadow": true
}
```

### ⚠️ transform_y 的真实换算（接口文档写反了）

接口文档说「正值向下，负值向上，单位像素」，**实测不是**。剪映读的是
`clip.transform.y`，这个值是接口把 `transform_y ÷ 1920` 写进去的，
而剪映按「**1.0 = 半个画布高（960px）**、**正值向上**」来解释它。

推导出的唯一正确公式：

```
画布Y = 960 − transform_y ÷ 2
transform_y = (960 − 期望画布Y) × 2
```

两个实测点验证过（1204×914 截图逐像素测量）：

| 配置值 | 写入的 clip.transform.y | 实际渲染画布Y | 直观位置 |
|---|---|---|---|
| `-320` | −0.1667 | **1120**（58%） | 画面中间 ← 第一次踩坑 |
| `+620` | +0.3229 | **650**（34%） | 偏上 ← 第二次踩坑 |
| `-1240` | −0.6458 | **1580**（82%） | 底部 ✅ |

**常用取值**

| 目标位置 | transform_y |
|---|---|
| 画面中部 50% | 0 |
| 底部 80% | −1150 |
| **底部 82.3%（本片用）** | **−1240** |
| 底部 85% | −1340 |

判断口诀：**要往下走，就写负数；数值 ≈ 想离中心多远 × 2。**

**text_cleanup（字幕文本清理）**

| 字段 | 默认 | 说明 |
|---|---|---|
| `strip_tail_punct` | `true` | 去掉行尾的 `，。；：、` 等。问号不在清除名单里——它承载语气 |
| `strip_book_marks` | 未开 | 去掉 `《》〈〉「」`，书名那行会变成纯文字 |

只清**行尾**标点，句中标点保留。短字幕里行尾逗号句号是纯视觉噪音，去掉后更干净。

### overlays[]（叠加层）

压在背景轨之上的独立图层，每层单独一次 `add_images` 调用。

| 字段 | 说明 |
|---|---|
| `name` | 层名，只用于日志 |
| `image` | 路径规则同 `shots[].image`。**建议用 1080×1920 透明 PNG**，这样一次铺满画布，不需要算 scale |
| `start` / `end` | 秒。`end` 大于全片长度也没关系，会自动按素材时长截断 |
| `alpha` | 0—1，默认 1.0，可省 |
| `scale_x` / `scale_y` / `transform_x` / `transform_y` | 可选，**层内所有图片共用**（接口级参数），一般不需要写 |

本项目用法：

```json
"overlays": [
  { "name": "标题层", "image": "00_原始素材/叠加层/标题层_1080x1920.png", "start": 0, "end": 61 },
  { "name": "书封层", "image": "00_原始素材/叠加层/书封层_1080x1920.png", "start": 0, "end": 8 }
]
```

**为什么书名/书封要做成图片层，而不是剪映文字轨或直接贴在背景图上**

- 剪映文字轨：`add_captions` 的 `text_color`/`font_size`/`transform_y` 都是接口级参数，一次调用只能一种样式。书名（白 98px）+ 作者（金 45px）无论怎么拆都要两条轨，且字体是否被剪映识别不可控。
- 贴进背景图：每个镜头都要重新合成，改一个字要重跑全部 N 张图，剪映里也动不了。
- 独立透明层：一次 `add_images` 就位，位置像素级可控，改书名只需重跑 `gen_overlay.mjs`。

生成命令见 `tools/`：

```bash
node tools/gen_bookcover.mjs --cover <无字底图> --title "<书名>" --author "<作者>" --out <书封.png>
node tools/gen_overlay.mjs --title "<书名>" --author "<作者>" --cover <书封.png> --outdir 00_原始素材/叠加层
```

---

## 换一本书要改哪些

只改 `project.json` 一个文件：

1. `book` 和 `draft_name` 换成新书名
2. `asset_base` 换成新素材的仓库/图床前缀
3. `shots` 按新分镜重写（镜头数不限，时间跟音频走）
4. `audios` 换成新配音的三段（或任意段数）
5. `captions.path` 指向新的时长清单 JSON

**不用动的**：画布尺寸、转场参数、字幕样式、接口地址、调用顺序。

---

## 脚本会自动帮你检查

`--dry-run` 会跑这些校验，有问题直接拦下来，不会白建草稿：

| 检查 | 处理 |
|---|---|
| `shots` 为空 | 致命，中止 |
| 第一个镜头不从 0 秒开始 | 提醒 |
| 镜头之间有空档 / 重叠 | 提醒（不中止，可能是有意的） |
| `end <= start` | 致命，中止 |
| 素材写相对路径但没配 `asset_base` | 致命，中止 |
| 本地找不到素材文件 | 提醒（已推到公网则忽略） |
| 字幕来源文件不存在 / 结构不认识 | 抛出异常，中止 |

---

## 加了 `--dry-run` 之后，一次典型的迭代长这样

```bash
# 1. 改 project.json
# 2. 看计划对不对
python gen_draft.py --dry-run

# 3. 想核对字幕逐条时间，加参数
python gen_draft.py --dry-run --show-captions

# 4. 没问题，真跑
python gen_draft.py
```

---

## 常见错误对照

| 报错 | 原因 | 解法 |
|---|---|---|
| `素材 xxx 是相对路径，但 project.json 没配 asset_base` | 漏了前缀 | 补 `asset_base` |
| `字幕来源文件不存在` | path 写错或用了绝对路径 | 检查相对位置 |
| `无法识别的字幕 JSON 结构` | JSON 里既没有 `segments` 也没有 `captions` | 换 `source: "srt"` 或改数据源 |
| `add_images 业务失败` | 素材 URL 服务端拉不到 | 确认图片能在公网直接访问 |
| `add_captions 业务失败` | style 里有接口不认的字段 | 删掉多余参数，只留上面验证过的 7 个 |

---

## 时间单位说明（最容易错的地方）

**project.json 里全部写秒**，例如：

```json
{ "image": "封面.png", "start": 0, "end": 4 }
```

脚本内部转成微秒 `{"start": 0, "end": 4000000}` 再发给接口。
你不用记 1000000 这个数，也不该在配置文件里写微秒。
