# -*- coding: utf-8 -*-
"""
批量生成 6 张背景图，补齐全书单视频的 7 张背景图。
风格统一：水彩治愈暖调，3:4 竖版，与已有「晨光林间小径」一致。
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error

os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
MODEL = "doubao-seedream-5-0-flash-260915"
SIZE = "1776x2368"   # 3:4 竖版

PROJ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BG_DIR = os.path.join(PROJ, "00_原始素材", "背景图")

# 风格前缀，统一水彩治愈暖调
STYLE = (
    "竖版构图，宽高比3比4，温暖治愈的水彩手绘风格，"
    "色调以暖金色、奶油白、浅木色、淡青为主，光线柔和细腻，"
    "氛围宁静温柔、充满希望，像绘本插画，不出现任何人物正面特写和文字。"
)

# 6 张背景图，对应文案 v2 的 6 个后续段落
BG_TASKS = [
    {
        "name": "背景图2_失去光",
        "prompt": "一间昏暗的旧房间，一扇木窗半掩，微弱的光从窗缝和门缝里透进来，"
                  "在黑暗的地板上拉出一道细细的光带。房间里有模糊的家具轮廓，"
                  "一只小手（只露手部）伸向那道微弱的光。整体是黑暗里透进一线光明的意境，"
                  "暖金色光线与暗调形成对比，克制而动人。" + STYLE,
    },
    {
        "name": "背景图3_水井房",
        "prompt": "一座乡村老水井，石砌的井沿长着青苔，一只温柔的手（只露手部）"
                  "正伸到井边接着缓缓流下的水，水花在阳光下闪着细碎的金光。"
                  "背景是斑驳的院墙和几片暖黄色的光斑，午后安静，"
                  "水流和光交织，有一种被耐心教导的温柔感。" + STYLE,
    },
    {
        "name": "背景图4_森林之问",
        "prompt": "一片幽深的森林，仰视视角看向高处的树冠，"
                  "阳光从层层叠叠的树叶间漏下来，形成一道道金色光柱。"
                  "树影浓密，光线通透，仿佛站在林间抬头发问。"
                  "氛围沉静而辽远，带着一点思考的留白感。" + STYLE,
    },
    {
        "name": "背景图5_三天",
        "prompt": "三幅画面上下柔和拼接的意象：上方是清晨里一张温柔的侧脸剪影，"
                  "中间是博物馆里一座大理石雕像沐浴在晨光中，"
                  "下方是城市街道上逐渐亮起的暖黄色街灯。"
                  "三段之间以柔和的光晕自然过渡，象征三天的旅程，"
                  "整体温暖、庄重、有层次，不出现文字。" + STYLE,
    },
    {
        "name": "背景图6_黑暗落下",
        "prompt": "黄昏时分，太阳刚刚落下地平线，天边还留着最后一抹暖金色与橙红色的余晖，"
                  "大地渐渐沉入柔和的暮色。远山和树影安静地剪影在暮色中，"
                  "画面宁静、克制，带着一种无遗憾的释然，"
                  "像一天平静地落下帷幕，没有悲伤只有温柔。" + STYLE,
    },
    {
        "name": "背景图7_下楼走一趟",
        "prompt": "从一扇半开的门向内向外看，门外是一条安静的林荫小道，"
                  "几片树叶在微风里轻轻摇晃，温暖的阳光洒在地面和树叶上，"
                  "投下斑驳的光影。门框和门外的光形成画框般的构图，"
                  "仿佛邀请人迈步走出去，去看树叶的颜色、去感受风的方向，"
                  "清新、通透、有行动感。" + STYLE,
    },
]


def generate(api_key, prompt, timeout=180):
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "size": SIZE,
        "output_format": "png",
        "response_format": "url",
        "watermark": False,
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def main():
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        print("缺少 ARK_API_KEY")
        return 2
    os.makedirs(BG_DIR, exist_ok=True)

    results = []
    for i, t in enumerate(BG_TASKS, 1):
        print("\n[%d/6] %s" % (i, t["name"]), flush=True)
        try:
            resp = generate(api_key, t["prompt"])
            url = resp["data"][0]["url"]
            fpath = os.path.join(BG_DIR, t["name"] + ".png")
            size = download(url, fpath)
            results.append({"name": t["name"], "path": fpath, "bytes": size})
            print("  ✓ %d bytes" % size, flush=True)
        except Exception as e:
            print("  ✗ %s" % str(e)[:200], flush=True)
            results.append({"name": t["name"], "error": str(e)[:200]})
        time.sleep(2)   # 轻微间隔，避免触发限流

    record = {
        "book": "假如给我三天光明",
        "model": MODEL,
        "ratio": "3:4",
        "size": SIZE,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
    }
    rpath = os.path.join(BG_DIR, "背景图生成记录.json")
    with open(rpath, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    ok = sum(1 for r in results if "path" in r)
    print("\n" + "=" * 60)
    print("完成：%d/6 张成功，记录：%s" % (ok, rpath))
    for r in results:
        if "path" in r:
            print("  ✓ %s" % os.path.basename(r["path"]))
        else:
            print("  ✗ %s → %s" % (r["name"], r["error"]))
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
