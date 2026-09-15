# -*- coding: utf-8 -*-
"""导出回归核验：构造带 charge_items 的报价单 payload，打 /api/export 与 /api/batch_export，
下载 Excel 用 openpyxl 读回，断言费用明细块/第二张表存在且数值正确。

用法：先启动后端（8540），再运行  python scripts/verify_export.py
"""
import io
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "http://127.0.0.1:8540"


def _post(path: str, payload: dict) -> bytes:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _f(v, conf, status=None):
    return {"value": v, "confidence": conf,
            "status": status or ("high" if conf >= 0.9 else "medium" if conf >= 0.7 else "low")}


# 与真实抽取同构：表头字段 + charge_items 逐格带置信度（含一格低置信演示分流）
QUOTATION_ER = {
    "quote_number": _f("AFQ-2026-0910-007", 0.94),
    "amount_total": _f(2194.00, 0.94),
    "currency": _f("USD", 0.96),
    "charge_items": [
        {"description": _f("Air Freight Charge", 0.92), "unit": _f("KG", 0.90), "rate": _f(3.5, 0.88),
         "quantity": _f(350, 0.90), "amount": _f(1225.00, 0.94), "currency": _f("USD", 0.96)},
        {"description": _f("燃油附加费", 0.55, "low"), "unit": _f("票", 0.90), "rate": _f(0.5, 0.88),
         "quantity": _f(1, 0.90), "amount": _f(969.00, 0.94), "currency": _f("USD", 0.96)},
    ],
}


def _numeric_cells(ws):
    return [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, (int, float))]


def check_single():
    from openpyxl import load_workbook
    xlsx = _post("/api/export", {"doc_type": "quotation", "extract_result": QUOTATION_ER,
                                 "filename": "sample_quotation.pdf"})
    wb = load_workbook(io.BytesIO(xlsx))
    ws = wb.active
    joined = "\n".join(str(c.value) for row in ws.iter_rows() for c in row if c.value is not None)
    assert "费用明细" in joined, "未找到费用明细区块"
    assert "Air Freight Charge" in joined and "燃油附加费" in joined, "明细行缺失"
    assert "合计 Total" in joined, "合计行缺失"
    nums = _numeric_cells(ws)
    assert any(abs(n - 2194.0) < 0.01 for n in nums), "合计数值不等于 2194（1225+969）"
    assert 55.0 in nums, "置信度对照块未输出 55%"
    print(f"✓ 单份导出：sheet={ws.title} · {ws.max_row} 行 · 费用明细 + 合计 + 置信度对照齐全")


def check_batch():
    from openpyxl import load_workbook
    xlsx = _post("/api/batch_export", {
        "doc_type": "quotation",
        "items": [
            {"filename": "q1.pdf", "extract_result": QUOTATION_ER},
            {"filename": "q2.pdf", "extract_result": QUOTATION_ER},
        ],
    })
    wb = load_workbook(io.BytesIO(xlsx))
    assert "费用明细" in wb.sheetnames, f"批量导出缺费用明细表：{wb.sheetnames}"
    ws2 = wb["费用明细"]
    names = [ws2.cell(row=r, column=1).value for r in range(2, ws2.max_row + 1)]
    assert names.count("q1.pdf") == 2 and names.count("q2.pdf") == 2, f"明细行数不符：{names}"
    print(f"✓ 批量导出：sheets={wb.sheetnames} · 费用明细表 {ws2.max_row - 1} 行（文件名关联主表）")


if __name__ == "__main__":
    check_single()
    check_batch()
    print("导出回归核验全部通过")
