# -*- coding: utf-8 -*-
"""
豆包 Seedream 5.0 图片生成脚本
——《假如给我三天光明》书单短视频封面 + 背景图

接口：POST https://ark.cn-beijing.volces.com/api/v3/images/generations
鉴权：Authorization: Bearer <ARK_API_KEY>（火山方舟 Key，ark- 前缀）
模型：doubao-seedream-5-0-pro-260628（pro 画质更高）

输出：
  封面   → 00_原始素材/封面/
  背景图 → 00_原始素材/背景图/

环境变量：
  ARK_API_KEY   必填，火山方舟 API Key
"""

import os
import sys
import json
import base64
import time
import urllib.request
import urllib.error

os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
MODEL = "doubao-seedream-5-0-flash-260915"

PROJ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
COVER_DIR = os.path.join(PROJ, "00_原始素材", "封面")
BG_DIR = os.path.join(PROJ, "00_原始素材", "背景图")
OUTPUT_DIR = os.path.join(PROJ, "02_分镜与画面", "封面与背景")

# 封面：3:4 竖版，2K 分辨率，明确指定宽高比 3:4
COVER_PROMPT = (
    "一幅书籍封面插画，竖版构图，画面宽高比严格为 3:4。"
    "画面主体是一束温暖的金色晨光穿过一扇半开的木窗，照进一间安静的旧书房，"
    "光斑落在桌面上一本摊开的旧书上，书页微微泛黄。"
    "窗外是柔和朦胧的清晨光线，有薄雾和初升的太阳。"
    "整体氛围宁静、温柔、充满希望，色调以暖金色、奶油白、浅木色为主，"
    "光线柔和，笔触细腻，像手绘水彩绘本。"
    "画面下方留出干净的留白区域，不出现任何文字。"
)

# 背景图：3:4 竖版，治愈暖调，契合文案"黑暗里的光"
BG_PROMPT = (
    "一幅竖版治愈系背景插画，3:4 比例。"
    "画面描绘清晨时分，柔和的暖金色阳光穿透雾气，洒在一片静谧的林间小径上，"
    "光线透过树叶形成一道道温暖的光柱，地面有露水和斑驳的光影。"
    "远景有朦胧的山丘和初升的太阳，近景有几片发光的树叶。"
    "整体氛围安静、温柔、有希望，像黑暗过后迎来的第一缕光。"
    "色调以暖金色、柔和的黄、奶油白为主，光影细腻，"
    "画风像温暖的手绘水彩，带一点梦幻感，不出现任何人物和文字。"
)


def ensure_dir(p):
    os.makedirs(p, exist_ok=True)
    return p


def generate_image(api_key, prompt, size="2K", output_format="png",
                   response_format="url", watermark=False, timeout=180):
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "size": size,
        "output_format": output_format,
        "response_format": response_format,
        "watermark": watermark,
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError("HTTP %s %s" % (e.code, body[:500]))


def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def save_image(resp, name, out_dir):
    """响应里 data[0] 可能含 url 或 b64_json，统一落盘"""
    data = resp.get("data", [])
    if not data:
        raise RuntimeError("响应无 data: %s" % json.dumps(resp, ensure_ascii=False)[:300])
    item = data[0]
    ext = item.get("output_format", "png") or "png"
    fpath = os.path.join(out_dir, "%s.%s" % (name, ext))

    if item.get("url"):
        size = download(item["url"], fpath)
        return fpath, size, "url"
    elif item.get("b64_json"):
        raw = base64.b64decode(item["b64_json"])
        with open(fpath, "wb") as f:
            f.write(raw)
        return fpath, len(raw), "b64_json"
    else:
        raise RuntimeError("响应 item 无 url 也无 b64_json: %s" % json.dumps(item, ensure_ascii=False)[:300])


def main():
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        print("缺少 ARK_API_KEY。请设置环境变量：")
        print("  set ARK_API_KEY=你的方舟Key")
        return 2

    ensure_dir(COVER_DIR)
    ensure_dir(BG_DIR)
    ensure_dir(OUTPUT_DIR)

    results = []
    tasks = [
        ("封面", COVER_PROMPT, COVER_DIR, "1584x2816"),
        ("背景图", BG_PROMPT, BG_DIR, "1776x2368"),
    ]

    for name, prompt, out_dir, size in tasks:
        print("\n[%s] 生成中 ..." % name, flush=True)
        print("  prompt(%d字): %s" % (len(prompt), prompt[:40]), flush=True)
        try:
            resp = generate_image(api_key, prompt, size=size)
            fpath, size, src = save_image(resp, name, out_dir)
            results.append({"name": name, "path": fpath, "bytes": size, "source": src})
            print("  ✓ %s (%d bytes, %s)" % (os.path.basename(fpath), size, src), flush=True)
        except Exception as e:
            print("  ✗ 失败: %s" % e, flush=True)
            results.append({"name": name, "error": str(e)})

    # 写生成记录
    record = {
        "book": "假如给我三天光明",
        "model": MODEL,
        "ratio": "3:4",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
    }
    rpath = os.path.join(OUTPUT_DIR, "图片生成记录.json")
    with open(rpath, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("完成。生成记录：%s" % rpath)
    for r in results:
        if "path" in r:
            print("  ✓ %s → %s" % (r["name"], r["path"]))
        else:
            print("  ✗ %s → %s" % (r["name"], r["error"]))
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
