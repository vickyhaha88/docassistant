import pdfplumber, os
path = r"D:\AI_Project\DocAssistant\samples\sample_commercial_invoice.pdf"
with pdfplumber.open(path) as pdf:
    page = pdf.pages[0]
    text = page.extract_text() or ""
    print(text[:500])
print()
has_square = "■" in text or "\ufffd" in text or "?" in text[:200] and "餐椅" not in text
print(f"含黑方块?: {has_square}")
print(f"包含中文 '餐椅'?: {'餐椅' in text}")
print(f"文件大小: {os.path.getsize(path)/1024:.1f} KB")
