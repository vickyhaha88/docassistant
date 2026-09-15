# -*- coding: utf-8 -*-
"""诊断智谱 GLM 认证问题。

只输出 HTTP 状态、错误信息、Key 形态特征（长度/是否含点号/首尾少量字符），
不打印 Key 本身。用法：python scripts/diag_glm_auth.py
"""
import json
import os
import sys
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows GBK 控制台兼容
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api"))
from server import glm_config, _key_status  # 复用 server 的 .env 加载逻辑

def main():
    cfg = glm_config()
    if not cfg:
        raw = (os.environ.get("ZHIPU_API_KEY") or "").strip()
        status = _key_status(raw)
        if status == "missing":
            print("未配置 ZHIPU_API_KEY（当前为 Mock 模式），无需诊断")
        else:
            print(f"✗ ZHIPU_API_KEY 格式异常（长度={len(raw)} · 含点号={'.' in raw} · 前缀={raw[:4]}****）")
            print("  智谱 Key 完整格式为 \"32位hex.16位字符\"（含一个点号，约 49 字符）。")
            print("  你可能只复制了点号前半段 → 后端已按未配置处理（Mock 模式）。")
            print("  请到 https://open.bigmodel.cn/ 的 API Keys 页面重新复制完整 Key 更新到 api/.env 后重启后端。")
        return
    key = cfg["api_key"]
    print(f"key 形态 : 长度={len(key)} · 含点号={'.' in key} · 前缀={key[:4]}**** · 尾缀=****{key[-3:]}")
    print(f"base_url : {cfg['base_url']}")
    print(f"model    : {cfg['model']}")

    # 最小文本请求验证认证与模型可用性
    req = urllib.request.Request(
        cfg["base_url"] + "/api/paas/v4/chat/completions",
        data=json.dumps({
            "model": cfg["model"],
            "messages": [{"role": "user", "content": "回复OK"}],
            "max_tokens": 4,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.loads(r.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            print(f"结果     : HTTP {r.status} ✓ 认证通过、模型可用（模型返回: {content[:20]}）")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        print(f"结果     : HTTP {e.code} ✗ {detail}")
        if e.code == 429 and "1113" in detail:
            print("提示     : 1113 = 账户余额不足/无资源包。免费档 VLM 可用 glm-4v-flash；")
            print("           或到 https://open.bigmodel.cn/ 充值后在 api/.env 设 ZHIPU_VLM_MODEL=glm-4.6v-flashx。")
        elif e.code == 401:
            print("提示     : 401 = Key 无效/未激活/复制不完整。去 https://open.bigmodel.cn/ 的 API Keys 页面")
            print("           确认 Key 状态，重新复制完整的 Key 更新到 api/.env 后重启后端。")
    except Exception as e:
        print(f"结果     : 其他错误 {type(e).__name__}: {e}")

if __name__ == "__main__":
    main()
