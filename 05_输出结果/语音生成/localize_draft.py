# -*- coding: utf-8 -*-
"""
把已安装到剪映草稿箱的草稿做「素材本地化」：
1. 把 GitHub raw URL 素材复制进草稿目录（保持相对结构）
2. draft_content.json / draft_info.json 里的 path 改成 Windows 绝对路径
3. 修正 draft_meta_info.json 的草稿名
4. 原文件备份为 *.orig

运行前提：剪映已完全关闭。

用法：
    python localize_draft.py 20261101180416a4ee4900
"""

import os
import sys
import json
import shutil
import urllib.parse

os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJ = r"C:/Users/scott/WorkBuddy/书单视频"
DRAFT_ROOT_BASE = r"C:/Users/scott/AppData/Local/JianyingPro/User Data/Projects/com.lveditor.draft"
DRAFT_ID = sys.argv[1] if len(sys.argv) > 1 else "20261101180416a4ee4900"
DRAFT_NAME = "假如给我三天光明-书单视频"
RAW_MARK = "/main/"


def url_to_rel(url: str) -> str:
    """GitHub raw URL -> 仓库内相对路径（URL 解码）"""
    idx = url.find(RAW_MARK)
    if idx == -1:
        return ""
    return urllib.parse.unquote(url[idx + len(RAW_MARK):])


def main():
    draft_dir = os.path.join(DRAFT_ROOT_BASE, DRAFT_ID).replace("/", "\\")
    if not os.path.isdir(draft_dir):
        print("[X] 草稿目录不存在:", draft_dir)
        sys.exit(1)

    print("草稿目录:", draft_dir)
    copied = 0
    missing = []

    for fname in ("draft_content.json", "draft_info.json"):
        fpath = os.path.join(draft_dir, fname)
        if not os.path.isfile(fpath):
            print("[!] 跳过不存在的", fname)
            continue

        # 备份一次
        bak = fpath + ".orig"
        if not os.path.exists(bak):
            shutil.copy2(fpath, bak)

        with open(fpath, encoding="utf-8") as f:
            d = json.load(f)

        m = d.get("materials", {})
        changed = 0
        for key in ("videos", "audios"):
            for item in m.get(key, []):
                p = item.get("path", "")
                if not isinstance(p, str) or not p.startswith("http"):
                    continue
                rel = url_to_rel(p)
                if not rel:
                    missing.append(p)
                    continue

                # 源文件 -> 草稿目录
                src = os.path.join(PROJ, rel.replace("/", os.sep))
                dst = os.path.join(draft_dir, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if not os.path.exists(dst):
                    if os.path.isfile(src):
                        shutil.copy2(src, dst)
                        copied += 1
                    else:
                        missing.append(rel)
                        continue

                item["path"] = dst
                item["media_path"] = ""
                item["category_name"] = "local"
                changed += 1

        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        print(f"[OK] {fname}: 改写 {changed} 条素材路径")

    # meta
    meta_path = os.path.join(draft_dir, "draft_meta_info.json")
    if os.path.isfile(meta_path):
        if not os.path.exists(meta_path + ".orig"):
            shutil.copy2(meta_path, meta_path + ".orig")
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        meta["draft_name"] = DRAFT_NAME
        meta["draft_fold_path"] = draft_dir
        meta["draft_root_path"] = DRAFT_ROOT_BASE.replace("/", "\\")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print("[OK] draft_meta_info.json: 草稿名 ->", DRAFT_NAME)

    print()
    print("=" * 56)
    print("新复制素材文件:", copied, "个")
    if missing:
        print("[!] 未找到源文件:", missing)
    print("完成，可以打开剪映了")
    print("=" * 56)


if __name__ == "__main__":
    main()
