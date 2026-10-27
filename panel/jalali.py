"""تبدیل تاریخ میلادی و جلالی، بدون وابستگی اضافه.

الگوریتم همان تبدیل رایج تقویم رسمی ایران است تا تاریخ فاکتور
در فرم «۱۴۰۵/۰۶/۱۲» بماند و در پایگاه به‌صورت میلادی ذخیره شود.
"""
import re
from datetime import date, datetime

_FA = '۰۱۲۳۴۵۶۷۸۹'
_AR = '٠١٢٣٤٥٦٧٨٩'


def to_en_digits(value):
    s = str(value or '')
    for i, ch in enumerate(_FA):
        s = s.replace(ch, str(i))
    for i, ch in enumerate(_AR):
        s = s.replace(ch, str(i))
    return s


def to_fa_digits(value):
    return ''.join(_FA[int(ch)] if ch.isdigit() else ch for ch in str(value))


def gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        - 80
        + gd
        + g_d_m[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def jalali_to_gregorian(jy, jm, jd):
    jy += 1595
    days = -355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += ((jm - 7) * 30) + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)
    months = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    while gm <= 12 and gd > months[gm]:
        gd -= months[gm]
        gm += 1
    return gy, gm, gd


def format_jalali(value, with_time=False):
    if not value:
        return '—'
    if isinstance(value, datetime):
        d = value.date()
        clock = value.strftime('%H:%M')
    elif isinstance(value, date):
        d = value
        clock = ''
    else:
        return '—'
    jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
    text = to_fa_digits(f'{jy:04d}/{jm:02d}/{jd:02d}')
    if with_time and clock:
        text = f'{text} {to_fa_digits(clock)}'
    return text


def parse_jalali(value):
    raw = to_en_digits(value).strip().replace('-', '/').replace('.', '/')
    match = re.fullmatch(r'(\d{4})/(\d{1,2})/(\d{1,2})', raw)
    if not match:
        return None
    jy, jm, jd = (int(part) for part in match.groups())
    if not (1 <= jm <= 12 and 1 <= jd <= 31):
        return None
    if jm > 6 and jd > 30:
        return None
    try:
        gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
        return date(gy, gm, gd)
    except ValueError:
        return None


JALALI_MONTHS = (
    'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
    'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند',
)


def month_key(value):
    jy, jm, _jd = gregorian_to_jalali(value.year, value.month, value.day)
    return f'{jy:04d}/{jm:02d}'


def month_label(key):
    return to_fa_digits(key)


def _month_index(key):
    year, month = str(key).split('/')
    index = int(month) - 1
    if not (0 <= index < 12):
        return None, year
    return index, year


def month_title(key):
    """برچسب ماه جلالی، مثل «مهر ۱۴۰۵»."""
    index, year = _month_index(key)
    if index is None:
        return month_label(key)
    return f'{JALALI_MONTHS[index]} {to_fa_digits(year)}'


def month_axis_label(key):
    """برچسب کوتاه محور نمودار، مثل «اردیبهشت ۰۵»."""
    index, year = _month_index(key)
    if index is None:
        return month_label(key)
    return f'{JALALI_MONTHS[index]} {to_fa_digits(str(year)[-2:])}'


def jalali_month_days(jy, jm):
    """تعداد روز ماه جلالی. اسفند در سال کبیسه ۳۰ روز است."""
    if not (1 <= jm <= 12):
        return 0
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    gy, gm, gd = jalali_to_gregorian(jy, 12, 30)
    return 30 if gregorian_to_jalali(gy, gm, gd) == (jy, 12, 30) else 29


def jalali_week_index(jy, jm, jd):
    """جای روز در هفته‌ای که از شنبه شروع می‌شود."""
    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
    return (date(gy, gm, gd).weekday() + 2) % 7


def month_span(key):
    """بازه میلادی یک ماه جلالی، از اول ماه تا پیش از ماه بعد."""
    parts = str(key or '').split('/')
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    jy, jm = int(parts[0]), int(parts[1])
    if not (1 <= jm <= 12):
        return None
    start = date(*jalali_to_gregorian(jy, jm, 1))
    if jm == 12:
        end = date(*jalali_to_gregorian(jy + 1, 1, 1))
    else:
        end = date(*jalali_to_gregorian(jy, jm + 1, 1))
    return start, end


def format_day_month(value):
    """برچسب روز و ماه جلالی، مثل «۲۰ مهر»."""
    if isinstance(value, datetime):
        d = value.date()
    elif isinstance(value, date):
        d = value
    else:
        return '—'
    _jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
    if not (1 <= jm <= 12):
        return '—'
    return f'{to_fa_digits(jd)} {JALALI_MONTHS[jm - 1]}'


def parse_money(value):
    raw = to_en_digits(value)
    raw = re.sub(r'[^\d.-]', '', raw)
    if raw in {'', '-', '.', '-.'}:
        return 0
    try:
        return int(round(float(raw)))
    except ValueError:
        return 0
