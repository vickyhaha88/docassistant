"""批量生成 3 份报价单 PDF 样本（不同数据）"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# 注册中文字体
try:
    pdfmetrics.registerFont(TTFont("msyh", r"C:\Windows\Fonts\msyh.ttc"))
    pdfmetrics.registerFont(TTFont("msyhbd", r"C:\Windows\Fonts\msyhbd.ttc"))
except Exception as e:
    print(f"font err: {e}")

OUT = r"D:\AI_Project\DocAssistant\samples\batch_invoices"
os.makedirs(OUT, exist_ok=True)

# 3 份商业发票不同数据
INVOICES = [
    {
        "no": "CI-2026-0908-00347", "date": "2026-09-08", "seller": "宁波永盛制造有限公司",
        "seller_addr": "浙江省宁波市北仑区出口加工区88号", "seller_tax": "91330200MA28D4K3X7",
        "buyer": "XYZ Global Trading Inc.", "buyer_addr": "123 Harbor Blvd, Los Angeles, CA 90001, USA",
        "port": "NINGBO, CHINA", "dest": "LOS ANGELES, USA", "terms": "FOB Ningbo",
        "items": [
            ("实木餐椅", "Solid Wood Dining Chair, Model DC-801", "9403.60.9000", 500, "PCS", 28.50, 14250.00),
            ("实木餐桌", "Solid Wood Dining Table, Model DT-120", "9403.60.9000", 80, "PCS", 158.00, 12640.00),
            ("餐边柜", "Wooden Sideboard Cabinet, Model SC-205", "9403.60.9000", 30, "PCS", 225.00, 6750.00),
            ("书架", "Wooden Bookshelf, Model BS-180", "9403.60.9000", 45, "PCS", 89.00, 4005.00),
            ("茶几", "Wooden Coffee Table, Model CT-90", "9403.60.9000", 60, "PCS", 78.00, 4680.00),
        ],
        "total_qty": 715, "subtotal": 42325.00, "discount_pct": 3, "total": 41055.25,
        "currency": "USD",
    },
    {
        "no": "CI-2026-0910-00351", "date": "2026-09-10", "seller": "深圳创新电子科技有限公司",
        "seller_addr": "广东省深圳市南山区科技园南区创新路100号", "seller_tax": "91440300MA5BCN2K9L",
        "buyer": "TechCorp Distribution LLC", "buyer_addr": "456 Tech Park, Dallas, TX 75201, USA",
        "port": "SHENZHEN, CHINA", "dest": "DALLAS, USA", "terms": "CIF Dallas",
        "items": [
            ("无线蓝牙耳机", "Wireless Bluetooth Earbuds, Pro X", "8518.30.0000", 2000, "PCS", 12.50, 25000.00),
            ("智能手表", "Smart Watch S1, 42mm", "8517.62.0000", 300, "PCS", 45.00, 13500.00),
            ("便携充电宝", "Portable Power Bank 20000mAh", "8507.60.0000", 1500, "PCS", 8.00, 12000.00),
        ],
        "total_qty": 3800, "subtotal": 50500.00, "discount_pct": 2, "total": 49490.00,
        "currency": "USD",
    },
    {
        "no": "CI-2026-0912-00355", "date": "2026-09-12", "seller": "广州纺织进出口有限公司",
        "seller_addr": "广东省广州市海珠区纺织路256号", "seller_tax": "91440101MA9XY7M43Q",
        "buyer": "Fashion Retail Group Ltd.", "buyer_addr": "789 Market Street, London EC2V 6DB, UK",
        "port": "GUANGZHOU, CHINA", "dest": "SOUTHAMPTON, UK", "terms": "FOB Guangzhou",
        "items": [
            ("棉质T恤", "100% Cotton T-Shirt, Unisex", "6109.10.0012", 5000, "PCS", 3.80, 19000.00),
            ("牛仔裤", "Denim Jeans, Regular Fit", "6203.42.4000", 2000, "PCS", 12.00, 24000.00),
            ("运动外套", "Sports Jacket, Polyester", "6101.20.0019", 800, "PCS", 18.50, 14800.00),
            ("围巾", "Cotton Scarf, Assorted Colors", "6117.10.0000", 3000, "PCS", 2.50, 7500.00),
        ],
        "total_qty": 10800, "subtotal": 65300.00, "discount_pct": 4, "total": 62688.00,
        "currency": "USD",
    },
]

def gen_invoice(data, path):
    doc = SimpleDocTemplate(path, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=18*mm, rightMargin=18*mm)
    elems = []
    styles = getSampleStyleSheet()
    zh = ParagraphStyle("zh", fontName="msyh", fontSize=10, leading=15)
    zh_b = ParagraphStyle("zhb", fontName="msyhbd", fontSize=11, leading=16)
    big = ParagraphStyle("big", fontName="msyhbd", fontSize=18, leading=22, alignment=1, textColor=HexColor("#2d7a7f"))

    elems.append(Paragraph("商业发票 / COMMERCIAL INVOICE", big))
    elems.append(Spacer(1, 6))

    # 抬头信息
    hdr = [
        [Paragraph("<b>发票号</b><br/>INVOICE NO.", zh_b), data["no"],
         Paragraph("<b>日期</b><br/>DATE", zh_b), data["date"]],
        [Paragraph("<b>卖方</b><br/>SELLER", zh_b),
         Paragraph(f"{data['seller']}<br/>{data['seller_addr']}<br/>税号 TAX ID: {data['seller_tax']}", zh),
         Paragraph("<b>买方</b><br/>BUYER", zh_b),
         Paragraph(f"{data['buyer']}<br/>{data['buyer_addr']}", zh)],
        [Paragraph("<b>起运港</b><br/>POL", zh_b), data["port"],
         Paragraph("<b>目的港</b><br/>POD", zh_b), data["dest"]],
        [Paragraph("<b>贸易条款</b><br/>INCOTERMS", zh_b), data["terms"],
         Paragraph("<b>币种</b><br/>CURRENCY", zh_b), data["currency"]],
    ]
    t_hdr = Table(hdr, colWidths=[32*mm, 65*mm, 32*mm, 65*mm])
    t_hdr.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), "msyh", 9),
        ("ALIGN", (0,0), (-1,-1), "LEFT"),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("GRID", (0,0), (-1,-1), 0.3, HexColor("#5c7390")),
        ("BACKGROUND", (0,0), (0,-1), HexColor("#1e2a3a")),
        ("BACKGROUND", (2,0), (2,-1), HexColor("#1e2a3a")),
    ]))
    elems.append(t_hdr)
    elems.append(Spacer(1, 10))

    # 货物明细
    elems.append(Paragraph("货物明细 / GOODS DESCRIPTION", zh_b))
    elems.append(Spacer(1, 4))

    rows = [["序号", "货物描述 / DESCRIPTION", "HS CODE", "数量", "单位", "单价", "金额"],
            ["NO.", "", "", "QTY", "UNIT", "PRICE", "AMOUNT"]]
    for i, item in enumerate(data["items"], 1):
        cn, en, hs, qty, unit, price, amt = item
        rows.append([str(i), f"{cn}\n{en}", hs, str(qty), unit, f"{price:.2f}", f"{amt:.2f}"])

    t = Table(rows, colWidths=[10*mm, 62*mm, 28*mm, 15*mm, 12*mm, 20*mm, 25*mm])
    t.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), "msyh", 8),
        ("FONT", (0,0), (-1,1), "msyhbd", 9),
        ("BACKGROUND", (0,0), (-1,1), HexColor("#243346")),
        ("TEXTCOLOR", (0,0), (-1,1), HexColor("#e1e8f0")),
        ("GRID", (0,0), (-1,-1), 0.3, HexColor("#5c7390")),
        ("ALIGN", (3,2), (-1,-1), "RIGHT"),
        ("ALIGN", (0,0), (0,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    elems.append(t)
    elems.append(Spacer(1, 6))

    # 金额汇总
    summary = [
        ["", "", "", "", "", "数量合计 TOTAL QTY:", f"{data['total_qty']}"],
        ["", "", "", "", "", "小计 SUBTOTAL:", f"{data['subtotal']:.2f} {data['currency']}"],
        ["", "", "", "", "", f"折扣 ({data['discount_pct']}%):", f"-{data['subtotal'] * data['discount_pct'] / 100:.2f}"],
        ["", "", "", "", "", "总金额 TOTAL AMOUNT:", f"{data['total']:.2f} {data['currency']}"],
    ]
    t_sum = Table(summary, colWidths=[10*mm, 62*mm, 28*mm, 15*mm, 12*mm, 35*mm, 30*mm])
    t_sum.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), "msyh", 8),
        ("FONT", (-2,-1), (-1,-1), "msyhbd", 10),
        ("BACKGROUND", (-2,-1), (-1,-1), HexColor("#2d7a7f")),
        ("TEXTCOLOR", (-2,-1), (-1,-1), "#ffffff"),
        ("ALIGN", (-2,0), (-1,-1), "RIGHT"),
        ("GRID", (-2,0), (-1,-1), 0.3, HexColor("#5c7390")),
    ]))
    elems.append(t_sum)

    doc.build(elems)
    print(f"✅ {path}")

for inv in INVOICES:
    gen_invoice(inv, os.path.join(OUT, f"invoice_{inv['no'].replace('/', '_')}.pdf"))

print(f"\n共生成 {len(INVOICES)} 份商业发票 → {OUT}")
