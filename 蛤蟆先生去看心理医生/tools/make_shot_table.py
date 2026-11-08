# -*- coding: utf-8 -*-
"""把 project.json + 语音时长清单 合成 02_分镜与画面/分镜表.csv（给剪辑核对用）。

行归属规则：某条字幕的绝对起点落在哪个镜头的时间区间里，就归哪个镜头。

用法：python tools/make_shot_table.py --project .
"""
import os
import csv
import json
import argparse

os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(os.sys.stdout, "reconfigure"):
    os.sys.stdout.reconfigure(encoding="utf-8")

SHOT_META = [
    ("钩子", "黄昏英式乡村小屋外景，唯一亮着的木框窗溢出暖黄灯光，前景木桌一杯凉透的红茶，草地浮薄雾"),
    ("痛点A", "塌陷的单人旧沙发，深绿羊毛毯皱成一团堆在扶手，地毯上散落报纸与一只脱掉的拖鞋，阴天冷灰侧光"),
    ("痛点B", "餐桌俯视，米色亚麻桌布，两只茶杯一只留水渍圆痕、一只凉透结膜，第三副座位空着，午后斜光"),
    ("引入书", "旧书桌局部：摊开的空白笔记本、蘸水钢笔、亮着的黄铜台灯形成光锥，空木椅被拉开、椅面有坐压凹陷"),
    ("观点1", "老式木柜三层敞开格：泰迪熊／金丝边眼镜／黄铜指南针，顶光在每层形成独立光区与短投影"),
    ("观点2", "狭窄旧走廊纵深透视，墙纸泛黄开裂，尽头半开的门透出更亮的光，墙上歪斜空相框"),
    ("反转", "一张旧纸页落在地板上，纸面涂改痕迹与折角但看不清字迹，被风掀起一角，斜光落在纸页偏右"),
    ("收尾", "床头小柜特写，暖光小台灯、合着的厚书、一杯温水，窗外深蓝夜色与室内暖光对比"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    args = ap.parse_args()
    proj_dir = os.path.abspath(args.project)

    proj = json.load(open(os.path.join(proj_dir, "project.json"), encoding="utf-8"))
    data = json.load(open(os.path.join(proj_dir, proj["captions"]["path"]), encoding="utf-8"))

    lines = []
    for seg in data["segments"]:
        for L in seg.get("lines") or []:
            lines.append((L["text"], L["abs_start_sec"]))

    out_path = os.path.join(proj_dir, "02_分镜与画面", "分镜表.csv")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    assigned = 0
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["镜号", "起(s)", "止(s)", "时长(s)", "功能", "画面素材",
                    "画面要点", "字幕（逐行）", "转场"])
        for i, s in enumerate(proj["shots"], 1):
            sub = [t for t, ts in lines if s["start"] - 1e-6 <= ts < s["end"] - 1e-6]
            assigned += len(sub)
            func, desc = SHOT_META[i - 1]
            w.writerow([i, "%.2f" % s["start"], "%.2f" % s["end"],
                        "%.2f" % (s["end"] - s["start"]), func,
                        os.path.basename(s["image"]), desc,
                        "\n".join(sub), s.get("transition") or "—"])

    print("已生成 %s" % out_path)
    print("镜头 %d 个 / 字幕 %d 行（归入 %d 行）" % (len(proj["shots"]), len(lines), assigned))


if __name__ == "__main__":
    main()
