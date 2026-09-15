# -*- coding: utf-8 -*-
"""预热抽取结果缓存：把 samples/ 下每份样本 × 每种单据类型真实过一遍 GLM。

全矩阵预热（样本数 × 3 类型）：演示现场无论面试官点哪个类型 Tab（跨类型切换=换
Schema 真实重抽），都命中缓存秒回，不会现场等 10-60s。

用法：先启动后端（8540），再运行  python scripts/warm_cache.py
脚本走 HTTP POST /api/upload（带 force_type），与前端切换 Tab 完全同链路，缓存键必然一致。
"""
import json
import os
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.environ.get("DOCASSISTANT_BASE", "http://127.0.0.1:8540")
SAMPLES_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples"))
DOC_TYPES = ["invoice", "quotation", "booking"]  # 全矩阵：每个样本 × 每种类型


def _post_upload(path: str, force_type: str) -> dict:
    boundary = "----docassistantwarm"
    name = os.path.basename(path)
    with open(path, "rb") as f:
        content = f.read()
    parts = [
        (f"--{boundary}\r\n"
         f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
         f"Content-Type: application/pdf\r\n\r\n").encode("utf-8") + content,
        (f"--{boundary}\r\n"
         f'Content-Disposition: form-data; name="force_type"\r\n\r\n{force_type}').encode("utf-8"),
    ]
    body = b"\r\n".join(parts) + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        BASE + "/api/upload", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=200) as r:
        return json.loads(r.read().decode("utf-8"))


def _conf_stats(er: dict) -> str:
    n = {"high": 0, "medium": 0, "low": 0}
    def walk(x):
        if isinstance(x, list):
            for i in x: walk(i)
        elif isinstance(x, dict):
            if "confidence" in x and "value" in x:
                s = x.get("status") or "medium"
                n[s] = n.get(s, 0) + 1
            else:
                for v in x.values(): walk(v)
    walk(er)
    return f"高置信 {n['high']} / 中 {n['medium']} / 低 {n['low']}"


def main():
    names = sorted(f for f in os.listdir(SAMPLES_DIR)
                   if f.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")))
    if not names:
        print(f"samples 目录为空：{SAMPLES_DIR}")
        return
    total = len(names) * len(DOC_TYPES)
    print(f"全矩阵预热 {len(names)} 份样本 × {len(DOC_TYPES)} 类型 = {total} 组合 → {BASE}")
    ok = fail = cached = 0
    t_all = time.time()
    for name in names:
        path = os.path.join(SAMPLES_DIR, name)
        for dt in DOC_TYPES:
            t0 = time.time()
            try:
                d = _post_upload(path, dt)
            except Exception as e:
                print(f"✗ {name} × {dt} 失败：{e}")
                fail += 1
                continue
            if "doc_type" not in d:
                print(f"✗ {name} × {dt} 后端报错：{str(d.get('detail'))[:120]}")
                fail += 1
                continue
            sec = time.time() - t0
            tag = "缓存命中" if d.get("cached") else "实时抽取"
            if d.get("cached"):
                cached += 1
            ok += 1
            print(f"✓ {name} × {dt} · {tag} · {sec:.1f}s · {_conf_stats(d['extract_result'])}")
    print(f"完成：{ok}/{total} 成功（其中 {cached} 个缓存命中）· 总耗时 {time.time() - t_all:.0f}s。"
          f"演示时任何样本点任何类型 Tab 都秒回（⚡缓存秒回标识）。")
    sys.exit(0 if fail == 0 else 1)


if __name__ == "__main__":
    main()
