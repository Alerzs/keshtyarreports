from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from django import template

from ..credit import check_status_tone
from ..jalali import format_jalali, to_fa_digits

register = template.Library()


@register.filter
def fa(value):
    return to_fa_digits(value)


@register.filter
def toman(value):
    try:
        number = int(round(float(value or 0)))
    except (TypeError, ValueError):
        return '۰'
    text = f'{number:,}'.replace(',', '٬')
    return to_fa_digits(text)


def _scaled(number, places):
    rounded = number.quantize(places, rounding=ROUND_HALF_UP)
    body = f'{rounded:,f}'
    if '.' in body:
        body = body.rstrip('0').rstrip('.')
    return body.replace(',', '٬').replace('.', '٫')


@register.filter
def money(value, unit='auto'):
    """مبلغ تومان را، اگر به اندازه کافی بزرگ باشد، به میلیون یا میلیارد برمی‌گرداند."""
    try:
        number = Decimal(str(value if value not in (None, '') else 0))
    except (ArithmeticError, ValueError, TypeError):
        return '۰'
    chosen = unit if unit in {'million', 'billion', 'toman'} else 'auto'
    abs_n = abs(number)
    if chosen == 'auto':
        if abs_n >= Decimal('1000000000'):
            chosen = 'billion'
        elif abs_n >= Decimal('1000000'):
            chosen = 'million'
        else:
            chosen = 'toman'
    if chosen == 'toman':
        return toman(number) + ' تومان'
    scaled = number / (Decimal('1000000000') if chosen == 'billion' else Decimal('1000000'))
    label = 'میلیارد' if chosen == 'billion' else 'میلیون'
    abs_scaled = abs(scaled)
    if abs_scaled == 0:
        body = '0'
    elif abs_scaled >= 100:
        body = _scaled(scaled, Decimal('0.1'))
    elif abs_scaled >= 1:
        body = _scaled(scaled, Decimal('0.01'))
    elif abs_scaled >= Decimal('0.01'):
        body = _scaled(scaled, Decimal('0.001'))
    elif abs_scaled >= Decimal('0.001'):
        body = _scaled(scaled, Decimal('0.0001'))
    else:
        body = _scaled(scaled, Decimal('0.000001'))
    return to_fa_digits(body) + ' ' + label


@register.filter
def jdate(value):
    return format_jalali(value)


@register.filter
def input_date(value):
    """تاریخ قابل‌نمایش در فیلد فرم؛ متن واردشده را اگر تاریخ نباشد نگه می‌دارد."""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        text = format_jalali(value)
        return '' if text == '—' else text
    return '' if value is None else str(value)


@register.filter
def jdt(value):
    return format_jalali(value, with_time=True)


@register.filter
def rate_pct(value):
    try:
        return to_fa_digits(int(round(float(value) * 100)))
    except (TypeError, ValueError):
        return '۰'


@register.filter
def get_item(mapping, key):
    if not mapping:
        return ''
    return mapping.get(key, '')


@register.filter
def check_tone(status):
    return check_status_tone(status)


@register.filter
def initial(value):
    text = (value or '').strip()
    return text[:1] or '؟'
