# -*- coding: utf-8 -*-
"""智谱 GLM VLM 客户端：多模态结构化抽取（httpx 异步）。"""
import base64
import json
import re
from typing import Any, Dict

import httpx

from config import glm_config, logger
from schemas import DOC_TYPES

# ============================== GLM 结构化抽取 ==============================

class ExtractionError(RuntimeError):
    """真实模式抽取失败（认证/网络/模型返回异常）。调用方必须显式处理，不允许静默降级 Mock。"""


def _parse_model_json(content: str) -> Dict[str, Any]:
    """把模型输出解析为 JSON：去 markdown 围栏、截取首尾花括号之间的部分、去尾逗号。
    免费档模型偶发在 JSON 前后混解释文字或留尾逗号，这里做确定性清洗。"""
    text = re.sub(r"```json\s*|\s*```", "", content).strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    text = re.sub(r",\s*([}\]])", r"\1", text)  # 尾逗号
    return json.loads(text)


async def _vlm_extract(file_bytes: bytes, doc_type: str) -> Dict[str, Any]:
    """调用 GLM 多模态模型做结构化抽取（httpx 异步）；失败抛 ExtractionError。"""
    cfg = glm_config()
    if not cfg:
        raise ExtractionError("未配置 ZHIPU_API_KEY")

    meta = DOC_TYPES.get(doc_type, DOC_TYPES["invoice"])
    schema_desc = json.dumps(meta["schema"], ensure_ascii=False, indent=2)

    prompt = (
        f"你是跨境物流单据信息抽取专家。从上传的{meta['display_name']}中提取所有可识别的字段，"
        f"严格按照下面的 JSON Schema 输出。找不到的字段值设为 null，不要编造。"
        f"金额类字段需要去掉千分位逗号和货币符号，只保留数字；件数/重量/体积等数值字段同样只输出数字，不要带单位。"
        f"日期统一为 YYYY-MM-DD 格式。单据可能包含多页图片，请综合所有页面提取字段。\n\n"
        f"Schema:\n{schema_desc}\n\n"
        f"只输出纯 JSON，不要任何解释文字、不要 markdown 代码块标记。"
    )
    if doc_type == "invoice":
        # 发票只抽表头：商品明细表逐行抽取对免费档模型不可靠（实测漏行/错列），
        # 业务上 TMS 导入也只需要表头字段，goods_description 用一句话概括即可
        prompt += (
            "\n注意：发票只提取表头信息（单号/日期/买卖方/金额汇总/币种/贸易术语等），"
            "不提取商品明细表。goods_description 用一句话概括货物（如品名+用途），"
            "所有字段值必须是字符串或数字，不要输出数组。"
        )
    elif doc_type == "quotation":
        # 报价单恰恰相反：费用明细表是核心，必须逐行提取（免费档偶发整表漏抽）
        prompt += (
            "\n注意：费用明细表（Air Freight Charge/燃油附加费/安全附加费等）必须逐行提取到 charge_items，"
            "每行包含 description/unit/quantity/rate/amount（金额去掉千分位逗号），一行不漏；"
            "表尾 Total 合计填入 amount_total，币种填入 currency。"
        )

    try:
        # PDF 逐页转 PNG（VLM 不支持直接吃 PDF）。必须送全部页面：
        # 多页单据的关键内容常在后页——实测报价单费用明细表在第 2 页，
        # 只送首页时模型从未见过该表，charge_items 恒为空数组
        if file_bytes[:4] == b"%PDF":
            import pymupdf
            pdf_doc = pymupdf.open(stream=file_bytes, filetype="pdf")
            img_parts = [
                {"type": "image_url",
                 "image_url": {"url": "data:image/png;base64," + base64.b64encode(
                     pg.get_pixmap(dpi=200).tobytes("png")).decode("ascii")}}
                for pg in pdf_doc
            ]
        else:
            img_parts = [{
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64," + base64.b64encode(file_bytes).decode("ascii")},
            }]

        # httpx.AsyncClient：VLM 单次调用 10-60s，同步 urllib 会把 FastAPI 事件循环卡死
        # （期间 /api/health 等一切请求无响应）；异步化后长抽取与健康检查互不阻塞
        async def _send(prompt_text: str) -> str:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                r = await client.post(
                    cfg["base_url"] + "/api/paas/v4/chat/completions",
                    json={
                        "model": cfg["model"],
                        "messages": [{
                            "role": "user",
                            "content": [{"type": "text", "text": prompt_text}] + img_parts,
                        }],
                        "temperature": 0.1,
                    },
                    headers={"Authorization": f"Bearer {cfg['api_key']}"},
                )
            if r.status_code != 200:
                raise ExtractionError(f"智谱 API HTTP {r.status_code}（{r.text[:200]}）")
            return r.json()["choices"][0]["message"]["content"]

        content = await _send(prompt)
        try:
            parsed = _parse_model_json(content)
        except ValueError:
            # 免费档模型偶发输出非法 JSON（尾逗号/混文字），带更严格约束重试一次
            logger.warning("[VLM] %s 首次输出非合法 JSON（%s...），带严格约束重试", doc_type, content[:120].replace("\n", " "))
            content = await _send(prompt + "\n注意：只输出一个合法 JSON 对象，属性名与字符串值必须用双引号，最后一个属性后不要有逗号，不要输出任何其他文字。")
            try:
                parsed = _parse_model_json(content)
            except ValueError as e2:
                raise ExtractionError(f"模型两次输出均不是合法 JSON（{e2}），建议在 api/.env 换 ZHIPU_VLM_MODEL 或充值用 glm-4.6v-flashx") from e2
        logger.info("[VLM] %s 抽取成功，字段数=%d", doc_type, len(parsed))
        return parsed
    except ExtractionError:
        raise
    except httpx.HTTPError as e:
        # 网络/超时类异常（连接失败、读超时等）；HTTP 状态码错误已在 _send 内转 ExtractionError
        raise ExtractionError(f"智谱 API 网络异常（{type(e).__name__}: {e}）") from e
    except Exception as e:
        raise ExtractionError(f"{type(e).__name__}: {e}") from e
