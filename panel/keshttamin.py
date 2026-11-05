"""ارسال فروش چکیِ تاییدشده به سایت کشت‌تأمین.

قرارداد درخواست و پاسخ در keshttamin_check_sale_api.txt است.
اعلام فروش فقط وقتی تایید می‌شود که این ارسال پاسخ موفق برگرداند.
"""
import json
import logging
from datetime import date, datetime
from decimal import Decimal

import requests
from django.conf import settings

from .jalali import format_jalali

log = logging.getLogger(__name__)

CHECK_SALE_URL = 'https://keshttamin.ir/api/keshtyar/check-sales'


class KeshttaminError(Exception):
    """ارسال به کشت‌تأمین انجام نشد یا پذیرفته نشد."""


def is_check_sale(req):
    """فروش قسطی در این سامانه با چک ثبت می‌شود."""
    return req.settlement == 'قسطی' or bool(req.checks)


def _iso(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or '')[:10]
    return text


def _jalali(value):
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return format_jalali(value)
    text = str(value or '')[:10]
    if not text:
        return ''
    try:
        return format_jalali(date.fromisoformat(text))
    except ValueError:
        return ''


def _money(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _qty(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_ready(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _operator(user):
    if user is None:
        return None
    return {
        'id': user.pk,
        'username': user.username,
        'full_name': user.full_name or '',
        'report_name': user.report_name(),
    }


def sale_payload(req, invoice):
    """همه اطلاعات فروش، برای بدنه JSON ارسال."""
    saved_lines = list(invoice.lines.all())
    saved_payments = list(invoice.payments.all())
    saved_checks = list(invoice.checks.all())
    lines = []
    for idx, raw in enumerate(req.lines or []):
        row = {
            'product_name': raw.get('product_name') or '',
            'qty': _qty(raw.get('qty')),
            'unit_price': _money(raw.get('unit_price')),
            'unit_cost': _money(raw.get('unit_cost')),
        }
        if idx < len(saved_lines):
            row['id'] = saved_lines[idx].pk
        lines.append(row)
    payments = []
    for idx, raw in enumerate(req.payments or []):
        paid_on = raw.get('paid_on')
        row = {
            'amount': _money(raw.get('amount')),
            'method': raw.get('method') or '',
            'paid_on': _iso(paid_on),
            'paid_on_jalali': _jalali(paid_on),
            'note': raw.get('note') or '',
        }
        if idx < len(saved_payments):
            row['id'] = saved_payments[idx].pk
        payments.append(row)
    checks = []
    for idx, raw in enumerate(req.checks or []):
        due_on = raw.get('due_on')
        row = {
            'number': raw.get('number') or '',
            'amount': _money(raw.get('amount')),
            'bank': raw.get('bank') or '',
            'status': raw.get('status') or '',
            'due_on': _iso(due_on),
            'due_on_jalali': _jalali(due_on),
        }
        if idx < len(saved_checks):
            row['id'] = saved_checks[idx].pk
            row['status'] = saved_checks[idx].status or row['status']
        checks.append(row)
    customer = invoice.customer
    payload = {
        'source': 'keshtyar',
        'event': 'check_sale_approved',
        'sale_request_id': req.pk,
        'sold_on': _iso(req.sold_on),
        'sold_on_jalali': _jalali(req.sold_on),
        'settlement': req.settlement,
        'note': req.note or '',
        'review_note': req.review_note or '',
        'reviewed_at': _iso(req.reviewed_at),
        'seller': _operator(req.seller),
        'reviewer': _operator(req.reviewed_by),
        'customer': {
            'id': customer.pk,
            'name': req.customer_name,
            'phone': req.phone,
            'city': req.city,
            'address': req.address,
            'customer_type': req.customer_type,
            'credit': req.credit or {},
        },
        'invoice': {
            'id': invoice.pk,
            'number': invoice.number,
            'status': invoice.status,
            'settlement': invoice.settlement,
            'sold_on': _iso(invoice.sold_on),
            'sold_on_jalali': _jalali(invoice.sold_on),
            'purchase_amount': _money(invoice.purchase_amount),
            'sale_amount': _money(req.sale_amount),
            'cost_amount': _money(req.cost_amount),
            'note': invoice.note or '',
        },
        'lines': lines,
        'payments': payments,
        'checks': checks,
        'guarantees': req.guarantees or [],
        'references': req.references or [],
        'docs': req.docs or [],
        'warnings': req.warnings or [],
        'files': [
            {'name': doc.name or '', 'uploaded_at': _iso(doc.uploaded_at)}
            for doc in req.files.all()
        ],
    }
    return _json_ready(payload)


def _error_text(response):
    """متن error پاسخ کشت‌تأمین، اگر JSON باشد."""
    try:
        parsed = response.json()
    except ValueError:
        return ''
    if not isinstance(parsed, dict):
        return ''
    detail = str(parsed.get('error') or parsed.get('message') or '').strip()
    if not detail:
        return ''
    return ' ' + detail[:180]


def send_check_sale(payload):
    """POST به کشت‌تأمین. فقط پاسخ JSON با ok=true موفق است."""
    key = (getattr(settings, 'KESHTTAMIN_API_KEY', '') or '').strip().strip("'\"")
    timeout = int(getattr(settings, 'KESHTTAMIN_TIMEOUT', 20) or 20)
    if not key:
        raise KeshttaminError('کلید اتصال کشت‌تأمین (KESHTTAMIN_API_KEY) تنظیم نشده است.')
    body = json.dumps(_json_ready(payload), ensure_ascii=False).encode('utf-8')
    headers = {
        'Content-Type': 'application/json; charset=utf-8',
        'Accept': 'application/json',
        'X-Api-Key': key,
        'User-Agent': 'Keshtyar/check-sale',
    }
    try:
        response = requests.post(
            CHECK_SALE_URL,
            data=body,
            headers=headers,
            timeout=(5, timeout),
            allow_redirects=False,
        )
    except requests.RequestException:
        log.warning('keshttamin connection failed for sale_request_id=%s', payload.get('sale_request_id'))
        raise KeshttaminError('ارتباط با کشت‌تأمین برقرار نشد.')
    if response.status_code < 200 or response.status_code >= 300:
        detail = _error_text(response)
        log.warning(
            'keshttamin rejected sale_request_id=%s status=%s',
            payload.get('sale_request_id'),
            response.status_code,
        )
        raise KeshttaminError(f'کشت‌تأمین این فروش را نپذیرفت (کد {response.status_code}).{detail}')
    try:
        parsed = response.json()
    except ValueError:
        raise KeshttaminError('پاسخ کشت‌تأمین قابل خواندن نبود.')
    if not isinstance(parsed, dict) or parsed.get('ok') is not True:
        detail = ''
        if isinstance(parsed, dict):
            detail = str(parsed.get('error') or parsed.get('message') or '').strip()
        if detail:
            detail = ' ' + detail[:180]
        raise KeshttaminError(f'کشت‌تأمین این فروش را تایید نکرد.{detail}')
    return parsed
