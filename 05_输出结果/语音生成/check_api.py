# -*- coding: utf-8 -*-
"""
语音合成接口连通性诊断
用法：python check_api.py [API_KEY]

只发一个极短的测试请求（消耗极少额度），返回明确的诊断结论。
"""
import os
import sys
import json
import base64
import urllib.request
import urllib.error

os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

URL = "https://openspeech.bytedance.com/api/v3/tts/create"

DIAGNOSIS = {
    45000010: (
        "鉴权失败：X-Api-Key 无效\n"
        "  · 这个 Key 必须属于「语音技术」产品线\n"
        "  · 火山方舟的 ark- 前缀 Key 不能用于本接口\n"
        "  · 获取地址：https://console.volcengine.com/speech/new/setting/apikeys"
    ),
    45000030: (
        "未开通服务：账号没有该服务的资源授权\n"
        "  · 开通路径：火山引擎控制台 > 语音技术 > 开通「音频生成（seed-audio-1.0）」\n"
        "  · 开通后在「API Key 管理」里确认 Key 已关联该服务\n"
        "  · 如果 resource_id 显示 tts.sync.level1，说明缺的是「标准语音合成」授权"
    ),
}


def check(key):
    payload = {
        "model": "seed-audio-1.0",
        "text_prompt": "测试",
        "audio_config": {"format": "wav", "sample_rate": 40000},
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Api-Key": key,
                 "X-Api-Request-Id": "diag-001"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            logid = resp.headers.get("X-Tt-Logid", "")
            if body.get("code") == 0:
                audio = body.get("audio") or ""
                n = len(base64.b64decode(audio)) if audio else 0
                print("✓ 接口可用！")
                print("  音频字节数: %d" % n)
                print("  时长: %s 秒" % body.get("duration"))
                print("  logid: %s" % logid)
                return True
            print("✗ 接口返回错误 code=%s message=%s" % (body.get("code"), body.get("message")))
            print(DIAGNOSIS.get(body.get("code"), "  详见错误码文档：https://docs.volcengine.com/docs/6561/2534853"))
            return False
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        print("✗ HTTP %s" % e.code)
        try:
            j = json.loads(raw)
            code = j.get("code")
            print("  code=%s message=%s" % (code, j.get("message")))
            print("\n" + DIAGNOSIS.get(code, "  详见错误码文档：https://docs.volcengine.com/docs/6561/2534853"))
        except Exception:
            print("  " + raw[:400])
        return False
    except Exception as e:
        print("✗ 网络/请求异常: %s" % e)
        return False


if __name__ == "__main__":
    k = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("VOLC_API_KEY", "")
    if not k:
        print("用法: python check_api.py <API_KEY>")
        print("或先设置环境变量 VOLC_API_KEY")
        sys.exit(2)
    print("=" * 60)
    print("诊断端点: POST %s" % URL)
    print("Key: %s...%s" % (k[:8], k[-6:] if len(k) > 14 else ""))
    print("=" * 60)
    sys.exit(0 if check(k) else 1)
