from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access import visible_invoices
from .credit import CHECK_STATES, INVOICE_STATUSES, PAY_METHODS, SETTLEMENTS
from .decorators import page_required
from .jalali import parse_jalali, parse_money, to_en_digits, to_fa_digits
from .models import Check, Payment
from .stats import cash_due_of, cash_of, collected_of, outstanding_of, received_of

PAGE_SIZE = 10
SORTS = (
    ('number', 'شماره فاکتور', False),
    ('customer', 'نام مشتری', False),
    ('expert', 'مسئول فروش', False),
    ('sale', 'مبلغ کل فروش', True),
    ('cost', 'مبلغ کل خرید', True),
    ('cash', 'جمع دریافتی نقدی', True),
    ('check', 'جمع دریافتی چکی', True),
    ('cash_due', 'مانده حساب نقدی', True),
    ('check_due', 'مانده حساب چکی', True),
)


def _money(value):
    text = f'{int(value):,}'.replace(',', '٬')
    return to_fa_digits(text)


def _qty_text(qty):
    text = format(qty.normalize(), 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text or '0'


def _figures(invoice):
    sale = invoice.sale_amount
    cost = int(invoice.purchase_amount or 0)
    check_rows = list(invoice.checks.all())
    checks = sum(int(chk.amount or 0) for chk in check_rows)
    paid = sum(int(pay.amount or 0) for pay in invoice.payments.all())
    check_received = collected_of(invoice)
    room = max(0, sale - checks - paid)
    return {
        'sale': sale,
        'cost': cost,
        'profit': sale - cost,
        'received': received_of(invoice),
        'outstanding': outstanding_of(invoice),
        'cash_received': cash_of(invoice),
        'check_received': check_received,
        'cash_due': cash_due_of(invoice),
        'check_due': checks - check_received,
        'checks': checks,
        'paid': paid,
        'room': room,
    }


def _rows(user):
    rows = []
    for invoice in visible_invoices(user):
        figures = _figures(invoice)
        rows.append({'invoice': invoice, **figures})
    return rows


def _fold(text):
    text = to_en_digits(text or '')
    return text.replace('ي', 'ی').replace('ك', 'ک').replace('ى', 'ی').replace('ة', 'ه').casefold()


def _match(row, query):
    invoice = row['invoice']
    expert = invoice.expert_label or ''
    haystack = _fold(f'{invoice.number} {invoice.customer.name} {expert}')
    return _fold(query) in haystack


def _number_key(row):
    number = str(row['invoice'].number)
    if number.isdigit():
        return (0, int(number))
    return (1, _fold(number))


def _sort_value(row, key):
    invoice = row['invoice']
    if key == 'number':
        return _number_key(row)
    if key == 'customer':
        return _fold(invoice.customer.name)
    if key == 'expert':
        return _fold(invoice.expert_label)
    field = {'cash': 'cash_received', 'check': 'check_received'}.get(key, key)
    return int(row.get(field) or 0)


def _apply_sort(rows, key, direction):
    known = {item[0]: item[2] for item in SORTS}
    if key not in known:
        return rows, '', ''
    if direction not in {'asc', 'desc'}:
        direction = 'desc' if known[key] else 'asc'
    rows.sort(key=lambda row: (_sort_value(row, key), row['invoice'].pk), reverse=direction == 'desc')
    return rows, key, direction


def _sort_columns(params, key, direction):
    columns = []
    for name, label, numeric in SORTS:
        if key == name:
            nxt = 'asc' if direction == 'desc' else 'desc'
            mark = '▲' if direction == 'asc' else '▼'
            aria = 'ascending' if direction == 'asc' else 'descending'
        else:
            nxt = 'desc' if numeric else 'asc'
            mark = '↕'
            aria = 'none'
        query = {**params, 'sort': name, 'dir': nxt}
        columns.append({
            'label': label,
            'href': '?' + urlencode(query),
            'active': key == name,
            'mark': mark,
            'aria': aria,
        })
    return columns


@page_required('sales')
def sales(request):
    query = (request.GET.get('q') or '').strip()
    settlement = request.GET.get('settlement') or ''
    if settlement not in SETTLEMENTS:
        settlement = ''
    status = request.GET.get('status') or ''
    if status not in INVOICE_STATUSES:
        status = ''
    balance = request.GET.get('balance') or ''
    if balance not in {'open', 'cleared'}:
        balance = ''
    expert_id = request.GET.get('expert') or ''
    rows = _rows(request.user)
    experts = []
    seen = set()
    for row in rows:
        expert = row['invoice'].expert
        if expert and expert.pk not in seen:
            seen.add(expert.pk)
            experts.append(expert)
    experts.sort(key=lambda person: person.report_name())
    if query:
        rows = [row for row in rows if _match(row, query)]
    if settlement:
        rows = [row for row in rows if row['invoice'].settlement == settlement]
    if status:
        rows = [row for row in rows if row['invoice'].status == status]
    if expert_id.isdigit():
        chosen = int(expert_id)
        rows = [row for row in rows if row['invoice'].expert_id == chosen]
    else:
        expert_id = ''
    if balance == 'open':
        rows = [row for row in rows if row['cash_due'] > 0 or row['check_due'] > 0]
    elif balance == 'cleared':
        rows = [row for row in rows if row['cash_due'] <= 0 and row['check_due'] <= 0]
    sort_key = request.GET.get('sort') or ''
    sort_dir = request.GET.get('dir') or ''
    rows, sort_key, sort_dir = _apply_sort(rows, sort_key, sort_dir)
    filtered = bool(query or settlement or status or balance or expert_id)
    page_size = (len(rows) or 1) if filtered else PAGE_SIZE
    page_number = 1 if filtered else (request.GET.get('page') or 1)
    page = Paginator(rows, page_size).get_page(page_number)
    kept = {
        'q': query,
        'settlement': settlement,
        'status': status,
        'balance': balance,
        'expert': expert_id,
        'sort': sort_key,
        'dir': sort_dir,
    }
    filters = urlencode({name: value for name, value in kept.items() if value})
    columns = _sort_columns(
        {name: value for name, value in kept.items() if value and name not in {'sort', 'dir'}},
        sort_key,
        sort_dir,
    )
    return render(request, 'panel/sales.html', {
        'rows': page.object_list,
        'page': page,
        'total': len(rows),
        'filters': filters,
        'columns': columns,
        'sort': sort_key,
        'sort_dir': sort_dir,
        'query': query,
        'settlement': settlement,
        'status': status,
        'balance': balance,
        'expert_id': expert_id,
        'experts': experts,
        'settlements': SETTLEMENTS,
        'statuses': INVOICE_STATUSES,
    })


@page_required('sales')
def sale_detail(request, pk):
    invoice = get_object_or_404(visible_invoices(request.user), pk=pk)
    lines = [
        {
            'product': line.product_name,
            'qty': _qty_text(line.qty),
            'unit_price': int(line.unit_price or 0),
            'amount': int(line.qty * (line.unit_price or 0)),
            'unit_cost': int(line.unit_cost or 0),
            'cost': int(line.qty * (line.unit_cost or 0)),
        }
        for line in invoice.lines.all()
    ]
    return render(request, 'panel/sale_detail.html', {
        'invoice': invoice,
        'lines': lines,
        'payments': list(invoice.payments.all()),
        'checks': list(invoice.checks.all()),
        'figures': _figures(invoice),
        'pay_methods': PAY_METHODS,
        'check_states': CHECK_STATES,
        'today': timezone.localdate(),
    })


@require_POST
@page_required('sales')
def save_purchase(request, pk):
    invoice = get_object_or_404(visible_invoices(request.user), pk=pk)
    amount = parse_money(request.POST.get('purchase_amount'))
    if amount < 0:
        messages.error(request, 'مبلغ خرید نمی‌تواند منفی باشد.')
    else:
        invoice.purchase_amount = amount
        invoice.save(update_fields=['purchase_amount'])
        messages.success(request, 'مبلغ خرید ذخیره شد.')
    return redirect('sale_detail', pk=invoice.pk)


@require_POST
@page_required('sales')
def add_payment(request, pk):
    invoice = get_object_or_404(visible_invoices(request.user), pk=pk)
    figures = _figures(invoice)
    amount = parse_money(request.POST.get('amount'))
    method = (request.POST.get('method') or '').strip()
    paid_on = parse_jalali(request.POST.get('paid_on', ''))
    note = (request.POST.get('note') or '').strip()
    if amount <= 0:
        messages.error(request, 'مبلغ پرداخت را وارد کنید.')
    elif method not in PAY_METHODS:
        messages.error(request, 'روش پرداخت را انتخاب کنید.')
    elif paid_on is None:
        messages.error(request, 'تاریخ پرداخت را وارد کنید.')
    elif amount > figures['room']:
        messages.error(
            request,
            f'مجموع پرداخت نقدی نمی‌تواند از تفاضل مبلغ فاکتور و جمع چک‌ها بیشتر شود. سقف باقی‌مانده {_money(figures["room"])} تومان است.',
        )
    else:
        Payment.objects.create(invoice=invoice, amount=amount, method=method, paid_on=paid_on, note=note)
        messages.success(request, 'پرداخت ثبت شد.')
    return redirect('sale_detail', pk=invoice.pk)


@require_POST
@page_required('sales')
def set_check_status(request, pk, check_pk):
    invoice = get_object_or_404(visible_invoices(request.user), pk=pk)
    check = get_object_or_404(Check.objects.filter(invoice=invoice), pk=check_pk)
    status = (request.POST.get('status') or '').strip()
    if status not in CHECK_STATES:
        messages.error(request, 'وضعیت چک معتبر نیست.')
    else:
        check.status = status
        check.save(update_fields=['status'])
        messages.success(request, 'وضعیت چک ذخیره شد.')
    return redirect('sale_detail', pk=invoice.pk)
