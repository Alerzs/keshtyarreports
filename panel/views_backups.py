import logging

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .backup import (
    MAX_SNAPSHOTS, prune_snapshots, restore_snapshot,
    summarize_customers, summarize_requests, summarize_users, take_snapshot,
)
from .decorators import page_required
from .jalali import format_jalali
from .models import Customer, Invoice, Snapshot
from .workbook import WorkbookError, export_workbook, import_workbook, template_workbook

logger = logging.getLogger(__name__)
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

TAGS = {
    'users': ('کاربران و نقش‌ها', summarize_users),
    'requests': ('درخواست‌های اعلام فروش', summarize_requests),
    'customers': ('پرونده‌ی مشتریان', summarize_customers),
}


@page_required('backups')
def backups(request):
    sections = []
    for tag, (title, summary) in TAGS.items():
        prune_snapshots(tag)
        rows = list(Snapshot.objects.filter(tag=tag)[:MAX_SNAPSHOTS])
        live = rows[0] if rows else None
        sections.append({
            'tag': tag,
            'title': title,
            'summary': summary(),
            'live_rev': live.rev if live else 0,
            'live_at': format_jalali(live.created_at, with_time=True) if live else '—',
            'rows': rows,
        })
    return render(request, 'panel/backups.html', {
        'sections': sections,
        'data_dir': 'پایگاه SQLite پروژه (بیرون از فایل‌های قالب)',
        'excel_invoices': Invoice.objects.count(),
        'excel_customers': Customer.objects.count(),
    })


def _xlsx(payload, filename):
    response = HttpResponse(payload, content_type=XLSX)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@page_required('backups')
def excel_template(request):
    return _xlsx(template_workbook(), 'Sales-CRM-template.xlsx')


@page_required('backups')
def excel_export(request):
    return _xlsx(export_workbook(), 'Sales-CRM.xlsx')


@require_POST
@page_required('backups')
def excel_import(request):
    upload = request.FILES.get('workbook')
    if upload is None:
        messages.error(request, 'فایل اکسل را انتخاب کنید.')
        return redirect('backups')
    if not (upload.name or '').lower().endswith('.xlsx'):
        messages.error(request, 'فقط فایل xlsx با قالب فروش پذیرفته می‌شود.')
        return redirect('backups')
    try:
        result = import_workbook(upload)
    except WorkbookError as exc:
        messages.error(request, str(exc))
        return redirect('backups')
    except Exception:
        logger.exception('excel import failed')
        messages.error(request, 'ورود فایل انجام نشد. قالب شیت‌ها را با فایل نمونه مقایسه کنید.')
        return redirect('backups')
    messages.success(
        request,
        'از اکسل اضافه شد: '
        f'{result["invoices_created"]} فاکتور تازه، '
        f'{result["invoices_updated"]} فاکتور به‌روز، '
        f'{result["customers_created"]} مشتری تازه'
        + (f'، {result["experts_created"]} کارشناس تازه' if result['experts_created'] else '')
        + '.',
    )
    return redirect('backups')


@require_POST
@page_required('backups')
def snapshot_now(request):
    for tag in TAGS:
        take_snapshot(tag, manual=True)
    messages.success(request, 'از کاربران، درخواست‌ها و پرونده‌ی مشتریان پشتیبان گرفته شد.')
    return redirect('backups')


@require_POST
@page_required('backups')
def restore(request, pk):
    snap = get_object_or_404(Snapshot, pk=pk)
    if snap.tag not in TAGS:
        messages.error(request, 'این نسخه قابل بازگردانی نیست.')
        return redirect('backups')
    restore_snapshot(snap, request.user)
    messages.success(request, f'نسخه‌ی r{snap.rev} برگردانده شد. وضعیت قبلی هم پشتیبان شده است.')
    return redirect('backups')


@page_required('backups')
def download_snapshot(request, pk):
    snap = get_object_or_404(Snapshot, pk=pk)
    return JsonResponse(snap.payload, safe=False, json_dumps_params={'ensure_ascii': False, 'indent': 2})
