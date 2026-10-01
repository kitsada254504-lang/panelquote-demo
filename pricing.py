"""Price provenance is independent of supplier confirmation."""
from datetime import date
from decimal import Decimal
import pandas as pd
from quote_excel import money

PRICE_STATUSES = {'pending', 'reference', 'confirmed', 'expired'}


def price_item(part, markup, today=None, markup_mode='markup'):
    today = today or date.today()
    def numeric(value):
        if value is None or pd.isna(value) or value == '':
            return None
        return money(value)
    cost, sell = numeric(part.get('cost_price')), numeric(part.get('sell_price'))
    rate = Decimal(str(markup))
    if not rate.is_finite() or rate < 0:
        raise ValueError('Invalid markup.')
    if sell is not None and sell > 0:
        price, source = sell, 'sell_price'
    elif cost is not None and cost > 0:
        from pricing_settings import apply_markup
        price, source = apply_markup(cost, {'markup_percent': rate, 'markup_mode': markup_mode}), 'cost_markup'
    else:
        price, source = None, 'pending'
    status = part.get('price_status')
    if status not in PRICE_STATUSES:
        status = 'reference' if price is not None else 'pending'
    expiry = part.get('price_valid_until')
    if expiry is not None and not pd.isna(expiry) and str(expiry).strip():
        if date.fromisoformat(str(expiry)) < today:
            status = 'expired'
    if price is None:
        status = 'pending'
    return {'unit_price': price, 'price_source': source, 'price_status': status,
            'cost_price': cost if cost and cost > 0 else None, 'sell_price': sell,
            'markup_percent': rate, 'price_valid_until': str(expiry) if expiry is not None and not pd.isna(expiry) else None}
