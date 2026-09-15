# -*- coding: utf-8 -*-
"""三类单据 Schema 注册表 + 抽取结果归一化（Schema 即合同）。"""
import json
import os
from typing import Any, Dict

from config import DEMO_ROOT

# ============================== Schema 注册表 ==============================
# 三类单据差异化 Schema 外置于 schemas/*.json，作为给 VLM 的"抽取合同"。
# 新增单据类型 = 在 schemas/ 加一份 JSON + 在 DOC_TYPES 注册一项，
# 类型识别 / 提示词 / 置信度 / 前端展示全链路自动复用。

SCHEMAS_DIR = os.path.join(DEMO_ROOT, "schemas")


def _load_schema(name: str) -> Dict[str, Any]:
    with open(os.path.join(SCHEMAS_DIR, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


DOC_TYPES: Dict[str, Dict[str, Any]] = {
    "invoice": {
        "schema": _load_schema("invoice"),
        "display_name": "商业发票 / Commercial Invoice",
        "label": "发票 Invoice",
        "sheet_title": "商业发票",
        "detect_keywords": ["invoice", "发票", "commercial invoice", "tax invoice"],
    },
    "quotation": {
        "schema": _load_schema("quotation"),
        "display_name": "货代报价单 / Freight Quotation",
        "label": "报价单 Quotation",
        "sheet_title": "货代报价单",
        "detect_keywords": ["quotation", "报价", "freight quote", "air freight", "sea freight", "freight quotation"],
    },
    "booking": {
        "schema": _load_schema("booking"),
        "display_name": "托书 / Booking Note",
        "label": "托书 Booking",
        "sheet_title": "托书",
        "detect_keywords": ["booking note", "托书", "订舱", "letter of instruction", "shipper's letter"],
    },
}


def _normalize_extracted(extracted: Dict[str, Any], doc_type: str) -> Dict[str, Any]:
    """Schema 即合同（全类型强制）：模型输出一律按对应 schema 白名单过滤——
    不是识别到什么都装进来，字段集恒定，前端展示与 TMS 导入不受模型输出噪声影响。
    附带守卫：string 型字段收到数组（实测模型把报价单条款 1./2./3. 整列表塞进
    remarks，前端平铺成序号行）折叠成一句话文本，绝不把数组透传。"""
    props = DOC_TYPES.get(doc_type, DOC_TYPES["invoice"])["schema"].get("properties", {})

    def _rows_to_text(rows) -> str:
        descs = []
        for it in rows:
            if isinstance(it, dict):
                d = it.get("description") or it.get("货物描述") or ""
                if d:
                    descs.append(str(d))
            elif it:
                descs.append(str(it))
        return "；".join(descs)

    if doc_type == "invoice":
        # 历史问题：免费档模型偶发把商品明细行塞进 goods_description/line_items
        # （实测 5 行商品只返回 3 行且键名错位），明细数组折叠成一句话品名概括
        gd = extracted.get("goods_description")
        if isinstance(gd, list):
            gd = _rows_to_text(gd) or None
            extracted["goods_description"] = gd
        items = extracted.pop("line_items", None)
        if items and not gd:
            # 发票不返回明细行，但品名至少要概括进货物描述，避免信息全丢
            extracted["goods_description"] = _rows_to_text(items) or None

    # 全类型白名单：schema 外字段无论模型多吐什么都丢弃；
    # string 字段收到数组 → 折叠成文本（报价单条款列表塞 remarks 的实测问题）
    for k in list(extracted.keys()):
        if k not in props:
            extracted.pop(k)
        elif props[k].get("type") == "string" and isinstance(extracted[k], list):
            extracted[k] = _rows_to_text(extracted[k]) or None
    return extracted
