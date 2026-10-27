"""فهرست پورسانت فاکتورها برای گروه مالی."""
from collections import defaultdict
from urllib.parse import urlencode, urlparse

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .access import visible_invoices
from .decorators import page_required
from .jalali import month_key, month_title
from .levels import level_for

PAGE_SIZE = 15


def _rows(user):
    invoices = [
        row for row in visible_invoices(user)
        if row.status != 'لغو شده' and row.sold_on
    ]
    monthly = defaultdict(int)
    for invoice in invoices:
        if invoice.expert_id:
            monthly[(invoice.expert_id, month_key(invoice.sold_on))] += invoice.profit
    rows = []
    for invoice in invoices:
        key = month_key(invoice.sold_on)
        level = level_for(monthly[(invoice.expert_id, key)]) if invoice.expert_id else None
        rate = level['rate'] if level else 0
        rows.append({
            'invoice': invoice,
            'month_key': key,
            'month_label': month_title(key),
            'profit': invoice.profit,
            'level': level,
            'level_name': level['name'] if level else 'هنوز وارد مسیر نشده',
            'rate': int(round(rate * 100)),
            'amount': int(invoice.profit * rate),
            'paid': invoice.commission_paid,
        })
    return rows


def _match(row, query):
    invoice = row['invoice']
    expert = invoice.expert_label or ''
    haystack = f'{invoice.number} {invoice.customer.name} {expert} {row["level_name"]}'.casefold()
    return query.casefold() in haystack


def _safe_next(request):
    target = (request.POST.get('next') or '').strip()
    home = reverse('commissions')
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or parsed.path.rstrip('/') != home.rstrip('/'):
        return home
    return target


@page_required('commissions')
def commissions(request):
    query = (request.GET.get('q') or '').strip()
    expert_id = request.GET.get('expert') or ''
    paid = request.GET.get('paid') or ''
    if paid not in {'yes', 'no'}:
        paid = ''
    month = request.GET.get('month') or ''
    rows = _rows(request.user)
    experts = []
    months = []
    seen_experts = set()
    seen_months = set()
    for row in rows:
        expert = row['invoice'].expert
        if expert and expert.pk not in seen_experts:
            seen_experts.add(expert.pk)
            experts.append(expert)
        if row['month_key'] not in seen_months:
            seen_months.add(row['month_key'])
            months.append({'key': row['month_key'], 'label': row['month_label']})
    experts.sort(key=lambda person: person.report_name())
    months.sort(key=lambda item: item['key'], reverse=True)
    if query:
        rows = [row for row in rows if _match(row, query)]
    if expert_id.isdigit():
        chosen = int(expert_id)
        rows = [row for row in rows if row['invoice'].expert_id == chosen]
    else:
        expert_id = ''
    if month and month not in seen_months:
        month = ''
    if month:
        rows = [row for row in rows if row['month_key'] == month]
    if paid == 'yes':
        rows = [row for row in rows if row['paid']]
    elif paid == 'no':
        rows = [row for row in rows if not row['paid']]
    total_amount = sum(row['amount'] for row in rows)
    paid_amount = sum(row['amount'] for row in rows if row['paid'])
    page = Paginator(rows, PAGE_SIZE).get_page(request.GET.get('page') or 1)
    filters = urlencode({
        key: value for key, value in {
            'q': query,
            'expert': expert_id,
            'paid': paid,
            'month': month,
        }.items() if value
    })
    return render(request, 'panel/commissions.html', {
        'rows': page.object_list,
        'page': page,
        'total': len(rows),
        'total_amount': total_amount,
        'paid_amount': paid_amount,
        'unpaid_amount': total_amount - paid_amount,
        'filters': filters,
        'query': query,
        'expert_id': expert_id,
        'paid': paid,
        'month': month,
        'experts': experts,
        'months': months,
    })


@require_POST
@page_required('commissions')
def commission_status(request, pk):
    invoice = get_object_or_404(
        visible_invoices(request.user).exclude(status='لغو شده'),
        pk=pk,
    )
    paid = request.POST.get('paid') == '1'
    if invoice.commission_paid != paid:
        invoice.commission_paid = paid
        invoice.save(update_fields=['commission_paid'])
        state = 'پرداخت‌شده' if paid else 'پرداخت‌نشده'
        messages.success(request, f'پورسانت فاکتور {invoice.number} {state} ثبت شد.')
    return redirect(_safe_next(request))
