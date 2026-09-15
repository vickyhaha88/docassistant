import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api"))
# 加载 .env
from server import _load_env, _vlm_extract, _guess_doc_type
_load_env()

pdf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples", "sample_commercial_invoice.pdf")
with open(pdf_path, "rb") as f:
    pdf_bytes = f.read()

print("调用 _vlm_extract ...")
try:
    result = asyncio.run(_vlm_extract(pdf_bytes, "invoice"))  # _vlm_extract 已异步化（httpx.AsyncClient）
    print(f"返回: type={type(result)}, len={len(result) if isinstance(result, dict) else 'N/A'}")
    if result:
        for k, v in list(result.items())[:5]:
            print(f"  {k}: {v}")
    else:
        print("  空 dict！VLM 调用失败，看控制台 stderr")
except Exception as e:
    print(f"异常: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
