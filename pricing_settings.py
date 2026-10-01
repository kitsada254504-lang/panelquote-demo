"""Shop-level pricing settings and the quote total breakdown.

Order of calculation (see docs/PRICING_FORM.md):
items (already marked up per line) + contingency % of items + labor (optionally marked up)
+ shipping = gross; gross - discount % = before VAT; + VAT = total.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from quote_excel import money

SETTINGS_PATH = Path(__file__).parent / 'data' / 'pricing_settings.json'

# ค่าตั้งต้นตรงกับพฤติกรรมเดิมของแอป ไม่ใช่ตัวเลขธุรกิจที่ยืนยันแล้ว
DEFAULTS = {
    'markup_percent': 25.0,
    'markup_mode': 'markup',        # markup = บวกจากต้นทุน, margin = กำไรต่อยอดขาย
    'labor_amount': 0.0,            # ค่าแรงต่อใบเสนอราคา (บาท)
    'labor_marked_up': True,
    'shipping_amount': 0.0,
    'contingency_percent': 0.0,     # % ของยอดรายการอุปกรณ์
    'discount_percent': 0.0,
    'vat_percent': 7.0,
    'vat_enabled': True,
    'confirmed': False,             # เจ้าของงานยืนยันค่าชุดนี้แล้ว จึงออกฉบับจริงได้
}
PERCENT_FIELDS = ['markup_percent', 'contingency_percent', 'discount_percent', 'vat_percent']
AMOUNT_FIELDS = ['labor_amount', 'shipping_amount']
FLAG_FIELDS = ['labor_marked_up', 'vat_enabled', 'confirmed']


def validate_settings(values: dict | None) -> dict:
    clean = dict(DEFAULTS)
    clean.update({k: v for k, v in (values or {}).items() if k in DEFAULTS})
    for key in PERCENT_FIELDS + AMOUNT_FIELDS:
        number = Decimal(str(clean[key]))
        if not number.is_finite() or number < 0:
            raise ValueError(f'{key} must be a finite nonnegative number.')
        clean[key] = float(number)
    if clean['markup_mode'] not in {'markup', 'margin'}:
        raise ValueError('markup_mode must be markup or margin.')
    if clean['markup_mode'] == 'margin' and clean['markup_percent'] >= 100:
        raise ValueError('Margin must be below 100%.')
    if clean['discount_percent'] > 100:
        raise ValueError('Discount cannot exceed 100%.')
    for key in FLAG_FIELDS:
        clean[key] = bool(clean[key])
    return clean


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return dict(DEFAULTS)
    return validate_settings(json.loads(SETTINGS_PATH.read_text(encoding='utf-8')))


def save_settings(values: dict) -> dict:
    clean = validate_settings(values)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding='utf-8')
    return clean


def apply_markup(cost, settings: dict | None = None) -> Decimal:
    s = validate_settings(settings)
    rate = Decimal(str(s['markup_percent'])) / 100
    if s['markup_mode'] == 'margin':
        return money(Decimal(str(cost)) / (1 - rate))
    return money(Decimal(str(cost)) * (1 + rate))


def breakdown(items_subtotal, settings: dict | None = None) -> dict:
    """คืนยอดแต่ละขั้นเป็น Decimal; settings=None ใช้ค่าตั้งต้น (ไม่อ่านไฟล์)"""
    s = validate_settings(settings)
    pct = lambda key: Decimal(str(s[key])) / 100
    items = money(items_subtotal)
    contingency = money(items * pct('contingency_percent'))
    labor = apply_markup(s['labor_amount'], s) if s['labor_marked_up'] else money(s['labor_amount'])
    shipping = money(s['shipping_amount'])
    gross = items + contingency + labor + shipping
    discount = money(gross * pct('discount_percent'))
    before_vat = gross - discount
    vat = money(before_vat * pct('vat_percent')) if s['vat_enabled'] else Decimal('0.00')
    return {'items': items, 'contingency': contingency, 'labor': labor, 'shipping': shipping,
            'discount': discount, 'before_vat': before_vat, 'vat': vat, 'total': before_vat + vat}


BREAKDOWN_LABELS = {'items': 'รวมรายการอุปกรณ์', 'contingency': 'ค่าเผื่อ', 'labor': 'ค่าแรงประกอบ',
                    'shipping': 'ค่าขนส่ง', 'discount': 'ส่วนลด'}


def vat_label(settings: dict | None = None) -> str:
    s = validate_settings(settings)
    return f"VAT {s['vat_percent']:g}%" if s['vat_enabled'] else 'ไม่คิด VAT'
