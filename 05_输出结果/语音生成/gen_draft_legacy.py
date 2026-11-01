# -*- coding: utf-8 -*-
"""
生成剪映草稿：create_draft → add_images → add_audios → add_captions → save_draft
素材用 GitHub raw 直链（免登录、无时效），画布 1080×1920 竖屏。
"""

import os
import sys
import json
import urllib.request
import urllib.error

os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://capcut-mate.jcaigc.cn/openapi/capcut-mate/v1"
RAW = "https://raw.githubusercontent.com/lile828/book-video/main"

PROJ = r"C:/Users/scott/WorkBuddy/书单视频"

# 素材在 GitHub 上的路径（相对仓库根）
COVER_PATH = "00_原始素材/封面/封面.png"
BG_PATHS = {
    "bg1": "00_原始素材/背景图/背景图.png",
    "bg2": "00_原始素材/背景图/背景图2_失去光.png",
    "bg3": "00_原始素材/背景图/背景图3_水井房.png",
    "bg4": "00_原始素材/背景图/背景图4_森林之问.png",
    "bg5": "00_原始素材/背景图/背景图5_三天.png",
    "bg6": "00_原始素材/背景图/背景图6_黑暗落下.png",
    "bg7": "00_原始素材/背景图/背景图7_下楼走一趟.png",
}
AUDIO_PATHS = {
    "a1": "03_成片素材/音频/假如给我三天光明/01_开场白_今天要分享的是.wav",
    "a2": "03_成片素材/音频/假如给我三天光明/02_书名_假如给我三天光明.wav",
    "a3": "03_成片素材/音频/假如给我三天光明/03_正文_正文.wav",
}

# 分镜：9 个镜头（全片绝对时间，秒）
SHOTS = [
    ("封面", COVER_PATH, 0, 4),
    ("失去光", BG_PATHS["bg2"], 4, 9),
    ("水井房", BG_PATHS["bg3"], 9, 14),
    ("森林之问", BG_PATHS["bg4"], 14, 25),
    ("晨光小径", BG_PATHS["bg1"], 25, 32),
    ("三天", BG_PATHS["bg5"], 32, 45),
    ("黑暗落下", BG_PATHS["bg6"], 45, 48),
    ("晨光小径复用", BG_PATHS["bg1"], 48, 56),
    ("下楼走一趟", BG_PATHS["bg7"], 56, 61),
]

# 三段音频（首尾相接）
AUDIOS = [
    ("a1", 0, 2),
    ("a2", 2, 4),
    ("a3", 4, 61),
]


def url(path):
    """路径 → GitHub raw 直链（URL 编码中文）"""
    from urllib.parse import quote
    return RAW + "/" + quote(path)


def post_json(endpoint, payload):
    req = urllib.request.Request(
        BASE + "/" + endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError("HTTP %s: %s" % (e.code, body[:500]))


def main():
    # 1. 创建草稿
    print("=" * 60)
    print("第 1 步：创建草稿")
    print("=" * 60)
    r = post_json("create_draft", {"width": 1080, "height": 1920})
    draft_url = r["draft_url"]
    print("  draft_url:", draft_url)

    # 2. 添加图片（9 个镜头，叠化转场）
    print("\n" + "=" * 60)
    print("第 2 步：添加图片（9 镜头）")
    print("=" * 60)
    image_infos = []
    for i, (name, path, s, e) in enumerate(SHOTS):
        item = {
            "image_url": url(path),
            "start": int(s * 1000000),
            "end": int(e * 1000000),
        }
        # 镜头间加叠化转场（最后一张不加）
        if i < len(SHOTS) - 1:
            item["transition"] = "叠化"
            item["transition_duration"] = 500000  # 0.5 秒
        image_infos.append(item)
    r = post_json("add_images", {
        "draft_url": draft_url,
        "image_infos": json.dumps(image_infos, ensure_ascii=False),
    })
    draft_url = r.get("draft_url", draft_url)
    print("  ✓ 已添加 %d 个镜头，segment_ids: %d" % (len(image_infos), len(r.get("segment_ids", []))))

    # 3. 添加音频（3 段首尾相接）
    print("\n" + "=" * 60)
    print("第 3 步：添加音频（3 段）")
    print("=" * 60)
    audio_infos = []
    for name, s, e in AUDIOS:
        audio_infos.append({
            "audio_url": url(AUDIO_PATHS[name]),
            "start": int(s * 1000000),
            "end": int(e * 1000000),
            "volume": 1.0,
        })
    r = post_json("add_audios", {
        "draft_url": draft_url,
        "audio_infos": json.dumps(audio_infos, ensure_ascii=False),
    })
    draft_url = r.get("draft_url", draft_url)
    print("  ✓ 已添加 %d 段音频" % len(audio_infos))

    # 4. 添加字幕（从逐句时间轴读取）
    print("\n" + "=" * 60)
    print("第 4 步：添加字幕")
    print("=" * 60)
    timeline_path = os.path.join(PROJ, "05_输出结果", "语音时长", "语音时长清单.json")
    tl = json.load(open(timeline_path, encoding="utf-8"))
    captions = []
    for seg in tl["segments"]:
        for line in seg.get("lines", []):
            if line.get("abs_start_sec") is None or line.get("abs_end_sec") is None:
                continue
            captions.append({
                "start": int(line["abs_start_sec"] * 1000000),
                "end": int(line["abs_end_sec"] * 1000000),
                "text": line["text"],
            })
    r = post_json("add_captions", {
        "draft_url": draft_url,
        "captions": json.dumps(captions, ensure_ascii=False),
        "text_color": "#ffffff",
        "border_color": "#000000",
        "alignment": 1,
        "font_size": 18,
        "transform_y": -320,
        "bold": True,
        "has_shadow": True,
    })
    draft_url = r.get("draft_url", draft_url)
    print("  ✓ 已添加 %d 条字幕" % len(captions))

    # 5. 保存草稿
    print("\n" + "=" * 60)
    print("第 5 步：保存草稿")
    print("=" * 60)
    r = post_json("save_draft", {"draft_url": draft_url})
    draft_url = r.get("draft_url", draft_url)
    print("  ✓ 草稿已保存")

    # 输出结果
    print("\n" + "=" * 60)
    print("完成！草稿地址：")
    print("=" * 60)
    print(draft_url)

    # 落盘结果
    result = {
        "draft_url": draft_url,
        "width": 1080,
        "height": 1920,
        "shots": len(image_infos),
        "audios": len(audio_infos),
        "captions": len(captions),
        "total_duration_sec": 61,
    }
    out = os.path.join(PROJ, "05_输出结果", "语音生成", "draft_result.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("\n结果已保存:", out)


if __name__ == "__main__":
    main()
