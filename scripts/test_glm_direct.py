import os, json, base64, urllib.request, urllib.error

# 直接从 .env 读 Key
key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api", ".env")
key = None
model = "glm-4.6v-flashx"
with open(key_file) as f:
    for line in f:
        line = line.strip()
        if line.startswith("ZHIPU_API_KEY="):
            key = line.split("=", 1)[1].strip('"').strip("'")
        if line.startswith("ZHIPU_VLM_MODEL="):
            model = line.split("=", 1)[1].strip()

print(f"Key 前缀: {key[:8]}..." if key else "Key 未找到!")
print(f"Model: {model}")

# 测 PDF
pdf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples", "sample_commercial_invoice.pdf")
with open(pdf_path, "rb") as f:
    pdf_bytes = f.read()

b64 = base64.b64encode(pdf_bytes).decode("ascii")
file_uri = f"data:application/pdf;base64,{b64}"

prompt = "从上传的商业发票中提取 seller_name, seller_tax_id, invoice_number, invoice_date, buyer_name, amount_total, currency, hs_code, incoterm。严格输出 JSON，字段值设为 null 表示找不到。只输出 JSON，不要其他内容。"

payload = {
    "model": model,
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": file_uri}},
        ],
    }],
    "temperature": 0.1,
}

url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    },
)

print(f"\n请求 URL: {url}")
print(f"Payload size: {len(json.dumps(payload))} bytes")
print("调用中...")

try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    print("\n✅ 成功!")
    print(f"response time: {body.get('usage', '?')}")
    content = body["choices"][0]["message"]["content"]
    print("\n回复 (前500字):")
    print(content[:500])
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8") if hasattr(e, "read") else ""
    print(f"\n❌ HTTP {e.code}")
    print(body[:1000])
except Exception as e:
    print(f"\n❌ 错误: {type(e).__name__}: {e}")
