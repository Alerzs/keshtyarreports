import os
import re
from datetime import date

from django.contrib import messages
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .access import seller_choices, visible_customers, visible_requests
from .backup import take_snapshot
from .credit import (
    BANKS, CHECK_STATES, CREDIT_DOCS, CREDIT_SCHEMA, CUST_TYPES, GUARANTEE_TYPES,
    PAY_METHODS, REFERENCE_RELATIONS, SETTLEMENTS,
)
from .decorators import page_required
from .jalali import format_jalali, parse_jalali, parse_money, to_en_digits
from .models import (
    Check, Customer, CustomerDocument, Invoice, InvoiceLine, Operator, Payment, SaleDocument, SaleRequest,
)
from .perms import can_review


def _digits(value):
    return re.sub(r'\D', '', to_en_digits(value or ''))


_UPLOAD_LIMIT = 8 * 1024 * 1024
_UPLOAD_TYPES = {'.pdf', '.jpg', '.jpeg', '.png', '.webp'}


def _store_uploads(request, sale):
    removed = [int(pk) for pk in request.POST.getlist('remove_file') if str(pk).isdigit()]
    if removed:
        sale.files.filter(pk__in=removed).delete()
    for upload in request.FILES.getlist('uploads'):
        ext = os.path.splitext(upload.name)[1].lower()
        if ext not in _UPLOAD_TYPES:
            messages.warning(request, f'«{upload.name}» ذخیره نشد. فقط تصویر یا PDF مجاز است.')
            continue
        if upload.size > _UPLOAD_LIMIT:
            messages.warning(request, f'«{upload.name}» ذخیره نشد. هر فایل حداکثر ۸ مگابایت است.')
            continue
        SaleDocument.objects.create(request=sale, file=upload, name=upload.name[:160])


def _copy_sale_files(sale, customer):
    for doc in sale.files.all():
        doc.file.open('rb')
        try:
            payload = doc.file.read()
        finally:
            doc.file.close()
        CustomerDocument.objects.create(
            customer=customer,
            doc_type=(doc.name or 'مدرک فروش')[:80],
            file=ContentFile(payload, name=os.path.basename(doc.file.name)),
        )


class _FormEntry:
    """نمای فرم بعد از خطای اعتبارسنجی، بدون ذخیره در پایگاه."""

    def __init__(self, **fields):
        self.__dict__.update(fields)


class _FormRow:
    def __init__(self, data):
        self.__dict__.update(data)


def _posted(request, name):
    return request.POST.getlist(name)


def _cell(values, idx):
    return values[idx] if idx < len(values) else ''


def _entry_from_post(request, seller, credit, docs):
    """همان چیزی که کاربر فرستاده، حتی اگر هنوز برای ذخیره کامل نباشد."""
    products, qtys, prices, costs = (
        _posted(request, name) for name in ('product', 'qty', 'unit_price', 'unit_cost')
    )
    line_count = max(len(products), len(qtys), len(prices), len(costs))
    lines = [
        _FormRow({
            'product_name': _cell(products, idx).strip(),
            'qty': _cell(qtys, idx),
            'unit_price': _cell(prices, idx),
            'unit_cost': _cell(costs, idx),
        })
        for idx in range(line_count)
    ]
    amounts, dates, methods, notes = (
        _posted(request, name) for name in ('pay_amount', 'pay_date', 'pay_method', 'pay_note')
    )
    pay_count = max(len(amounts), len(dates), len(methods), len(notes))
    payments = [
        _FormRow({
            'amount': _cell(amounts, idx),
            'paid_on': _cell(dates, idx),
            'method': _cell(methods, idx),
            'note': _cell(notes, idx),
        })
        for idx in range(pay_count)
    ]
    numbers, chk_amounts, chk_dates, banks = (
        _posted(request, name) for name in ('chk_number', 'chk_amount', 'chk_date', 'chk_bank')
    )
    chk_count = max(len(numbers), len(chk_amounts), len(chk_dates), len(banks))
    checks = [
        _FormRow({
            'number': _cell(numbers, idx),
            'amount': _cell(chk_amounts, idx),
            'due_on': _cell(chk_dates, idx),
            'bank': _cell(banks, idx),
        })
        for idx in range(chk_count)
    ]
    g_types, g_holders, g_amounts = (
        _posted(request, name) for name in ('guar_type', 'guar_holder', 'guar_amount')
    )
    g_count = max(len(g_types), len(g_holders), len(g_amounts))
    guarantees = [
        {'type': _cell(g_types, idx), 'holder': _cell(g_holders, idx), 'amount': _cell(g_amounts, idx)}
        for idx in range(g_count)
    ]
    r_names, r_rels, r_phones = (
        _posted(request, name) for name in ('ref_name', 'ref_rel', 'ref_phone')
    )
    r_count = max(len(r_names), len(r_rels), len(r_phones))
    references = [
        {'name': _cell(r_names, idx), 'relation': _cell(r_rels, idx), 'phone': _cell(r_phones, idx)}
        for idx in range(r_count)
    ]
    return _FormEntry(
        seller_id=seller.pk if seller else None,
        sold_on=request.POST.get('sold_on', ''),
        settlement=request.POST.get('settlement', ''),
        customer_type=request.POST.get('customer_type', ''),
        phone=request.POST.get('phone', ''),
        city=request.POST.get('city', ''),
        address=request.POST.get('address', ''),
        note=request.POST.get('note', ''),
        line_list=lines,
        payment_list=payments,
        check_list=checks,
        credit=credit,
        guarantees=guarantees,
        references=references,
        docs=docs,
    )


def _rows_from_post(request):
    lines, payments, checks = [], [], []
    products = request.POST.getlist('product')
    qtys = request.POST.getlist('qty')
    prices = request.POST.getlist('unit_price')
    costs = request.POST.getlist('unit_cost')
    for idx, name in enumerate(products):
        name = name.strip()
        price = parse_money(prices[idx] if idx < len(prices) else 0)
        cost = parse_money(costs[idx] if idx < len(costs) else 0)
        if not name and price <= 0:
            continue
        raw_qty = to_en_digits(qtys[idx] if idx < len(qtys) else '')
        raw_qty = raw_qty.replace('٬', '').replace(',', '').replace('٫', '.')
        raw_qty = re.sub(r'[^\d.]', '', raw_qty)
        try:
            qty_num = float(raw_qty) if raw_qty else 0
        except ValueError:
            qty_num = 0
        if qty_num < 1:
            qty_num = 1
        lines.append({'product_name': name, 'qty': qty_num, 'unit_price': price, 'unit_cost': cost})

    for idx, amount in enumerate(request.POST.getlist('pay_amount')):
        value = parse_money(amount)
        if value <= 0:
            continue
        methods = request.POST.getlist('pay_method')
        dates = request.POST.getlist('pay_date')
        notes = request.POST.getlist('pay_note')
        payments.append({
            'amount': value,
            'method': methods[idx] if idx < len(methods) else PAY_METHODS[0],
            'paid_on': parse_jalali(dates[idx]) if idx < len(dates) else None,
            'note': notes[idx] if idx < len(notes) else '',
        })

    for idx, amount in enumerate(request.POST.getlist('chk_amount')):
        value = parse_money(amount)
        if value <= 0:
            continue
        numbers = request.POST.getlist('chk_number')
        dates = request.POST.getlist('chk_date')
        banks = request.POST.getlist('chk_bank')
        checks.append({
            'amount': value,
            'number': numbers[idx] if idx < len(numbers) else '',
            'due_on': parse_jalali(dates[idx]) if idx < len(dates) else None,
            'bank': banks[idx] if idx < len(banks) else '',
            'status': 'در جریان',
        })
    return lines, payments, checks


def _credit_from_post(request):
    data, warnings = {}, []
    for group in CREDIT_SCHEMA:
        for field in group['fields']:
            raw = request.POST.get(f"c_{field['k']}", '').strip()
            if field['type'] == 'digits':
                raw = _digits(raw)[:field.get('max', 30)]
            elif field['type'] in {'money', 'int'}:
                number = parse_money(raw)
                raw = str(number) if number else ''
            elif field['type'] == 'select' and raw not in field.get('opts', []):
                raw = ''
            if field['k'] == 'nationalId' and raw and (len(raw) != 10):
                warnings.append('کد ملی باید ۱۰ رقم باشد.')
            data[field['k']] = raw
    guarantees = []
    types = request.POST.getlist('guar_type')
    holders = request.POST.getlist('guar_holder')
    amounts = request.POST.getlist('guar_amount')
    for idx, kind in enumerate(types):
        holder = holders[idx] if idx < len(holders) else ''
        amount = parse_money(amounts[idx]) if idx < len(amounts) else 0
        if not kind and not holder and amount <= 0:
            continue
        guarantees.append({'type': kind or 'سایر', 'holder': holder, 'amount': amount})
    references = []
    names = request.POST.getlist('ref_name')
    rels = request.POST.getlist('ref_rel')
    phones = request.POST.getlist('ref_phone')
    for idx, name in enumerate(names):
        phone = _digits(phones[idx]) if idx < len(phones) else ''
        if not name.strip() and not phone:
            continue
        references.append({
            'name': name.strip(),
            'relation': rels[idx] if idx < len(rels) else 'سایر',
            'phone': phone[:11],
        })
    docs = [doc for doc in request.POST.getlist('doc') if doc in CREDIT_DOCS]
    return data, guarantees, references, docs, warnings


def _validate(seller, sold_on, settlement, customer_type, name, phone, city, address, lines, checks, defer):
    errors = []
    if seller is None:
        errors.append('فروشنده را انتخاب کنید.')
    if not sold_on:
        errors.append('تاریخ فروش باید مثل ۱۴۰۵/۰۶/۱۲ باشد.')
    if settlement not in SETTLEMENTS:
        errors.append('نوع تسویه معتبر نیست.')
    if customer_type not in CUST_TYPES:
        errors.append('نوع مشتری معتبر نیست.')
    if not name:
        errors.append('نام مشتری ضروری است.')
    if not re.fullmatch(r'09\d{9}', phone or ''):
        errors.append('شماره تماس باید ۱۱ رقم و با ۰۹ شروع شود.')
    if not city:
        errors.append('شهر / استان ضروری است.')
    if not address:
        errors.append('آدرس ضروری است.')
    good_lines = [ln for ln in lines if ln['product_name'] and ln['unit_price'] > 0 and ln['qty'] > 0]
    if not good_lines:
        errors.append('حداقل یک قلم فاکتور با نام، تعداد و قیمت لازم است.')
    if settlement == 'قسطی' and not checks:
        errors.append('فروش قسطی حداقل یک چک می‌خواهد.')
    for chk in checks:
        if not chk['due_on']:
            errors.append('تاریخ سررسید چک باید پر شود.')
            break
    sale = sum(int(ln['qty'] * ln['unit_price']) for ln in good_lines)
    if sale <= 0:
        errors.append('جمع فاکتور صفر است.')
    return errors, good_lines, bool(errors and defer)


def _saved_date(value):
    if isinstance(value, date):
        return value
    text = str(value or '')[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return parse_jalali(text)


def _as_float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def request_gaps(req):
    """نواقصی که باعث شده اعلام فروش قابل تایید نباشد."""
    if req is None or not req.incomplete:
        return []
    lines = []
    for raw in req.lines or []:
        lines.append({
            'product_name': str(raw.get('product_name') or '').strip(),
            'qty': _as_float(raw.get('qty')),
            'unit_price': _as_float(raw.get('unit_price')),
        })
    checks = [{'due_on': _saved_date(raw.get('due_on'))} for raw in (req.checks or [])]
    errors, _good, _flag = _validate(
        req.seller, req.sold_on, req.settlement, req.customer_type,
        req.customer_name, req.phone, req.city, req.address, lines, checks, True,
    )
    line_error = 'حداقل یک قلم فاکتور با نام، تعداد و قیمت لازم است.'
    if line_error in errors:
        errors = [err for err in errors if err != 'جمع فاکتور صفر است.']
    return errors


@page_required('requests')
def request_list(request):
    status = request.GET.get('status') or 'all'
    qs = visible_requests(request.user)
    counts = {
        'all': qs.count(),
        'pending': qs.filter(status='pending').count(),
        'approved': qs.filter(status='approved').count(),
        'rejected': qs.filter(status='rejected').count(),
        'incomplete': qs.filter(incomplete=True).count(),
    }
    if status == 'incomplete':
        qs = qs.filter(incomplete=True)
    elif status in {'pending', 'approved', 'rejected'}:
        qs = qs.filter(status=status)
    return render(request, 'panel/requests.html', {
        'requests': qs,
        'counts': counts,
        'status': status,
        'can_review': can_review(request.user),
    })


@require_http_methods(['GET', 'POST'])
@page_required('requests')
def request_form(request, pk=None):
    current = None
    if pk:
        current = get_object_or_404(visible_requests(request.user), pk=pk)
        if current.status != 'pending' and not can_review(request.user):
            messages.error(request, 'فقط درخواست در انتظار قابل ویرایش است.')
            return redirect('request_detail', pk=pk)
    sellers = seller_choices(request.user)
    if request.method == 'POST':
        return _save_request(request, current, sellers)
    prefill = {}
    autofill = False
    if request.GET.get('customer'):
        customer = visible_customers(request.user).filter(pk=request.GET['customer']).first()
        if customer:
            prefill = {
                'customer_id': customer.pk,
                'customer_name': customer.name, 'phone': customer.phone,
                'city': customer.city, 'address': customer.address,
                'customer_type': customer.customer_type,
            }
            autofill = current is None
    gaps = request_gaps(current)
    warnings = list(current.warnings or []) if current else []
    return render(
        request, 'panel/request_form.html',
        _form_context(request, current, sellers, prefill, gaps, warnings, autofill_credit=autofill),
    )


def _credit_snapshot(row):
    credit = row.get('credit') or {}
    if any(str(value or '').strip() for value in credit.values()):
        return True
    return bool(row.get('guarantees') or row.get('references') or row.get('docs'))


def _customer_choices(user):
    """مشتری‌های قابل‌انتخاب، همراه پرونده اعتبار برای پر شدن خودکار فرم."""
    rows = list(visible_customers(user).order_by('name').values(
        'id', 'name', 'phone', 'city', 'address', 'customer_type', 'dossier',
    ))
    names = [row['name'] for row in rows]
    richest = {}
    if names:
        history = (
            visible_requests(user)
            .filter(customer_name__in=names)
            .order_by('-id')
            .values('customer_name', 'credit', 'guarantees', 'references', 'docs')
        )
        for req in history:
            name = req['customer_name']
            if name in richest:
                continue
            if _credit_snapshot(req):
                richest[name] = req
    ids = [row['id'] for row in rows]
    file_docs = {}
    if ids:
        for item in CustomerDocument.objects.filter(customer_id__in=ids).values('customer_id', 'doc_type'):
            if item['doc_type'] not in CREDIT_DOCS:
                continue
            bucket = file_docs.setdefault(item['customer_id'], [])
            if item['doc_type'] not in bucket:
                bucket.append(item['doc_type'])
    payload = []
    for row in rows:
        snap = richest.get(row['name']) or {}
        credit = {}
        for key, value in (snap.get('credit') or {}).items():
            if str(value or '').strip():
                credit[key] = value
        for key, value in (row.get('dossier') or {}).items():
            if str(value or '').strip():
                credit[key] = value
        docs = []
        for doc in list(snap.get('docs') or []) + file_docs.get(row['id'], []):
            if doc in CREDIT_DOCS and doc not in docs:
                docs.append(doc)
        payload.append({
            'id': row['id'],
            'name': row['name'],
            'phone': row['phone'] or '',
            'city': row['city'] or '',
            'address': row['address'] or '',
            'customer_type': row['customer_type'] or '',
            'credit': credit,
            'guarantees': snap.get('guarantees') or [],
            'references': snap.get('references') or [],
            'docs': docs,
        })
    return payload


def _product_choices(current=None, extra_names=()):
    names = set()
    for name in InvoiceLine.objects.values_list('product_name', flat=True):
        text = str(name or '').strip()
        if text:
            names.add(text)
    for blob in SaleRequest.objects.values_list('lines', flat=True):
        if not isinstance(blob, list):
            continue
        for raw in blob:
            if not isinstance(raw, dict):
                continue
            text = str(raw.get('product_name') or '').strip()
            if text:
                names.add(text)
    if current is not None:
        for line in current.line_list:
            text = str(getattr(line, 'product_name', '') or '').strip()
            if text:
                names.add(text)
    for name in extra_names:
        text = str(name or '').strip()
        if text:
            names.add(text)
    return sorted(names)


def _form_context(request, current, sellers, prefill, errors, warnings, autofill_credit=False, entry=None):
    filled = {
        'seller_id': None, 'customer_id': None, 'customer_name': '', 'phone': '', 'city': '',
        'address': '', 'customer_type': '', 'settlement': '', 'note': '',
    }
    filled.update(prefill or {})
    customers = _customer_choices(request.user)
    if prefill and 'customer_name' in prefill:
        name = prefill.get('customer_name') or ''
    elif current is not None:
        name = current.customer_name or ''
    else:
        name = filled.get('customer_name') or ''
    selected = filled.get('customer_id') or None
    if not selected and name:
        for row in customers:
            if row['name'] == name:
                selected = row['id']
                break
    filled['customer_name'] = name
    filled['customer_id'] = selected or ''
    shown = current if entry is None else entry
    extra_products = []
    if shown is not None:
        for line in shown.line_list:
            extra_products.append(getattr(line, 'product_name', ''))
    lock_seller = request.user.role in {'mentor', 'specialist'}
    if lock_seller:
        sellers = [request.user]
        filled['seller_id'] = request.user.pk
    return {
        'current': current,
        'entry': shown,
        'sellers': sellers,
        'lock_seller': lock_seller,
        'prefill': filled,
        'errors': errors,
        'warnings': warnings,
        'schema': CREDIT_SCHEMA,
        'settlements': SETTLEMENTS,
        'cust_types': CUST_TYPES,
        'pay_methods': PAY_METHODS,
        'check_states': CHECK_STATES,
        'guarantees': GUARANTEE_TYPES,
        'relations': REFERENCE_RELATIONS,
        'docs': CREDIT_DOCS,
        'banks': BANKS,
        'customers': customers,
        'products': _product_choices(current, extra_products),
        'autofill_credit': autofill_credit and bool(selected),
    }


def _next_invoice_number():
    """شماره پنج‌رقمی بعدی، یکی بیشتر از بزرگ‌ترین فاکتور عددی موجود."""
    highest = 0
    for raw in Invoice.objects.values_list('number', flat=True):
        text = to_en_digits(str(raw or '')).strip()
        if text.isdigit():
            highest = max(highest, int(text))
    return f'{highest + 1:05d}'


def _seller_from_post(request, sellers):
    if request.user.role in {'mentor', 'specialist'}:
        return request.user
    raw = request.POST.get('seller', '').strip()
    if not raw.isdigit():
        return None
    allowed = {person.pk: person for person in sellers}
    seller = allowed.get(int(raw))
    if seller is None and can_review(request.user):
        seller = Operator.objects.filter(pk=int(raw), is_active=True).first()
    return seller


def _save_request(request, current, sellers):
    seller = _seller_from_post(request, sellers)
    sold_on = parse_jalali(request.POST.get('sold_on', ''))
    settlement = request.POST.get('settlement', '')
    customer_type = request.POST.get('customer_type', '')
    name = request.POST.get('customer_name', '').strip()
    phone = _digits(request.POST.get('phone', ''))
    city = request.POST.get('city', '').strip()
    address = request.POST.get('address', '').strip()
    defer = request.POST.get('defer') == '1'
    lines, payments, checks = _rows_from_post(request)
    credit, guarantees, references, docs, warnings = _credit_from_post(request)
    errors, good_lines, incomplete = _validate(
        seller, sold_on, settlement, customer_type, name, phone, city, address, lines, checks, defer,
    )
    if errors and not defer:
        messages.error(request, 'فرم کامل نیست.')
        if current is not None:
            _store_uploads(request, current)
        elif request.FILES.getlist('uploads'):
            messages.warning(request, 'مدارک انتخاب‌شده ذخیره نشد. بعد از کامل شدن فرم دوباره آن‌ها را انتخاب کنید.')
        prefill = {
            'seller_id': seller.pk if seller else None, 'customer_name': name, 'phone': phone, 'city': city,
            'address': address, 'customer_type': customer_type, 'settlement': settlement,
            'note': request.POST.get('note', ''),
        }
        entry = _entry_from_post(request, seller, credit, docs)
        return render(
            request, 'panel/request_form.html',
            _form_context(request, current, sellers, prefill, errors, warnings, entry=entry),
        )
    if seller is None:
        seller = request.user
    with transaction.atomic():
        req = current or SaleRequest()
        req.seller = seller
        req.sold_on = sold_on or timezone.localdate()
        req.settlement = settlement or 'نقدی'
        req.customer_type = customer_type
        req.customer_name = name
        req.phone = phone
        req.city = city
        req.address = address
        req.note = request.POST.get('note', '').strip()
        req.incomplete = bool(errors)
        req.credit = credit
        req.guarantees = guarantees
        req.references = references
        req.docs = docs
        req.warnings = warnings
        req.lines = good_lines
        req.payments = [
            {**pay, 'paid_on': pay['paid_on'].isoformat() if pay.get('paid_on') else ''}
            for pay in payments
        ]
        req.checks = [
            {**chk, 'due_on': chk['due_on'].isoformat() if chk.get('due_on') else ''}
            for chk in checks
        ]
        if not req.pk:
            req.status = 'pending'
        req.save()
        _store_uploads(request, req)
        take_snapshot('requests')
    messages.success(request, 'درخواست ناقص ثبت شد و تا تکمیل قابل تایید نیست.' if req.incomplete else 'درخواست برای تایید ارسال شد.')
    return redirect('request_detail', pk=req.pk)


@page_required('requests')
def request_detail(request, pk):
    req = get_object_or_404(visible_requests(request.user), pk=pk)
    return render(request, 'panel/request_detail.html', {
        'req': req,
        'gaps': request_gaps(req),
        'can_review': can_review(request.user),
        'schema': CREDIT_SCHEMA,
    })


@require_POST
@page_required('requests')
def request_review(request, pk):
    if not can_review(request.user):
        messages.error(request, 'تایید فروش فقط برای مدیر است.')
        return redirect('request_detail', pk=pk)
    req = get_object_or_404(SaleRequest, pk=pk)
    action = request.POST.get('action')
    note = request.POST.get('review_note', '').strip()
    if action == 'reject':
        req.status = 'rejected'
        req.review_note = note
        req.reviewed_by = request.user
        req.reviewed_at = timezone.now()
        req.save()
        take_snapshot('requests')
        messages.success(request, 'درخواست رد شد.')
        return redirect('request_detail', pk=pk)
    if req.incomplete or req.status != 'pending':
        messages.error(request, 'درخواست ناقص یا بررسی‌شده قابل تایید نیست.')
        return redirect('request_detail', pk=pk)
    with transaction.atomic():
        customer = Customer.objects.filter(name=req.customer_name).first()
        created = customer is None
        if created:
            customer = Customer.objects.create(
                name=req.customer_name, phone=req.phone, city=req.city,
                address=req.address, customer_type=req.customer_type, expert=req.seller,
            )
        else:
            if not customer.phone:
                customer.phone = req.phone
            if not customer.city:
                customer.city = req.city
            if not customer.address:
                customer.address = req.address
            if not customer.customer_type:
                customer.customer_type = req.customer_type
        dossier = dict(customer.dossier or {})
        for key, value in (req.credit or {}).items():
            if value and not str(dossier.get(key) or '').strip():
                dossier[key] = value
        if created and not str(dossier.get('firstDealDate') or '').strip():
            dossier['firstDealDate'] = format_jalali(timezone.localdate())
        customer.dossier = dossier
        customer.is_lead = False
        customer.save()
        _copy_sale_files(req, customer)
        invoice = None
        for _ in range(5):
            try:
                with transaction.atomic():
                    invoice = Invoice.objects.create(
                        number=_next_invoice_number(), customer=customer, expert=req.seller,
                        sold_on=req.sold_on, settlement=req.settlement,
                        status='در حال پیگیری' if req.settlement == 'قسطی' else 'تکمیل شده',
                        note=req.note,
                    )
                break
            except IntegrityError:
                invoice = None
        if invoice is None:
            messages.error(request, 'شماره فاکتور ساخته نشد. یک بار دیگر تایید کنید.')
            return redirect('request_detail', pk=pk)
        for line in req.line_list:
            InvoiceLine.objects.create(
                invoice=invoice, product_name=line.product_name, qty=line.qty,
                unit_price=line.unit_price, unit_cost=line.unit_cost,
            )
        for pay in req.payment_list:
            Payment.objects.create(
                invoice=invoice, amount=pay.amount, method=pay.method,
                paid_on=pay.paid_on or req.sold_on, note=pay.note,
            )
        for chk in req.check_list:
            Check.objects.create(
                invoice=invoice, number=chk.number, amount=chk.amount,
                due_on=chk.due_on or req.sold_on, status=chk.status, note=chk.bank,
            )
        req.status = 'approved'
        req.review_note = note
        req.reviewed_by = request.user
        req.reviewed_at = timezone.now()
        req.invoice = invoice
        req.save()
        take_snapshot('requests')
        take_snapshot('customers')
    messages.success(request, f'فروش تایید شد و فاکتور {invoice.number} در داشبورد نشست.')
    return redirect('request_detail', pk=pk)
