import requests, json, os, time

print("=" * 55)
print("🚀 真实 AI 模式（glm-4.6v-flashx）PDF 识别测试")
print("=" * 55)

BASE = r"D:\AI_Project\DocAssistant\samples"
files = [
    "sample_commercial_invoice.pdf",
    "sample_quotation.pdf",
    "滴滴电子发票.pdf",
]

for f in files:
    path = os.path.join(BASE, f)
    print(f"\n📄 {f}")
    print("-" * 50)
    t0 = time.time()
    with open(path, "rb") as fh:
        r = requests.post(
            "http://127.0.0.1:8540/api/upload",
            files={"file": (f, fh, "application/pdf")},
            timeout=60,
        )
    elapsed = time.time() - t0
    d = r.json()
    print(f"  mode_used: {d['mode_used']}")
    print(f"  doc_type:  {d['doc_type']}")
    print(f"  耗时: {elapsed:.1f}s")

    er = d["extract_result"]
    if isinstance(er, dict):
        keys = list(er.keys())[:6]
        for k in keys:
            v = er[k]
            if isinstance(v, dict) and "value" in v:
                print(f"  → {k}: {str(v['value'])[:60]}  (conf={v.get('confidence', '?')})")
        # 低置信
        low = [(k, v) for k, v in er.items()
               if isinstance(v, dict) and "confidence" in v and v["confidence"] < 0.7]
        if low:
            print(f"  ⚠️ 低置信字段 {len(low)} 个:")
            for k, v in low[:3]:
                print(f"    {k}: conf={v['confidence']}")
    else:
        print(f"  extract_result type: {type(er)}")
        print(f"  前 300 字: {str(er)[:300]}")

print("\n✅ 完成")
