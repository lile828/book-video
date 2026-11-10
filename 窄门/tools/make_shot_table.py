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

# 画面要点优先读 project.json 的 shot_meta（每本一套），没写才回落到下面的通用兜底
SHOT_META_FALLBACK = [
    ("钩子", ""), ("痛点A", ""), ("痛点B", ""), ("引入书", ""),
    ("观点1", ""), ("观点2", ""), ("反转", ""), ("收尾", ""),
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

    meta = proj.get("shot_meta") or []
    if len(meta) != len(proj["shots"]):
        meta = SHOT_META_FALLBACK

    assigned = 0
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["镜号", "起(s)", "止(s)", "时长(s)", "功能", "画面素材",
                    "画面要点", "字幕（逐行）", "转场"])
        for i, s in enumerate(proj["shots"], 1):
            sub = [t for t, ts in lines if s["start"] - 1e-6 <= ts < s["end"] - 1e-6]
            assigned += len(sub)
            if isinstance(meta[i - 1], dict):
                func = meta[i - 1].get("func", "")
                desc = meta[i - 1].get("desc", "")
            else:
                func, desc = meta[i - 1]
            w.writerow([i, "%.2f" % s["start"], "%.2f" % s["end"],
                        "%.2f" % (s["end"] - s["start"]), func,
                        os.path.basename(s["image"]), desc,
                        "\n".join(sub), s.get("transition") or "—"])

    print("已生成 %s" % out_path)
    print("镜头 %d 个 / 字幕 %d 行（归入 %d 行）" % (len(proj["shots"]), len(lines), assigned))


if __name__ == "__main__":
    main()
