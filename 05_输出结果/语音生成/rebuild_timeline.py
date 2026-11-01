# -*- coding: utf-8 -*-
"""
重建时间轴 / SRT —— 不重新合成，只用已落盘的字幕 JSON 重算行级时间轴。
用于调整时间轴分配算法后，无需再消耗额度重新生成音频。

用法：python rebuild_timeline.py
"""
import os
import sys
import json
import wave

os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_seed_audio.py")
src = open(SCRIPT, encoding="utf-8").read()
mod_src = src.replace('if __name__ == "__main__":\n    sys.exit(main())', '')
ns = {"__name__": "tts_mod", "__file__": SCRIPT}
exec(compile(mod_src, SCRIPT, "exec"), ns)

BOOK = ns["BOOK"]
PROJ = ns["PROJ"]
AUDIO_DIR = ns["AUDIO_DIR"]
DUR_DIR = ns["DUR_DIR"]
SEGMENTS = ns["SEGMENTS"]


def wav_duration(path):
    with wave.open(path, "rb") as w:
        return round(w.getnframes() / float(w.getframerate()), 3)


def main():
    os.makedirs(DUR_DIR, exist_ok=True)
    results = []
    timelines = []
    seg_cursor = 0.0

    for seg in SEGMENTS:
        # 找已生成的音频与字幕
        wavs = [f for f in os.listdir(AUDIO_DIR)
                if f.startswith(seg["id"]) and f.endswith(".wav")]
        subs = [f for f in os.listdir(AUDIO_DIR)
                if f.startswith(seg["id"]) and f.endswith("_字幕.json")]
        if not wavs or not subs:
            print("跳过 %s（缺少已生成文件）" % seg["id"])
            continue

        wpath = os.path.join(AUDIO_DIR, wavs[0])
        spath = os.path.join(AUDIO_DIR, subs[0])
        dur = wav_duration(wpath)
        sub = json.load(open(spath, encoding="utf-8"))

        lines = ns["build_line_timeline"](seg, sub, seg_cursor)
        rec = {
            "id": seg["id"],
            "title": seg["title"],
            "file": wavs[0],
            "path": os.path.relpath(wpath, PROJ).replace("\\", "/"),
            "format": "wav",
            "char_count": len(seg["text"].replace("\n", "")),
            "duration_sec": dur,
            "api_duration_sec": dur,
            "original_duration_sec": dur,
            "duration_source": "文件实测",
            "expect_sec": seg.get("expect_sec"),
            "abs_start_sec": round(seg_cursor, 3),
            "abs_end_sec": round(seg_cursor + dur, 3),
            "lines": lines,
            "subtitle_file": subs[0],
            "rebuilt": True,
        }
        results.append(rec)
        timelines.append({"id": seg["id"], "title": seg["title"], "lines": lines})
        seg_cursor += dur
        print("✓ %-12s %6.3f 秒 | 逐句 %d 条" % (seg["id"], dur, len(lines)))

    if not results:
        print("没有可重建的文件，请先运行 tts_seed_audio.py")
        return 1

    total = round(sum(r["duration_sec"] for r in results), 3)

    # 写 JSON 清单
    manifest = {
        "book": BOOK,
        "model": ns["MODEL"],
        "generated_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
        "segments": results,
        "failed": [],
        "total_duration_sec": total,
        "total_char_count": sum(r["char_count"] for r in results),
        "audio_dir": os.path.relpath(AUDIO_DIR, PROJ).replace("\\", "/"),
        "notes": [
            "本次为重建：音频未重新合成，仅重算行级时间轴与 SRT",
            "duration_sec 为本地实测时长，用于字幕与剪映时间线对齐",
        ],
    }
    jpath = os.path.join(DUR_DIR, "语音时长清单.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # 写 Markdown 清单
    mpath = os.path.join(DUR_DIR, "语音时长清单.md")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write("# 《%s》配音时长清单\n\n" % BOOK)
        f.write("> 生成时间：%s ｜ 模型：%s ｜ 总时长：**%s 秒**\n\n" % (
            manifest["generated_at"], ns["MODEL"], total))
        f.write("| 段落 | 文件 | 字数 | 真实时长(秒) | 期望 | 偏差 | 语速(字/秒) |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for r in results:
            dev = ("%+0.1f" % (r["duration_sec"] - r["expect_sec"])) if r["expect_sec"] else "—"
            spd = ("%.2f" % (r["char_count"] / r["duration_sec"])) if r["duration_sec"] else "—"
            f.write("| %s | `%s` | %d | **%.3f** | %s | %s | %s |\n" % (
                r["title"], r["file"], r["char_count"], r["duration_sec"],
                r["expect_sec"], dev, spd))
        f.write("\n**合计** ｜ 总字数 %d ｜ 总时长 %.3f 秒\n" % (
            manifest["total_char_count"], total))
        f.write("\n## 同目录产出文件\n\n")
        f.write("| 文件 | 用途 |\n|---|---|\n")
        f.write("| `语音时长清单.json` | 结构化清单，含每段的 lines 逐句时间轴 |\n")
        f.write("| `逐句时间轴.md` | 每句文案的起止时间（全片绝对时间） |\n")
        f.write("| `字幕_%s.srt` | **剪映可直接导入**的字幕文件 |\n" % BOOK)

    # 逐句时间轴
    tl_path = os.path.join(DUR_DIR, "逐句时间轴.md")
    ns["write_line_timeline"](timelines, tl_path, BOOK)

    # SRT
    srt_path = os.path.join(DUR_DIR, "字幕_%s.srt" % BOOK)
    MIN_DUR = 0.2
    with open(srt_path, "w", encoding="utf-8-sig") as f:
        idx = 1
        for seg in timelines:
            for x in seg.get("lines", []):
                if x["abs_start_sec"] is None or x["abs_end_sec"] is None:
                    continue
                st, et = x["abs_start_sec"], x["abs_end_sec"]
                if et - st < MIN_DUR:
                    et = st + MIN_DUR
                f.write("%d\n%s --> %s\n%s\n\n" % (
                    idx, ns["srt_ts"](st), ns["srt_ts"](et), x["text"]))
                idx += 1

    print("\n总时长 %s 秒，重建完成" % total)
    print("清单: %s" % mpath)
    print("SRT : %s" % srt_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
