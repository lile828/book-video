# -*- coding: utf-8 -*-
"""
部署「本地素材版」剪映草稿：
1. 从 draft_content_raw.json 读明文草稿
2. 素材 path 改成草稿目录内的相对路径（素材已在草稿目录）
3. 清理剪映加密的 Timelines/ 子目录 + 加密 meta
4. 写明文 draft_content.json + 明文 draft_meta_info.json
运行前提：剪映已完全关闭。
"""
import os
import sys
import json
import shutil
import urllib.parse

os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DRAFT_ID = "20261101164141023d7fd5"
DRAFT_ROOT = r"C:/Users/scott/AppData/Local/JianyingPro/User Data/Projects/com.lveditor.draft" + "/" + DRAFT_ID
RAW_JSON = r"C:/Users/scott/WorkBuddy/书单视频/05_输出结果/语音生成/draft_content_raw.json"


def url_to_rel(url):
    """GitHub raw URL -> 相对路径（去掉域名前缀 + URL 解码）"""
    idx = url.find("/main/")
    if idx == -1:
        return url
    enc = url[idx + 6:]
    return urllib.parse.unquote(enc)


def main():
    # 1. 读明文草稿
    d = json.load(open(RAW_JSON, encoding="utf-8"))
    m = d["materials"]

    n_img = n_audio = 0
    # 图片
    for v in m.get("videos", []):
        url = v.get("path", "")
        if url.startswith("http"):
            rel = url_to_rel(url)
            v["path"] = rel
            v["media_path"] = ""
            v["category_name"] = "local"
            n_img += 1
    # 音频
    for a in m.get("audios", []):
        url = a.get("path", "")
        if url.startswith("http"):
            rel = url_to_rel(url)
            a["path"] = rel
            a["category_name"] = "local"
            n_audio += 1

    print("图片改 path: %d 个，音频改 path: %d 个" % (n_img, n_audio))

    # 2. 清理剪映加密产生的 Timelines 子目录和加密 meta
    timelines_dir = os.path.join(DRAFT_ROOT, "Timelines")
    if os.path.exists(timelines_dir):
        shutil.rmtree(timelines_dir)
        print("已删除 Timelines/ 加密子目录")

    # 3. 写明文 draft_content.json
    content_path = os.path.join(DRAFT_ROOT, "draft_content.json")
    with open(content_path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print("已写入明文 draft_content.json")

    # 同步写 .bak（剪映有时读 .bak）
    with open(content_path + ".bak", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print("已写入 draft_content.json.bak")

    # 4. 写明文 draft_meta_info.json（关键：覆盖加密的）
    meta_path = os.path.join(DRAFT_ROOT, "draft_meta_info.json")
    meta = {
        "draft_id": DRAFT_ID,
        "draft_name": "假如给我三天光明-书单视频",
        "draft_fold_path": DRAFT_ROOT,
        "draft_root_path": os.path.dirname(DRAFT_ROOT),
        "draft_removable_storage_device": "",
        "draft_cover": "draft_cover.jpg",
        "draft_new_version": "",
        "draft_timeline_version": 5,
        "tm_draft_create": 1793522642,
        "tm_draft_modified": 1793522642,
        "draft_json_version": "1.0",
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("已写入明文 draft_meta_info.json")

    print()
    print("=" * 50)
    print("本地素材草稿部署完成")
    print("草稿目录:", DRAFT_ROOT)
    print("现在可以重新打开剪映，素材将直接本地加载")
    print("=" * 50)


if __name__ == "__main__":
    main()
