# -*- coding: utf-8 -*-
"""Mock 演示数据：数据本体外置 mock_data.json，这里只做选取与低置信字段注入。

无 GLM Key 时 /api/upload 返回这些预设结构化数据，保证 Demo 可跑；
预包装的 {value, confidence, status} 低/中置信字段用于演示人工复核分流。
"""
import copy
import hashlib
import json
import os
from typing import Any, Dict

_DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_data.json")
with open(_DATA_PATH, encoding="utf-8") as _f:
    DATA: Dict[str, Any] = json.load(_f)


def _is_domestic_invoice(hint_text: str) -> bool:
    """根据 OCR 文本判断是否为国内增值税电子发票（两组关键词统一在小写文本上比对）"""
    t = (hint_text or "").lower()
    domestic_keywords = ["滴滴", "电子发票", "增值税", "电子普通发票", "客运服务", "小桔", "普通发票"]
    commercial_keywords = ["commercial invoice", "fob", "cif", "exw", "shipper", "consignee", "air freight", "sea freight", "海运"]
    return any(k in t for k in domestic_keywords) and not any(k in t for k in commercial_keywords)


def _extract_variant_from_filename(filename: str) -> int:
    """从文件名提取 hash 作为 mock variant 索引，让不同 PDF 返回不同 mock 数据"""
    name = filename or ""
    h = int(hashlib.md5(name.encode()).hexdigest(), 16)
    return h % 3  # 最多 3 个 variant


def _mock_result(doc_type: str, hint_text: str = "", filename: str = "") -> Dict[str, Any]:
    """生成带置信度的 mock 抽取结果——根据文件名 variant 返回不同数据"""
    variant = _extract_variant_from_filename(filename)
    if doc_type == "booking":
        # 托书：vessel_name 中置信 / remarks 低置信，演示人工复核分流
        return copy.deepcopy(DATA["booking_variants"][0])
    if doc_type == "invoice":
        if _is_domestic_invoice(hint_text):
            raw = copy.deepcopy(DATA["invoice_domestic"])
            raw.update(copy.deepcopy(DATA["invoice_domestic_low_overrides"]))
            return raw
        variants = DATA["invoice_commercial_variants"]
        idx = variant % len(variants)
        # 故意让 1-2 个字段低可信，展示置信度标记效果
        raw = copy.deepcopy(variants[idx])
        raw.update(copy.deepcopy(DATA["invoice_commercial_low_overrides"][idx]))
        return raw
    variants = DATA["quotation_variants"]
    raw = copy.deepcopy(variants[variant % len(variants)])
    raw.update(copy.deepcopy(DATA["quotation_low_overrides"]))
    return raw
