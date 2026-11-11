# -*- coding: utf-8 -*-
"""去掉逐行音频末尾的孤立爆音（技能包的 clean_clicks 抓不到的那种）。

为什么需要单独一支
------------------
clean_clicks.py 的判据要求爆音「前后各有 180ms 绝对静音」。但 TTS 常在句子
念完之后、文件结束前 40ms 甩一个「哒」：位置离文件尾太近，后面没有 180ms
静音，于是被判成「无爆音」。

这个尾巴的杀伤力不在听感，而在**响度归一化**：voiced_span() 会把爆音当成
句子的最后一个有声帧，行时长因此被拉长 40—60ms，峰值冲到 -1dBFS，于是
gain_with_headroom 为保住 ceiling 把整行增益压下来，最终这一行比相邻行
轻 5—7dB——就是 verify_loudness 报的「相邻落差」。

判据：只看文件尾部的「最后一段连续有声」。
  1. 这段连续有声 ≤ 4 帧（40ms）
  2. 它的峰值比前 200ms 的峰值中位数高 ≥ 12dB
  3. 它之后到文件结束只剩静音
尾部的一个真音节念不到 40ms，所以不会误伤；而「哒」正好落在 1—2 帧。

用法：python tools/trim_tail_click.py --dir 03_成片素材/音频/书名/_lines [--dry-run]
"""
import argparse
import glob
import os
import shutil
import sys
import wave

import numpy as np

FRAME = 0.01          # 10ms 一帧
SPIKE_DB = 12.0       # 相对前 200ms 峰值的抬升
MAX_LEN = 0.04        # 尾段连续有声的最大长度


def analyze(path):
    w = wave.open(path, "rb")
    r, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
    a = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float64)
    a = a.reshape(-1, ch).mean(axis=1) / 32768.0
    w.close()

    step = int(FRAME * r)
    nb = len(a) // step
    if nb < 40:
        return None, a, r, ch
    env = np.abs(a[:nb * step]).reshape(nb, step).max(axis=1)
    db = 20 * np.log10(np.maximum(env, 1e-9))

    # 尾部最后一段「连续有声」的起点
    last = -1
    for i in range(nb - 1, -1, -1):
        if db[i] > -45:
            last = i
            break
    if last < 0:
        return None, a, r, ch

    j = last
    while j > 0 and db[j - 1] > -45:
        j -= 1
    run_len = (last - j + 1) * FRAME
    if run_len > MAX_LEN:
        return None, a, r, ch

    ref_lo = max(0, j - 22)
    ref = db[ref_lo:j]
    if len(ref) < 8:
        return None, a, r, ch
    med = float(np.median(ref))
    peak = float(db[j:last + 1].max())
    lift = peak - med
    if lift < SPIKE_DB:
        return None, a, r, ch

    return (int(j * step), last, med, peak, lift), a, r, ch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "*.wav")))
    hit = 0
    for p in files:
        info, a, r, ch = analyze(p)
        if not info:
            continue
        cut, last, med, peak, lift = info
        print("[%s] %-18s 尾帧 %.1fdB（前段中位 %.1f，抬升 %.1f）切点 %.2fs/共 %.2fs"
              % ("命中" if not args.dry_run else "试运行",
                 os.path.basename(p), peak, med, lift, cut / r, len(a) / float(r)))
        hit += 1
        if args.dry_run:
            continue
        bak = os.path.join(os.path.dirname(args.dir.rstrip("/\\")), "_爆音备份")
        os.makedirs(bak, exist_ok=True)
        shutil.copy2(p, os.path.join(bak, os.path.basename(p)))
        y = a[:cut]
        # 尾部补 60ms 淡出，避免硬切产生新的咔声
        fade = min(int(0.06 * r), len(y))
        if fade > 0:
            y = y.copy()
            y[-fade:] *= np.linspace(1.0, 0.0, fade)
        out = np.repeat(np.clip(y, -1, 1)[:, None], ch, axis=1)
        w = wave.open(p, "wb")
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(r)
        w.writeframes((out * 32767.0).astype("<i2").tobytes())
        w.close()

    print("\n%s %d 处" % ("试运行命中" if args.dry_run else "已处理", hit))


if __name__ == "__main__":
    sys.exit(main())
