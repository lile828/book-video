# -*- coding: utf-8 -*-
"""把草稿登记进剪映草稿列表（root_meta_info.json）。

背景：capcut-mate 系的 install-draft.mjs 只落文件，从不写剪映的根索引
`root_meta_info.json` 的 `all_draft_store`，所以草稿在剪映里根本看不见。
本脚本负责：

1. 备份 root_meta_info.json
2. 清掉指向已不存在目录的失效条目（删过草稿目录后会留下僵尸条目）
3. 把目标草稿目录 upsert 进 all_draft_store
4. 顺带修草稿自身 draft_meta_info.json 里的几个错值（未来时间戳、
   材料体积字段名带下划线、版本号为空）
5. 修正 draft_ids 计数

用法：
    python tools/register_draft.py --draft "C:/.../com.lveditor.draft/20261108202802039f4f01"
    python tools/register_draft.py --draft <目录> --name "自定义草稿名"
    python tools/register_draft.py --draft <目录> --dry-run
"""
import argparse
import json
import os
import shutil
import sys
import time
import uuid

DEFAULT_DRAFT_ROOT = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "JianyingPro", "User Data", "Projects", "com.lveditor.draft",
)

# 新建条目的默认值，与剪映自己写出来的一致
DEFAULTS = {
    "cloud_draft_cover": False,
    "cloud_draft_sync": False,
    "draft_cloud_last_action_download": False,
    "draft_cloud_purchase_info": "",
    "draft_cloud_template_id": "",
    "draft_cloud_tutorial_info": "",
    "draft_cloud_videocut_purchase_info": "",
    "draft_is_ai_shorts": False,
    "draft_is_cloud_temp_draft": False,
    "draft_is_infinite_canvas_draft": False,
    "draft_is_invisible": False,
    "draft_is_pippit_draft": False,
    "draft_is_web_article_video": False,
    "draft_new_version": "164.0.0",
    "draft_type": "",
    "draft_web_article_video_enter_from": "",
    "pippit_avatar_url": "",
    "pippit_extra_info": "",
    "pippit_id": "",
    "pippit_user_name": "",
    "streaming_edit_draft_ready": True,
    "tm_draft_cloud_completed": "",
    "tm_draft_cloud_entry_id": -1,
    "tm_draft_cloud_modified": 0,
    "tm_draft_cloud_parent_entry_id": -1,
    "tm_draft_cloud_space_id": -1,
    "tm_draft_cloud_user_id": -1,
    "tm_draft_removed": 0,
}


def now_us():
    return int(time.time() * 1_000_000)


def dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def norm(p):
    """统一成剪映惯用的正斜杠路径 + 反斜杠拼接风格不重要，只要 Jianying 能解析。

    剪映自己写的 draft_fold_path 用正斜杠，draft_json_file 用正斜杠 + 反斜杠混，
    这里统一用正斜杠，Jianying 两种都能认。
    """
    return os.path.abspath(p).replace("\\", "/")


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def load_meta(draft_dir):
    """读草稿自身元信息；新版剪映的 draft_meta_info.json 是加密的，读不动就退回默认值。"""
    p = os.path.join(draft_dir, "draft_meta_info.json")
    if os.path.exists(p):
        try:
            return read_json(p)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
    return None


def draft_name_of(draft_dir, meta, override):
    if override:
        return override
    if meta:
        for k in ("draft_name", "name"):
            v = meta.get(k)
            if v and str(v).strip():
                return str(v)
    return os.path.basename(draft_dir)


def build_entry(draft_dir, root, meta, name):
    content_path = os.path.join(draft_dir, "draft_content.json")
    content = read_json(content_path)
    duration = int(content.get("duration") or 0)

    cover = os.path.join(draft_dir, "draft_cover.jpg")
    cover_path = norm(cover) if os.path.exists(cover) else ""

    draft_id = ""
    if meta:
        draft_id = meta.get("draft_id") or ""
    if not draft_id:
        draft_id = str(uuid.uuid4()).upper()

    created = (meta or {}).get("tm_draft_create") or now_us()
    # 模板生成的草稿常带一个荒谬的未来时间戳（比如 2055 年），会被排到列表最前面，
    # 这里统一改成当前时间
    if not isinstance(created, int) or created > now_us() + 86_400_000_000:
        created = now_us()

    entry = dict(DEFAULTS)
    entry.update({
        "draft_cover": cover_path,
        "draft_fold_path": norm(draft_dir),
        "draft_id": draft_id,
        "draft_json_file": norm(content_path),
        "draft_name": name,
        "draft_root_path": norm(root),
        "draft_timeline_materials_size": dir_size(draft_dir),
        "draft_new_version": (meta or {}).get("draft_new_version") or "164.0.0",
        "tm_draft_create": created,
        "tm_draft_modified": now_us(),
        "tm_duration": duration,
    })
    return entry


def fix_meta(draft_dir, meta, entry):
    """修草稿自身 meta 里的错值，让列表排序和体积显示正常。"""
    if not meta:
        return False
    changed = False
    for k, v in (
        ("draft_name", entry["draft_name"]),
        ("draft_fold_path", entry["draft_fold_path"]),
        ("draft_root_path", entry["draft_root_path"]),
        ("draft_id", entry["draft_id"]),
        ("draft_timeline_materials_size", entry["draft_timeline_materials_size"]),
        ("draft_timeline_materials_size_", entry["draft_timeline_materials_size"]),
        ("tm_draft_modified", entry["tm_draft_modified"]),
        ("draft_new_version", entry["draft_new_version"]),
        ("draft_removed", 0),
    ):
        if meta.get(k) != v:
            meta[k] = v
            changed = True
    if changed:
        write_json(os.path.join(draft_dir, "draft_meta_info.json"), meta)
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", required=True, help="草稿目录（绝对路径）")
    ap.add_argument("--root", default=DEFAULT_DRAFT_ROOT, help="com.lveditor.draft 根目录")
    ap.add_argument("--name", help="草稿显示名，默认取 draft_meta_info.draft_name")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-missing", action="store_true", help="保留指向不存在目录的条目")
    args = ap.parse_args()

    draft_dir = os.path.abspath(args.draft)
    root = os.path.abspath(args.root)
    content_path = os.path.join(draft_dir, "draft_content.json")
    if not os.path.exists(content_path):
        sys.exit("找不到 %s，草稿目录不对" % content_path)

    index_path = os.path.join(root, "root_meta_info.json")
    if not os.path.exists(index_path):
        sys.exit("找不到根索引 %s" % index_path)

    index = read_json(index_path)
    store = index.get("all_draft_store") or []

    # 1) 清失效条目
    kept, dropped = [], []
    for e in store:
        fold = (e.get("draft_fold_path") or "").replace("\\", "/")
        if args.keep_missing or (fold and os.path.isdir(fold)):
            kept.append(e)
        else:
            dropped.append(os.path.basename(fold) or "<空路径>")

    # 2) 同一草稿目录的旧条目先摘掉，避免重复
    meta = load_meta(draft_dir)
    name = draft_name_of(draft_dir, meta, args.name)
    target = norm(draft_dir)
    before = len(kept)
    kept = [e for e in kept
            if (e.get("draft_fold_path") or "").replace("\\", "/") != target]
    replaced = before - len(kept)

    entry = build_entry(draft_dir, root, meta, name)

    print("根索引：原 %d 条 → 清理失效 %d 条 → 替换同名 %d 条 → 新增 1 条"
          % (len(store), len(dropped), replaced))
    if dropped:
        for d in dropped:
            print("  移除失效条目:", d)
    print("  新条目:")
    for k in ("draft_name", "draft_id", "draft_fold_path", "tm_duration",
              "draft_timeline_materials_size", "draft_cover", "draft_json_file"):
        v = entry[k]
        if k == "draft_timeline_materials_size":
            v = "%.1f MB" % (v / 1024 / 1024)
        print("    %-30s %s" % (k, v))

    kept.append(entry)
    index["all_draft_store"] = kept
    index["draft_ids"] = len(kept)

    if args.dry_run:
        print("\n[dry-run] 未写入。写入后共 %d 条。" % len(kept))
        return

    shutil.copy2(index_path, index_path + ".bak")
    write_json(index_path, index)
    print("\n已备份原索引 → root_meta_info.json.bak")
    print("已写入根索引，共 %d 条（draft_ids=%d）" % (len(kept), index["draft_ids"]))

    if fix_meta(draft_dir, meta, entry):
        print("已修正草稿自身 draft_meta_info.json（时间戳/体积字段/版本号）")
    else:
        print("草稿自身 meta 无需修正或为加密格式（跳过）")


if __name__ == "__main__":
    main()
