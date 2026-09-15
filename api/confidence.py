# -*- coding: utf-8 -*-
"""确定性置信度：规则校验分 + 原文回溯加分 + 类型关键词路由。"""
import re
from typing import Any, Dict, Optional

from schemas import DOC_TYPES


def _compute_confidence(field_name: str, value: Any, is_cn_invoice: Optional[bool] = None) -> float:
    """确定性规则校验分（0~1）：由代码对字段值做格式/数值/字典校验得出，非模型自评估。

    设计口径（与产品叙事一致："数值、字典、求和等由代码确定性校验"）：
    - 高分：通过专属规则校验（税号/日期/HS 编码格式匹配、币种/贸易术语在字典内、数值可解析）
    - 中分：无专属规则的常规字段，交人工抽查
    - 低分：格式可疑或缺失，强制人工复核
    规则级分流（is_cn_invoice）：校验规则跟着票据子类型走——
    - 国内数电票（电子发票/增值税普票专票）：发票号 20 位纯数字强校验；税额必有（价税合计铁律）
    - 商业发票（Commercial/出口）：发票号为自编号不校验位数；出口常免税，税栏缺失不强制标红
    模型侧置信度（如二次采样一致性）列为 roadmap，当前不参与打分。
    """
    if value is None or value == "" or value == []:
        # 规则级分流：商业发票（出口）常无税栏，缺失不强制标红，交人工抽查确认"无税"
        if is_cn_invoice is False and field_name in ("tax_rate", "tax_amount"):
            return 0.80
        return 0.60  # 缺失字段（留空并标记低分，引导用户补填）

    v = str(value)
    ln = len(v)

    # HS 编码（4-6位数字起头，可带 . 分隔）——必须先于通用"编号"分支判定：
    # hs_code 字段名含 "code"，否则会被下面的短编号规则吞掉（历史 bug）
    if "hs" in field_name:
        return 0.88 if re.match(r"^\d{4,6}([.\-]\d{1,4})*$", v) else 0.60

    # 金额/数字类 —— 可解析即高分，小数位异常降级
    if field_name in ("amount_total", "amount_subtotal", "tax_amount", "gross_weight", "volume",
                      "chargeable_weight", "unit_price", "amount", "container_count", "packages"):
        try:
            float(v.replace(",", ""))
            if "." in v and len(v.split(".")[-1]) > 4:
                return 0.68
            return 0.94
        except Exception:
            return 0.45

    # 税率（档位字典校验，必须先于税号分支——tax_rate 含 "tax" 会被税号正则吞掉恒 0.72）：
    # 中国增值税率是固定档位集合，档位外的"税率"大概率是模型从单据上随手抓的数字
    # （件数/费率/编号片段）冒充——判低分强制人工复核，别让它以中置信混过去
    if field_name == "tax_rate":
        raw = str(v).strip()
        if raw.upper() in ("EXEMPT", "NONE", "N/A") or "免税" in raw:
            return 0.85
        s = raw.rstrip("%").strip()
        try:
            rate = float(s.replace(",", ""))
            if rate < 1:  # 模型偶发输出 0.13 小数形式
                rate *= 100
            return 0.90 if rate in (0, 1, 3, 5, 6, 9, 13, 17) else 0.55
        except Exception:
            return 0.55

    # 税号（统一社会信用代码 18位 / 纳税人识别号 15-20位）
    if "tax" in field_name or "credit_code" in field_name:
        if re.match(r"^[0-9A-Z]{15,20}$", v):
            return 0.90
        return 0.72  # 格式不对 → 可疑但不是完全错

    # 箱型（字典校验）：标准集装箱箱型集合之外的高度可疑
    if field_name == "container_type":
        cu = v.strip().upper()
        return 0.90 if any(cu.startswith(t) for t in
                           ("20GP", "40GP", "40HQ", "45HQ", "20RF", "40RF", "45RF",
                            "20OT", "40OT", "20FR", "40FR")) else 0.72

    # 币种（字典校验）
    if field_name == "currency":
        return 0.96 if v.upper() in ["USD", "CNY", "EUR", "GBP", "HKD", "JPY", "AUD", "CAD"] else 0.78

    # 日期（含 ETD/ETA）
    if field_name.endswith("_date") or field_name in ("valid_until", "etd", "eta"):
        if re.match(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", v):
            return 0.94
        return 0.62

    # 发票号（规则级分流，先于通用短编号分支）
    if "invoice" in field_name and "number" in field_name:
        if is_cn_invoice is True:
            # 国内数电票发票号 = 20 位纯数字（全国统一规则），不符即高度可疑
            return 0.94 if re.fullmatch(r"\d{20}", v) else 0.58
        if is_cn_invoice is False:
            return 0.91  # 商业发票自编号（CI-xxx），无全国规则可校验

    # 发票号/订单号等短编号
    if any(k in field_name for k in ("number", "no", "code")) and ln < 25:
        return 0.91

    # 姓名（人名一般短，容易 OCR 错字）
    if "name" in field_name and ln <= 4:
        return 0.75
    # 公司名称（中长，格式规整）
    if "name" in field_name:
        return 0.87

    # 电话/邮箱
    if "phone" in field_name or "tel" in field_name:
        return 0.83 if re.match(r"[\d\-+\s]{6,20}", v) else 0.62
    if "email" in field_name:
        return 0.82 if "@" in v and "." in v.split("@")[-1] else 0.50

    # 地址（长文本，容易漏字）
    if "address" in field_name:
        return 0.83 if ln > 30 else (0.72 if ln < 10 else 0.86)

    # 货物描述（长文本，专业词）
    if "description" in field_name or "goods" in field_name:
        return 0.87

    # 贸易术语（字典校验，允许带港口后缀如 "FOB Ningbo"）
    if "incoterm" in field_name:
        return 0.88 if any(v.upper().startswith(t) for t in ["FOB", "CIF", "EXW", "DDP", "DAP", "FCA", "CPT"]) else 0.72

    # 重量/数量
    if "quantity" in field_name or "weight" in field_name:
        try:
            float(v.replace(",", ""))
            return 0.90
        except Exception:
            return 0.60

    # 运输方式/船舶信息
    if "transport" in field_name or "shipping" in field_name or "freight" in field_name:
        return 0.86

    # 常规文本字段（港口、备注、付款条款等）无确定性校验手段，给中高分，依赖人工抽查
    return 0.88


def _norm_for_match(s: Any) -> str:
    """归一化用于原文回溯匹配：去空白/千分位逗号/货币符号/百分号，大小写不敏感"""
    return re.sub(r"[\s,，%$￥¥]", "", str(s)).upper()


def _trace_locate(value: Any, hay: str) -> Optional[str]:
    """原文回溯三档定位（扛 pdfplumber 双栏交错 / 跨行拼接排版）：

    - "full"：整串归一化后连续命中（模型照抄原文，最强防幻觉信号）
    - "full"：去括号注释后命中——"SZX (Shenzhen Bao'an)" 的核心 "SZX" 命中。
      双栏表格（起运港|目的港）常被 pdfplumber 左右逐段交错成
      "SZX (Shenzhen Destination LAX (Los Angeles"，注释被打散但核心代码完整
    - "segment"：按标点/空白切 token 后全部命中——内容每个实词都在文本层，
      足以证明不是编造，只是被跨栏拆散/拼接过，给中置信而非高分
    - None：定位不到（可能模型概括/编造/格式换算），不加分
    """
    s = str(value)
    needle = _norm_for_match(s)
    if len(needle) >= 2 and needle in hay:
        return "full"
    stripped = _norm_for_match(re.sub(r"[（(][^（）()]*[）)]", "", s))
    if len(stripped) >= 2 and stripped != needle and stripped in hay:
        return "full"
    tokens = [_norm_for_match(t) for t in re.split(r"[\s,，、/;；()（）\[\]]+", s)]
    tokens = [t for t in tokens if len(t) >= 2]
    if len(tokens) >= 2 and all(t in hay for t in tokens):
        return "segment"
    return None


def _attach_confidence(data: Dict[str, Any], prefix: str = "", ocr_text: str = "", doc_type: str = "") -> Dict[str, Any]:
    """递归给字段挂置信度和状态。若字段已带 value+confidence 则保留不重包。

    置信度 = 基础规则分 与 原文回溯加分 取大者：
    - 基础规则分：_compute_confidence 的确定性格式/字典/数值校验
    - 原文回溯（_trace_locate 三档）：整串/去注释命中加到 0.92——模型照抄原文，
      最强的防幻觉确定性信号；分段命中（token 全在原文但整串断裂，跨栏排版所致）
      加到 0.88 中置信；定位不到不扣分（扫描件无文本层、格式换算等不误伤）。
    """
    hay = _norm_for_match(ocr_text)

    # 规则级分流：按发票子类型选校验规则（国内数电票 vs 出口商业发票）
    is_cn_invoice: Optional[bool] = None
    if doc_type == "invoice":
        t = data.get("invoice_type")
        raw_type = str(t.get("value")) if isinstance(t, dict) and "value" in t else str(t or "")
        if any(k in raw_type for k in ("电子发票", "增值税", "普票", "专票", "数电")):
            is_cn_invoice = True
        elif "commercial" in raw_type.lower() or "商业发票" in raw_type:
            is_cn_invoice = False

    def _score(field_name: str, value: Any) -> float:
        conf = _compute_confidence(field_name, value, is_cn_invoice)
        if hay and value not in (None, "", []):
            tier = _trace_locate(value, hay)
            if tier == "full":
                conf = max(conf, 0.92)
            elif tier == "segment":
                conf = max(conf, 0.88)
        return conf

    def _wrap(field_name: str, value: Any) -> Dict[str, Any]:
        conf = round(_score(field_name, value), 2)
        return {"value": value, "confidence": conf,
                "status": "high" if conf >= 0.9 else ("medium" if conf >= 0.7 else "low")}

    result: Dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, dict):
            if "value" in v and "confidence" in v:
                # 已经是带置信度的包装，保留
                result[k] = v
            else:
                result[k] = _attach_confidence(v, f"{prefix}{k}.", ocr_text, doc_type)
        elif isinstance(v, list):
            result[k] = []
            for item in v:
                if isinstance(item, dict):
                    result[k].append(_attach_confidence(item, f"{prefix}{k}[].", ocr_text, doc_type) or item)
                else:
                    result[k].append(_wrap(f"{prefix}{k}", item))
        else:
            result[k] = _wrap(f"{prefix}{k}", v)
    return result


def _guess_doc_type(text: str) -> str:
    """根据 OCR 文本猜测单据类型：报价单/托书关键词优先，默认发票"""
    t = (text or "").lower()
    for doc_type in ("quotation", "booking", "invoice"):
        if any(k in t for k in DOC_TYPES[doc_type]["detect_keywords"]):
            return doc_type
    return "invoice"  # 默认
