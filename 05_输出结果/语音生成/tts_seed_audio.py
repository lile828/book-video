# -*- coding: utf-8 -*-
"""
豆包语音合成（seed-audio-1.0）批量脚本
——《假如给我三天光明》书单短视频配音

按接口文档实现：
  POST https://openspeech.bytedance.com/api/v3/tts/create
  鉴权：X-Api-Key（新版控制台）
  模型：seed-audio-1.0
  单次最长 120 秒

输出：
  音频 → 该书专属文件夹
  时长清单 → JSON + Markdown（供字幕对齐、剪映时间线使用）

环境变量：
  VOLC_API_KEY      必填，火山引擎控制台 > API Key 管理
  VOLC_APP_ID      选填，旧版控制台双头鉴权时需要
  VOLC_ACCESS_KEY  选填，旧版控制台双头鉴权时需要
"""

import os
import sys
import io
import json
import base64
import time
import wave
import struct
import urllib.request
import urllib.error

# Windows 控制台中文输出保护
os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API_URL = "https://openspeech.bytedance.com/api/v3/tts/create"
MODEL = "seed-audio-1.0"

# 音色 ID：豆包语音合成模型 2.0「知性女声」
# 固定 speaker 可保证多段合成的音色一致（seed-audio-1.0 默认每次随机音色）
DEFAULT_SPEAKER = "zh_female_zhixingnv_uranus_bigtts"

# ========== 剧本定义 ==========
# 三段：开场白 / 书名 / 正文
# 文本取自 假如给我三天光明_配音字幕稿_60秒_v2.txt（40 行）
# 停顿、语速、重音依据「假如给我三天光明_文案方案_60秒_v2.md」第二、四节
# seed-audio-1.0 的纯文本生成模式：描述 + 待合成文本都放在 text_prompt，
# 且该模型支持用自然语言描述控制总时长与人声说话的具体时间段。

SEGMENTS = [
    {
        "id": "01_开场白",
        "title": "今天要分享的是",
        "text": "今天要分享的是；",
        "instruction": (
            "请合成一段中文朗读音频。用平缓、温和的语气，像向朋友引荐一本书。"
            "语速约每秒4字，总时长约2秒，句末留轻微停顿与期待感。"
            "不要上扬，不要朗诵腔。"
        ),
        "expect_sec": 2.0,
    },
    {
        "id": "02_书名",
        "title": "《假如给我三天光明》",
        "text": "《假如给我三天光明》",
        "instruction": (
            "请合成一段中文朗读音频。念出书名《假如给我三天光明》，"
            "声音沉静有分量，读到书名后稍作停顿让字音落地，收尾干净，尾音不拖。"
            "语速约每秒4字，总时长约2秒，音量略低，带郑重感。"
        ),
        "expect_sec": 2.0,
    },
    {
        "id": "03_正文",
        "title": "正文",
        "text": """海伦·凯勒十九个月大，
失去光，
也失去了声音。

七岁那年，
老师蹲在水井边，
在她手心，
写下水的名字。

书里最动人的，
不是她有多苦。
是她问看得见的朋友：
你在森林里走了一小时，
看到了什么？

朋友说，
没什么特别的。

一个看不见的人，
只靠一双手，
找到了几百样可爱的东西。

她假想自己，
只剩三天光明。

第一天，
看清每一张对她好过的脸。

第二天，
去看黎明，
去看那些她摸过的雕像。

第三天，
看人们上班，
看孩子奔跑。

三天过完，
黑暗重新落下。

她没有遗憾。

我们和她最大的不同，
是我们有一辈子。

一辈子可以看日出，
可我们从不抬头。

这本书很薄。
读完你会想下楼走一趟。

就看看树叶，
是什么颜色。""",
        # 时间轴取自 v2 方案第二节，段内相对时间（正文段起点为 0:00）
        "instruction": (
            "请合成一段中文朗读音频，用沉稳、克制、富有叙事感的语气，"
            "像在夜里轻声讲一个故事。全程不激昂、不煽情、不上扬尾音，"
            "句与句之间留出呼吸的停顿。总时长约57秒，语速约每秒4.7字。"
            "请按以下时间轴分配人声说话的时间段：\n"
            "0:00-0:05 海伦·凯勒十九个月大，失去光，也失去了声音。语速稍慢，情绪下沉。\n"
            "0:05-0:11 老师蹲在水井边，在她手心，写下水的名字。语速放慢，「水的名字」加重。\n"
            "0:11-0:21 是在森林里走了一小时，看到了什么。语速正常，问句后留0.8秒空白。\n"
            "0:21-0:27 一个看不见的人，只靠一双手，找到了几百样可爱的东西。语速略推。\n"
            "0:27-0:40 第一天，看清每一张对她好过的脸。第二天，去看黎明，去看那些她摸过的雕像。第三天，看人们上班，看孩子奔跑。语速稍快，像清单一样推进。\n"
            "0:40-0:45 三天过完，黑暗重新落下。她没有遗憾。语速放慢，情绪回收，「她没有遗憾」加重。\n"
            "0:45-0:53 我们和她最大的不同，是我们有一辈子。一辈子可以看日出，可我们从不抬头。语速正常，「可我们从不抬头」加重。\n"
            "0:53-0:57 这本书很薄。读完你会想下楼走一趟。就看看树叶，是什么颜色。语速由慢到更慢，最后一句收尾要轻要慢，留出余韵。\n"
            "其中「没什么特别的」这一句语气要平淡，平淡才有力量。"
        ),
        "expect_sec": 57.0,
    },
]

def build_line_timeline(seg, subtitle, seg_start):
    """
    按字幕稿的每一行，构建行级时间轴（剪映/字幕对齐直接可用）。

    接口返回的 sentences 是句级时间戳（一次可能覆盖多行），
    words 词级时间戳不一定返回。因此策略：
      1) 先用文本匹配定位每行落在哪个句子里
      2) 同一句覆盖多行时，按各行字数比例在句内分配时间
      3) 未匹配到任何句的行，用相邻已知行插值兜底
    """
    if not subtitle:
        return []
    sentences = subtitle.get("sentences") or []
    lines = [l.strip() for l in seg["text"].split("\n") if l.strip()]

    def norm(s):
        return "".join(ch for ch in (s or "")
                       if ch not in "，。？！；、：…—·《》\"'（）()").strip()

    # ---- 1. 把每一行分配到句子 ----
    # 用「字符位置累计法」：把脚本所有行拼成一条归一化长串，
    # 再把句子的归一化文本在同一长串中定位，
    # 由字符偏移量反查每一行落在哪一句 —— 这样即使模型吞掉了引导语
    # （如"朋友说，"），也不会造成行与句的错位。
    assigns = []
    # 脚本行 -> 在长串中的起止偏移
    line_spans = []
    _acc = ""
    for line in lines:
        n = norm(line)
        start = len(_acc)
        _acc += n
        line_spans.append((start, len(_acc)))
    full = _acc

    if not full:
        assigns = [-1] * len(lines)
    else:
        # 定位每个句子在长串中的位置
        cursor = 0
        sent_spans = []
        for sent in sentences:
            sn = norm(sent.get("text"))
            if not sn:
                sent_spans.append(None)
                continue
            pos = full.find(sn, cursor)
            if pos < 0:
                pos = full.find(sn)
            if pos < 0:
                sent_spans.append(None)
                continue
            sent_spans.append((pos, pos + len(sn)))
            cursor = pos + len(sn)

        # 每行归属：字符区间落在哪个句子的区间内
        for (ls, le) in line_spans:
            hit = -1
            for sidx, span in enumerate(sent_spans):
                if not span:
                    continue
                ss, se = span
                if le > ss and ls < se:      # 有交集
                    hit = sidx
                    break
            assigns.append(hit)

    # ---- 2. 句内按字数比例分配 ----
    # group_lines[s] = 该句覆盖的行下标列表
    group_lines = {}
    for i, sidx in enumerate(assigns):
        if sidx >= 0:
            group_lines.setdefault(sidx, []).append(i)

    out = [None] * len(lines)
    for sidx, idxs in group_lines.items():
        s = sentences[sidx]
        st = s.get("start_time", 0) / 1000.0
        et = s.get("end_time", 0) / 1000.0
        if et < st:
            et = st
        if len(idxs) == 1:
            out[idxs[0]] = {
                "start_sec": round(st, 3),
                "end_sec": round(et, 3),
                "source": "接口句级时间戳",
            }
        else:
            # 句内按字数比例分配（标点不计入字数）
            weights = [max(1, len(norm(lines[i]))) for i in idxs]
            total = sum(weights)
            span = et - st
            cur = st
            for k, i in enumerate(idxs):
                seg_len = span * weights[k] / total
                out[i] = {
                    "start_sec": round(cur, 3),
                    "end_sec": round(cur + seg_len, 3),
                    "source": "句内按字数比例分配",
                }
                cur += seg_len

    # ---- 3. 未匹配行处理 ----
    # 情况一：行落在两句之间（模型吞掉了引导语，如"朋友说，"）
    #   → 归到前一句的尾部，按字数比例从该句结束时间往回分配
    # 情况二：行在首句之前 / 末句之后
    #   → 用相邻已知行插值
    known = [i for i, x in enumerate(out) if x is not None]
    if known and len(known) < len(out):
        durs = {}
        for i in known:
            d = out[i]["end_sec"] - out[i]["start_sec"]
            if d > 0:
                durs[i] = d
        avg_dur = (sum(durs.values()) / len(durs)) if durs else 0.4

        for i in range(len(out)):
            if out[i] is not None:
                continue
            prev = max([k for k in known if k < i], default=None)
            nxt = min([k for k in known if k > i], default=None)

            if prev is not None and nxt is not None:
                # 位于两个已知行之间：按前后行时间比例分配
                p, n = out[prev], out[nxt]
                gap = n["start_sec"] - p["end_sec"]
                step = gap / float(nxt - prev)
                st = p["end_sec"] + step * (i - prev)
                out[i] = {"start_sec": round(st, 3), "end_sec": round(st + step, 3),
                          "source": "线性插值估算"}
            elif prev is not None:
                # 尾部：借用前一句时长顺延
                st = out[prev]["end_sec"]
                d = durs.get(prev, avg_dur)
                for k in range(i, len(out)):
                    if out[k] is not None:
                        continue
                    out[k] = {"start_sec": round(st, 3), "end_sec": round(st + d, 3),
                              "source": "按时长顺延估算"}
                    st += d
            else:
                # 首部：从首句起始往前顺延
                st = out[nxt]["start_sec"] - avg_dur * (nxt - i)
                out[i] = {"start_sec": round(st, 3), "end_sec": round(out[nxt]["start_sec"], 3),
                          "source": "按时长顺延估算"}

    # ---- 4. 组装输出 + 全片绝对时间 ----
    result = []
    for i, line in enumerate(lines):
        x = out[i] or {"start_sec": None, "end_sec": None, "source": "无时间戳"}
        st, et = x["start_sec"], x["end_sec"]
        dur = round(et - st, 3) if (st is not None and et is not None) else None
        note = ""
        # 模型未单独发音的引导语（如"朋友说，"被并入下一句）
        if dur is not None and dur < 0.25:
            note = "模型未单独发音，字幕需按需合并到相邻行"
        result.append({
            "seq": i + 1,
            "text": line,
            "start_sec": st,
            "end_sec": et,
            "abs_start_sec": round(seg_start + st, 3) if st is not None else None,
            "abs_end_sec": round(seg_start + et, 3) if et is not None else None,
            "source": x["source"],
            "note": note,
        })
    return result


def srt_ts(sec):
    """秒 → SRT 时间戳 00:00:00,000"""
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def write_line_timeline(all_timelines, path, book):
    """行级时间轴 Markdown —— 剪映/字幕逐句对齐用"""
    with open(path, "w", encoding="utf-8") as f:
        f.write("# 《%s》逐句时间轴\n\n" % book)
        f.write("> 时间戳来源：接口句级时间戳（精确）｜句内按字数比例分配（推荐，精度足够）"
                "｜线性插值估算 / 按时长顺延估算（推算值）\n")
        f.write("> 标记「模型未单独发音」的行，其字幕时长极短，上剪映时建议与相邻行合并。\n\n")
        for seg in all_timelines:
            if not seg.get("lines"):
                continue
            f.write("## %s（%s）\n\n" % (seg["title"], seg["id"]))
            f.write("| # | 字幕文案 | 起(秒) | 止(秒) | 时长 | 全片起(秒) | 全片止(秒) | 来源 | 备注 |\n")
            f.write("|---|---|---|---|---|---|---|---|---|\n")
            for x in seg["lines"]:
                d = (x["end_sec"] - x["start_sec"]) if x["start_sec"] is not None else None
                f.write("| %d | %s | %s | %s | %s | %s | %s | %s | %s |\n" % (
                    x["seq"], x["text"],
                    "%.2f" % x["start_sec"] if x["start_sec"] is not None else "—",
                    "%.2f" % x["end_sec"] if x["end_sec"] is not None else "—",
                    "%.2f" % d if d is not None else "—",
                    "%.2f" % x["abs_start_sec"] if x["abs_start_sec"] is not None else "—",
                    "%.2f" % x["abs_end_sec"] if x["abs_end_sec"] is not None else "—",
                    x["source"], x.get("note") or ""))
            f.write("\n")


# ========== 目录 ==========
# 以书单视频项目根为基准（脚本位于 <项目根>/05_输出结果/语音生成/）
BOOK = "假如给我三天光明"
PROJ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
AUDIO_DIR = os.path.join(PROJ, "03_成片素材", "音频", BOOK)
DUR_DIR = os.path.join(PROJ, "05_输出结果", "语音时长")


# ========== 工具 ==========
def ensure_dir(p):
    os.makedirs(p, exist_ok=True)
    return p


def wav_duration(path):
    """用 wave 模块读真实时长，PCM/WAV 精确；其他格式回退为文件大小估算"""
    try:
        with wave.open(path, "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate() or 40000
            return round(frames / float(rate), 3), rate, w.getnchannels()
    except Exception:
        return None, None, None


def pcm_duration(path, rate=40000, channels=1, sample_width=2):
    """裸 PCM 按时长计算"""
    size = os.path.getsize(path)
    bytes_per_sec = rate * channels * sample_width
    return round(size / float(bytes_per_sec), 3)


def build_payload(seg, speaker=None, fmt="wav", sample_rate=40000,
                  speech_rate=0, loudness_rate=0, pitch_rate=0,
                  enable_subtitle=True):
    # seed-audio-1.0 纯文本生成模式：生成描述与待合成文本同在 text_prompt
    instruction = seg.get("instruction", "").strip()
    text = seg["text"].strip()
    text_prompt = ("%s\n\n待朗读内容：\n%s" % (instruction, text)) if instruction else text

    body = {
        "model": MODEL,
        "text_prompt": text_prompt,
        "audio_config": {
            "format": fmt,
            "sample_rate": sample_rate,
            "speech_rate": speech_rate,
            "loudness_rate": loudness_rate,
            "pitch_rate": pitch_rate,
            "enable_subtitle": enable_subtitle,
        },
    }
    # 音色：speaker 与 参考音频（audio_data/audio_url）互斥。
    # 文档标准格式：speaker 放在 references 数组内 {"speaker": "<speaker_id>"}
    if speaker:
        body["references"] = [{"speaker": speaker}]
    return body


def call_api(api_key, payload, app_id=None, access_key=None, timeout=120):
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": api_key,
        "X-Api-Request-Id": str(int(time.time() * 1000)),
    }
    # 旧版控制台双头鉴权
    if app_id and access_key:
        headers["X-Api-App-Id"] = app_id
        headers["X-Api-Access-Key"] = access_key

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            logid = resp.headers.get("X-Tt-Logid", "")
    except urllib.error.HTTPError as e:
        # 4xx/5xx 时把响应体里的 code/message/logid 一并抛出，便于排查
        body = e.read().decode("utf-8", errors="replace")
        detail = ""
        code = None
        try:
            j = json.loads(body)
            code = j.get("code")
            detail = " code=%s message=%s" % (code, j.get("message"))
            logid = j.get("logid") or ""
        except Exception:
            detail = " " + body[:300]
        if logid:
            detail += " logid=%s" % logid
        raise RuntimeError("HTTP %s%s\n%s" % (e.code, detail, diagnose(code, e.code)))
    return json.loads(raw.decode("utf-8")), logid


# 常见错误码 → 可执行的排查指引
DIAGNOSIS = {
    45000010: (
        "【鉴权失败】X-Api-Key 无效。\n"
        "  · 确认 Key 属于「语音技术」产品线（openspeech.bytedance.com），"
        "火山方舟的 ark- 前缀 Key 不能用于此接口\n"
        "  · 确认 Key 未被删除/禁用\n"
        "  · 新版控制台获取：https://console.volcengine.com/speech/new/setting/apikeys"
    ),
    45000030: (
        "【未开通服务】账号没有该服务的资源授权（requested resource not granted）。\n"
        "  · 开通路径：火山引擎控制台 > 语音技术 > 开通「音频生成（seed-audio-1.0）」\n"
        "  · 若报错 resource_id=tts.sync.level1，则需开通「标准语音合成」\n"
        "  · 开通后需在「API Key 管理」中确认该 Key 已关联对应服务资源"
    ),
    45000020: (
        "【参数错误】请求体字段不符合接口要求。\n"
        "  · 核对 model / text_prompt / audio_config 字段名与类型\n"
        "  · text_prompt 最大 3000 字符；speaker 与 audio_data/audio_url 互斥"
    ),
    40000000: (
        "【请求格式错误】请检查 Content-Type 与 JSON 结构。"
    ),
}


def diagnose(code, http_status):
    """根据错误码给出可执行的排查指引"""
    if code in DIAGNOSIS:
        return DIAGNOSIS[code]
    if http_status == 401:
        return DIAGNOSIS[45000010]
    if http_status == 403:
        return DIAGNOSIS[45000030]
    if http_status == 404:
        return ("【端点不存在】URL 路径有误。当前使用的端点：\n"
                "  POST https://openspeech.bytedance.com/api/v3/tts/create")
    if http_status == 429:
        return "【限流】请求过于频繁，请降低并发并退避重试。"
    return ""


def synthesize(api_key, seg, out_dir, **kw):
    """合成单段，返回记录 dict"""
    app_id = os.environ.get("VOLC_APP_ID")
    access_key = os.environ.get("VOLC_ACCESS_KEY")
    # speaker 优先级：显式传参 > 环境变量 > 默认音色（保证音色一致）
    speaker = kw.get("speaker") or os.environ.get("VOLC_SPEAKER") or DEFAULT_SPEAKER

    fmt = kw.get("fmt", "wav")
    sample_rate = kw.get("sample_rate", 40000)

    payload = build_payload(seg, speaker=speaker, fmt=fmt,
                            sample_rate=sample_rate,
                            speech_rate=kw.get("speech_rate", 0),
                            loudness_rate=kw.get("loudness_rate", 0),
                            pitch_rate=kw.get("pitch_rate", 0))

    print("  → 请求中 ...", flush=True)
    resp, logid = call_api(api_key, payload, app_id, access_key)

    # 成功响应不含 code 字段（文档示例：audio / duration / url）；
    # 只有出错时才有 code+message。用「有 code 且非 0」判定失败更稳妥。
    if "code" in resp and resp.get("code") != 0:
        raise RuntimeError("接口返回错误 code=%s message=%s logid=%s"
                           % (resp.get("code"), resp.get("message"), logid))

    audio_b64 = resp.get("audio")
    if not audio_b64:
        raise RuntimeError("响应中无 audio 字段 logid=%s body_keys=%s"
                           % (logid, list(resp.keys())))

    audio_bytes = base64.b64decode(audio_b64)
    ext = {"wav": "wav", "mp3": "mp3", "pcm": "pcm", "ogg_opus": "ogg"}.get(fmt, "wav")
    fname = "%s_%s.%s" % (seg["id"], seg["title"].replace("/", "").replace("《", "").replace("》", ""), ext)
    fpath = os.path.join(out_dir, fname)
    with open(fpath, "wb") as f:
        f.write(audio_bytes)

    # ---- 真实时长：优先用接口返回，其次本地实测 ----
    api_duration = resp.get("duration")
    api_original = resp.get("original_duration")
    file_duration = None
    rate = channels = None
    if fmt == "wav":
        file_duration, rate, channels = wav_duration(fpath)
    elif fmt == "pcm":
        file_duration = pcm_duration(fpath, rate=sample_rate)

    real = file_duration if file_duration is not None else api_duration

    rec = {
        "id": seg["id"],
        "title": seg["title"],
        "file": fname,
        "path": os.path.relpath(fpath, PROJ).replace("\\", "/"),
        "format": fmt,
        "sample_rate": sample_rate if fmt != "ogg_opus" else 48000,
        "channels": channels,
        "char_count": len(seg["text"].replace("\n", "")),
        "duration_sec": real,
        "api_duration_sec": api_duration,
        "original_duration_sec": api_original,
        "duration_source": "文件实测" if file_duration is not None else "接口返回",
        "expect_sec": seg.get("expect_sec"),
        "logid": logid,
        "url_expire_note": "接口返回的 url 有效期 2 小时",
    }

    # ---- 字幕信息 ----
    sub = resp.get("subtitle")
    if sub:
        rec["subtitle"] = sub
        # 单独落盘一份，便于后续做字幕对齐
        sub_path = os.path.join(out_dir, seg["id"] + "_字幕.json")
        with open(sub_path, "w", encoding="utf-8") as f:
            json.dump(sub, f, ensure_ascii=False, indent=2)
        rec["subtitle_file"] = os.path.basename(sub_path)

    return rec


# ========== 主流程 ==========
def main():
    api_key = os.environ.get("VOLC_API_KEY")
    if not api_key:
        print("=" * 60)
        print("缺少 API Key。请先设置环境变量：")
        print("  Windows:  set VOLC_API_KEY=你的key")
        print("  或在 .env 中写入 VOLC_API_KEY=...")
        print("Key 获取：https://console.volcengine.com/speech/new/setting/apikeys")
        print("=" * 60)
        return 2

    ensure_dir(AUDIO_DIR)
    ensure_dir(DUR_DIR)

    fmt = os.environ.get("TTS_FORMAT", "wav")
    sample_rate = int(os.environ.get("TTS_SAMPLE_RATE", "40000"))
    speech_rate = int(os.environ.get("TTS_SPEECH_RATE", "0"))
    loudness_rate = int(os.environ.get("TTS_LOUDNESS_RATE", "0"))
    pitch_rate = int(os.environ.get("TTS_PITCH_RATE", "0"))

    results = []
    failed = []
    timelines = []
    seg_cursor = 0.0

    for i, seg in enumerate(SEGMENTS, 1):
        print("\n[%d/%d] %s —— %s" % (i, len(SEGMENTS), seg["id"], seg["title"]), flush=True)
        print("  文本(%d字): %s" % (len(seg["text"].replace("\n", "")), seg["text"][:28].replace("\n", " ")), flush=True)
        try:
            rec = synthesize(api_key, seg, AUDIO_DIR, fmt=fmt,
                             sample_rate=sample_rate, speech_rate=speech_rate,
                             loudness_rate=loudness_rate, pitch_rate=pitch_rate)
            # 行级时间轴（跨段拼接，全片绝对时间）
            lines = build_line_timeline(seg, rec.get("subtitle"), seg_cursor)
            rec["lines"] = lines
            rec["abs_start_sec"] = round(seg_cursor, 3)
            rec["abs_end_sec"] = round(seg_cursor + (rec["duration_sec"] or 0), 3)
            timelines.append({"id": seg["id"], "title": seg["title"], "lines": lines})
            seg_cursor += (rec["duration_sec"] or 0)

            results.append(rec)
            print("  ✓ %s" % rec["file"], flush=True)
            print("    真实时长: %s 秒（全片 %s - %s）" % (
                rec["duration_sec"], rec["abs_start_sec"], rec["abs_end_sec"]), flush=True)
        except Exception as e:
            print("  ✗ 失败: %s" % e, flush=True)
            failed.append({"id": seg["id"], "title": seg["title"], "error": str(e)})

    # ---- 时长清单 ----
    total = round(sum(r["duration_sec"] or 0 for r in results), 3)
    manifest = {
        "book": BOOK,
        "model": MODEL,
        "speaker": DEFAULT_SPEAKER,
        "speaker_name": "知性女声",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "segments": results,
        "failed": failed,
        "total_duration_sec": total,
        "total_char_count": sum(r["char_count"] for r in results),
        "audio_dir": os.path.relpath(AUDIO_DIR, PROJ).replace("\\", "/"),
        "notes": [
            "duration_sec 为本地实测时长（WAV 读帧数 / PCM 按字节数），用于字幕与剪映时间线对齐",
            "original_duration_sec 为接口返回的计费依据",
            "接口返回的 url 有效期 2 小时，已落盘的文件不受影响",
            "lines 为逐句时间轴，abs_* 为全片绝对时间，可直接导入剪映",
            "speaker 固定为知性女声（zh_female_zhixingnv_uranus_bigtts），保证多段音色一致",
        ],
    }

    # 行级时间轴 Markdown
    tl_path = os.path.join(DUR_DIR, "逐句时间轴.md")
    write_line_timeline(timelines, tl_path, BOOK)

    # SRT 字幕（剪映可直接导入）
    srt_path = os.path.join(DUR_DIR, "字幕_%s.srt" % BOOK)
    MIN_DUR = 0.2  # 最短字幕时长，防御零时长/负时长
    with open(srt_path, "w", encoding="utf-8-sig") as f:
        idx = 1
        for seg in timelines:
            for x in seg.get("lines", []):
                if x["abs_start_sec"] is None or x["abs_end_sec"] is None:
                    continue
                st = x["abs_start_sec"]
                et = x["abs_end_sec"]
                if et - st < MIN_DUR:
                    et = st + MIN_DUR
                f.write("%d\n" % idx)
                f.write("%s --> %s\n" % (srt_ts(st), srt_ts(et)))
                f.write("%s\n\n" % x["text"])
                idx += 1

    jpath = os.path.join(DUR_DIR, "语音时长清单.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # Markdown 版
    mpath = os.path.join(DUR_DIR, "语音时长清单.md")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write("# 《%s》配音时长清单\n\n" % BOOK)
        f.write("> 生成时间：%s ｜ 模型：%s ｜ 总时长：**%s 秒**\n\n" % (
            manifest["generated_at"], MODEL, total))
        f.write("| 段落 | 文件 | 字数 | 真实时长(秒) | 接口时长 | 计费时长 | 期望 | 偏差 | 语速(字/秒) |\n")
        f.write("|---|---|---|---|---|---|---|---|---|\n")
        for r in results:
            dur = r["duration_sec"]
            exp = r["expect_sec"]
            dev = ("%+0.1f" % (dur - exp)) if exp else "—"
            spd = ("%.2f" % (r["char_count"] / dur)) if dur else "—"
            f.write("| %s | `%s` | %d | **%.3f** | %s | %s | %s | %s | %s |\n" % (
                r["title"], r["file"], r["char_count"], dur,
                r["api_duration_sec"], r["original_duration_sec"],
                exp, dev, spd))
        f.write("\n**合计**：`%s` ｜ 总字数 %d ｜ 总时长 %.3f 秒\n" % (
            os.path.basename(AUDIO_DIR), manifest["total_char_count"], total))
        if failed:
            f.write("\n## 失败段落\n\n")
            for x in failed:
                f.write("- **%s**（%s）：%s\n" % (x["title"], x["id"], x["error"]))
        f.write("\n## 使用说明\n\n")
        f.write("- 音频目录：`%s`\n" % manifest["audio_dir"])
        f.write("- 「真实时长」为本地实测值（不依赖接口返回），**直接用于字幕时间轴与剪映对齐**\n")
        f.write("- 「计费时长」= `original_duration`，为火山引擎计费依据\n")
        f.write("- 期望值为文案方案 v2 的预估，实测偏差超过 ±15% 需回看该段文案或调整语速\n")
        f.write("\n## 同目录产出文件\n\n")
        f.write("| 文件 | 用途 |\n|---|---|\n")
        f.write("| `语音时长清单.json` | 结构化清单，含每段的 lines 逐句时间轴 |\n")
        f.write("| `语音时长清单.md` | 本文件，人工查看 |\n")
        f.write("| `逐句时间轴.md` | 每句文案的起止时间（全片绝对时间） |\n")
        f.write("| `字幕_%s.srt` | **剪映可直接导入**的字幕文件 |\n" % BOOK)
        f.write("| 各段 `_字幕.json` | 接口原始字级时间戳（词粒度） |\n")

    print("\n" + "=" * 60)
    print("完成。总时长 %s 秒，共 %d 段" % (total, len(results)))
    print("音频目录: %s" % AUDIO_DIR)
    print("时长清单: %s" % mpath)
    if failed:
        print("失败 %d 段: %s" % (len(failed), ", ".join(x["id"] for x in failed)))
    print("=" * 60)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
