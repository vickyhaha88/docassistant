# -*- coding: utf-8 -*-
"""
DocAssistant · 跨境物流智能单据助手（演示）
处理链路：上传 → 智谱 GLM-4V-Flash 多模态结构化抽取（内置 OCR） → 置信度标记 → 导出 Excel
无 GLM Key 时自动进入 Mock 模式，返回预设结构化数据，保证 Demo 可跑。

模块拆分（原单文件 ~1200 行，按职责分层，函数名与行为不变）：
- config.py        环境变量与 GLM 配置（.env 加载 / Key 状态检查 / glm_config）
- schemas.py       三类单据 Schema 注册表 + 抽取结果归一化（Schema 即合同）
- confidence.py    确定性置信度（规则校验分 + 原文回溯加分 + 类型关键词路由）
- zhipu_client.py  智谱 VLM 客户端（httpx 异步调用、JSON 清洗与严格重试）
- mock_data.py     Mock 演示数据（数据本体外置 mock_data.json）
- exporters.py     Excel 导出构造（发票横表 / 报价单竖排+费用明细块 / 批量大表+明细第二表）
- server.py        本文件：HTTP 路由 + 抽取结果缓存 + 预览缩略图 + uvicorn 入口

兼容两种启动方式：python api/server.py（脚本模式，sys.path[0]=api/）与
uvicorn api.server:app（包模式，api/__init__.py 把 api/ 注入 sys.path）。
下方 `from config import …` 等平级导入在两种模式下都可解析；这批 import 同时把
scripts/ 诊断脚本 `from server import …` 依赖的内部名（glm_config/_key_status/
_load_env/_vlm_extract/_guess_doc_type…）再导出，脚本无需改动。
"""
import base64
import hashlib
import io
import json
import os
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

# ---- 分层模块（平级绝对导入，双启动模式见模块 docstring）----
from config import DEMO_ROOT, logger, _load_env, _key_status, glm_config, is_mock_mode  # noqa: F401
from schemas import DOC_TYPES, _normalize_extracted  # noqa: F401
from confidence import _compute_confidence, _norm_for_match, _attach_confidence, _guess_doc_type  # noqa: F401
from zhipu_client import ExtractionError, _parse_model_json, _vlm_extract  # noqa: F401
from mock_data import _mock_result  # noqa: F401
from exporters import (  # noqa: F401
    INVOICE_FIELD_LABELS, STATUS_ZH, FIELD_LABELS_ZH,
    build_single_workbook, build_batch_workbook,
)


# ============================== FastAPI 应用 ==============================

app = FastAPI(title="DocAssistant · 智能单据助手", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ============================== 预览缩略图 ==============================

def _make_preview_thumbnail(file_bytes: bytes, max_w: int = 600) -> Optional[str]:
    """把 PDF（全部页面纵向拼接）或图片转成缩图 JPEG base64，失败返回 None。
    预览必须覆盖 VLM 看到的每一页：多页单据的关键内容常在后页
    （报价单费用表在第 2 页），只给首页会让"对照原图复核"落空。"""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        from io import BytesIO
        pages = []
        if file_bytes[:4] == b"%PDF":
            import pymupdf
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
            for pg in doc:  # 与 _vlm_extract 同口径：全部页面
                pix = pg.get_pixmap(dpi=120)
                pages.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
        else:
            pages.append(Image.open(BytesIO(file_bytes)).convert("RGB"))

        GAP = 12  # 页与页之间留白，视觉上分清两页
        width = max(p.width for p in pages)
        height = sum(p.height for p in pages) + GAP * (len(pages) - 1)
        canvas = Image.new("RGB", (width, height), (208, 208, 208))
        y = 0
        for p in pages:
            canvas.paste(p, (0, y))
            y += p.height + GAP
        img = canvas

        w, h = img.size
        if w > max_w:
            new_h = int(h * max_w / w)
            img = img.resize((max_w, new_h), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=75, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


# ============================== API ==============================

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "mock_mode": is_mock_mode(),
        "glm_configured": glm_config() is not None,
        "key_status": _key_status((os.environ.get("ZHIPU_API_KEY") or "").strip()),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


# ============================== 样本文件服务 ==============================
# samples/ 下的真实单据通过 API 暴露，前端样本按钮拉取真实文件走完整识别链路
# （此前前端只发 6 字节假 PDF，预览缩略图必然为空）。

SAMPLES_DIR = os.path.normpath(os.path.join(DEMO_ROOT, "..", "samples"))


@app.get("/api/samples")
async def list_samples():
    """列出可用的演示样本单据"""
    if not os.path.isdir(SAMPLES_DIR):
        return {"samples": []}
    names = sorted(
        f for f in os.listdir(SAMPLES_DIR)
        if os.path.isfile(os.path.join(SAMPLES_DIR, f))
        and f.lower().endswith((".pdf", ".png", ".jpg", ".jpeg"))
    )
    return {"samples": [{"name": n, "size": os.path.getsize(os.path.join(SAMPLES_DIR, n))} for n in names]}


@app.get("/api/samples/{name}")
async def get_sample(name: str):
    """返回样本原始文件（仅允许 samples 顶层文件名，防路径穿越）"""
    safe_name = os.path.basename(name)
    path = os.path.normpath(os.path.join(SAMPLES_DIR, safe_name))
    if not path.startswith(SAMPLES_DIR) or not os.path.isfile(path):
        raise HTTPException(404, "样本不存在")
    return FileResponse(path, filename=safe_name)


# ============================== 抽取结果缓存 ==============================
# 演示防卡顿：同一文件（内容哈希）+ 类型 + 模型 + Schema 版本再次上传时，
# 直接返回上一次 GLM 真实抽取的结果（缓存真模型输出，不是 Mock 数据）。
# 上传任何新文件仍走实时调用。条目少（演示规模），不做淘汰。

CACHE_DIR = os.path.join(DEMO_ROOT, "data", "extraction_cache")


def _cache_key(file_bytes: bytes, doc_type: str) -> str:
    schema_hash = hashlib.md5(json.dumps(
        DOC_TYPES.get(doc_type, DOC_TYPES["invoice"])["schema"], sort_keys=True).encode("utf-8")).hexdigest()[:8]
    model = (glm_config() or {}).get("model", "mock")
    return hashlib.sha256(file_bytes + doc_type.encode() + model.encode() + schema_hash.encode()).hexdigest()


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _cache_put(key: str, extracted: Dict[str, Any]) -> None:
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(os.path.join(CACHE_DIR, f"{key}.json"), "w", encoding="utf-8") as f:
            json.dump(extracted, f, ensure_ascii=False)
    except Exception as e:
        logger.warning("[cache] 写入失败（不影响主流程）：%s", e)


def _rebuild_page_text(page) -> str:
    """单页文本层重建：表格区域按"格子"提取（格内换行→空格），表外区域常规提取。

    背景：extract_text() 按"整页同一水平带"连行——同行并排的多个格子各自换行时，
    各格的第 1/2 行 Y 坐标分别相同，左右串行成 "SZX (Shenzhen Destination LAX (Los
    Angeles"，值逐字在原文、整串回溯却匹配不上。find_tables() 用表格边框线（几何
    对象）切出格子坐标，字按坐标归属各自格子，格内换行拼空格，单元格内容完整。

    纯几何确定性重建，不依赖任何模型——校验信源的独立性不受影响；无边框/无表格
    的页面自动退回常规提取（find_tables 检不出表格即原样返回）。
    """
    tables = page.find_tables()
    if not tables:
        return page.extract_text() or ""
    bboxes = [t.bbox for t in tables]

    def _outside(obj) -> bool:
        x0, top, x1, bottom = obj["x0"], obj["top"], obj["x1"], obj["bottom"]
        return not any(x0 >= bx0 - 1 and x1 <= bx1 + 1
                       and top >= btop - 1 and bottom <= bbot + 1
                       for bx0, btop, bx1, bbot in bboxes)

    parts = []
    rest = page.filter(_outside).extract_text() or ""
    if rest:
        parts.append(rest)
    for t in sorted(tables, key=lambda tb: tb.bbox[1]):
        lines = []
        for row in t.extract():
            cells = [re.sub(r"\s+", " ", c or "").strip() for c in row]
            if any(cells):
                lines.append(" | ".join(cells))
        if lines:
            parts.append("\n".join(lines))
    return "\n".join(parts)


@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    force_type: Optional[str] = Form(default=None),
):
    """上传单据，返回 OCR 文本 + AI 结构化抽取结果"""
    try:
        file_bytes = await file.read()
    except Exception as e:
        raise HTTPException(400, f"读取文件失败: {e}")

    if not file_bytes:
        raise HTTPException(400, "文件为空")

    # 步骤 1：提取文本层（文件名 + PDF 全页文本，表格区域格子感知重建）：类型路由 +
    # 前端"原文定位" + 原文回溯校验共用。只取首页会让第 2 页内容（报价单费用表）永远无法定位/回溯
    ocr_text = file.filename or ""
    if file_bytes[:4] == b"%PDF":
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(file_bytes)) as _pdf:
                ocr_text += "\n" + "\n".join(
                    filter(None, (_rebuild_page_text(p) for p in _pdf.pages)))
        except Exception:
            pass

    # 步骤 2：确定单据类型（force_type 优先，批量/类型改选用）
    if force_type in DOC_TYPES:
        doc_type = force_type
    else:
        doc_type = _guess_doc_type(ocr_text or file.filename or "")

    # 步骤 3：结构化抽取（真实模式先查结果缓存：同文件+类型+模型+Schema → 秒回）
    hint = ocr_text or file.filename or ""
    from_cache = False
    if is_mock_mode():
        extracted = _mock_result(doc_type, hint, file.filename)
        mode_used = "mock"
    else:
        ck = _cache_key(file_bytes, doc_type)
        extracted = _cache_get(ck)
        if extracted is not None:
            mode_used = glm_config()["model"]
            from_cache = True
            logger.info("[upload] 命中抽取缓存（%s / %s）", file.filename, doc_type)
        else:
            try:
                # 抽取后立刻归一（发票折叠明细行），缓存里存的就是干净表头结构
                extracted = _normalize_extracted(await _vlm_extract(file_bytes, doc_type), doc_type)
                mode_used = glm_config()["model"]
                _cache_put(ck, extracted)
            except ExtractionError as e:
                # 真实模式失败：显式报错，绝不静默回落 Mock——
                # 假数据一旦被导进 TMS 比报错严重得多
                logger.warning("[upload] GLM 抽取失败（%s）：%s", file.filename, e)
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"GLM 结构化抽取失败：{e}。"
                        f"请检查 api/.env 中的 ZHIPU_API_KEY（可运行 python scripts/diag_glm_auth.py 诊断），"
                        f"或清空 Key 重启后端进入 Mock 演示模式。"
                    ),
                )

    # 步骤 4：挂置信度（确定性规则校验分 + 原文回溯加分；Mock 模式保留预设的中/低分演示分流）
    result_with_confidence = _attach_confidence(
        extracted, ocr_text="" if is_mock_mode() else ocr_text, doc_type=doc_type)

    # 步骤 5：生成预览缩略图（PDF 全部页面拼接或图片原文件 → 缩到 600px 宽 JPEG）
    preview_b64 = None
    try:
        preview_b64 = _make_preview_thumbnail(file_bytes)
    except Exception as e:
        logger.warning("[preview] 缩略图生成失败（%s）：%s", file.filename, e)

    resp = {
        "filename": file.filename,
        "doc_type": doc_type,
        "ocr_text": ocr_text[:3000],  # 前端展示截断
        "extract_result": result_with_confidence,
        "mode_used": mode_used,
        "mock_mode": is_mock_mode(),
        "cached": from_cache,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if preview_b64:
        resp["preview_image"] = preview_b64

    return resp


# ============================== Excel 导出 ==============================
# 构造逻辑全部在 exporters.py；这里只做 HTTP 载荷、文件名与流式返回。

class ExportPayload(BaseModel):
    doc_type: str
    extract_result: Dict[str, Any]
    filename: str = ""


class BatchExportItem(BaseModel):
    filename: str
    extract_result: Dict[str, Any]


class BatchExportPayload(BaseModel):
    doc_type: str
    items: List[BatchExportItem]


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@app.post("/api/export")
async def export_excel(payload: ExportPayload):
    """将结构化结果导出为 Excel。
    发票 → 转置横表（一行一票，TMS 直接导入格式；列顺序按 schema 固定 15 列）；
    报价单/托书 → 保持竖排字段表（字段/值/置信度/状态）；
    报价单另附费用明细块（charge_items 逐行 + 合计 + 置信度对照，发票无明细、托书本无金额明细）。"""
    wb = build_single_workbook(payload.doc_type, payload.extract_result, payload.filename)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"docassistant_{payload.doc_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(buf, media_type=XLSX_MEDIA_TYPE,
                             headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.post("/api/batch_export")
async def batch_export_excel(payload: BatchExportPayload):
    """批量导出：所有单据 → 一张横排大表（TMS 直接导入格式）；
    报价单另附费用明细第二张表（一行一费用项，文件名关联主表）。"""
    wb = build_batch_workbook(payload.doc_type, payload.items)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    count = len(payload.items)
    filename = f"batch_{payload.doc_type}s_{count}docs_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(buf, media_type=XLSX_MEDIA_TYPE,
                             headers={"Content-Disposition": f"attachment; filename={filename}"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8540)
