# -*- coding: utf-8 -*-
"""提升已有配音的响度：前视限幅器（look-ahead limiter）。

用途：音色已经定稿、只想把声音调大时用这个，不必重跑 TTS。
好处是音色与逐行时间轴 100% 不变，时长一个采样都不差。

做法：
  1. 按「有声段 RMS」算增益，把整体推到目标响度
  2. 前视限幅：用未来 look_ms 的峰值决定当前增益，只在瞬态处下压，
     不做整体动态压缩，所以音色个性（气声、留白）保留
  3. 硬限幅兜底到 ceiling，保证不削波

用法：
  python tools/gain_and_limit.py --file x.wav --target -16.0
  python tools/gain_and_limit.py --dir 03_成片素材/音频/书名 --target -16.0 --suffix _loud
"""
import argparse
import math
import os
import wave

import numpy as np


def read_wav(path):
    w = wave.open(path, "rb")
    ch, sw, r, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    raw = w.readframes(n)
    w.close()
    a = np.frombuffer(raw, dtype="<i2").astype(np.float64).reshape(-1, ch) / 32768.0
    return a, ch, sw, r


def write_wav(path, a, ch, r):
    x = np.clip(a, -1.0, 1.0)
    x = (x * 32767.0).astype("<i2")
    w = wave.open(path, "wb")
    w.setnchannels(ch)
    w.setsampwidth(2)
    w.setframerate(r)
    w.writeframes(x.tobytes())
    w.close()


def voiced_rms(x, r):
    """只统计有声音的部分，静音段不参与——否则停顿多的音频会被误推爆。"""
    step = int(0.02 * r)
    segs = [x[i:i + step] for i in range(0, len(x) - step, step)
            if math.sqrt(float((x[i:i + step] ** 2).mean())) > 0.004]
    if not segs:
        return 0.0
    return math.sqrt(float((np.concatenate(segs) ** 2).mean()))


def limit(x, r, ceiling_db=-1.0, look_ms=6.0, release_ms=120.0):
    """块级前视限幅：增益只压峰，回升缓慢，避免抽气感。"""
    ceil = 10 ** (ceiling_db / 20.0)
    blk = max(1, int(r * 0.001))          # 1ms 一块
    nb = len(x) // blk
    if nb < 4:
        return np.clip(x, -ceil, ceil)
    pk = np.abs(x[:nb * blk]).reshape(nb, blk).max(axis=1)

    k = max(1, int(look_ms))              # 前视块数
    env = np.empty(nb)
    for i in range(nb):
        env[i] = pk[i:min(nb, i + k + 1)].max()
    env = np.maximum(env, 1e-9)

    g_req = np.minimum(1.0, ceil / env)
    rel = math.exp(-1.0 / release_ms)     # 每 ms 的释放系数

    g = np.empty(nb)
    cur = 1.0
    for i in range(nb):
        t = g_req[i]
        cur = t if t < cur else cur * rel + t * (1.0 - rel)
        g[i] = cur

    centers = (np.arange(nb) + 0.5) * blk
    gs = np.interp(np.arange(len(x)), centers, g)
    return np.clip(x * gs, -ceil, ceil)


def report(tag, x, r):
    vr = voiced_rms(x, r)
    peak = float(np.abs(x).max())
    db = 20 * math.log10(vr) if vr > 0 else -99
    pk = 20 * math.log10(peak) if peak > 0 else -99
    print("  %-14s %.2fs  有声RMS %.1f dBFS  峰值 %.1f dBFS" % (tag, len(x) / r, db, pk))
    return db, pk


def process(path, out_path, target_db, ceiling_db):
    a, ch, sw, r = read_wav(path)
    m = a.mean(axis=1)
    print("[%s]" % os.path.basename(path))
    report("原始", m, r)

    vr = voiced_rms(m, r)
    if vr <= 0:
        raise SystemExit("  [X] 全静音，跳过")
    gain_db = target_db - 20 * math.log10(vr)
    x = m * (10 ** (gain_db / 20.0))
    report("加 %.1fdB" % gain_db, x, r)

    y = limit(x, r, ceiling_db=ceiling_db)
    report("限幅后", y, r)

    out = np.repeat(y[:, None], ch, axis=1)
    write_wav(out_path, out, ch, r)
    print("  → %s" % out_path)
    return gain_db


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=None, help="单个 wav")
    ap.add_argument("--dir", default=None, help="目录，处理其下所有 wav（不含子目录）")
    ap.add_argument("--target", type=float, default=-16.0, help="目标有声段 RMS dBFS")
    ap.add_argument("--ceiling", type=float, default=-1.0, help="峰值上限 dBFS")
    ap.add_argument("--suffix", default="", help="输出文件后缀，空则原地覆盖")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.file and not args.dir:
        raise SystemExit("需要 --file 或 --dir")

    targets = []
    if args.file:
        targets.append(args.file)
    if args.dir:
        targets += [os.path.join(args.dir, f) for f in sorted(os.listdir(args.dir))
                    if f.lower().endswith(".wav")]

    for p in targets:
        if not os.path.exists(p):
            print("[!] 不存在 %s" % p)
            continue
        if args.dry_run:
            a, ch, sw, r = read_wav(p)
            m = a.mean(axis=1)
            vr = voiced_rms(m, r)
            print("[%s] 有声 %.1f → 目标 %.1f，需 +%.1f dB"
                  % (os.path.basename(p), 20 * math.log10(vr), args.target,
                     args.target - 20 * math.log10(vr)))
            continue
        base, ext = os.path.splitext(p)
        out = base + args.suffix + ext
        process(p, out, args.target, args.ceiling)


if __name__ == "__main__":
    main()
