import requests, json, os

BASE = r"D:\AI_Project\DocAssistant\samples"
files = [
    "sample_commercial_invoice.pdf",
    "sample_quotation.pdf", 
    "滴滴电子发票.pdf",
]

for f in files:
    path = os.path.join(BASE, f)
    if not os.path.exists(path):
        print(f"[{f}] MISSING!")
        continue
    with open(path, "rb") as fh:
        r = requests.post(
            "http://127.0.0.1:8540/api/upload",
            files={"file": (f, fh, "application/pdf")}
        )
    d = r.json()
    er = d["extract_result"]
    # 置信度分布
    stats = {"high": 0, "medium": 0, "low": 0}
    for k, v in er.items():
        if isinstance(v, dict) and "confidence" in v:
            c = v["confidence"]
            if c >= 0.9: stats["high"] += 1
            elif c >= 0.7: stats["medium"] += 1
            else: stats["low"] += 1

    print(f"\n{'='*55}")
    print(f"📄 {f}")
    print(f"  doc_type={d['doc_type']}  mode={d['mode_used']}")
    print(f"  conf分布: {json.dumps(stats)}")
    
    # 打印识别到的关键字段（商业发票/国内发票/报价单各取 3 个）
    keys = list(er.keys())[:4]
    for k in keys:
        v = er[k]
        if isinstance(v, dict) and "value" in v:
            print(f"  → {k}: {v['value']} (conf={v['confidence']})")
