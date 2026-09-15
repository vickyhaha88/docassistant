# -*- coding: utf-8 -*-
"""生成跨境物流报价单 PDF 样张"""
import os

# ========= 报价单 =========
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

SAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")


def _register_font():
    """注册中文字体，失败则回退"""
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyh.ttf",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for i, path in enumerate(candidates):
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(f"sample_font_{i}", path))
                return f"sample_font_{i}"
            except Exception:
                continue
    return None


def gen_quotation():
    if not HAS_REPORTLAB:
        print("reportlab not installed, skip PDF generation")
        return
    os.makedirs(SAMPLES_DIR, exist_ok=True)
    out = os.path.join(SAMPLES_DIR, "sample_quotation.pdf")

    font_name = _register_font()
    styles = getSampleStyleSheet()
    if font_name:
        base = ParagraphStyle("base", parent=styles["Normal"], fontName=font_name, fontSize=10, leading=14)
        h1 = ParagraphStyle("h1", parent=base, fontSize=20, leading=26, spaceAfter=6, fontName=font_name)
        h2 = ParagraphStyle("h2", parent=base, fontSize=12, leading=18, spaceBefore=10, spaceAfter=4, fontName=font_name)
        bold = ParagraphStyle("bold", parent=base, fontName=font_name, spaceAfter=2)
    else:
        base = styles["Normal"]
        h1 = styles["Title"]
        h2 = styles["Heading2"]
        bold = ParagraphStyle("bold", parent=base)

    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm)
    story = []

    story.append(Paragraph("ABC INTERNATIONAL LOGISTICS CO., LTD.", h1))
    story.append(Paragraph("Air Freight Quotation / 空运报价单", ParagraphStyle("sub", parent=base, fontSize=14, textColor=colors.HexColor("#2563eb"))))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563eb")))
    story.append(Spacer(1, 0.3 * cm))

    header_data = [
        [Paragraph("<b>Quotation No.:</b> AFQ-2026-0910-007", base),
         Paragraph("<b>Date:</b> 2026-09-10", base),
         Paragraph("<b>Valid Until:</b> 2026-09-24", base)],
    ]
    story.append(Table(header_data, colWidths=[6 * cm, 5 * cm, 6 * cm]))
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("From / 货代信息", h2))
    from_data = [
        [Paragraph("<b>Company:</b>", bold), Paragraph("ABC International Logistics Co., Ltd.", base)],
        [Paragraph("<b>Contact:</b>", bold), Paragraph("John Zhang", base)],
        [Paragraph("<b>Email:</b>", bold), Paragraph("john.zhang@abclogistics.com", base)],
        [Paragraph("<b>Phone:</b>", bold), Paragraph("+86 755 8888 6666", base)],
        [Paragraph("<b>Address:</b>", bold), Paragraph("Room 2018, Southern International Center, Shenzhen, China", base)],
    ]
    story.append(Table(from_data, colWidths=[3 * cm, 14 * cm], style=TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])))
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("To / 客户信息", h2))
    to_data = [
        [Paragraph("<b>Company:</b>", bold), Paragraph("XYZ Global Trading Inc.", base)],
        [Paragraph("<b>Contact:</b>", bold), Paragraph("Jane Smith", base)],
        [Paragraph("<b>Email:</b>", bold), Paragraph("jane.smith@xyzglobal.com", base)],
        [Paragraph("<b>Phone:</b>", bold), Paragraph("+1 555 987 6543", base)],
        [Paragraph("<b>Address:</b>", bold), Paragraph("123 Harbor Blvd, Los Angeles, CA 90001, USA", base)],
    ]
    story.append(Table(to_data, colWidths=[3 * cm, 14 * cm], style=TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])))
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("Shipment Details / 货物信息", h2))
    ship_data = [
        [Paragraph("<b>Origin Airport</b>", bold), Paragraph("SZX (Shenzhen Bao'an)", base),
         Paragraph("<b>Destination Airport</b>", bold), Paragraph("LAX (Los Angeles International)", base)],
        [Paragraph("<b>Transport Mode</b>", bold), Paragraph("Air Freight", base),
         Paragraph("<b>Incoterm</b>", bold), Paragraph("EXW Shenzhen", base)],
        [Paragraph("<b>Commodity</b>", bold), Paragraph("USB-C Charging Cable, 100% Recycled Plastic", base),
         Paragraph("<b>HS Code</b>", bold), Paragraph("8544.42", base)],
        [Paragraph("<b>No. of Cartons</b>", bold), Paragraph("25", base),
         Paragraph("<b>Gross Weight</b>", bold), Paragraph("350 kg", base)],
        [Paragraph("<b>Volume</b>", bold), Paragraph("1.8 m³", base),
         Paragraph("<b>Chargeable Weight</b>", bold), Paragraph("350 kg", base)],
        [Paragraph("<b>ETD</b>", bold), Paragraph("2026-09-25", base),
         Paragraph("<b>Transit Time</b>", bold), Paragraph("5-7 Working Days", base)],
    ]
    story.append(Table(ship_data, colWidths=[3.5 * cm, 4 * cm, 3.5 * cm, 5 * cm], style=TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f1f5f9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ])))
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("Quotation Breakdown / 费用明细", h2))
    charge_header = [
        Paragraph("<b>Description</b>", base),
        Paragraph("<b>Unit</b>", base),
        Paragraph("<b>Quantity</b>", base),
        Paragraph("<b>Rate (USD)</b>", base),
        Paragraph("<b>Amount (USD)</b>", base),
    ]
    charge_rows = [charge_header] + [
        [Paragraph("Air Freight Charge / 空运费", base), "kg", "350", "4.20", "1,470.00"],
        [Paragraph("Fuel Surcharge / 燃油附加费", base), "kg", "350", "0.84", "294.00"],
        [Paragraph("Security Fee / 安全附加费", base), "shipment", "1", "120.00", "120.00"],
        [Paragraph("Handling Fee / 操作费", base), "shipment", "1", "80.00", "80.00"],
        [Paragraph("Documentation Fee / 文件费", base), "shipment", "1", "50.00", "50.00"],
        [Paragraph("Export Customs Clearance / 出口报关", base), "shipment", "1", "180.00", "180.00"],
    ]
    charge_rows.append([Paragraph("", base), Paragraph("", base), Paragraph("", base),
                        Paragraph("<b>Total</b>", base), Paragraph("<b>2,194.00</b>", base)])

    story.append(Table(charge_rows, colWidths=[7 * cm, 2.5 * cm, 2.5 * cm, 3 * cm, 3 * cm], style=TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e40af")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#dbeafe")),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ])))
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("Remarks / 条款与注意事项", h2))
    remarks = [
        "1. This quotation is valid for 14 days from the date of issue.",
        "2. Rates are based on current carrier tariffs and may change without prior notice.",
        "3. Quotation does not include destination duties, taxes or customs clearance at destination.",
        "4. Payment terms: 100% prepayment before shipment.",
        "5. Transit time is estimated and subject to airline schedule confirmation.",
        "6. Dangerous goods, batteries or liquids require prior notification and may incur additional charges.",
    ]
    for r in remarks:
        story.append(Paragraph(r, base))

    story.append(Spacer(1, 1 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Table([
        [Paragraph("<b>Authorized Signature:</b>", base), Paragraph("_______________________________", base),
         Paragraph("<b>Date:</b>", base), Paragraph("2026-09-10", base)],
    ], colWidths=[3.5 * cm, 6 * cm, 2 * cm, 5 * cm]))

    doc.build(story)
    print(f"  -> generated {out}")


def gen_commercial_invoice():
    """生成供应商商业发票 Commercial Invoice PDF"""
    if not HAS_REPORTLAB:
        print("reportlab not installed, skip PDF generation")
        return
    os.makedirs(SAMPLES_DIR, exist_ok=True)
    out = os.path.join(SAMPLES_DIR, "sample_commercial_invoice.pdf")

    font_name = _register_font()
    styles = getSampleStyleSheet()
    if font_name:
        base = ParagraphStyle("ci_base", parent=styles["Normal"], fontName=font_name, fontSize=9, leading=12)
        h1 = ParagraphStyle("ci_h1", parent=base, fontSize=18, leading=22, spaceAfter=4, fontName=font_name)
        h2 = ParagraphStyle("ci_h2", parent=base, fontSize=11, leading=14, spaceBefore=8, spaceAfter=4, fontName=font_name, textColor=colors.HexColor("#1e40af"))
        bold = ParagraphStyle("ci_bold", parent=base, fontName=font_name)
        small = ParagraphStyle("ci_small", parent=base, fontSize=8, leading=10)
    else:
        base = styles["Normal"]
        h1 = styles["Title"]
        h2 = styles["Heading2"]
        bold = ParagraphStyle("ci_bold", parent=base)
        small = base

    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm)
    story = []

    # 抬头
    story.append(Paragraph("宁波永盛制造有限公司", h1))
    story.append(Paragraph("商 业 发 票", ParagraphStyle("ci_sub", parent=base, fontSize=14, textColor=colors.HexColor("#1e40af"), spaceAfter=2)))
    story.append(Paragraph("COMMERCIAL INVOICE", ParagraphStyle("ci_sub2", parent=base, fontSize=9, textColor=colors.grey, spaceAfter=4)))
    story.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor("#1e40af")))
    story.append(Spacer(1, 0.3 * cm))

    # 发票号/日期
    story.append(Table([
        [Paragraph("<b>发票号：</b> CI-20260908-00347", bold),
         Paragraph("<b>日期：</b> 2026-09-08", bold),
         Paragraph("<b>币种：</b> USD 美元", bold)],
        [Paragraph("<b>起运港：</b> 中国 宁波 NINGBO", base),
         Paragraph("<b>目的港：</b> 美国 洛杉矶 LOS ANGELES", base),
         Paragraph("<b>贸易术语：</b> FOB Ningbo", base)],
        [Paragraph("<b>付款方式：</b> 电汇 T/T（30%预付，70%发货前付清）", base),
         Paragraph("<b>贸易方式：</b> 一般贸易", base),
         Paragraph("<b>HS 编码：</b> 9403.60.9000", base)],
    ], colWidths=[6.2 * cm, 6.2 * cm, 5.5 * cm], style=TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])))

    story.append(Spacer(1, 0.35 * cm))

    # 卖方 / 买方 两栏
    seller_data = [
        [Paragraph("<b>卖方 Seller</b>", base)],
        [Paragraph("宁波永盛制造有限公司", base)],
        [Paragraph("NINGBO EVERGREEN MANUFACTURING CO., LTD.", base)],
        [Paragraph("地址：浙江省宁波市鄞州区工业区 88 号", small)],
        [Paragraph("电话：0574-88881234  传真：0574-88885678", small)],
        [Paragraph("邮箱：sales@evergreen-mfg.com", small)],
        [Paragraph("<b>纳税人识别号：</b> 91330200MA28XXXXXX", base)],
    ]
    buyer_data = [
        [Paragraph("<b>买方 Buyer</b>", base)],
        [Paragraph("XYZ 环球贸易有限公司", base)],
        [Paragraph("XYZ GLOBAL TRADING INC.", base)],
        [Paragraph("地址：123 Harbor Blvd, Suite 400, Los Angeles, CA 90001, USA", small)],
        [Paragraph("电话：+1 555 987 6543  传真：+1 555 987 6544", small)],
        [Paragraph("邮箱：jane.smith@xyzglobal.com", small)],
        [Paragraph("<b>纳税人识别号：</b> 88-1234567", base)],
    ]
    story.append(Table([[Table(seller_data, colWidths=[8.8 * cm]), Table(buyer_data, colWidths=[8.8 * cm])]],
                       colWidths=[17.6 * cm]))

    story.append(Spacer(1, 0.3 * cm))

    # 货物明细
    story.append(Paragraph("货物明细", h2))

    def _p(text, style=None):
        """安全包装 plain string → Paragraph，确保用中文字体"""
        return Paragraph(str(text), style or base)

    item_header = [
        _p("<b>序号</b>"),
        _p("<b>货物描述</b>"),
        _p("<b>HS Code</b>"),
        _p("<b>数量</b>"),
        _p("<b>单位</b>"),
        _p("<b>单价 (USD)</b>"),
        _p("<b>金额 (USD)</b>"),
    ]
    item_data = [
        ["1", "实木餐椅 DC-801 Solid Wood Dining Chair", "9403.60.9000", "500", "PCS", "28.50", "14,250.00"],
        ["2", "实木餐桌 DT-120 1.2m Solid Wood Dining Table", "9403.60.9000", "80", "PCS", "156.00", "12,480.00"],
        ["3", "实木餐边柜 SC-205 Wooden Sideboard Cabinet", "9403.60.9000", "30", "PCS", "220.00", "6,600.00"],
        ["4", "实木书架 BS-180 Wooden Bookshelf", "9403.60.9000", "45", "PCS", "89.00", "4,005.00"],
        ["5", "实木茶几 CT-90 Wooden Coffee Table", "9403.60.9000", "60", "PCS", "75.00", "4,500.00"],
        ["6", "包装：5层瓦楞纸箱 + 泡沫保护", "", "", "", "", ""],
        ["7", "原产国：中国 (MADE IN CHINA)", "", "", "", "", ""],
    ]
    item_rows = [item_header] + [[_p(c) for c in row] for row in item_data]
    # 合计行
    item_rows.append([_p(""), _p(""), _p(""), _p(""), _p("<b>合计</b>"), _p(""),
                      _p("<b>41,835.00</b>")])

    story.append(Table(item_rows,
                       colWidths=[1.2*cm, 7*cm, 2.2*cm, 1.3*cm, 1.2*cm, 2.5*cm, 2.5*cm],
                       style=TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e40af")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -3), (-1, -3), colors.HexColor("#fef3c7")),  # packing row
        ("BACKGROUND", (0, -2), (-1, -2), colors.HexColor("#fef3c7")),  # origin row
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#dbeafe")),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("ALIGN", (3, 1), (5, -1), "CENTER"),
        ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])))

    story.append(Spacer(1, 0.3 * cm))

    # 金额汇总
    story.append(Paragraph("金额汇总", h2))
    summary = [
        [Paragraph("<b>小计 Subtotal</b>", bold), Paragraph("", base), Paragraph("41,835.00", base)],
        [Paragraph("<b>运费 Freight (FOB)</b>", bold), Paragraph("", base), Paragraph("0.00", base)],
        [Paragraph("<b>保险 Insurance</b>", bold), Paragraph("", base), Paragraph("0.00", base)],
        [Paragraph("<b>折扣 Discount</b>", bold), Paragraph("电汇预付 3%", small), Paragraph("-1,255.05", base)],
        [Paragraph("<b>发票总额 INVOICE TOTAL</b>", ParagraphStyle("tot", parent=bold, fontSize=11)),
         Paragraph("", base), Paragraph("<b>40,579.95</b>", ParagraphStyle("tot2", parent=bold, fontSize=11, textColor=colors.HexColor("#b91c1c")))],
        [Paragraph("", base), Paragraph("", base),
         Paragraph("<b>英文金额：U.S. Dollars Forty Thousand Five Hundred Seventy-Nine and Cents Ninety-Five Only</b>",
                   ParagraphStyle("words", parent=base, fontSize=8, textColor=colors.grey))],
    ]
    story.append(Table(summary, colWidths=[5*cm, 7*cm, 5.5*cm], style=TableStyle([
        ("GRID", (0, 0), (-1, 5), 0.3, colors.grey),
        ("BACKGROUND", (0, 4), (-1, 4), colors.HexColor("#fee2e2")),
        ("FONTNAME", (0, 0), (-1, -1), font_name or "Helvetica"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (-1, 0), (-1, 5), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])))

    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))

    # 签名区
    story.append(Spacer(1, 0.4 * cm))
    story.append(Table([
        [Paragraph("<b>授权签字人：</b>", base),
         Paragraph("_______________________________", base),
         Paragraph("<b>日期：</b>", base),
         Paragraph("2026-09-08", base)],
        [Paragraph("", base), Paragraph("王悠悠 (销售经理)", small), Paragraph("", base), Paragraph("", base)],
        [Paragraph("<b>银行信息：</b>", base),
         Paragraph("ABC Bank 宁波分行\n账号：6222 **** **** 8899\nSWIFT：BKCHCNBJ92A", small),
         Paragraph("", base), Paragraph("", base)],
    ], colWidths=[3.5*cm, 8*cm, 2*cm, 4*cm], style=TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, -1), font_name or "Helvetica"),
    ])))

    doc.build(story)
    print(f"  -> generated {out}")


if __name__ == "__main__":
    gen_quotation()
    gen_commercial_invoice()
    print("Done!")
