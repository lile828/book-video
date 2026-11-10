# -*- coding: utf-8 -*-
"""逐行配音断点续跑：接口抖动（55001309）时不必从头重跑。

tts_lines.py 会把每行音频缓存到 03_成片素材/音频/<书名>/_lines/<段>_LNN.wav，
但只有传 --reuse 才会复用。本脚本按同样的路径规则扫描缓存，只补缺失/不达标的行，
并在接口抖动时做长退避重试；补完后再跑 `tts_lines.py --project . --reuse` 拼装。

用法：python tools/fill_lines.py --project .
"""
import argparse
import json
import os
import sys
import time
import wave

SKILL = os.path.join(os.path.expanduser("~"), ".workbuddy", "skills", "booklist-video", "scripts")
sys.path.insert(0, SKILL)
import tts_lines as TL  # noqa: E402


def read_wav(path):
    with wave.open(path, "rb") as w:
        raw = w.readframes(w.getnframes())
        rate, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
    return raw, rate, ch, sw


def check(path, text):
    if not os.path.exists(path):
        return None
    try:
        raw, r, ch, sw = read_wav(path)
        s, e, _ = TL.voiced_span(raw, ch, sw, r)
    except Exception:
        return None
    dur = e - s
    n = TL.count_chars(text)
    if dur <= 0.05:
        return None
    return dur if TL.accept_speed(n, dur) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    args = ap.parse_args()
    proj_dir = os.path.abspath(args.project)

    proj = json.load(open(os.path.join(proj_dir, "project.json"), encoding="utf-8"))
    book = proj.get("book", "")
    tts_cfg = proj.get("tts") or {}
    style = tts_cfg.get("base_style") or TL.BASE_STYLE
    cfg = json.load(open(os.path.join(proj_dir, "01_脚本文案", "tts_segments.json"), encoding="utf-8"))
    speaker = cfg.get("speaker") or os.environ.get("VOLC_SPEAKER") or tts_cfg.get("speaker")
    api_key = os.environ.get("VOLC_API_KEY")
    if not api_key:
        print("缺少 VOLC_API_KEY")
        return 1

    asset_dir = proj.get("asset_dir") or ("03_成片素材/音频/%s" % book)
    line_dir = os.path.join(proj_dir, asset_dir, "_lines")
    os.makedirs(line_dir, exist_ok=True)

    total = ok = 0
    for seg in cfg.get("segments") or []:
        lines = [L.strip() for L in seg["text"].split("\n") if L.strip()]
        hints = seg.get("line_hints") or {}
        rate = seg.get("target_rate") or tts_cfg.get("target_rate") or TL.DEFAULT_RATE
        style_hint = seg.get("style_hint") or ""
        print("\n[%s] %d 行，目标 %.1f 字/秒" % (seg["id"], len(lines), rate), flush=True)
        for i, text in enumerate(lines, 1):
            total += 1
            path = os.path.join(line_dir, "%s_L%02d.wav" % (seg["id"], i))
            dur = check(path, text)
            if dur:
                ok += 1
                print("  %02d 已有 %.2fs  %s" % (i, dur, text), flush=True)
                continue

            n = TL.count_chars(text)
            want = round(TL.LEN_BASE + n / rate, 1)
            extra = style_hint
            for kw, hint in hints.items():
                if kw in text:
                    extra = (extra + hint) if extra else hint
                    break

            done = False
            for round_ in range(3):
                instr = TL.build_instruction(want, extra, style)
                for attempt in range(4):
                    try:
                        TL.synth_one(api_key, text, instr, path, speaker, retries=1)
                        break
                    except Exception as e:
                        wait = 4 * (attempt + 1) + round_ * 3
                        print("  %02d 失败（%s），%ds 后重试" % (i, str(e)[:60], wait), flush=True)
                        time.sleep(wait)
                dur = check(path, text)
                if dur:
                    ok += 1
                    done = True
                    print("  %02d 合成 %.2fs  %.1f字/秒  %s" % (i, dur, n / dur, text), flush=True)
                    break
                if os.path.exists(path):
                    raw, r, ch, sw = read_wav(path)
                    s, e, _ = TL.voiced_span(raw, ch, sw, r)
                    cps = n / max(e - s, 0.01)
                    want = max(0.4, min(want * (1.4 if cps > 9 else 0.8), n / 3.0))
                    print("  %02d 语速 %.1f 字/秒，改目标 %.1f 秒重做" % (i, cps, want), flush=True)
            if not done:
                print("  %02d 仍未达标，留待 tts_lines 处理：%s" % (i, text), flush=True)

    print("\n完成 %d/%d 行" % (ok, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
