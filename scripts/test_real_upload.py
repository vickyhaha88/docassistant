import requests, time, os, json

print("=== 真实 AI 上传测试 ===")
files = [
    ("sample_commercial_invoice.pdf", "invoice"),
    ("sample_quotation.pdf", "quotation"),
]

for fname, ftype in files:
    path = os.path.join(r"D:\AI_Project\DocAssistant\samples", fname)
    print(f"\n📄 {fname}")
    print("-" * 50)
    t0 = time.time()
    with open(path, "rb") as f:
        r = requests.post(
            "http://127.0.0.1:8540/api/upload",
            files={"file": (fname, f, "application/pdf")},
            timeout=180,
        )
    elapsed = time.time() - t0
    d = r.json()
    print(f"  mode_used: {d['mode_used']}")
    print(f"  doc_type:  {d['doc_type']}")
    print(f"  耗时: {elapsed:.1f}s")

    er = d["extract_result"]
    if isinstance(er, dict):
        # 打印前几个关键字段
        for k in list(er.keys())[:8]:
            v = er[k]
            if isinstance(v, dict) and "value" in v:
                val = str(v["value"])[:50]
                conf = v.get("confidence", "?")
                print(f"    {k}: {val}  (conf={conf})")
    else:
        print(f"  extract_result: {str(er)[:300]}")

print("\n✅ 完成")
