# -*- coding: utf-8 -*-
"""配音 A/B 试听对比：同文案、同提示词骨架，只换音色与音色倾向，客观测量 + 拼对比条。"""
import os
import sys
import json
import math
import wave
import shutil

sys.path.insert(0, r"C:/Users/scott/.workbuddy/skills/booklist-video/scripts")
import numpy as np
import tts

OUT = r"05_输出结果/试听对比"
os.makedirs(OUT, exist_ok=True)

TEXT = "你不是抑郁。\n你只是太久，\n没被人好好问过一句，\n“你还好吗”。"

# 现行提示词（原稿，气声向）
OLD_INSTR = (
    "请合成一段中文朗读音频。用低沉、磁性、有叙事感的男声，像深夜电台主播在念一句戳心的话，"
    "全程不激昂、不上扬尾音、不用朗诵腔。第一句「你不是抑郁」咬清楚，像下结论，不上扬。"
    "「你只是太久」稍停半拍，语气软下来。「没被人好好问过一句」放平，不要渲染。"
    "最后「你还好吗」放轻，像真的在问对面的人，句尾微微下压而不是上扬，收得干净。"
    "总时长约6秒，语速约每秒5.2字。"
)

# 新版提示词（实声、胸腔共鸣向）
NEW_INSTR = (
    "请合成一段中文朗读音频。用浑厚、稳重、有胸腔共鸣的成熟男声，像一位四十多岁的男性"
    "在认真跟对面的人说话。声音要结实、有中气、实声为主——不要气声、不要耳语感、"
    "不要刻意把声音压轻压虚。全程语气克制，不激昂，尾音不上扬，但音量要撑住。"
    "第一句「你不是抑郁」字音咬实，像下结论。「你只是太久」稍停半拍，语气放缓但音量不掉。"
    "「没被人好好问过一句」平稳推进。「你还好吗」放慢，声音往下沉，收得干脆。"
    "总时长约6秒，语速约每秒5.2字。"
)

CASES = [
    ("A", "zh_male_shenyeboke_uranus_bigtts", "深夜播客（当前在用）", OLD_INSTR, 0, 0),
    ("B", "zh_male_shenyeboke_uranus_bigtts", "深夜播客+新提示词", NEW_INSTR, -3, -2),
    ("C", "zh_male_cixingjieshuonan_uranus_bigtts", "磁性解说", NEW_INSTR, -3, -2),
    ("D", "zh_male_liufei_uranus_bigtts", "刘飞成熟男声", NEW_INSTR, -3, -2),
]


def load(path):
    w = wave.open(path, "rb")
    ch, sw, r, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    a = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float64).reshape(-1, ch) / 32768.0
    w.close()
    return a.mean(axis=1), r


def voiced_rms_db(x, r):
    step = int(0.02 * r)
    vals = []
    for i in range(0, len(x) - step, step):
        f = x[i:i + step]
        e = math.sqrt(float((f ** 2).mean()))
        if e > 0.004:
            vals.append(e)
    if not vals:
        return -99.0
    a = math.sqrt(sum(v * v for v in vals) / len(vals))
    return 20 * math.log10(max(a, 1e-9))


def spectral(x, r):
    step = int(0.02 * r)
    frames = [x[i:i + step] for i in range(0, len(x) - step, step)
              if math.sqrt(float((x[i:i + step] ** 2).mean())) > 0.006]
    if not frames:
        return None
    s = np.concatenate(frames)
    N = 4096
    if len(s) < N:
        return None
    win = np.hanning(N)
    S = np.zeros(N // 2 + 1)
    for i in range(0, len(s) - N, N // 2):
        S += np.abs(np.fft.rfft(s[i:i + N] * win)) ** 2
    f = np.fft.rfftfreq(N, 1.0 / r)
    mag = np.sqrt(S)

    def band(lo, hi):
        m = (f >= lo) & (f < hi)
        return float((mag[m] ** 2).sum())

    tot = band(20, 16000)
    return {
        "centroid": float((f * mag).sum() / mag.sum()),
        "chest": 100 * band(120, 300) / tot,
        "body": 100 * band(300, 1000) / tot,
        "breath": 100 * band(3000, 8000) / tot,
        "f0": float(f[np.argmax(mag)]),
    }


def normalize(x, target_db=-18.0):
    cur = voiced_rms_db(x, 40000)
    g = 10 ** ((target_db - cur) / 20.0)
    y = x * g
    pk = float(np.abs(y).max())
    if pk > 0.89:  # 峰值封顶 -1 dBFS
        y *= 0.89 / pk
    return y


api_key = os.environ.get("VOLC_API_KEY")
if not api_key:
    raise SystemExit("缺少 VOLC_API_KEY")

rows = []
for tag, spk, name, instr, srate, prate in CASES:
    print("\n[%s] %s  speaker=%s  speech_rate=%d pitch_rate=%d" % (tag, name, spk, srate, prate), flush=True)
    seg = {"id": "AB_%s" % tag, "title": name, "text": TEXT, "instruction": instr}
    rec = tts.synthesize(api_key, seg, OUT, speaker=spk, fmt="wav",
                         sample_rate=40000, speech_rate=srate, loudness_rate=0, pitch_rate=prate)
    p = os.path.join(OUT, rec["file"])
    x, r = load(p)
    db = voiced_rms_db(x, r)
    sp = spectral(x, r)
    rows.append({"tag": tag, "name": name, "speaker": spk, "path": p,
                 "dur": len(x) / r, "db": db, "spec": sp})
    print("    时长 %.2fs  有声RMS %.1f dBFS  重心 %.0fHz  胸腔%.1f%%  实声%.1f%%  气声%.1f%%"
          % (len(x) / r, db, sp["centroid"], sp["chest"], sp["body"], sp["breath"]), flush=True)

# 统一响度后拼一条对比带（每段前 0.6s 静音）
SR = 40000
gap = np.zeros(int(0.7 * SR))
parts = []
for row in rows:
    x, _ = load(row["path"])
    parts.append(gap)
    parts.append(normalize(x))
band = np.concatenate(parts)
band = np.clip(band, -1, 1)
pcm = (band * 32767).astype("<i2")
out = os.path.join(OUT, "AB对比_统一响度.wav")
w = wave.open(out, "wb")
w.setnchannels(1)
w.setsampwidth(2)
w.setframerate(SR)
w.writeframes(pcm.tobytes())
w.close()

print("\n=== 汇总（统一到 -18 dBFS 后比较音色）===")
print("%-3s %-22s %6s %8s %7s %7s %7s %7s" % ("", "音色", "时长", "原生dB", "重心Hz", "胸腔%", "实声%", "气声%"))
for row in rows:
    s = row["spec"]
    print("%-3s %-22s %5.2fs %7.1f %7.0f %6.1f %6.1f %6.1f"
          % (row["tag"], row["name"], row["dur"], row["db"], s["centroid"], s["chest"], s["body"], s["breath"]))
print("\n对比带已输出:", out)
json.dump([{k: v for k, v in r.items() if k != "spec"} | {"spec": r["spec"]} for r in rows],
          open(os.path.join(OUT, "AB测量.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
