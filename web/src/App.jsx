import React, { useState, useRef, useCallback, useEffect, useMemo } from "react";
import { api, apiFormData, apiDownload, apiBase } from "./api.js";

const SAMPLE_FILES = [
  { name: "sample_commercial_invoice.pdf", label: "🧾 供应商商业发票", docType: "invoice", hint: "Commercial Invoice FOB" },
  { name: "sample_quotation.pdf", label: "✈️ 货代报价单", docType: "quotation", hint: "Air Freight Quotation" },
  { name: "sample_booking.pdf", label: "🚢 海运出口托书", docType: "booking", hint: "Booking Note 2×40HQ" },
  { name: "滴滴电子发票.pdf", label: "🧾 国内电子发票", docType: "invoice", hint: "Domestic e-Invoice" },
];
// 三类单据元信息（托书已上线，与后端 DOC_TYPES 对应）
const DOC_TYPE_META = {
  invoice: { label: "发票 Invoice", icon: "📄" },
  quotation: { label: "报价单 Quotation", icon: "✈️" },
  booking: { label: "托书 Booking", icon: "📑" },
};
const DISABLED_TYPES = new Set(); // 暂无禁用类型

// 置信度阈值：单一定义、全文件共用（与后端 server.py 口径一致）
const CONF = { high: 0.9, medium: 0.7, forceRequired: 0.65 };

// 原文高亮组件：在原文里找到当前字段值，高亮显示上下文（原文来自 VLM 抄录 / PDF 文本层，仅作出处比对）
function OcrHighlight({ text, query }) {
  if (!text) return null;
  const q = (query || "").trim();
  let matched = false;
  let segment = false;
  let parts = [<span key="full" style={{ background: "transparent" }}>{text}</span>];

  // 归一化口径与后端"原文回溯"一致：去空白/千分位/货币符、大小写不敏感。
  // 归一化时保留 原文索引映射，命中后把区间映射回原文再高亮（41835.0 能命中 "41,835.00"）
  const buildNorm = (s) => {
    let norm = "";
    const map = [];
    for (let i = 0; i < s.length; i++) {
      const c = s[i];
      if (/[,\s，%％$￥¥]/.test(c)) continue;
      norm += c.toLowerCase();
      map.push(i);
    }
    return { norm, map };
  };

  // 三档定位（与后端 confidence.py 的 _trace_locate 同口径）：
  // 整串 → 去括号注释（"SZX (Shenzhen Bao'an)" 的核心 "SZX"，扛双栏交错排版）→ 分段（各片段全命中）
  const locate = (hay, raw) => {
    const n1 = buildNorm(raw).norm;
    if (n1.length >= 2 && hay.norm.includes(n1)) return { tier: "full", needle: n1 };
    const n2 = buildNorm(raw.replace(/[（(][^（）()]*[）)]/g, "")).norm;
    if (n2.length >= 2 && n2 !== n1 && hay.norm.includes(n2)) return { tier: "full", needle: n2 };
    const toks = raw.split(/[\s,，、/;；()（）[\]]+/).map((t) => buildNorm(t).norm).filter((t) => t.length >= 2);
    if (toks.length >= 2 && toks.every((t) => hay.norm.includes(t))) {
      // 分段命中：高亮最长的片段（信息量最大的核心词）
      const core = toks.reduce((a, b) => (b.length > a.length ? b : a));
      return { tier: "segment", needle: core };
    }
    return null;
  };

  if (q && q.length >= 2) {
    try {
      const hay = buildNorm(text);
      const loc = locate(hay, q);
      if (loc) {
        matched = true;
        segment = loc.tier === "segment";
        const idx = hay.norm.indexOf(loc.needle);
        const start = hay.map[idx];
        const end = hay.map[idx + loc.needle.length - 1] + 1;
        const context = 150;
        const ctxStart = Math.max(0, start - context);
        const ctxEnd = Math.min(text.length, end + context);
        const before = start > 0 ? "... " : "";
        const after = end < text.length ? " ..." : "";
        parts = [
          <span key="b" style={{ color: "var(--text-3)" }}>{before}{text.slice(ctxStart, start)}</span>,
          <span key="h" style={{ background: "rgba(56,217,235,0.35)", color: "#ffffff", padding: "0 2px", borderRadius: 2, fontWeight: 600 }}>{text.slice(start, end)}</span>,
          <span key="a" style={{ color: "var(--text-3)" }}>{text.slice(end, ctxEnd)}{after}</span>,
        ];
      }
    } catch (e) { /* 忽略 */ }
  }
  const hintStyle = { fontSize: 11, marginBottom: 6, lineHeight: 1.5 };
  return (
    <div className="ocr-text">
      {!q
        ? <div style={{ ...hintStyle, color: "var(--warn)" }}>⚠ 该字段未识别到值——单据可能没有此栏，请对照原图确认后补填</div>
        : segment
          ? <div style={{ ...hintStyle, color: "var(--ok)" }}>✓ 已分段定位：原文为跨栏/换行排版，整串被打散，但各内容片段均在原文命中（高亮为核心片段）</div>
          : (!matched && <div style={{ ...hintStyle, color: "var(--warn)" }}>⚠ 原文未逐字定位到该值（可能是模型概括/格式换算），请对照原图核对</div>)}
      {parts}
    </div>
  );
}

function statusClass(c) { return c >= CONF.high ? "high" : c >= CONF.medium ? "medium" : "low"; }
const stageSeq = ["upload", "type", "ocr", "extract", "verify", "export"];
// 节点图标：24×24 描边线性 SVG（不用 emoji，与界面单色视觉语言统一；currentColor 随主题色）
function FlowIcon({ name }) {
  const P = {
    upload: (
      <>
        <path d="M12 15V3" />
        <path d="m7 8 5-5 5 5" />
        <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
      </>
    ),
    type: (
      <>
        <path d="M12 2H4v8l8.5 8.5a2.12 2.12 0 0 0 3 0l5.5-5.5a2.12 2.12 0 0 0 0-3Z" />
        <circle cx="7.5" cy="7.5" r="1.2" />
      </>
    ),
    ocr: (
      <>
        <path d="M3 7V5a2 2 0 0 1 2-2h2" />
        <path d="M17 3h2a2 2 0 0 1 2 2v2" />
        <path d="M21 17v2a2 2 0 0 1-2 2h-2" />
        <path d="M7 21H5a2 2 0 0 1-2-2v-2" />
        <circle cx="12" cy="12" r="2.5" />
      </>
    ),
    extract: (
      <>
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M3 10h18" />
        <path d="M10 10v10" />
      </>
    ),
    verify: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m8.5 11 1.8 1.8 3.2-3.6" />
        <path d="m16.2 16.2 4 4" />
      </>
    ),
    export: (
      <>
        <path d="M12 3v12" />
        <path d="m7 10 5 5 5-5" />
        <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
      </>
    ),
  }[name];
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {P}
    </svg>
  );
}

// 流程环六节点（左栏小环 / 落地页大环共用同一份渲染；线性图标统一青色，序号退到左上角角标）
const FLOW_NODES = [
  { key: "upload", label: "上传单据" },
  { key: "type", label: "识别类型" },
  { key: "ocr", label: "多模态识别" },
  { key: "extract", label: "结构化" },
  { key: "verify", label: "疑点复核" },
  { key: "export", label: "导出" },
];

function fieldLabel(key) {
  const map = {
    invoice_type: "发票类型", invoice_number: "发票号", invoice_date: "开票日期",
    seller_name: "开票方名称", seller_tax_id: "开票方税号", seller_address: "开票方地址",
    buyer_name: "受票方名称", buyer_tax_id: "受票方税号", buyer_address: "受票方地址",
    goods_description: "货物描述", hs_code: "HS Code", quantity: "数量",
    description: "费用项", unit: "单位", rate: "单价", amount: "金额",
    unit_price: "单价", amount_subtotal: "金额小计", tax_rate: "税率",
    tax_amount: "税额", amount_total: "总金额", currency: "币种",
    incoterm: "贸易术语", shipping_method: "运输方式",
    quote_type: "报价单类型", quote_number: "报价单号", quote_date: "报价日期",
    valid_until: "有效期至", forwarder_name: "货代公司", forwarder_contact: "货代联系人",
    forwarder_phone: "货代电话", forwarder_email: "货代邮箱", client_name: "客户公司",
    client_contact: "客户联系人", port_of_loading: "起运港", port_of_discharge: "目的港",
    transport_mode: "运输方式", cargo_description: "货物描述", packages: "件数",
    gross_weight: "毛重(kg)", volume: "体积(m³)", chargeable_weight: "计费重(kg)",
    transit_days: "运输时效", remarks: "备注",
    booking_number: "托书号", booking_date: "托书日期",
    shipper_name: "发货人", shipper_address: "发货人地址",
    vessel_name: "船名", voyage_number: "航次",
    place_of_delivery: "交货地", etd: "预计开船(ETD)", eta: "预计到港(ETA)",
    container_type: "箱型", container_count: "箱量", payment_terms: "付款条款",
  };
  const simple = key.split(".").pop();
  return map[simple] || simple;
}

function flatFields(obj, prefix = "") {
  const rows = [];
  for (const [k, v] of Object.entries(obj)) {
    if (k === "line_items" || k === "charge_items") continue;
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && "value" in v && "confidence" in v) {
      rows.push({ key, label: fieldLabel(key), ...v });
    } else if (v && typeof v === "object") {
      rows.push(...flatFields(v, key));
    }
  }
  return rows;
}

function itemsTableData(result) {
  if (!result) return null;
  if (Array.isArray(result.charge_items) && result.charge_items.length) return result.charge_items;
  if (Array.isArray(result.line_items) && result.line_items.length) return result.line_items;
  return null;
}

function _v(row, c) {
  const v = row[c];
  if (v != null && typeof v === "object" && "value" in v) return v.value;
  return v;
}

// 明细行数组键（charge_items 优先；发票 line_items 已随 Schema 收敛移除，保留兼容）
function itemsKeyOf(er) {
  if (Array.isArray(er?.charge_items) && er.charge_items.length) return "charge_items";
  if (Array.isArray(er?.line_items) && er.line_items.length) return "line_items";
  return null;
}

// 行置信度 = 该行未人工修正字段中的最低分（行分数即行内最弱一环；全行已修正 → 1）
function rowConf(row) {
  let min = 1, seen = false;
  for (const v of Object.values(row || {})) {
    if (v && typeof v === "object" && "confidence" in v) {
      seen = true;
      if (!v._userEdited && v.confidence < min) min = v.confidence;
    }
  }
  return seen ? min : 1;
}

// 明细行字段平铺：与主表字段同构（key=charge_items.N.列名），纳入统计、导出闸门与待处理导航
function itemFieldsFlat(er, docType) {
  const itemsKey = itemsKeyOf(er);
  if (!itemsKey) return [];
  const cols = docType === "invoice"
    ? ["description", "hs_code", "quantity", "unit", "unit_price", "amount"]
    : ["description", "unit", "rate", "quantity", "amount", "currency"];
  const rows = [];
  (er[itemsKey] || []).forEach((row, i) => {
    cols.forEach((c) => {
      const v = row[c];
      if (v && typeof v === "object" && "value" in v) {
        rows.push({ key: `${itemsKey}.${i}.${c}`, label: `明细第 ${i + 1} 行 · ${fieldLabel(c)}`, ...v });
      }
    });
  });
  return rows;
}

// 按点路径取字段（主表 + 明细行统一入口，updateField/markFieldReviewed 同一路径写回）。
// 行存在但该列缺失 → 待填伪字段（置信度 0.6），点单元格仍能进面板补填。
function fieldByKey(er, docType, key) {
  if (!er || !key) return null;
  const parts = key.split(".");
  if (parts.length === 3 && /^\d+$/.test(parts[1])) {
    const row = Array.isArray(er[parts[0]]) ? er[parts[0]][Number(parts[1])] : null;
    if (!row) return null;
    const v = row[parts[2]];
    const label = `明细第 ${Number(parts[1]) + 1} 行 · ${fieldLabel(parts[2])}`;
    if (v && typeof v === "object" && "value" in v) return { key, label, ...v };
    return { key, label, value: v != null ? v : "", confidence: 0.6 };
  }
  return flatFields(er).find((x) => x.key === key) || null;
}

// 递归统计低置信字段数（含行项目内字段）。人工修正后置信度置 1，自动退出统计。
function countLowConf(node) {
  let n = 0;
  const walk = (x) => {
    if (Array.isArray(x)) { x.forEach(walk); return; }
    if (x && typeof x === "object") {
      if ("confidence" in x && "value" in x) {
        if (x.confidence < CONF.forceRequired && !x._userEdited) n += 1;
      } else {
        Object.values(x).forEach(walk);
      }
    }
  };
  walk(node);
  return n;
}

// 确定性校验（与后端导出拦截同一套规则，前端修正后实时复检）：
// 发票（按子类型分流）：国内数电票价税合计必校验（缺税额=不通过）；商业发票小计+税额 vs 总金额（可无税）
// 报价单：费用项合计 vs 总金额
function computeValidation(doc) {
  if (!doc || doc.status !== "ok") return [];
  const er = doc.extract_result || {};
  const checks = [];
  const num = (x) => {
    const v = x && typeof x === "object" && "value" in x ? x.value : x;
    const f = parseFloat(v);
    return isNaN(f) ? null : f;
  };
  const items = itemsTableData(er);
  const itemsSum = items ? items.reduce((s, r) => s + (num(_v(r, "amount")) || 0), 0) : null;

  if (doc.doc_type === "quotation") {
    const total = num(er.amount_total);
    if (items && items.length && total != null && itemsSum != null) {
      const ok = Math.abs(itemsSum - total) <= 0.01;
      checks.push({ pass: ok, msg: ok ? `✓ 费用项合计与总金额一致（${total.toFixed(2)}）` : `✗ 费用项合计 ${itemsSum.toFixed(2)} ≠ 总金额 ${total.toFixed(2)}` });
    }
    return checks;
  }

  // 托书：纯物流单据无金额，确定性交叉校验落在时间勾稽与柜型容量勾稽
  if (doc.doc_type === "booking") {
    const dateOf = (x) => {
      const v = x && typeof x === "object" && "value" in x ? x.value : x;
      const m = v == null ? null : String(v).match(/\d{4}-\d{2}-\d{2}/);
      return m ? m[0] : null;
    };
    const etd = dateOf(er.etd), eta = dateOf(er.eta);
    if (etd && eta) {
      const ok = etd < eta;
      checks.push({ pass: ok, msg: ok ? `✓ 开船日早于到港日（${etd} → ${eta}）` : `✗ 开船日 ${etd} 不早于到港日 ${eta}，日期疑似抓错` });
    }
    // 柜型容量勾稽：体积/毛重不得超过 该箱型上限 × 箱量（超了必是箱量或数抓错）
    const ct = er.container_type && typeof er.container_type === "object" && "value" in er.container_type ? String(er.container_type.value ?? "") : String(er.container_type ?? "");
    const CAPS = { "20GP": [33, 28], "40GP": [67, 27], "40HQ": [76, 27], "45HQ": [86, 27], "20RF": [31, 27], "40RF": [67, 27] };
    const cap = Object.entries(CAPS).find(([t]) => ct.toUpperCase().startsWith(t));
    const count = num(er.container_count);
    const vol = num(er.volume);
    const wt = num(er.gross_weight);
    if (cap && count != null && count > 0) {
      const [cbmCap, tCap] = cap[1];
      if (vol != null) {
        const ok = vol <= cbmCap * count;
        checks.push({ pass: ok, msg: ok ? `✓ 体积 ${vol} m³ 在 ${count}×${cap[0]} 容量内（上限 ${cbmCap * count} m³）` : `✗ 体积 ${vol} m³ 超出 ${count}×${cap[0]} 容量上限（${cbmCap * count} m³），箱量或体积疑似抓错` });
      }
      if (wt != null) {
        const ok = wt <= tCap * 1000 * count;
        checks.push({ pass: ok, msg: ok ? `✓ 毛重 ${wt} kg 在 ${count}×${cap[0]} 限重内（上限 ${tCap * count} t）` : `✗ 毛重 ${wt} kg 超出 ${count}×${cap[0]} 限重（${tCap * count} t），疑似抓错` });
      }
    }
    return checks;
  }

  // 发票类：校验规则按子类型分流（与后端 _compute_confidence 的 is_cn_invoice 同口径）
  // 国内数电票：价税分离是铁律，税额缺失=校验不通过；商业发票（出口）：常免税，税栏缺失不强求
  const invTypeRaw = er.invoice_type && typeof er.invoice_type === "object" && "value" in er.invoice_type ? String(er.invoice_type.value ?? "") : String(er.invoice_type ?? "");
  const isCNInvoice = /电子发票|增值税|普票|专票|数电/.test(invTypeRaw);
  const subtotal = num(er.amount_subtotal);
  if (items && items.length && subtotal != null && itemsSum != null) {
    const ok = Math.abs(itemsSum - subtotal) <= 0.01;
    checks.push({ pass: ok, msg: ok ? `✓ 行项目合计与小计一致（${subtotal.toFixed(2)}）` : `✗ 行项目合计 ${itemsSum.toFixed(2)} ≠ 金额小计 ${subtotal.toFixed(2)}` });
  }
  const tax = num(er.tax_amount);
  const total = num(er.amount_total);
  const sumLabel = isCNInvoice ? "价税合计" : "小计+税额=总金额";
  if (subtotal != null && tax != null && total != null) {
    const ok = Math.abs(subtotal + tax - total) <= 0.01;
    checks.push({ pass: ok, msg: ok ? `✓ ${sumLabel}一致（${total.toFixed(2)}）` : `✗ 小计 ${subtotal.toFixed(2)} + 税额 ${tax.toFixed(2)} ≠ 总金额 ${total.toFixed(2)}` });
  } else if (isCNInvoice && tax == null) {
    checks.push({ pass: false, msg: "✗ 电子发票缺少税额，价税合计校验无法执行——请对照原图补填" });
  } else if (isCNInvoice && subtotal == null) {
    checks.push({ pass: false, msg: "✗ 电子发票缺少金额小计，价税合计校验无法执行——请对照原图补填" });
  }
  // 税率×小计≈税额 勾稽：税率档位由后端字典校验，这里交叉验证金额自洽——
  // 两道防线一起拦"模型随手抓个数字当税率"的幻觉
  const rateRaw = er.tax_rate && typeof er.tax_rate === "object" && "value" in er.tax_rate ? er.tax_rate.value : er.tax_rate;
  const rateMatch = rateRaw != null ? String(rateRaw).replace(",", "").match(/[\d.]+/) : null;
  const rateNum = rateMatch ? parseFloat(rateMatch[0]) : NaN;
  const ratePct = isNaN(rateNum) ? null : (rateNum < 1 ? rateNum * 100 : rateNum);
  if (ratePct != null && ratePct > 0 && subtotal != null && tax != null) {
    const expect = subtotal * ratePct / 100;
    const ok = Math.abs(expect - tax) <= Math.max(0.05, tax * 0.02);
    checks.push({ pass: ok, msg: ok ? `✓ 税率×小计≈税额（${ratePct}% × ${subtotal.toFixed(2)} ≈ ${tax.toFixed(2)}）` : `✗ 税率 ${ratePct}% × 小计 ${subtotal.toFixed(2)} = ${expect.toFixed(2)} ≠ 税额 ${tax.toFixed(2)}，税率或税额疑似抓错` });
  }
  return checks;
}

// 把后端返回的抽取结果包装成统一的单据项（单份/批量共用）：
// 置信度分流——低分字段置空待人工修正，原值保留在 _originalValue
function buildDocItem(data, file, useType) {
  const er = data.extract_result || {};
  for (const k of Object.keys(er)) {
    const f = er[k];
    if (f && typeof f === "object" && "confidence" in f && f.confidence < CONF.forceRequired) {
      f._originalValue = f.value;
      f.value = "";
      f._forceRequired = true;
    }
  }
  return {
    filename: data.filename || (file ? file.name : ""),
    doc_type: data.doc_type || useType || "invoice",
    extract_result: er,
    ocr_text: data.ocr_text || "",
    preview_image: data.preview_image || null,
    mock_mode: !!data.mock_mode,
    cached: !!data.cached,
    mode_used: data.mode_used || "",
    status: "ok",
    error: null,
    _file: file || null,
  };
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

function App() {
  const [file, setFile] = useState(null);
  const [docType, setDocType] = useState("invoice");
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState(null);
  const [toast, setToast] = useState(null);
  // 初始 null：落地页六节点完全统一（序号"1"已表达入口语义，首节点不再常驻 active 光晕）；处理链路各步显式赋值，节奏不受影响
  const [processStage, setProcessStage] = useState(null);
  const [selectedField, setSelectedField] = useState(null);
  const [inputVal, setInputVal] = useState(""); // 当前编辑框的本地值，避免打字时被重置
  const [flowRotation, setFlowRotation] = useState(0);
  const [pendingType, setPendingType] = useState(null); // 等待用户确认的单据类型
  const [pendingSwitch, setPendingSwitch] = useState(null); // 跨类型切换待确认（重抽是真实调用，首次 10-60s）
  const [showImage, setShowImage] = useState(false); // 放大图片弹窗
  const [contentTab, setContentTab] = useState("table"); // "table" | "preview" 中间区 Tab
  const [elapsed, setElapsed] = useState(0); // 加载耗时计数（>3s 才显示，长等待时不像卡死）
  const [heroLeaving, setHeroLeaving] = useState(false); // 落地页 → 全布局："散开"过渡播放中
  const [landing, setLanding] = useState(true); // 初始落地页：仅水波环 + 四个样本（无侧栏/顶栏），点任一即散开进全布局
  const [overlayOn, setOverlayOn] = useState(false); // loading 遮罩延迟出现：缓存秒回（<500ms）不闪黑罩

  // ===== 统一结果数据源 =====
  // 单份=1 项、批量=N 项，全部存 docs；右侧工作区始终渲染 docs[currentIdx]。
  // 不再有 result + batchResults 双状态双写——两条链路看到的是同一份数据。
  const [docs, setDocs] = useState([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [batchMode, setBatchMode] = useState(false); // true=左侧显示批量列表 UI
  const [batchFiles, setBatchFiles] = useState(null);
  const [batchProgress, setBatchProgress] = useState({ current: 0, total: 0 });
  const [confirmBatchType, setConfirmBatchType] = useState(null);

  const inputRef = useRef();
  const batchInputRef = useRef();

  useEffect(() => { api("/api/health").then(setHealth).catch(() => setHealth({ mock_mode: true })); }, []);

  // loading 期间每秒计时，让长耗时抽取有"活着"的反馈
  useEffect(() => {
    if (!loading) { setElapsed(0); return; }
    const t0 = Date.now();
    const iv = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(iv);
  }, [loading]);

  // 当前展示的单据项（右侧工作区的唯一数据来源）
  const cur = docs[currentIdx] || null;

  // 落地页 → 全布局：水波环放大淡出"散开"（650ms），侧栏/顶栏淡入进场；清空回落地页：静默复位
  useEffect(() => {
    if (landing) return;
    setHeroLeaving(true);
    const t = setTimeout(() => setHeroLeaving(false), 650);
    return () => clearTimeout(t);
  }, [landing]);

  // loading 遮罩延迟 500ms 出现：<500ms 的缓存秒回不闪黑罩，真实抽取照常显示进度
  useEffect(() => {
    if (!loading) { setOverlayOn(false); return; }
    const t = setTimeout(() => setOverlayOn(true), 500);
    return () => clearTimeout(t);
  }, [loading]);

  // 切换单据时清空字段选中（修正面板回到初始态）
  const selectDoc = useCallback((i) => {
    setCurrentIdx(i);
    setSelectedField(null);
  }, []);

  // 切换字段时，把当前字段值同步到本地输入 state
  useEffect(() => {
    if (!selectedField || !cur) { setInputVal(""); return; }
    const f = fieldByKey(cur.extract_result, cur.doc_type, selectedField);
    setInputVal(f?.value ?? "");
  }, [selectedField, cur]);

  const showToast = useCallback((msg, type = "ok") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 2500);
  }, []);

  // 上传识别：forceType 为空时由后端按内容识别类型（类型确认弹窗展示真实识别结果）
  const analyzeFile = useCallback(async (f, forceType) => {
    const fd = new FormData();
    fd.append("file", f);
    if (forceType) fd.append("force_type", forceType);
    return apiFormData("/api/upload", fd);
  }, []);

  const onAnalyze = useCallback(async (fArg) => {
    const f = fArg || file; // 支持文件选择器 onChange 直接传入（选完即识别，不再依赖隐藏按钮）
    if (!f) return;
    setLoading(true);
    setPendingType(null);
    setProcessStage("upload");
    await sleep(120);
    setProcessStage("type");
    try {
      const data = await analyzeFile(f);
      // type 阶段停住：弹出 AI 识别的单据类型让用户确认
      setPendingType({ recognized: data.doc_type, filename: data.filename, _data: data, _file: f });
    } catch (e) {
      showToast("识别失败：" + e.message, "err");
      setProcessStage("upload");
      setLoading(false);
    }
  }, [file, showToast, analyzeFile]);

  const confirmTypeAndContinue = useCallback(async (useType) => {
    const pending = pendingType;
    setPendingType(null);
    if (!pending) return;
    setProcessStage("ocr");
    await sleep(120);
    let data = pending._data;
    // 用户改选类型：带 force_type 真正重新抽取（换用对应 Schema），而不是只换标签
    if (useType !== pending.recognized) {
      try {
        data = await analyzeFile(pending._file, useType);
      } catch (e) {
        showToast(`按「${(DOC_TYPE_META[useType] || {}).label || useType}」重新抽取失败：` + e.message, "err");
        setProcessStage("upload");
        setLoading(false);
        return;
      }
    }
    setProcessStage("extract");
    await sleep(120);
    setDocs([buildDocItem(data, pending._file, useType)]);
    setCurrentIdx(0);
    setSelectedField(null);
    setBatchMode(false);
    setProcessStage("verify");
    await sleep(80);
    setProcessStage("export");
    if (useType !== docType) setDocType(useType);
    setLoading(false);
  }, [pendingType, docType, analyzeFile, showToast]);

  // Tab 切换样本直出：带 force_type 加载该类型示例单据，跳过类型确认弹窗
  // （类型已由 Tab 明确；预热矩阵全缓存秒回，原文/字段/预览一起切换）
  const onPickSampleDirect = useCallback(async (sample, forceType) => {
    setDocType(forceType);
    setLoading(true);
    setDocs([]);
    setSelectedField(null);
    setPendingType(null);
    setProcessStage("upload");
    await sleep(120);
    setProcessStage("type");
    try {
      const res = await fetch(apiBase(`/api/samples/${encodeURIComponent(sample.name)}`));
      if (!res.ok) throw new Error(`样本下载失败（HTTP ${res.status}）`);
      const blob = await res.blob();
      const sampleFile = new File([blob], sample.name, { type: blob.type || "application/pdf" });
      setFile(sampleFile);
      const data = await analyzeFile(sampleFile, forceType);
      setProcessStage("extract");
      setDocs([buildDocItem(data, sampleFile, forceType)]);
      setCurrentIdx(0);
      setBatchMode(false);
      setProcessStage("export");
      showToast(`已加载「${sample.label}」`, "ok");
    } catch (e) {
      showToast("样本加载失败：" + e.message, "err");
      setProcessStage("upload");
    }
    setLoading(false);
  }, [analyzeFile, showToast]);

  // 已有识别结果时切换类型：对当前单据带 force_type 重新抽取（单份/批量通用）
  const reExtractCurrent = useCallback(async (useType) => {
    if (DISABLED_TYPES.has(useType)) return;
    if (!cur || !cur._file) { setDocType(useType); return; }
    setLoading(true);
    setProcessStage("ocr");
    try {
      const data = await analyzeFile(cur._file, useType);
      const item = buildDocItem(data, cur._file, useType);
      setDocs(prev => prev.map((d, i) => (i === currentIdx ? item : d)));
      setSelectedField(null);
      if (!batchMode) setDocType(useType);
      showToast(`已按「${(DOC_TYPE_META[useType] || {}).label || useType}」重新抽取`, "ok");
      setProcessStage("export");
    } catch (e) {
      showToast("重新抽取失败：" + e.message, "err");
      setProcessStage("export");
    }
    setLoading(false);
  }, [cur, currentIdx, batchMode, analyzeFile, showToast]);

  // 顶部/左侧类型切换入口：
  // - 无结果：只改下次上传的默认类型
  // - 当前是样本文件：直接切到该类型的示例单据（原文+字段+预览一起换，预热矩阵全缓存秒回）。
  //   "同一文件换 Schema 重抽"的打串观感已被用户三次误判为 bug，演示价值不抵困惑成本
  // - 当前是自上传文件：换 Schema 真实重抽当前文件（类型识别纠错场景），先弹确认——
  //   误点一下干等 10-60 秒很伤演示节奏（同组合重抽过一次后走缓存秒回）
  const switchDocType = useCallback((t) => {
    if (DISABLED_TYPES.has(t) || t === docType) return;
    if (!cur || !cur._file) { setDocType(t); return; }
    const target = SAMPLE_FILES.find((s) => s.docType === t);
    if (target && SAMPLE_FILES.some((s) => s.name === cur._file.name)) {
      onPickSampleDirect(target, t);
      return;
    }
    setPendingSwitch(t);
  }, [cur, docType, onPickSampleDirect]);

  const confirmSwitchType = useCallback(() => {
    const t = pendingSwitch;
    setPendingSwitch(null);
    if (t) reExtractCurrent(t);
  }, [pendingSwitch, reExtractCurrent]);

  // 样本按钮：从后端拉取真实样本文件，走与手动上传完全相同的识别链路
  const onPickSample = useCallback(async (sample) => {
    setDocType(sample.docType);
    setLoading(true);
    setDocs([]);
    setSelectedField(null);
    setPendingType(null);
    setProcessStage("upload");
    await sleep(120);
    setProcessStage("type");
    try {
      const res = await fetch(apiBase(`/api/samples/${encodeURIComponent(sample.name)}`));
      if (!res.ok) throw new Error(`样本下载失败（HTTP ${res.status}）`);
      const blob = await res.blob();
      const sampleFile = new File([blob], sample.name, { type: blob.type || "application/pdf" });
      setFile(sampleFile);
      const data = await analyzeFile(sampleFile);
      // 停住弹类型确认
      setPendingType({ recognized: data.doc_type, filename: data.filename, _data: data, _file: sampleFile });
    } catch (e) {
      showToast("样本加载失败：" + e.message, "err");
      setProcessStage("upload");
      setLoading(false);
    }
  }, [analyzeFile, showToast]);

  // ===== 批量模式 =====
  const handleBatchFiles = useCallback((files) => {
    // 过滤有效文件
    const valid = Array.from(files).filter(f => /\.(pdf|png|jpg|jpeg)$/i.test(f.name));
    if (valid.length === 0) {
      showToast("未找到有效单据文件", "err");
      return;
    }
    // 检测类型：用文件名关键词推断
    const first = valid[0].name.toLowerCase();
    const guessedType = first.includes("quotation") || first.includes("quote") || first.includes("报价") ? "quotation" : "invoice";
    setBatchFiles(valid);
    setConfirmBatchType({ count: valid.length, guessedType });
  }, [showToast]);

  const runBatchRecognize = useCallback(async (useType) => {
    const files = batchFiles;
    if (!files || files.length === 0) return;
    setConfirmBatchType(null);
    setBatchMode(true);
    setCurrentIdx(0);
    setSelectedField(null);
    setLoading(true);
    setProcessStage("upload");

    // 串行逐个处理，结果统一写入 docs
    const results = [];
    for (let i = 0; i < files.length; i++) {
      setBatchProgress({ current: i, total: files.length });
      setProcessStage(i === 0 ? "ocr" : "extract");

      const f = files[i];
      try {
        const data = await analyzeFile(f, useType); // 告诉后端按这个类型抽
        results.push(buildDocItem(data, f, useType));
      } catch (e) {
        results.push({
          filename: f.name, doc_type: useType, extract_result: {}, ocr_text: "",
          preview_image: null, mock_mode: false, mode_used: "", status: "error", error: e.message, _file: f,
        });
      }
      setDocs([...results]);
    }
    setBatchProgress({ current: files.length, total: files.length });
    setProcessStage("export");
    setLoading(false);
    if (useType !== docType) setDocType(useType);
    showToast(`批量识别完成：成功 ${results.filter(r => r.status === "ok").length}/${files.length}`, "ok");
  }, [batchFiles, docType, showToast, analyzeFile]);

  const resetAll = useCallback(() => {
    setDocs([]);
    setCurrentIdx(0);
    setSelectedField(null);
    setFile(null);
    setBatchMode(false);
    setBatchFiles(null);
    setProcessStage("upload");
    setLanding(true); // 清空 = 回落地页（水波环 + 四样本）
  }, []);

  // ===== 统一的字段更新（单份/批量共用，只写 docs[currentIdx]）=====
  const updateField = useCallback((key, newValue) => {
    setDocs(prev => prev.map((d, i) => {
      if (i !== currentIdx) return d;
      const er = JSON.parse(JSON.stringify(d.extract_result));
      const parts = key.split(".");
      let node = er;
      for (let p of parts.slice(0, -1)) {
        if (!node[p]) node[p] = {};
        node = node[p];
      }
      const leaf = parts[parts.length - 1];
      if (!node[leaf] || typeof node[leaf] !== "object") node[leaf] = {};
      node[leaf] = {
        ...node[leaf],
        value: newValue,
        confidence: 1,
        status: "high",
        _forceRequired: false,
        _userEdited: true,
      };
      return { ...d, extract_result: er };
    }));
  }, [currentIdx]);

  const markFieldReviewed = useCallback((key) => {
    setDocs(prev => prev.map((d, i) => {
      if (i !== currentIdx) return d;
      const er = JSON.parse(JSON.stringify(d.extract_result));
      const parts = key.split(".");
      let node = er;
      for (let p of parts.slice(0, -1)) {
        if (!node[p]) return { ...d, extract_result: er };
        node = node[p];
      }
      const leaf = parts[parts.length - 1];
      if (node && node[leaf] && typeof node[leaf] === "object") {
        node[leaf] = {
          ...node[leaf],
          _reviewed: true,
          _forceRequired: false,
          _userEdited: true,
          confidence: 1,
          status: "high",
        };
      }
      return { ...d, extract_result: er };
    }));
  }, [currentIdx]);

  // ===== 导出 =====
  const onExport = useCallback(async () => {
    if (!cur) return;
    const lowFields = [...flatFields(cur.extract_result), ...itemFieldsFlat(cur.extract_result, cur.doc_type)].filter(
      (f) => (f.confidence < CONF.forceRequired || f._forceRequired) && (f.value === "" || f.value == null)
    );
    const failed = computeValidation(cur).filter(c => !c.pass);
    if (lowFields.length > 0) {
      showToast(`还有 ${lowFields.length} 个字段需人工修正后才能导出`, "warn");
      setSelectedField(lowFields[0].key);
      return;
    }
    if (failed.length > 0) {
      showToast(`校验不通过：${failed[0].msg}，请修正后再导出`, "warn");
      return;
    }
    try {
      await apiDownload("/api/export", {
        doc_type: cur.doc_type,
        extract_result: cur.extract_result,
        filename: cur.filename,
      });
      showToast("Excel 已导出", "ok");
      setProcessStage("export");
    } catch (e) {
      showToast("导出失败：" + e.message, "err");
    }
  }, [cur, showToast]);

  const onExportBatch = useCallback(async () => {
    const okDocs = docs.filter(d => d.status === "ok");
    if (okDocs.length === 0) return;
    // 确定性校验拦截：行合计≠总金额等不允许导出 TMS
    const failedIdx = docs.findIndex(d => d.status === "ok" && computeValidation(d).some(c => !c.pass));
    if (failedIdx >= 0) {
      selectDoc(failedIdx);
      showToast(`第 ${failedIdx + 1} 份（${docs[failedIdx].filename}）校验不通过，请修正后再导出`, "warn");
      return;
    }
    try {
      await apiDownload("/api/batch_export", {
        doc_type: okDocs[0].doc_type,
        items: okDocs.map(r => ({
          filename: r.filename,
          extract_result: r.extract_result,
        })),
      });
      showToast("批量 Excel 已导出", "ok");
    } catch (e) {
      showToast("导出失败：" + e.message, "err");
    }
  }, [docs, showToast, selectDoc]);

  const mockMode = cur?.mock_mode ?? health?.mock_mode ?? true;
  const currentStageIdx = stageSeq.indexOf(processStage);

  // 统计（当前单据）
  const flat = cur ? flatFields(cur.extract_result) : [];
  // 明细行字段并入同一套统计/导航（费用明细完整纳入置信度体系）
  const itemFlat = cur ? itemFieldsFlat(cur.extract_result, cur.doc_type) : [];
  const flatAll = [...flat, ...itemFlat];
  const lowCount = cur ? countLowConf(cur.extract_result) : 0;
  const lowUnfilled = flatAll.filter((f) => (f.confidence < CONF.forceRequired || f._forceRequired) && (f.value === "" || f.value == null)).length;
  const editedCount = flatAll.filter(f => f._userEdited).length;
  const validation = useMemo(() => computeValidation(cur), [cur]);
  const failedChecks = validation.filter(c => !c.pass).length;

  // 统计（批量整体）
  const batchLowCount = batchMode ? docs.reduce((s, d) => s + countLowConf(d.extract_result), 0) : 0;
  const batchOkCount = batchMode ? docs.filter(d => d.status === "ok").length : 0;

  // 流程环节点渲染（左栏小环 / 落地页大环共用，落地页经 CSS scale 放大）
  const renderFlowNodes = (radius = 92) => (
    <div className="rotator" style={{ transform: `rotate(${flowRotation}deg)` }}>
      {FLOW_NODES.map((n, idx, arr) => {
        const angle = (idx / arr.length) * 2 * Math.PI - Math.PI / 2;
        const x = Math.cos(angle) * radius;
        const y = Math.sin(angle) * radius;
        const nIdx = stageSeq.indexOf(n.key);
        const done = cur && currentStageIdx > nIdx;
        const active = processStage === n.key;
        return (
          <div key={n.key}
            className={`flow-node ${done ? "done" : ""} ${active ? "active" : ""}`}
            style={{
              top: "50%", left: "50%",
              transform: `translate(-50%, -50%) translate(${x}px, ${y}px) rotate(${-flowRotation}deg)`,
            }}
            onClick={() => setProcessStage(n.key)}
            title={n.label}
          >
            <div className="node-circle">
              <span className="node-icon"><FlowIcon name={n.key} /></span>
              {/* 左上角角标：待处理=青色序号，完成=原地变绿✓（任何时刻每节点只有一个角标，stepper 模式） */}
              <span className={`node-idx${done ? " done" : ""}`}>{done ? "✓" : idx + 1}</span>
            </div>
            <span className="lbl">{n.label}</span>
          </div>
        );
      })}
    </div>
  );

  return (
    <div className="app">
      {/* ====== 顶栏 ====== */}
      <header className="header">
        <div className="logo-mark">AI</div>
        <div className="header-title">
          智能单据助手
          <span className="en">DocAssistant</span>
        </div>
        <div className="header-right" title={mockMode && health?.key_status === "invalid_format"
          ? "api/.env 中的 ZHIPU_API_KEY 疑似复制不完整（不含点号），已按未配置处理，当前展示的是演示数据"
          : undefined}>
          <span className={`status-dot ${mockMode ? "mock" : "online"}`}></span>
          {mockMode
            ? (health?.key_status === "invalid_format" ? "演示模式（Key 格式异常，检查 .env）" : "演示模式（无 Key）")
            : "线上模型（已连接）"}
        </div>
      </header>

      {/* ====== 主体 ====== */}
      <div className="main">
        {/* ====== 左侧：环形流程图（落地页"散开"后随布局淡入） ====== */}
        {!landing && (<aside className="flow-side">
          <div className="flow-title">DOCUMENT PIPELINE · 处理流程</div>

          <div
            className="flow-circle-wrap"
            onWheel={(e) => {
              e.preventDefault();
              setFlowRotation((r) => r + e.deltaY / 3);
            }}
            style={{ cursor: "grab" }}
          >
            {/* 三层水波环（里亮外淡，缓慢呼吸扩散） */}
            <div className="orbit-track"></div>
            {/* 中心星 */}
            <div className="flow-center" onClick={() => setFlowRotation((r) => r + 60)} title="点击旋转">
              AI 抽取
            </div>
            {/* 六个流程节点（与落地页同一份渲染） */}
            {renderFlowNodes()}
          </div>

          <div className="flow-section">
            <div
              className={`upload-zone ${loading ? "drag" : ""}`}
              onClick={() => !loading && inputRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) { setFile(f); onAnalyze(f); } }}
            >
              <div className="hint-row">点击或拖拽上传单据</div>
              <div className="hint-sub">支持 PDF / 图片 (PNG JPG)</div>
            </div>

            {/* 单据类型选择胶囊 */}
            <div className="doc-type-tabs">
              <div
                className={`doc-type-tab ${docType === "invoice" ? "active" : ""}`}
                onClick={() => switchDocType("invoice")}
              >发票</div>
              <div
                className={`doc-type-tab ${docType === "quotation" ? "active" : ""}`}
                onClick={() => switchDocType("quotation")}
              >报价单</div>
              <div
                className={`doc-type-tab ${docType === "booking" ? "active" : ""}`}
                onClick={() => switchDocType("booking")}
              >托书</div>
            </div>

            {file && !loading && !batchMode && (
              <button className="btn btn-primary" style={{ width: "100%" }} onClick={onAnalyze}>
                🚀 AI 辅助识别
              </button>
            )}

            <div style={{ display: "flex", gap: 8 }}>
              <button
                className="btn btn-outline"
                style={{ flex: 1, padding: "8px 10px", fontSize: 12 }}
                onClick={() => batchInputRef.current?.click()}
                disabled={loading}
              >
                📂 批量识别
              </button>
            </div>
            <input
              ref={batchInputRef} type="file" hidden multiple
              accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
              directory="" webkitdirectory=""
              onChange={(e) => { if (e.target.files.length > 0) handleBatchFiles(e.target.files); e.target.value = ""; }}
            />

            {/* 非批量模式：样本快速加载（真实文件，走完整识别链路） */}
            {!batchMode && (
              <div className="samples-list">
                {SAMPLE_FILES.map((s) => (
                  <button key={s.name} className="sample-list-item" onClick={() => onPickSample(s)}>
                    {s.label} · <span style={{ color: "var(--text-dim)" }}>{s.hint}</span>
                  </button>
                ))}
              </div>
            )}

            {/* 批量模式：结果列表（与右侧工作区同一数据源 docs） */}
            {batchMode && docs.length > 0 && (
              <>
                <div style={{
                  padding: "6px 10px", background: "var(--panel-2)",
                  borderRadius: 6, fontSize: 11, color: "var(--text-2)",
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                }}>
                  <span><b>📋 批量 {docs.length}</b> · 成功 {batchOkCount}/{docs.length}</span>
                  {batchLowCount > 0
                    ? <span style={{ color: "var(--warn)" }}>⚠️ {batchLowCount}项待修</span>
                    : <span style={{ color: "var(--accent)" }}>✅ 全部就绪</span>}
                </div>
                <div className="batch-list" style={{ overflowY: "auto", maxHeight: 240 }}>
                  {docs.map((r, i) => {
                    const isSel = i === currentIdx;
                    const lowN = r.status === "error" ? 0 : countLowConf(r.extract_result);
                    const statusCls = r.status === "error" ? "batch-item err" :
                                     lowN > 0 ? "batch-item warn" : "batch-item ok";
                    return (
                      <div
                        key={i}
                        className={`${statusCls} ${isSel ? "sel" : ""}`}
                        onClick={() => selectDoc(i)}
                      >
                        <span className="bi-icon">{r.status === "error" ? "❌" : lowN > 0 ? "⚠️" : "✅"}</span>
                        <span className="bi-name">{r.filename}</span>
                        {r.status === "ok" && <span className="bi-count">{lowN > 0 ? `${lowN}项` : "干净"}</span>}
                      </div>
                    );
                  })}
                </div>
                <button className="btn btn-outline" style={{ width: "100%", padding: "7px 10px", fontSize: 11, marginTop: 8 }} onClick={resetAll}>
                  ＋ 开始新任务
                </button>
              </>
            )}
          </div>
        </aside>)}

        {/* ====== 右侧：工作区 ====== */}
        <section className="work-area">
          {overlayOn && (
            <div className="loading-overlay" style={{ position: "absolute" }}>
              <div className="loading-spinner"></div>
              <div className="loading-text">{
                { upload: "正在上传文件...", type: "AI 识别单据类型中...", ocr: "多模态识别文档...", extract: "结构化字段抽取...", verify: "置信度校验分流..." }[processStage] || "处理中..."
              }{elapsed > 3 ? `（${elapsed}s）` : ""}</div>
            </div>
          )}

          {/* 顶栏（落地页"散开"后随布局淡入） */}
          {!landing && (<div className="work-topbar">
            {/* 类型切换与左栏同款胶囊（同一功能同一控件语言；英文保留在右侧「按『..』模板抽取」信息里） */}
            <div className="doc-type-tabs">
              <div className={`doc-type-tab ${docType === "invoice" ? "active" : ""}`} onClick={() => switchDocType("invoice")} title={cur ? "样本单据：直接切换到该类型示例；自上传文件：按该模板重抽" : undefined}>发票</div>
              <div className={`doc-type-tab ${docType === "quotation" ? "active" : ""}`} onClick={() => switchDocType("quotation")} title={cur ? "样本单据：直接切换到该类型示例；自上传文件：按该模板重抽" : undefined}>报价单</div>
              <div className={`doc-type-tab ${docType === "booking" ? "active" : ""}`} onClick={() => switchDocType("booking")} title={cur ? "样本单据：直接切换到该类型示例；自上传文件：按该模板重抽" : undefined}>托书</div>
            </div>
            <div className="topbar-info">
              {cur && (
                <span className="docfile" title={`当前单据：${cur.filename}，字段按该模板（Schema）抽取。切换上方类型 Tab = 换模板重抽同一份文件，原文不变属正常行为`}>
                  📄 {cur.filename} · 按「{(DOC_TYPE_META[cur.doc_type] || {}).label || cur.doc_type}」模板抽取
                </span>
              )}
            </div>
            <div className="topbar-right">
              {cur && (
                <>
                  <button className="btn btn-outline" onClick={resetAll}>清空</button>
                  <button
                    className="btn btn-primary"
                    disabled={batchMode
                      ? (batchLowCount > 0 || docs.some(d => d.status === "ok" && computeValidation(d).some(c => !c.pass)))
                      : (lowUnfilled > 0 || failedChecks > 0)}
                    onClick={batchMode ? onExportBatch : onExport}
                    title={batchMode
                      ? (batchLowCount > 0 ? `还有 ${batchLowCount} 项待修正` : "批量导出 Excel 大表（校验不通过的单据会被拦截）")
                      : (lowUnfilled > 0 ? `还有 ${lowUnfilled} 项低可信字段需修正` : (failedChecks > 0 ? "存在校验不通过的项，请先修正" : "导出 Excel"))}
                  >
                    {batchMode ? "批量导出" : "导出 Excel"}
                  </button>
                </>
              )}
            </div>
          </div>)}

          {/* 落地页：水波环 + 四样本（点中间/样本后"散开"进全布局） */}
          {(landing || heroLeaving) && (
            <div className={"hero-state" + (heroLeaving ? " scatter" : "")}>
              <div className="hero-flow">
                <div className="hero-flow-scale">
                  <div
                    className="flow-circle-wrap"
                    onWheel={(e) => {
                      e.preventDefault();
                      setFlowRotation((r) => r + e.deltaY / 3);
                    }}
                  >
                    <div className="orbit-track"></div>
                    <div
                      className="flow-center"
                      onClick={() => { if (loading) return; setLanding(false); }}
                      title="进入工作台：左侧上传单据，或点击示例单据开始识别"
                    >
                      AI 抽取
                    </div>
                    {renderFlowNodes()}
                  </div>
                </div>
              </div>
              <p className="hero-title">上传单据，AI 识别图片内容自动转成表格</p>
              <div className="hero-samples">
                {SAMPLE_FILES.map((s) => (
                  <button key={s.name} className="hero-sample" onClick={() => { if (loading) return; setLanding(false); onPickSampleDirect(s, s.docType); }}>
                    <span className="hs-label">{s.label}</span>
                    <span className="hs-hint">{s.hint}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {!landing && !cur && !heroLeaving && (
            <div className="work-empty">从左侧上传单据，或点击示例单据开始识别</div>
          )}
          {cur && (
            <div className="work-content">
              <div className="doc-info-bar">
                <span>📄 文档：<span className="fname">{cur.filename}</span></span>
                <span>📌 类型：<span className="fname">{(DOC_TYPE_META[cur.doc_type] || {}).label || cur.doc_type}</span></span>
                <span className={`badge ${mockMode ? "mock" : "live"}`}>
                  {mockMode ? "🔸 演示 Mock" : "🔹 线上模型"}
                </span>
                {editedCount > 0 && (
                  <span style={{ marginLeft: "auto", color: "var(--accent)" }}>✏️ 已修正 {editedCount} 项</span>
                )}
              </div>

              <div className="content-body">
                {/* 中间区 Tab */}
                <div className="content-tabs">
                  <div className={`content-tab ${contentTab === "table" ? "active" : ""}`} onClick={() => setContentTab("table")}>📋 字段表格</div>
                  <div className={`content-tab ${contentTab === "preview" ? "active" : ""}`} onClick={() => setContentTab("preview")}>🖼️ 原始单据</div>
                </div>

                {/* Tab 内容 */}
                {cur.status === "error" ? (
                  <div className="content-pane" style={{ padding: 30 }}>
                    <div style={{ color: "var(--err)", fontSize: 13, marginBottom: 8 }}>❌ 识别失败</div>
                    <div style={{ color: "var(--text-3)", fontSize: 12 }}>{cur.error}</div>
                  </div>
                ) : contentTab === "table" ? (
                  <div className="content-pane">
                    <table className="fields-table">
                      <thead>
                        <tr>
                          <th className="col-label">字段名</th>
                          <th>识别结果</th>
                          <th className="col-conf">置信度</th>
                          <th className="col-action">操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {flat.map((f) => {
                          const cls = f.status || statusClass(f.confidence);
                          return (
                            <tr
                              key={f.key}
                              className={cls === "low" ? "row-low" : ""}
                              onClick={() => { setSelectedField(f.key); setContentTab("preview"); }}
                              style={{ cursor: "pointer" }}
                            >
                              <td className="col-label">
                                {f.label}
                                {f._forceRequired && !f._reviewed && <span className="force-required">⚠ 需修正</span>}
                                {f._reviewed && <span className="locked-badge" style={{ background: "rgba(56,217,235,0.15)", color: "var(--accent)" }}>✓ 已复核</span>}
                              </td>
                              <td>
                                {f.value === "" || f.value == null ? (
                                  <span className="col-value empty">（待填）</span>
                                ) : (
                                  <span className="col-value">{String(f.value)}</span>
                                )}
                              </td>
                              <td className="col-conf">
                                <span className={`conf-dot ${cls}`}><span className="dot"></span><span className="pct">{Math.round(f.confidence * 100)}%</span></span>
                              </td>
                              <td className="col-action">
                                {(cls === "low" || f._forceRequired)
                                  ? <span style={{ color: "var(--err)" }}>修正 →</span>
                                  : cls === "medium"
                                    ? <span style={{ color: "var(--warn)" }}>抽查 →</span>
                                    : <span style={{ color: "var(--ok)" }}>确认 ✓</span>}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    {itemsTableData(cur.extract_result) && (
                      <div className="items-section">
                        <h4>{cur.doc_type === "invoice" ? "货物明细行项目" : "费用明细行项目"}</h4>
                        <table className="item-table-mini">
                          <thead><tr>
                            {(cur.doc_type === "invoice"
                              ? ["描述", "HS Code", "数量", "单位", "单价", "金额", "置信度"]
                              : ["费用项", "单位", "单价", "数量", "金额", "币种", "置信度"]
                            ).map((h, i) => <th key={i}>{h}</th>)}
                          </tr></thead>
                          <tbody>
                            {(() => {
                              const itemsKey = itemsKeyOf(cur.extract_result);
                              const keyCols = cur.doc_type === "invoice"
                                ? ["description", "hs_code", "quantity", "unit", "unit_price", "amount"]
                                : ["description", "unit", "rate", "quantity", "amount", "currency"];
                              // 点数据格修正该格字段；点置信度格直接跳到该行最低分字段
                              const pickItemField = (i, col) => {
                                setSelectedField(`${itemsKey}.${i}.${col}`);
                                setContentTab("preview");
                              };
                              return itemsTableData(cur.extract_result).map((row, i) => {
                                const rc = rowConf(row);
                                const cls = statusClass(rc);
                                let worstCol = keyCols[0], worstConf = Infinity;
                                keyCols.forEach((c) => {
                                  const v = row[c];
                                  if (v && typeof v === "object" && "confidence" in v && !v._userEdited && v.confidence < worstConf) {
                                    worstConf = v.confidence; worstCol = c;
                                  }
                                });
                                return (
                                  <tr key={i} className={cls === "low" ? "row-low" : ""}>
                                    {keyCols.map((c) => (
                                      <td key={c} onClick={() => pickItemField(i, c)}>{_v(row, c) ?? "-"}</td>
                                    ))}
                                    <td onClick={() => pickItemField(i, worstCol)}>
                                      <span className={`conf-dot ${cls}`}><span className="dot"></span><span className="pct">{Math.round(rc * 100)}%</span></span>
                                    </td>
                                  </tr>
                                );
                              });
                            })()}
                            <tr className="total">
                              <td colSpan={6} style={{ textAlign: "right" }}>合计 Total</td>
                              <td>{itemsTableData(cur.extract_result).reduce((s, r) => s + (parseFloat(_v(r, "amount")) || 0), 0).toFixed(2)}</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                ) : (
                  /* Tab 2: 原始单据大图（点击可放大） */
                  <div className="preview-pane">
                    {cur.preview_image ? (
                      <img
                        src={`data:image/jpeg;base64,${cur.preview_image}`}
                        alt="原始单据"
                        style={{ cursor: "zoom-in" }}
                        title="点击放大"
                        onClick={() => setShowImage(true)}
                      />
                    ) : (
                      <div style={{ color: "var(--text-dim)", fontSize: 12 }}>暂无图片预览</div>
                    )}
                  </div>
                )}
              </div>

              {/* 右侧：纯输入修正面板 */}
              <div className="detail-panel">
                <div className="detail-header">✏️ 人工修正 {editedCount > 0 && <span className="edit-count">{editedCount}</span>}</div>
                <div className="detail-body">
                  {selectedField ? (() => {
                    const f = fieldByKey(cur.extract_result, cur.doc_type, selectedField);
                    if (!f) return null;
                    const cls = f.status || statusClass(f.confidence);
                    return (
                      <>
                        <div className="field-info">
                          <div className="fname">{f.label}</div>
                          <div className="fmeta">置信度 {Math.round(f.confidence * 100)}% · {cls === "high" ? "高可信（自动预填）" : cls === "medium" ? "中置信（可抽查）" : "低置信（需修正）"}</div>
                        </div>

                        <div className="field-input">
                          <input
                            type="text"
                            value={inputVal}
                            onChange={(e) => { setInputVal(e.target.value); updateField(f.key, e.target.value); }}
                            autoFocus
                            className={cls === "low" ? "low" : ""}
                            placeholder={f._forceRequired ? "⚠️ 请人工核对后输入" : "核对后输入修正值"}
                          />
                        </div>

                        {cur.ocr_text && (
                          <div className="ocr-block">
                            <div className="ocr-label">📝 原文定位</div>
                            <OcrHighlight text={cur.ocr_text} query={String(f.value ?? "")} />
                          </div>
                        )}
                      </>
                    );
                  })() : (
                    <div style={{ padding: 30, textAlign: "center", color: "var(--text-dim)", fontSize: 12 }}>
                      ← 从中间表格选字段
                    </div>
                  )}
                </div>
                {selectedField && (() => {
                  const f = fieldByKey(cur.extract_result, cur.doc_type, selectedField);
                  if (!f) return null;
                  const vals = flatAll.map(x => x.key);
                  const idx = vals.indexOf(f.key);
                  // 待处理 = 未复核 且 非高置信——高置信自动预填的不一个个过，浪费时间
                  const isPending = (ff) =>
                    ff && !ff._reviewed && !((ff.confidence ?? 0) >= CONF.high && ff.value != null && ff.value !== "");
                  let prevIdx = -1, nextIdx = -1;
                  for (let i = idx - 1; i >= 0; i--) { if (isPending(flatAll[i])) { prevIdx = i; break; } }
                  for (let i = idx + 1; i < vals.length; i++) { if (isPending(flatAll[i])) { nextIdx = i; break; } }

                  const onReviewed = () => {
                    markFieldReviewed(selectedField);
                    if (nextIdx >= 0) {
                      setSelectedField(vals[nextIdx]);
                    } else {
                      showToast(prevIdx >= 0 ? "后面已无待处理字段（上方还有）" : "已无待处理字段", "ok");
                    }
                  };

                  return (
                    <div className="detail-footer">
                      <button
                        className="btn btn-primary"
                        style={{ padding: "8px 10px", fontSize: 11, marginBottom: 6 }}
                        onClick={onReviewed}
                      >✓ 确认复核</button>
                      <div style={{ display: "flex", gap: 6 }}>
                        <button className="btn btn-outline" style={{ flex: 1, padding: "6px 8px", fontSize: 10 }}
                          disabled={prevIdx < 0}
                          onClick={() => setSelectedField(vals[prevIdx])}>↑ 上一个待处理</button>
                        <button className="btn btn-outline" style={{ flex: 1, padding: "6px 8px", fontSize: 10 }}
                          disabled={nextIdx < 0}
                          onClick={() => setSelectedField(vals[nextIdx])}>↓ 下一个待处理</button>
                      </div>
                    </div>
                  );
                })()}
                {validation.length > 0 && (
                  <div className="validate-block">
                    {validation.map((c, i) => (
                      <div key={i} className={`validate-item ${c.pass ? "ok" : "error"}`} style={{ marginBottom: i < validation.length - 1 ? 4 : 0 }}>
                        {c.msg}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </section>
      </div>

      {/* 单据类型确认弹窗 */}
      {pendingType && (
        <div className="type-confirm-modal">
          <div className="type-confirm-box">
            <div className="type-confirm-title">🎯 AI 识别完成 · 请确认单据类型</div>
            <div className="type-confirm-file">📄 {pendingType.filename}</div>
            <div className="type-confirm-row">
              <div>
                <div className="type-confirm-label">AI 识别结果</div>
                <div className="type-confirm-value">
                  {(DOC_TYPE_META[pendingType.recognized] || {}).icon} {(DOC_TYPE_META[pendingType.recognized] || {}).label || pendingType.recognized}
                </div>
              </div>
              <div>
                <div className="type-confirm-label">如需修正，选择下方类型</div>
                <div className="type-confirm-btns">
                  {Object.entries(DOC_TYPE_META).map(([t, m]) => (
                    <button
                      key={t}
                      className={`tc-btn ${pendingType.recognized === t ? "active" : ""}`}
                      onClick={() => confirmTypeAndContinue(t)}
                    >{m.icon} {m.label}</button>
                  ))}
                </div>
              </div>
            </div>
            <div className="type-confirm-sub">
              确认后进入 <b>多模态识别 → 结构化抽取 → 置信度校验</b> 完整流程；改选类型会按对应模板重新抽取
            </div>
          </div>
        </div>
      )}

      {/* 跨类型切换确认：换模板=换 Schema 真实重抽（首次 10-60s，同组合之后缓存秒回） */}
      {pendingSwitch && (
        <div className="type-confirm-modal" onClick={() => setPendingSwitch(null)}>
          <div className="type-confirm-box" onClick={(e) => e.stopPropagation()}>
            <div className="type-confirm-title">🔄 按「{(DOC_TYPE_META[pendingSwitch] || {}).label || pendingSwitch}」重新抽取？</div>
            <div style={{ fontSize: 12, color: "var(--text-2)", margin: "12px 0 16px", lineHeight: 1.8 }}>
              当前单据将换用<b>{(DOC_TYPE_META[pendingSwitch] || {}).label || pendingSwitch}</b>的字段模板重新抽取
              （不同单据字段集不同，必须重抽），约 <b>10-60 秒</b>（真实调用，多页 PDF 更慢）。现有识别结果将被替换。
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button className="btn btn-outline" style={{ flex: 1 }} onClick={() => setPendingSwitch(null)}>取消</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={confirmSwitchType}>继续抽取</button>
            </div>
          </div>
        </div>
      )}

      {/* 批量类型确认弹窗 */}
      {confirmBatchType && (
        <div className="type-confirm-modal">
          <div className="type-confirm-box">
            <div className="type-confirm-title">📂 批量识别 · 请确认单据类型</div>
            <div className="type-confirm-file">共 {confirmBatchType.count} 份文件 · 选择统一单据类型</div>
            <div className="type-confirm-btns" style={{ display: "flex", gap: 10 }}>
              <button
                className={`tc-btn ${confirmBatchType.guessedType === "invoice" ? "active" : ""}`}
                style={{ flex: 1, padding: "14px 16px" }}
                onClick={() => runBatchRecognize("invoice")}
              >📄 发票类<br /><span style={{ fontSize: 11, color: "var(--text-3)" }}>商业发票 / 增值税发票</span></button>
              <button
                className={`tc-btn ${confirmBatchType.guessedType === "quotation" ? "active" : ""}`}
                style={{ flex: 1, padding: "14px 16px" }}
                onClick={() => runBatchRecognize("quotation")}
              >🚚 报价单<br /><span style={{ fontSize: 11, color: "var(--text-3)" }}>货代报价单 / 运费报价</span></button>
              <button
                className={`tc-btn ${confirmBatchType.guessedType === "booking" ? "active" : ""}`}
                style={{ flex: 1, padding: "14px 16px" }}
                onClick={() => runBatchRecognize("booking")}
              >📑 托书<br /><span style={{ fontSize: 11, color: "var(--text-3)" }}>订舱委托书 / Booking</span></button>
            </div>
            <div className="type-confirm-sub">
              所有文件将按统一类型串行识别，每份独立计算置信度
            </div>
          </div>
        </div>
      )}

      {/* 批量进度弹窗 */}
      {batchMode && loading && (
        <div className="type-confirm-modal" style={{ position: "absolute" }}>
          <div className="type-confirm-box">
            <div className="type-confirm-title">🔄 批量识别中...</div>
            <div style={{ marginTop: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 12, color: "var(--text-2)" }}>
                <span>正在处理第 {Math.min(batchProgress.current + 1, batchProgress.total)} / {batchProgress.total} 份</span>
                <span>{Math.round((batchProgress.current / Math.max(1, batchProgress.total)) * 100)}%</span>
              </div>
              <div style={{ width: "100%", height: 6, background: "var(--panel-2)", borderRadius: 3, overflow: "hidden" }}>
                <div style={{
                  height: "100%", background: "var(--accent)", borderRadius: 3,
                  width: `${(batchProgress.current / Math.max(1, batchProgress.total)) * 100}%`,
                  transition: "width 0.2s",
                }} />
              </div>
            </div>
            <div style={{ marginTop: 12, fontSize: 11, color: "var(--text-3)", textAlign: "center" }}>
              当前：{batchFiles?.[batchProgress.current]?.name || "..."}
            </div>
          </div>
        </div>
      )}

      {/* 隐藏文件输入（挂根节点：落地页无侧栏时，水波环中心也能直接打开选择器） */}
      <input
        ref={inputRef} type="file" hidden
        accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
        onChange={(e) => { const f = e.target.files[0]; if (f) { setFile(f); onAnalyze(f); } e.target.value = ""; }}
      />

      {/* Toast */}
      {toast && <div className={`toast ${toast.type}`}>{toast.msg}</div>}

      {/* 放大图片弹窗 */}
      {showImage && cur?.preview_image && (
        <div className="type-confirm-modal" onClick={() => setShowImage(false)}>
          <div style={{
            maxWidth: "90vw", maxHeight: "90vh", overflow: "auto",
            background: "var(--panel)", borderRadius: 10,
            border: "1px solid var(--line)", padding: 16,
          }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <span style={{ fontSize: 12, color: "var(--text-2)" }}>{cur.filename}</span>
              <button style={{
                background: "none", border: "none", color: "var(--text-3)",
                fontSize: 20, cursor: "pointer", lineHeight: 1,
              }} onClick={() => setShowImage(false)}>×</button>
            </div>
            <img src={`data:image/jpeg;base64,${cur.preview_image}`}
              style={{ maxWidth: "100%", display: "block" }} alt="原始单据放大" />
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
