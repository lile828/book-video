# -*- coding: utf-8 -*-
"""
离线演练：用假的接口响应跑通全链路，
验证 音频落盘 / 时长实测 / 逐句时间轴 / SRT 生成 是否正确。

不消耗额度，不联网（通过 monkey-patch call_api）。
"""
import os
import sys
import json
import base64
import struct
import io
import shutil
import tempfile

os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_seed_audio.py")
src = open(SCRIPT, encoding="utf-8").read()

# 载入模块（把 __name__ 改成非 __main__，避免自动执行 main）
mod_src = src.replace('if __name__ == "__main__":\n    sys.exit(main())', '')
ns = {"__name__": "tts_mod", "__file__": SCRIPT}
exec(compile(mod_src, SCRIPT, "exec"), ns)

# ---------- 构造假响应 ----------
def make_wav(seconds, rate=40000):
    """生成指定秒数的静音 WAV"""
    n = int(seconds * rate)
    data = b"\x00\x00" * n
    buf = io.BytesIO()
    import wave
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data)
    return buf.getvalue()


# 假响应：按段返回不同时长 + 句级字幕
FAKE = {
    "01_开场白": {
        "dur": 2.4,
        "sentences": [{"text": "今天要分享的是；", "start_time": 0, "end_time": 2400}],
    },
    "02_书名": {
        "dur": 2.6,
        "sentences": [{"text": "《假如给我三天光明》", "start_time": 0, "end_time": 2600}],
    },
    "03_正文": {
        "dur": 57.8,
        "sentences": [
            {"text": "海伦·凯勒十九个月大，失去光，也失去了声音。", "start_time": 0, "end_time": 4900},
            {"text": "七岁那年，老师蹲在水井边，在她手心，写下水的名字。", "start_time": 5600, "end_time": 11400},
            {"text": "书里最动人的，不是她有多苦。", "start_time": 12200, "end_time": 15600},
            {"text": "是她问看得见的朋友：你在森林里走了一小时，看到了什么？", "start_time": 16400, "end_time": 21600},
            {"text": "朋友说，没什么特别的。", "start_time": 22400, "end_time": 24800},
            {"text": "一个看不见的人，只靠一双手，找到了几百样可爱的东西。", "start_time": 25600, "end_time": 29600},
            {"text": "她假想自己，只剩三天光明。", "start_time": 30400, "end_time": 33200},
            {"text": "第一天，看清每一张对她好过的脸。", "start_time": 34000, "end_time": 37600},
            {"text": "第二天，去看黎明，去看那些她摸过的雕像。", "start_time": 38400, "end_time": 42400},
            {"text": "第三天，看人们上班，看孩子奔跑。", "start_time": 43200, "end_time": 46800},
            {"text": "三天过完，黑暗重新落下。", "start_time": 47600, "end_time": 50400},
            {"text": "她没有遗憾。", "start_time": 51200, "end_time": 52800},
            {"text": "我们和她最大的不同，是我们有一辈子。", "start_time": 53600, "end_time": 57000},
            {"text": "一辈子可以看日出，可我们从不抬头。", "start_time": 57800, "end_time": 61400},
            {"text": "这本书很薄。读完你会想下楼走一趟。", "start_time": 62200, "end_time": 65200},
            {"text": "就看看树叶，是什么颜色。", "start_time": 66000, "end_time": 57800},
        ],
    },
}

CALL_N = {"i": 0}


def fake_call_api(api_key, payload, app_id=None, access_key=None, timeout=120):
    segs = ns["SEGMENTS"]
    idx = CALL_N["i"]
    CALL_N["i"] += 1
    seg = segs[idx]
    key = seg["id"]
    f = FAKE[key]
    # 从 text_prompt 里反推待朗读文本，确认 instruction+text 都发出去了
    tp = payload["text_prompt"]
    assert "待朗读内容" in tp, "text_prompt 未包含待朗读内容标记"
    assert seg["instruction"][:20] in tp, "text_prompt 未包含生成指令"
    print("    [mock] text_prompt 长度 %d 字（含指令 %d + 正文 %d）" % (
        len(tp), len(seg["instruction"]), len(seg["text"])))
    wav = make_wav(f["dur"])
    return {
        "code": 0,
        "message": "Success",
        "audio": base64.b64encode(wav).decode(),
        "duration": f["dur"],
        "original_duration": f["dur"],
        "subtitle": {
            "text": seg["text"],
            "sentences": f["sentences"],
            "words": [],
        },
    }, "mock-logid-%d" % idx


ns["call_api"] = fake_call_api

# ---------- 临时目录，跑一遍 ----------
tmp = tempfile.mkdtemp(prefix="tts_mock_")
ns["PROJ"] = tmp
ns["AUDIO_DIR"] = os.path.join(tmp, "03_成片素材", "音频", ns["BOOK"])
ns["DUR_DIR"] = os.path.join(tmp, "05_输出结果", "语音时长")
os.environ["VOLC_API_KEY"] = "mock-key"

print("=" * 62)
print("离线演练开始（不消耗额度）")
print("=" * 62)
rc = ns["main"]()

print("\n" + "=" * 62)
print("产物检查")
print("=" * 62)
for root, dirs, files in os.walk(tmp):
    for f in files:
        p = os.path.join(root, f)
        rel = os.path.relpath(p, tmp).replace("\\", "/")
        print("  %-58s %8d bytes" % (rel, os.path.getsize(p)))

# ---- 校验时长清单 ----
mpath = os.path.join(tmp, "05_输出结果", "语音时长", "语音时长清单.json")
m = json.load(open(mpath, encoding="utf-8"))
print("\n=== 时长清单校验 ===")
print("总时长: %s 秒 (期望 62.8)" % m["total_duration_sec"])
assert abs(m["total_duration_sec"] - 62.8) < 0.1, "总时长不符"
for s in m["segments"]:
    print("  %-10s %-14s %6.3f 秒 | 全片 %6.2f-%6.2f | 逐句 %d 条 | %s" % (
        s["id"], s["title"], s["duration_sec"], s["abs_start_sec"],
        s["abs_end_sec"], len(s.get("lines") or []), s["duration_source"]))

# ---- 校验 SRT ----
srt = open(os.path.join(tmp, "05_输出结果", "语音时长", "字幕_假如给我三天光明.srt"),
           encoding="utf-8-sig").read()
blocks = [b for b in srt.strip().split("\n\n") if b.strip()]
print("\n=== SRT 校验 ===")
print("字幕条数: %d" % len(blocks))
print("前3条:")
for b in blocks[:3]:
    print("  " + b.replace("\n", " | "))
print("  ...")
print("  最后1条: " + blocks[-1].replace("\n", " | "))
assert "00:00:0" in blocks[0], "SRT 时间戳格式异常"

# ---- 校验逐句时间轴 ----
tl = open(os.path.join(tmp, "05_输出结果", "语音时长", "逐句时间轴.md"), encoding="utf-8").read()
print("\n=== 逐句时间轴校验 ===")
rows = [l for l in tl.split("\n") if l.startswith("| ") and l.count("|") >= 8]
print("表格数据行数: %d" % (len(rows) - 1))
print("表头: " + rows[0])
print("首行: " + rows[1])
print("末行: " + rows[-1])

# ---- 校验 SRT 时长合理性 ----
print("\n=== SRT 时长合理性校验 ===")
bad = []
for b in blocks:
    ls = b.split("\n")
    ts = ls[1].split(" --> ")
    def sec(x):
        h, m, rest = x.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    dur = sec(ts[1]) - sec(ts[0])
    if dur <= 0:
        bad.append((ls[0], ls[1], ls[2] if len(ls) > 2 else ""))
print("零时长或负时长条数: %d" % len(bad))
for x in bad:
    print("   ", x)
assert not bad, "存在零时长字幕"

# ---- 校验 WAV 真实时长 ----
import wave
print("\n=== 音频文件实测校验 ===")
for s in m["segments"]:
    p = os.path.join(tmp, s["path"].replace("/", os.sep))
    with wave.open(p, "rb") as w:
        d = w.getnframes() / float(w.getframerate())
    print("  %-42s 实测 %.3f 秒 | 清单记录 %.3f 秒 | %s" % (
        s["file"], d, s["duration_sec"], "一致" if abs(d - s["duration_sec"]) < 0.01 else "不一致"))
    assert abs(d - s["duration_sec"]) < 0.01

shutil.rmtree(tmp, ignore_errors=True)
print("\n" + "=" * 62)
print("离线演练全部通过 ✓")
print("=" * 62)
