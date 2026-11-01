# -*- coding: utf-8 -*-
"""
上传本地素材到 CapCut Mate（upload_file），拿到公网 URL。
再依次 create_draft → add_images → add_audios → add_captions → save_draft，生成剪映草稿。

素材：
  图片：封面 + 7 张背景图（8 张 png）
  音频：3 段 wav
  字幕：40 条（从逐句时间轴读取）
"""

import os
import sys
import json
import urllib.request
import urllib.error
import uuid

os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://capcut-mate.jcaigc.cn/openapi/capcut-mate/v1"
APIKEY = os.environ.get("CAPCUT_MATE_APIKEY", "请设置环境变量 CAPCUT_MATE_APIKEY")

PROJ = r"C:/Users/scott/WorkBuddy/书单视频"
COVER = os.path.join(PROJ, "00_原始素材", "封面", "封面.png")
BG_DIR = os.path.join(PROJ, "00_原始素材", "背景图")
AUDIO_DIR = os.path.join(PROJ, "03_成片素材", "音频", "假如给我三天光明")
TIMELINE = os.path.join(PROJ, "05_输出结果", "语音时长", "语音时长清单.json")

# 7 张背景图（按分镜顺序）
BG_FILES = [
    "背景图.png",           # 镜0 开场（复用为镜4、镜7）
    "背景图2_失去光.png",    # 镜1
    "背景图3_水井房.png",    # 镜2
    "背景图4_森林之问.png",  # 镜3
    "背景图5_三天.png",      # 镜5
    "背景图6_黑暗落下.png",  # 镜6
    "背景图7_下楼走一趟.png", # 镜8
]
AUDIO_FILES = [
    "01_开场白_今天要分享的是.wav",
    "02_书名_假如给我三天光明.wav",
    "03_正文_正文.wav",
]

# 分镜时间轴（全片绝对时间，单位微秒；1秒=1000000）
# 镜号, 画面文件, 起秒, 止秒
SHOTS = [
    ("封面.png", 0, 4),
    ("背景图2_失去光.png", 4, 9),
    ("背景图3_水井房.png", 9, 14),
    ("背景图4_森林之问.png", 14, 25),
    ("背景图.png", 25, 32),
    ("背景图5_三天.png", 32, 45),
    ("背景图6_黑暗落下.png", 45, 48),
    ("背景图.png", 48, 56),
    ("背景图7_下楼走一趟.png", 56, 61),
]


def upload_file(path, mime):
    """multipart/form-data 上传，返回带签名 URL"""
    boundary = "----wb" + uuid.uuid4().hex
    with open(path, "rb") as f:
        content = f.read()
    filename = os.path.basename(path)
    body = b""
    body += ("--%s\r\n" % boundary).encode()
    body += ('Content-Disposition: form-data; name="file"; filename="%s"\r\n' % filename).encode()
    body += ("Content-Type: %s\r\n\r\n" % mime).encode()
    body += content
    body += ("\r\n--%s\r\n" % boundary).encode()
    body += ('Content-Disposition: form-data; name="apiKey"\r\n\r\n').encode()
    body += (APIKEY + "\r\n").encode()
    body += ("--%s--\r\n" % boundary).encode()

    req = urllib.request.Request(
        BASE + "/upload_file",
        data=body,
        headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_json(endpoint, payload):
    req = urllib.request.Request(
        BASE + "/" + endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    # ---- 1. 上传图片 ----
    print("=" * 60)
    print("第 1 步：上传图片素材")
    print("=" * 60)
    img_urls = {}   # 文件名 -> url
    upload_queue = [("封面.png", COVER)]
    for f in BG_FILES:
        upload_queue.append((f, os.path.join(BG_DIR, f)))

    for name, path in upload_queue:
        if name in img_urls:
            continue
        print("  上传 %s ..." % name, flush=True)
        try:
            r = upload_file(path, "image/png")
            if r.get("code") == 0 and r.get("url"):
                img_urls[name] = r["url"]
                print("    ✓ %.2f MB, 费用 %.4f 元" % (r.get("size_mb", 0), r.get("cost", 0)))
            else:
                print("    ✗ %s" % json.dumps(r, ensure_ascii=False)[:200])
        except Exception as e:
            print("    ✗ 异常: %s" % str(e)[:200])

    # ---- 2. 上传音频 ----
    print("\n" + "=" * 60)
    print("第 2 步：上传音频素材")
    print("=" * 60)
    audio_urls = []
    for f in AUDIO_FILES:
        path = os.path.join(AUDIO_DIR, f)
        print("  上传 %s ..." % f, flush=True)
        try:
            r = upload_file(path, "audio/wav")
            if r.get("code") == 0 and r.get("url"):
                audio_urls.append({"url": r["url"], "name": f})
                print("    ✓ %.2f MB, 费用 %.4f 元" % (r.get("size_mb", 0), r.get("cost", 0)))
            else:
                print("    ✗ %s" % json.dumps(r, ensure_ascii=False)[:200])
        except Exception as e:
            print("    ✗ 异常: %s" % str(e)[:200])

    # 把上传结果落盘，供后续使用
    state = {"images": img_urls, "audios": audio_urls}
    spath = os.path.join(PROJ, "05_输出结果", "语音生成", "upload_state.json")
    with open(spath, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print("\n上传结果已保存: %s" % spath)
    print("图片 %d 张，音频 %d 段" % (len(img_urls), len(audio_urls)))


if __name__ == "__main__":
    main()
