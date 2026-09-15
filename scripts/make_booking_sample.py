# -*- coding: utf-8 -*-
"""生成空运托书演示样本 PDF（samples/sample_booking.pdf）。

设计约束（与确定性交叉校验对齐，数字可被代码勾稽）：
- ETD(2026-09-28) < ETA(2026-09-29)：时间勾稽可过
- 计费重 802 = max(毛重 760, 体积 4.8×167=801.6) 向上进位到 0.5kg：计费重勾稽可过
  （空运体积比 1:167，IATA 6000cm³/kg）
- 件数/毛重/体积/计费重为纯数字（单位写在标签里），数值校验可过
- 机场字段带 IATA 三字码（SZX / LAX），与报价单样本口径一致，三字码字典校验可过
- 无联系人/电话/邮箱/收货人/通知人（敏感信息不进 Schema；收货人属运单补料环节）
- 严格一行一字段（实测两栏同行会让文本层字符按 x 交错，抽取/回溯全毁）
- 混合字体渲染：拉丁字符用 Helvetica（正常字距），仅中文用 china-s——
  china-s 内置拉丁字形是全角宽字距，整行用它会导致英文"一个字母一个字母隔开"
- pymupdf insert_text 生成真文本层：类型路由 / 原文回溯 / 前端原文定位三层共用
"""
import os
import re
import sys

import pymupdf

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples", "sample_booking.pdf"))

W, H = 595, 842  # A4
M = 50           # 左右边距
GRAY = (0.55, 0.55, 0.55)
DARK = (0.1, 0.1, 0.1)

F_LATIN = "helv"      # 拉丁：Helvetica，正常比例字距
F_CJK = "china-s"     # 中文：pymupdf 内置简体
_LATIN_METRIC = pymupdf.Font(F_LATIN)
_CJK_METRIC = pymupdf.Font(F_CJK)
_CJK_RE = re.compile(r"[⺀-鿿豈-﫿＀-￯　-〿]")


def _runs(s: str):
    """把字符串切成 (片段, 是否中文) 序列，供分段选字体渲染"""
    runs = []
    for ch in s:
        cjk = bool(_CJK_RE.match(ch))
        if runs and runs[-1][1] == cjk:
            runs[-1] = (runs[-1][0] + ch, cjk)
        else:
            runs.append((ch, cjk))
    return runs


def text_width(s: str, size: float) -> float:
    return sum((_CJK_METRIC if cjk else _LATIN_METRIC).text_length(seg, fontsize=size)
               for seg, cjk in _runs(s))


def text(page, x, yy, s, size=11, color=DARK):
    """混合字体逐段绘制，返回行尾 x（拉丁正常字距 + 中文等宽，互不干扰）"""
    for seg, cjk in _runs(s):
        font = F_CJK if cjk else F_LATIN
        page.insert_text((x, yy), seg, fontname=font, fontsize=size, color=color)
        x += (_CJK_METRIC if cjk else _LATIN_METRIC).text_length(seg, fontsize=size)
    return x


# 单据数据（数字之间可勾稽：ETD<ETA；计费重=max(760, 4.8×167)≈802）
FIELDS = [
    ("header", "SHIPPER", "托运人"),
    ("field", "Name 公司名称", "广州纺织进出口有限公司"),
    ("field", "Address 地址", "广东省广州市海珠区纺织路256号"),
    ("header", "FLIGHT & ROUTING", "航班路线"),
    ("field", "Airline 航空公司", "China Southern Airlines 中国南方航空"),
    ("field", "Flight No. 航班号", "CZ3411"),
    ("field", "Airport of Departure 起运机场", "SZX (Shenzhen Bao'an Int'l Airport)"),
    ("field", "Airport of Arrival 目的机场", "LAX (Los Angeles Int'l Airport)"),
    ("field", "Place of Delivery 交货地", "Los Angeles, CA, USA"),
    ("field", "ETD 预计起飞日", "2026-09-28"),
    ("field", "ETA 预计到港日", "2026-09-29"),
    ("header", "CARGO", "货物信息"),
    ("field", "Cargo Description 货名", "涤纶针织上衣 Polyester Knitted Blouses"),
    ("field", "Packages 件数 (CTNS)", "48"),
    ("field", "Gross Weight 毛重 (KGS)", "760"),
    ("field", "Volume 体积 (CBM)", "4.8"),
    ("field", "Chargeable Weight 计费重 (KGS)", "802"),
    ("header", "TERMS", "条款"),
    ("field", "Incoterm 贸易术语", "FOB Shenzhen"),
    ("field", "Payment Terms 付款条款", "T/T 30 days"),
    ("field", "Special Requirements 特殊要求", "内置锂电池，随附 UN38.3 测试报告"),
    ("field", "Remarks 备注", "舱位确认后请邮件回执"),
]


def build():
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)

    def line(y0, color=GRAY, width=0.7):
        page.draw_line(pymupdf.Point(M, y0), pymupdf.Point(W - M, y0), color=color, width=width)

    # ===== 标题 =====
    y = 72
    title = "AIR FREIGHT BOOKING NOTE"
    text(page, (W - text_width(title, 17)) / 2, y, title, size=17)
    y += 22
    sub = "空运出口货物托书（空运订舱委托书）"
    text(page, (W - text_width(sub, 13)) / 2, y, sub, size=13)
    y += 14
    line(y)

    # ===== 编号区（一行一字段）=====
    y += 22
    text(page, M, y, "Booking Number 托书编号: BK-2026-0925-103")
    y += 16
    text(page, M, y, "Booking Date 托书日期: 2026-09-25")

    # ===== 字段区（行距收紧，全部落在页脚线之上）=====
    for kind, *vals in FIELDS:
        if kind == "header":
            y += 24
            page.draw_rect(pymupdf.Rect(M, y - 11, W - M, y + 4), color=None, fill=(0.92, 0.92, 0.92))
            text(page, M + 6, y, f"{vals[0]}  {vals[1]}", size=10, color=(0.25, 0.25, 0.25))
            y += 19
        else:
            label, value = vals
            text(page, M, y, f"{label}: {value}")
            y += 16

    # ===== 页脚 =====
    line(H - 60)
    text(page, M, H - 42, "Generated air booking note sample for system demo purposes only.", size=8, color=GRAY)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    doc.save(OUT)
    doc.close()
    print(f"生成 {OUT}（{os.path.getsize(OUT)} bytes）")


if __name__ == "__main__":
    build()
