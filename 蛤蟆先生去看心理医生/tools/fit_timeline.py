# -*- coding: utf-8 -*-
"""按「每镜占几行」把逐行时间轴切成镜头，回填 project.json。

为什么不用 tts_lines.py --reflow：reflow 是按旧时长等比缩放镜头，
而本片的镜头边界必须精确落在某一行字幕的起点上（图换早了三秒话还没说完，
换晚了上一句还在念旧画面），所以按行分组切。

用法：python tools/fit_timeline.py --project .
"""
import os
import sys
import json
import argparse

os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 每镜吃掉的字幕行数（顺序即 镜1..镜8），合计必须等于全片行数
SHOT_LINES = [4, 3, 3, 4, 5, 3, 3, 3]
# 书封层在第几镜开始时退场（1-based）
COVER_UNTIL_SHOT = 5
TAIL_PAD = 0.8  # 最后一镜在末句后再留 0.8 秒


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    args = ap.parse_args()

    proj_dir = os.path.abspath(args.project)
    proj_path = os.path.join(proj_dir, "project.json")
    with open(proj_path, encoding="utf-8") as f:
        proj = json.load(f)

    cap_path = os.path.join(proj_dir, proj["captions"]["path"])
    with open(cap_path, encoding="utf-8") as f:
        data = json.load(f)

    # 展平成有序的 (text, abs_start, abs_end)
    lines = []
    for seg in data["segments"]:
        for L in seg.get("lines") or []:
            lines.append((L["text"], L["abs_start_sec"], L["abs_end_sec"]))

    if len(lines) != sum(SHOT_LINES):
        raise SystemExit("[X] 行数不符：脚本 %d 行，SHOT_LINES 合计 %d 行"
                         % (len(lines), sum(SHOT_LINES)))

    total = round(data["total_duration_sec"], 3)
    bounds = []
    idx = 0
    for n in SHOT_LINES:
        bounds.append(lines[idx][1])
        idx += n
    bounds.append(round(total + TAIL_PAD, 3))

    # 镜头
    shots = proj.get("shots") or []
    if len(shots) != len(SHOT_LINES):
        raise SystemExit("[X] project.json 镜头数 %d ≠ %d" % (len(shots), len(SHOT_LINES)))
    for i, s in enumerate(shots):
        s["start"] = bounds[i]
        s["end"] = bounds[i + 1]
        if i == 0:
            s["transition"] = ""
            s["transition_duration"] = 0
        else:
            s["transition"] = "叠化"
            s["transition_duration"] = 0.5

    # 音轨首尾相接
    cursor = 0.0
    for a in proj.get("audios") or []:
        for seg in data["segments"]:
            if seg["id"] in a.get("audio", ""):
                a["start"] = round(cursor, 3)
                a["end"] = round(cursor + seg["duration_sec"], 3)
                cursor = a["end"]
                break
    end_of_audio = round(cursor, 3)

    # 叠加层
    for ov in proj.get("overlays") or []:
        ov["start"] = 0.0
        if "书封" in (ov.get("name") or ""):
            ov["end"] = bounds[COVER_UNTIL_SHOT - 1]
        else:
            ov["end"] = bounds[-1]

    with open(proj_path, "w", encoding="utf-8") as f:
        json.dump(proj, f, ensure_ascii=False, indent=2)

    print("配音总长 %.2fs，成片 %.2fs（含 %.1fs 尾留白）" % (total, bounds[-1], TAIL_PAD))
    print("")
    print("| 镜 | 起 | 止 | 时长 | 首行字幕 |")
    print("|---|---|---|---|---|")
    idx = 0
    for i, n in enumerate(SHOT_LINES, 1):
        print("| %d | %.2f | %.2f | %.2f | %s |"
              % (i, bounds[i - 1], bounds[i], bounds[i] - bounds[i - 1], lines[idx][0]))
        idx += n
    print("")
    for a in proj["audios"]:
        print("音轨 %-28s %6.2f - %6.2f" % (os.path.basename(a["audio"]), a["start"], a["end"]))
    for ov in proj["overlays"]:
        print("叠加 %-28s %6.2f - %6.2f" % (ov["name"], ov["start"], ov["end"]))
    print("\n音频总长 %.2f 秒" % end_of_audio)


if __name__ == "__main__":
    main()
