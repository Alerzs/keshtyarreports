from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access import visible_invoices
from .credit import INVOICE_STATUSES, PAY_METHODS, SETTLEMENTS
from .decorators import page_required
from .jalali import parse_jalali, parse_money, to_fa_digits
from .models import Check, Payment
from .stats import outstanding_of, received_of

PAGE_SIZE = 10


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
    checks = sum(chk.amount for chk in invoice.checks.all())
    paid = sum(pay.amount for pay in invoice.payments.all())
    room = max(0, sale - checks - paid)
    return {
        'sale': sale,
        'cost': cost,
        'profit': sale - cost,
        'received': received_of(invoice),
        'outstanding': outstanding_of(invoice),
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


def _match(row, query):
    invoice = row['invoice']
    expert = invoice.expert_label or ''
    haystack = f'{invoice.number} {invoice.customer.name} {expert}'.casefold()
    return query.casefold() in haystack


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
        rows = [row for row in rows if row['outstanding'] > 0]
    elif balance == 'cleared':
        rows = [row for row in rows if row['outstanding'] <= 0]
    page = Paginator(rows, PAGE_SIZE).get_page(request.GET.get('page') or 1)
    filters = urlencode({
        key: value for key, value in {
            'q': query,
            'settlement': settlement,
            'status': status,
            'balance': balance,
            'expert': expert_id,
        }.items() if value
    })
    return render(request, 'panel/sales.html', {
        'rows': page.object_list,
        'page': page,
        'total': len(rows),
        'filters': filters,
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
def collect_check(request, pk, check_pk):
    invoice = get_object_or_404(visible_invoices(request.user), pk=pk)
    check = get_object_or_404(Check.objects.filter(invoice=invoice), pk=check_pk)
    if check.status == 'وصول‌شده':
        messages.error(request, 'این چک قبلاً وصول شده است.')
    else:
        check.status = 'وصول‌شده'
        check.save(update_fields=['status'])
        messages.success(request, 'چک وصول شد.')
    return redirect('sale_detail', pk=invoice.pk)


@require_POST
@page_required('sales')
def bounce_check(request, pk, check_pk):
    invoice = get_object_or_404(visible_invoices(request.user), pk=pk)
    check = get_object_or_404(Check.objects.filter(invoice=invoice), pk=check_pk)
    if check.status == 'برگشتی':
        messages.error(request, 'این چک قبلاً برگشت خورده است.')
    else:
        check.status = 'برگشتی'
        check.save(update_fields=['status'])
        messages.success(request, 'چک برگشت خورد.')
    return redirect('sale_detail', pk=invoice.pk)
