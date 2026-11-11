# -*- coding: utf-8 -*-
"""从最终音频反推逐行时间轴，重建「语音时长清单.json」。

场景：音频经过增益/限幅（或任何非 TTS 直接产物）后，逐行时间轴需要重算。
原理：逐行合成的音频在行与行之间留了静音间隙，检测静音段即可找到边界；
      行内也可能有气口，所以用「每行字数 → 语速」做动态规划合并，
      挑出与目标字速最吻合的分组方式。
"""
import argparse
import json
import math
import os
import wave

import numpy as np


DROP = "，。、；：？！…—·「」『』《》（）()\"'“”‘’,.;:?! 　"


def count_chars(text):
    """有效字数：去掉标点与引号，只数要发音的字（与 tts_lines.py 口径一致）。"""
    return max(1, sum(1 for c in text if c not in DROP))


def read_mono(path):
    w = wave.open(path, "rb")
    ch, sw, r, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    a = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float64).reshape(-1, ch).mean(axis=1) / 32768.0
    w.close()
    return a, ch, r


def voiced_segments(a, r, thr_ratio=0.03, min_gap_ms=150, pad_ms=20):
    fsz = int(0.01 * r)
    nf = len(a) // fsz
    E = np.sqrt((a[:nf * fsz].reshape(nf, fsz) ** 2).mean(axis=1))
    ref = E[E > E.max() * 0.05]
    if len(ref) == 0:
        return []
    thr = float(np.sqrt((ref ** 2).mean())) * thr_ratio
    sil = E < thr

    runs = []
    i = 0
    while i < nf:
        if sil[i]:
            j = i
            while j < nf and sil[j]:
                j += 1
            if (j - i) >= min_gap_ms / 10.0:
                runs.append((i, j))
            i = j
        else:
            i += 1

    # 有声段 = 静音段之间
    segs = []
    prev = 0
    for s, e in runs:
        if s > prev:
            segs.append((prev, s))
        prev = e
    if prev < nf:
        segs.append((prev, nf))

    pad = pad_ms / 1000.0
    out = []
    for s, e in segs:
        start = max(0.0, s * 0.01 - pad)
        end = min(len(a) / r, e * 0.01 + pad)
        out.append((start, end))
    return out


def best_grouping(segs, char_counts, target_rate):
    """把 len(segs) 个有声段合并成 len(char_counts) 行，使每行语速贴近 target。"""
    K, M = len(segs), len(char_counts)
    if K < M:
        raise SystemExit("[X] 检测到 %d 个有声段，少于 %d 行，阈值太严" % (K, M))

    def cost(j, p, k):
        dur = segs[k - 1][1] - segs[p][0]
        if dur <= 0.05:
            return 1e9
        cps = char_counts[j] / dur
        if cps < 3.0 or cps > 10.0:
            return 1e6 + (cps - 3.0 if cps < 3.0 else cps) ** 2
        return (cps - target_rate) ** 2

    INF = float("inf")
    f = [[INF] * (K + 1) for _ in range(M + 1)]
    back = [[-1] * (K + 1) for _ in range(M + 1)]
    f[0][0] = 0.0
    for j in range(1, M + 1):
        for k in range(j, K + 1):
            for p in range(j - 1, k):
                if f[j - 1][p] == INF:
                    continue
                c = f[j - 1][p] + cost(j - 1, p, k)
                if c < f[j][k]:
                    f[j][k] = c
                    back[j][k] = p

    if f[M][K] == INF:
        raise SystemExit("[X] 无可行分组")
    cuts = []
    k = K
    for j in range(M, 0, -1):
        p = back[j][k]
        cuts.append((p, k))
        k = p
    cuts.reverse()
    return cuts, f[M][K]


def build(proj_dir):
    proj = json.load(open(os.path.join(proj_dir, "project.json"), encoding="utf-8"))
    cfg = json.load(open(os.path.join(proj_dir, "01_脚本文案", "tts_segments.json"), encoding="utf-8"))
    target_rate = cfg.get("target_rate") or 5.2
    book = proj.get("book") or ""

    result = {
        "book": book,
        "total_duration_sec": 0.0,
        "timeline_method": "由最终音频反推（静音间隙 + 字数语速动态规划对齐）",
        "segments": [],
    }
    abs_base = 0.0
    total_chars = 0
    total_dur = 0.0

    for seg in cfg["segments"]:
        sid = seg["id"]
        text_lines = [t.strip() for t in (seg.get("text") or "").split("\n") if t.strip()]
        path = os.path.join(proj_dir, "03_成片素材", "音频", book, sid + ".wav")
        a, ch, r = read_mono(path)
        seg_dur = len(a) / r
        segs = voiced_segments(a, r)
        chars_dp = [len(t) for t in text_lines]      # DP 分组用含标点字数（标点即停顿）
        chars_out = [count_chars(t) for t in text_lines]  # 展示与统计用有效字数
        cuts, cost = best_grouping(segs, chars_dp, target_rate)

        lines = []
        for i, (p, k) in enumerate(cuts):
            st, en = segs[p][0], segs[k - 1][1]
            dur = en - st
            lines.append({
                "seq": i + 1,
                "text": text_lines[i],
                "start_sec": round(st, 3),
                "end_sec": round(en, 3),
                "abs_start_sec": round(abs_base + st, 3),
                "abs_end_sec": round(abs_base + en, 3),
                "source": "由音频反推",
                "char_count": chars_out[i],
                "char_per_sec": round(chars_out[i] / dur, 2) if dur > 0 else 0,
            })

        cps = sum(chars_out) / seg_dur if seg_dur else 0
        result["segments"].append({
            "id": sid,
            "title": seg.get("title") or sid,
            "file": sid + ".wav",
            "path": "03_成片素材/音频/%s/%s.wav" % (book, sid),
            "format": "wav",
            "sample_rate": r,
            "channels": ch,
            "char_count": sum(chars_out),
            "duration_sec": round(seg_dur, 3),
            "duration_source": "文件实测",
            "speech_rate": round(cps, 2),
            "lines": lines,
        })

        print("[%s] %.2fs  检测 %d 段 → 归并 %d 行  整体 %.2f 字/秒  代价 %.3f"
              % (sid, seg_dur, len(segs), len(text_lines), cps, cost))
        for ln in lines:
            flag = "" if 3.0 <= ln["char_per_sec"] <= 9.0 else "  [!]"
            print("   %2d %.2f-%.2f  %4.2f字/秒  %s%s"
                  % (ln["seq"], ln["start_sec"], ln["end_sec"], ln["char_per_sec"], ln["text"], flag))

        abs_base += seg_dur
        total_chars += sum(chars_out)
        total_dur += seg_dur

    result["total_duration_sec"] = round(total_dur, 2)
    result["overall_speech_rate"] = round(total_chars / total_dur, 2)

    out_json = os.path.join(proj_dir, "05_输出结果", "语音时长", "语音时长清单.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    json.dump(result, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n→ %s  总时长 %.2fs  %d 行" % (out_json, total_dur, total_chars and sum(len(s["lines"]) for s in result["segments"])))

    # Markdown 摘要
    md = ["# 语音时长清单（%s）" % book, "",
          "- 总时长：%.2f 秒" % total_dur,
          "- 整体字速：%.2f 字/秒" % result["overall_speech_rate"],
          "- 时间轴来源：%s" % result["timeline_method"], ""]
    for s in result["segments"]:
        md.append("## %s（%.2fs，%d 行）" % (s["title"], s["duration_sec"], len(s["lines"])))
        md.append("")
        md.append("| # | 起 | 止 | 时长 | 字/秒 | 文本 |")
        md.append("|---|---|---|---|---|---|")
        for ln in s["lines"]:
            md.append("| %d | %.2f | %.2f | %.2f | %.2f | %s |"
                      % (ln["seq"], ln["start_sec"], ln["end_sec"],
                         ln["end_sec"] - ln["start_sec"], ln["char_per_sec"], ln["text"]))
        md.append("")
    open(os.path.join(proj_dir, "05_输出结果", "语音时长", "语音时长清单.md"),
         "w", encoding="utf-8").write("\n".join(md))
    print("→ 语音时长清单.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    args = ap.parse_args()
    build(os.path.abspath(args.project))
