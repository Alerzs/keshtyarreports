from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .decorators import page_required
from .perms import can_page
from .jalali import format_jalali, month_label, month_span
from .levels import RULES
from .stats import build_dashboard, period_months


@page_required('dashboard')
def dashboard(request):
    allowed = set(request.crm['tabs'])
    requested = request.GET.get('tab') or ''
    if not requested and request.crm['scope'] != 'all':
        requested = 'team' if 'team' in allowed else 'specialist'
    if requested in allowed:
        tab = requested
    else:
        tab = next(iter(request.crm['tabs']))
    periods = period_months(request.user)
    range_key = 'all'
    person = request.GET.get('person') or ''
    month = 'all'
    team_month = 'all'
    data = build_dashboard(request.user, range_key, person, month, team_month)
    charts = data.pop('charts')
    data['check_page'] = Paginator(data.pop('checks'), 10).get_page(request.GET.get('cpage') or 1)
    return render(request, 'panel/dashboard.html', {
        'tab': tab,
        'range_key': range_key,
        'period_months': periods,
        'person': person,
        'month': month,
        'team_month': team_month,
        'month_label': month_label,
        'rules': RULES,
        'dash_payload': {
            'range': 'all',
            'byRange': {'all': charts},
            'months': list(reversed(periods)),
            'kpis': data['kpis'],
            'chartsUrl': reverse('dashboard_charts'),
            'customerBase': reverse('customers'),
            'salesBase': reverse('sales') if can_page(request.user, 'sales') else '',
        },
        'synced_at': format_jalali(timezone.localtime(), with_time=True),
        **data,
    })


@require_GET
@page_required('dashboard')
def dashboard_charts(request):
    start = request.GET.get('from') or ''
    end = request.GET.get('to') or ''
    if not month_span(start) or not month_span(end):
        return JsonResponse({'error': 'بازه نامعتبر است.'}, status=400)
    if start > end:
        start, end = end, start
    person = request.GET.get('person') or ''
    built = build_dashboard(request.user, f'{start}..{end}', person, 'all', 'all')
    return JsonResponse({'charts': built['charts'], 'kpis': built['kpis']})
