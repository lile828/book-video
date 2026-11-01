#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成剪映草稿（通用版 · 读 project.json）

    create_draft -> add_images(背景) -> add_images(叠加层) -> add_audios -> add_captions -> save_draft

所有内容都从 project.json 来，换一本书只改配置文件，不动代码。

用法：
    python gen_draft.py                          # 读同目录/项目根的 project.json
    python gen_draft.py --project ../project.json
    python gen_draft.py --dry-run                # 只校验配置、打印计划，不调接口
    python gen_draft.py --dry-run --show-captions

project.json 关键约定：
    - 所有时间写「秒」（脚本内部自动转微秒），不写微秒
    - 素材路径写相对 project.json 所在目录的路径；也可以直接写 http(s) 完整地址
    - 素材以相对路径给出时，会拼到 asset_base 后面变成公网 URL（服务端要能访问）
    - captions.source 支持 timeline_json / inline / srt 三种
"""

import os
import re
import sys
import json
import argparse
import urllib.request
import urllib.error
import urllib.parse

os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = os.environ.get(
    "CAPCUT_MATE_BASE", "https://capcut-mate.jcaigc.cn/openapi/capcut-mate/v1"
).rstrip("/")

SEC = 1_000_000  # 1 秒 = 1000000 微秒


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------

def to_us(seconds):
    """秒 -> 微秒（整数）"""
    return int(round(float(seconds) * SEC))


def is_url(s):
    return isinstance(s, str) and s.lower().startswith(("http://", "https://"))


def build_url(asset_base, rel):
    """相对路径 -> 公网 URL（中文按 URL 编码）"""
    if is_url(rel):
        return rel
    if not asset_base:
        raise ValueError("素材 %s 是相对路径，但 project.json 没配 asset_base" % rel)
    clean = rel.replace("\\", "/").lstrip("/")
    return asset_base.rstrip("/") + "/" + urllib.parse.quote(clean)


def short_name(url):
    """URL -> 便于阅读的文件名（中文解码 + 截断）"""
    name = urllib.parse.unquote(url.rstrip("/").split("/")[-1])
    return name if len(name) <= 34 else name[:32] + ".."


def post_json(endpoint, payload, timeout=300):
    url = BASE + "/" + endpoint
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError("%s 失败 HTTP %s: %s" % (endpoint, e.code, body[:400]))
    except urllib.error.URLError as e:
        raise RuntimeError("%s 网络异常: %s" % (endpoint, e.reason))

    if data.get("code") not in (0, None):
        raise RuntimeError("%s 业务失败: %s" % (endpoint, data.get("message")))
    return data


def warn(msg):
    print("  [!] " + msg)

def ok(msg):
    print("  [OK] " + msg)


# --------------------------------------------------------------------------
# 读配置
# --------------------------------------------------------------------------

def find_project(explicit=None):
    if explicit:
        if not os.path.isfile(explicit):
            sys.exit("[X] 找不到配置文件: %s" % explicit)
        return os.path.abspath(explicit)

    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (
        os.path.join(here, "project.json"),
        os.path.join(here, "..", "..", "project.json"),
        os.path.join(os.getcwd(), "project.json"),
    ):
        if os.path.isfile(cand):
            return os.path.abspath(cand)
    sys.exit("[X] 没找到 project.json，请用 --project 指定")


def load_project(path):
    with open(path, encoding="utf-8") as f:
        try:
            proj = json.load(f)
        except json.JSONDecodeError as e:
            sys.exit("[X] project.json 不是合法 JSON：%s" % e)
    proj["_path"] = path
    proj["_root"] = os.path.dirname(path)
    return proj


# --------------------------------------------------------------------------
# 字幕来源
# --------------------------------------------------------------------------

def parse_srt(path):
    """解析 SRT -> [{start, end, text}]，时间转秒"""
    with open(path, encoding="utf-8-sig") as f:
        raw = f.read().replace("\r\n", "\n")

    pat = re.compile(
        r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
    )
    out = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        idx = 0
        if lines[0].strip().isdigit():
            idx = 1
        if idx >= len(lines):
            continue
        m = pat.search(lines[idx])
        if not m:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = m.groups()
        start = int(h1) * 3600 + int(m1) * 60 + int(s1) + int(ms1.ljust(3, "0")) / 1000.0
        end = int(h2) * 3600 + int(m2) * 60 + int(s2) + int(ms2.ljust(3, "0")) / 1000.0
        text = " ".join(lines[idx + 1:]).strip()
        if text:
            out.append({"start": start, "end": end, "text": text})
    return out


def collect_captions(cfg, root):
    """按配置取字幕列表，统一成 [{start(秒), end(秒), text}]"""
    source = (cfg.get("source") or "timeline_json").lower()

    def finish(items):
        return [{"start": c["start"], "end": c["end"],
                 "text": clean_text(c["text"], cfg.get("text_cleanup") or {})}
                for c in items]

    if source == "inline":
        raw = cfg.get("items") or []
        return finish([
            {"start": float(c["start"]), "end": float(c["end"]), "text": c["text"]}
            for c in raw
        ])

    path = cfg.get("path")
    if not path:
        raise ValueError("captions.path 没填")
    full = path if os.path.isabs(path) else os.path.join(root, path)
    if not os.path.isfile(full):
        raise ValueError("字幕来源文件不存在: %s" % full)

    if source == "srt":
        return finish(parse_srt(full))

    # timeline_json：兼容两种结构
    with open(full, encoding="utf-8") as f:
        data = json.load(f)

    out = []
    if isinstance(data.get("segments"), list):
        for seg in data["segments"]:
            for line in seg.get("lines", []):
                s, e = line.get("abs_start_sec"), line.get("abs_end_sec")
                if s is None or e is None:
                    continue
                out.append({"start": float(s), "end": float(e), "text": line["text"]})
    elif isinstance(data.get("captions"), list):
        for c in data["captions"]:
            s, e = c.get("start"), c.get("end")
            if s is None or e is None:
                continue
            out.append({"start": float(s), "end": float(e), "text": c["text"]})
    else:
        raise ValueError("无法识别的字幕 JSON 结构（需 segments[].lines[] 或 captions[]）")

    out.sort(key=lambda x: x["start"])
    return finish(out)


TAIL_PUNCT = "，。；：、,.;:!！"
BOOK_MARKS = "《》〈〉「」"


def clean_text(text, cfg):
    """按配置清理字幕文本：去尾部标点 / 去书名号。

    只清尾部标点，句中标点保留 —— 短字幕里行尾的逗号句号是纯粹的视觉噪音。
    问号不在清除名单里：它承载语气，删掉会削弱张力。
    """
    if not text:
        return text
    t = text.strip()
    if cfg.get("strip_book_marks"):
        for ch in BOOK_MARKS:
            t = t.replace(ch, "")
    if cfg.get("strip_tail_punct", True):
        while t and t[-1] in TAIL_PUNCT:
            t = t[:-1].rstrip()
    return t or text


# --------------------------------------------------------------------------
# 校验
# --------------------------------------------------------------------------

def validate(proj):
    problems, notes = [], []

    if not proj.get("shots"):
        problems.append("shots 为空")
    if not proj.get("audios"):
        notes.append("audios 为空，将只生成画面")

    # 镜头连续性
    shots = sorted(proj.get("shots", []), key=lambda x: float(x["start"]))
    if shots:
        if abs(float(shots[0]["start"])) > 1e-6:
            notes.append("第一个镜头不从 0 秒开始（实际 %.2f）" % float(shots[0]["start"]))
        for i in range(len(shots) - 1):
            gap = float(shots[i + 1]["start"]) - float(shots[i]["end"])
            if gap > 1e-6:
                notes.append("镜头 %d→%d 之间有空档 %.2fs" % (i, i + 1, gap))
            elif gap < -1e-6:
                notes.append("镜头 %d→%d 重叠 %.2fs" % (i, i + 1, -gap))
        for i, s in enumerate(shots):
            if float(s["end"]) <= float(s["start"]):
                problems.append("镜头 %d 的 end <= start" % i)

    # 素材是否可访问（只在本地相对路径时检查文件是否存在）
    base = proj.get("asset_base") or ""
    missing = []
    for s in shots:
        rel = s.get("image", "")
        if not is_url(rel):
            p = os.path.join(proj["_root"], rel.replace("/", os.sep))
            if not os.path.isfile(p):
                missing.append(rel)
    for a in proj.get("audios", []):
        rel = a.get("audio", "")
        if not is_url(rel):
            p = os.path.join(proj["_root"], rel.replace("/", os.sep))
            if not os.path.isfile(p):
                missing.append(rel)
    for o in proj.get("overlays") or []:
        rel = o.get("image", "")
        if rel and not is_url(rel):
            p = os.path.join(proj["_root"], rel.replace("/", os.sep))
            if not os.path.isfile(p):
                missing.append(rel)
    if missing:
        notes.append("本地找不到 %d 个素材文件（若已推到 asset_base 可忽略）" % len(missing))
    if not base and not all(is_url(s.get("image", "")) for s in shots):
        problems.append("asset_base 为空且存在相对路径素材，服务端取不到图")

    return problems, notes, missing


def build_plan(proj):
    """构造三个接口的载荷（不含 draft_url），供 dry-run 展示和实跑复用"""
    base = proj.get("asset_base") or ""
    root = proj["_root"]

    image_infos = []
    for s in sorted(proj["shots"], key=lambda x: float(x["start"])):
        item = {
            "image_url": build_url(base, s["image"]),
            "start": to_us(s["start"]),
            "end": to_us(s["end"]),
        }
        tr = s.get("transition")
        if tr:
            item["transition"] = tr
            item["transition_duration"] = to_us(s.get("transition_duration") or 0.5)
        image_infos.append(item)

    audio_infos = []
    for a in sorted(proj.get("audios", []), key=lambda x: float(x["start"])):
        audio_infos.append({
            "audio_url": build_url(base, a["audio"]),
            "start": to_us(a["start"]),
            "end": to_us(a["end"]),
            "volume": float(a.get("volume", 1.0)),
        })

    ccfg = proj.get("captions") or {}
    caps = collect_captions(ccfg, root) if ccfg else []
    captions = [
        {"start": to_us(c["start"]), "end": to_us(c["end"]), "text": c["text"]}
        for c in caps
    ]

    total = 0.0
    if image_infos:
        total = max(i["end"] for i in image_infos) / SEC
    if audio_infos:
        total = max(total, max(a["end"] for a in audio_infos) / SEC)

    overlays = build_overlays(proj, total)

    return image_infos, audio_infos, captions, total, ccfg.get("style", {}), overlays


def build_overlays(proj, total):
    """叠加层：每层单独一次 add_images 调用，独立成轨，叠在背景轨之上。

    层内所有图片共用同一位置（add_images 的 scale/transform 是接口级参数），
    所以只适合「全屏透明 PNG」这种同位置图层。
    """
    base = proj.get("asset_base") or ""
    out = []
    for idx, o in enumerate(proj.get("overlays") or []):
        img = o.get("image")
        if not img:
            continue
        start = float(o.get("start", 0))
        end = float(o.get("end", total if total else 0))
        out.append({
            "name": o.get("name") or ("叠加层%d" % (idx + 1)),
            "image_url": build_url(base, img),
            "start": to_us(start),
            "end": to_us(end),
            "alpha": float(o.get("alpha", 1.0)),
            "scale_x": float(o.get("scale_x", 1.0)),
            "scale_y": float(o.get("scale_y", 1.0)),
            "transform_x": float(o.get("transform_x", 0)),
            "transform_y": float(o.get("transform_y", 0)),
        })
    return out


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="按 project.json 生成剪映草稿")
    ap.add_argument("--project", help="project.json 路径")
    ap.add_argument("--dry-run", action="store_true", help="只校验和打印计划，不调接口")
    ap.add_argument("--show-captions", action="store_true", help="dry-run 时打印全部字幕")
    args = ap.parse_args()

    pj = find_project(args.project)
    proj = load_project(pj)

    book = proj.get("book") or "(未命名)"
    canvas = proj.get("canvas") or {}
    w, h = int(canvas.get("width", 1080)), int(canvas.get("height", 1920))

    print("=" * 64)
    print("项目配置：%s" % pj)
    print("书名：%s    画布：%d×%d" % (book, w, h))
    print("接口：%s" % BASE)
    print("=" * 64)

    # ---- 校验 ----
    print("\n[校验]")
    problems, notes, missing = validate(proj)
    for p in problems:
        print("  [X] " + p)
    for n in notes:
        warn(n)
    if missing:
        for m in missing[:5]:
            print("      - " + m)
        if len(missing) > 5:
            print("      ... 另有 %d 个" % (len(missing) - 5))
    if problems:
        sys.exit("\n[X] 配置有致命问题，已中止")
    ok("配置校验通过")

    image_infos, audio_infos, captions, total, style, overlays = build_plan(proj)

    print("\n[计划]")
    print("  画面 %d 段，音频 %d 段，字幕 %d 条，叠加层 %d 层" % (
        len(image_infos), len(audio_infos), len(captions), len(overlays)))
    print("  总时长 %.1f 秒（%d 微秒）" % (total, to_us(total)))
    for i, it in enumerate(image_infos):
        print("    镜%-2d %5.1f—%5.1f  %s%s" % (
            i, it["start"] / SEC, it["end"] / SEC,
            short_name(it["image_url"]),
            ("  [" + it["transition"] + "]") if it.get("transition") else "",
        ))
    for o in overlays:
        print("    叠   %5.1f—%5.1f  %-10s %s" % (
            o["start"] / SEC, o["end"] / SEC, o["name"], short_name(o["image_url"])))
    for a in audio_infos:
        print("    音   %5.1f—%5.1f  %s" % (
            a["start"] / SEC, a["end"] / SEC, short_name(a["audio_url"])))
    if args.show_captions:
        for c in captions:
            print("    字   %5.2f—%5.2f  %s" % (c["start"] / SEC, c["end"] / SEC, c["text"]))

    if args.dry_run:
        print("\n[DRY-RUN] 未调用任何接口，草稿未创建。")
        return

    # ---- 1. create_draft ----
    print("\n[1/5] 创建草稿")
    r = post_json("create_draft", {"width": w, "height": h})
    draft_url = r["draft_url"]
    ok(draft_url)

    try:
        # ---- 2. add_images ----
        print("\n[2/5] 添加画面（%d 段）" % len(image_infos))
        r = post_json("add_images", {
            "draft_url": draft_url,
            "image_infos": json.dumps(image_infos, ensure_ascii=False),
        })
        draft_url = r.get("draft_url", draft_url)
        ok("已添加 %d 段" % len(r.get("segment_ids", [])))

        # ---- 2.5 叠加层（书名层 / 书封层，独立成轨压在背景轨之上）----
        if overlays:
            print("\n[2.5] 添加叠加层（%d 层）" % len(overlays))
            for o in overlays:
                payload = {
                    "draft_url": draft_url,
                    "image_infos": json.dumps([{
                        "image_url": o["image_url"],
                        "start": o["start"],
                        "end": o["end"],
                    }], ensure_ascii=False),
                }
                if o["alpha"] != 1.0:
                    payload["alpha"] = o["alpha"]
                for k in ("scale_x", "scale_y", "transform_x", "transform_y"):
                    if o[k] != (1.0 if k.startswith("scale") else 0):
                        payload[k] = o[k]
                r = post_json("add_images", payload)
                draft_url = r.get("draft_url", draft_url)
                ok("%s（%.1f—%.1f 秒）" % (o["name"], o["start"] / SEC, o["end"] / SEC))

        # ---- 3. add_audios ----
        if audio_infos:
            print("\n[3/5] 添加音频（%d 段）" % len(audio_infos))
            r = post_json("add_audios", {
                "draft_url": draft_url,
                "audio_infos": json.dumps(audio_infos, ensure_ascii=False),
            })
            draft_url = r.get("draft_url", draft_url)
            ok("已添加")
        else:
            print("\n[3/5] 跳过音频（无）")

        # ---- 4. add_captions ----
        if captions:
            print("\n[4/5] 添加字幕（%d 条）" % len(captions))
            payload = {
                "draft_url": draft_url,
                "captions": json.dumps(captions, ensure_ascii=False),
            }
            payload.update(style or {})
            r = post_json("add_captions", payload)
            draft_url = r.get("draft_url", draft_url)
            ok("已添加 %d 条" % len(captions))
        else:
            print("\n[4/5] 跳过字幕（无）")

        # ---- 5. save_draft ----
        print("\n[5/5] 保存草稿")
        r = post_json("save_draft", {"draft_url": draft_url})
        draft_url = r.get("draft_url", draft_url)
        ok("已保存")

    except RuntimeError as e:
        print("\n[X] 中断：%s" % e)
        print("    已生成的草稿仍在，可继续排查：%s" % draft_url)
        sys.exit(1)

    # ---- 结果 ----
    draft_id = ""
    q = urllib.parse.urlparse(draft_url).query
    if q:
        draft_id = urllib.parse.parse_qs(q).get("draft_id", [""])[0]

    result = {
        "book": book,
        "draft_id": draft_id,
        "draft_url": draft_url,
        "width": w,
        "height": h,
        "shots": len(image_infos),
        "audios": len(audio_infos),
        "captions": len(captions),
        "overlays": len(overlays),
        "total_duration_sec": round(total, 3),
        "project": pj,
    }

    out_cfg = (proj.get("output") or {}).get("result")
    out_path = out_cfg if out_cfg and os.path.isabs(out_cfg) else os.path.join(
        proj["_root"], out_cfg or "draft_result.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 64)
    print("完成")
    print("=" * 64)
    print("  草稿地址: %s" % draft_url)
    print("  draft_id: %s" % draft_id)
    print("  统计: %d 镜 / %d 音 / %d 字幕 / %d 叠加层 / %.1f 秒" % (
        len(image_infos), len(audio_infos), len(captions), len(overlays), total))
    print("  结果落盘: %s" % out_path)
    if draft_id:
        print("\n  下一步（素材本地化，需先关闭剪映）：")
        print("    python localize_draft.py %s" % draft_id)


if __name__ == "__main__":
    main()
