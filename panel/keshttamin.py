"""ارسال فروش چکیِ تاییدشده به سایت کشت‌تأمین.

فقط حجم معامله، تعداد چک‌ها و سررسیدها فرستاده می‌شود.
اعلام فروش فقط وقتی تایید می‌شود که پاسخ ok=true باشد.
"""
import json
from datetime import date, datetime

import requests
from django.conf import settings

CHECK_SALE_URL = 'https://keshttamin.ir/api/keshtyar/check-sales'
_FAIL = 'ارسال به کشت‌تأمین ناموفق بود.'


class KeshttaminError(Exception):
    """ارسال به کشت‌تأمین انجام نشد یا پذیرفته نشد."""


def is_check_sale(req):
    """فروش قسطی در این سامانه با چک ثبت می‌شود."""
    return req.settlement == 'قسطی' or bool(req.checks)


def _due(value):
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    return str(value or '')[:10]


def sale_payload(req):
    """حجم معامله، تعداد چک‌ها و سررسید هر چک."""
    checks = list(req.checks or [])
    return {
        'sale_amount': int(req.sale_amount or 0),
        'check_count': len(checks),
        'check_due_dates': [_due(row.get('due_on')) for row in checks],
    }


def _response_body(response):
    text = getattr(response, 'text', None)
    if text is None:
        content = getattr(response, 'content', b'')
        if isinstance(content, bytes):
            text = content.decode('utf-8', errors='replace')
        else:
            text = str(content or '')
    text = str(text or '').strip()
    if len(text) > 4000:
        return text[:4000] + '…'
    return text


def _print_response(response):
    print(
        f'keshttamin response status={getattr(response, "status_code", "?")} '
        f'body={_response_body(response) or "(empty)"}',
        flush=True,
    )


def send_check_sale(payload):
    """POST به کشت‌تأمین. فقط پاسخ JSON با ok=true موفق است."""
    key = (getattr(settings, 'KESHTTAMIN_API_KEY', '') or '').strip().strip("'\"")
    timeout = int(getattr(settings, 'KESHTTAMIN_TIMEOUT', 20) or 20)
    if not key:
        print('keshttamin request failed: api key is not set', flush=True)
        raise KeshttaminError(_FAIL)
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
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
    except requests.RequestException as exc:
        print(f'keshttamin request failed: {exc}', flush=True)
        raise KeshttaminError(_FAIL)
    _print_response(response)
    if response.status_code < 200 or response.status_code >= 300:
        raise KeshttaminError(_FAIL)
    try:
        parsed = response.json()
    except ValueError:
        raise KeshttaminError(_FAIL)
    if not isinstance(parsed, dict) or parsed.get('ok') is not True:
        raise KeshttaminError(_FAIL)
    return parsed
