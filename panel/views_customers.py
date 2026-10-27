from datetime import date

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .access import visible_customers, visible_invoices
from .backup import take_snapshot
from .credit import BANKS, CREDIT_SCHEMA, CUST_TYPES, check_status_tone, missing_profile_fields, profile_percent
from .decorators import page_required
from .models import Customer, CustomerDocument, CustomerNote
from .stats import outstanding_of, received_of

ALPHABET = list('ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی')


def _customer_rows(user):
    customers = list(visible_customers(user).prefetch_related('invoices__lines', 'invoices__payments', 'invoices__checks'))
    rows = []
    for customer in customers:
        invoices = [inv for inv in customer.invoices.all() if inv.status != 'لغو شده']
        sales = sum(inv.sale_amount for inv in invoices)
        debt = sum(outstanding_of(inv) for inv in invoices)
        rows.append({
            'customer': customer,
            'sales': sales,
            'debt': debt,
            'invoices': len(invoices),
            'percent': profile_percent(customer),
            'received': sum(received_of(inv) for inv in invoices),
        })
    return rows


@page_required('customers')
def directory(request):
    tab = request.GET.get('tab') or 'all'
    if tab not in {'all', 'lead'}:
        tab = 'all'
    sort = request.GET.get('sort') or 'name'
    kind = request.GET.get('type') or ''
    debt = request.GET.get('debt') or 'all'
    letter = request.GET.get('letter') or ''
    query = (request.GET.get('q') or '').strip()
    rows = _customer_rows(request.user)
    counts = {
        'all': len(rows),
        'lead': sum(1 for row in rows if row['customer'].is_lead or row['invoices'] == 0),
    }
    filtered = rows
    if tab == 'lead':
        filtered = [row for row in filtered if row['customer'].is_lead or row['invoices'] == 0]
    if kind:
        filtered = [row for row in filtered if row['customer'].customer_type == kind]
    if debt == 'debtor':
        filtered = [row for row in filtered if row['debt'] > 0]
    elif debt == 'cleared':
        filtered = [row for row in filtered if row['debt'] <= 0 and row['invoices']]
    if letter:
        filtered = [row for row in filtered if row['customer'].name.startswith(letter)]
    if query:
        q = query.replace('ي', 'ی').replace('ك', 'ک')
        filtered = [
            row for row in filtered
            if q in row['customer'].name or q in (row['customer'].phone or '')
        ]
    if sort == 'sales':
        filtered.sort(key=lambda row: row['sales'], reverse=True)
    elif sort == 'invoices':
        filtered.sort(key=lambda row: row['invoices'], reverse=True)
    elif sort == 'debt':
        filtered.sort(key=lambda row: row['debt'], reverse=True)
    elif sort == 'incomplete':
        filtered.sort(key=lambda row: row['percent'])
    else:
        filtered.sort(key=lambda row: row['customer'].name)
    types = sorted({row['customer'].customer_type for row in rows if row['customer'].customer_type})
    return render(request, 'panel/customers.html', {
        'rows': filtered,
        'counts': counts,
        'stats': {
            'customers': len(rows),
            'sales': sum(row['sales'] for row in rows),
            'debt': sum(row['debt'] for row in rows),
        },
        'tab': tab,
        'sort': sort,
        'kind': kind,
        'debt': debt,
        'letter': letter,
        'query': query,
        'types': types,
        'alphabet': ALPHABET,
    })


def _dossier_sections(customer):
    """همان گروه‌های فرم اعلام فروش، با مقدارهای پرشده‌ی پرونده."""
    dossier = customer.dossier or {}
    sections = []
    for group in CREDIT_SCHEMA:
        fields = []
        filled = 0
        for field in group['fields']:
            value = str(dossier.get(field['k']) or '')
            if value.strip():
                filled += 1
            fields.append({**field, 'value': value})
        sections.append({
            'k': group['k'],
            't': group['t'],
            'd': group['d'],
            'fields': fields,
            'filled': filled,
            'total': len(fields),
        })
    return sections


def _qty_text(qty):
    text = format(qty.normalize(), 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text or '0'


def _invoice_item_rows(invoice):
    """اقلام فاکتور برای کشوی معامله."""
    rows = []
    for line in invoice.lines.all():
        rows.append({
            'product': line.product_name,
            'qty': _qty_text(line.qty),
            'unit_price': int(line.unit_price or 0),
            'amount': int(line.qty * (line.unit_price or 0)),
        })
    return rows


def _installment_rows(invoice):
    """ردیف‌های کشوی معامله: پرداخت‌های وصول‌شده و اقساط (چک‌ها)."""
    rows = []
    for pay in invoice.payments.all():
        rows.append({
            'title': pay.method or 'پرداخت',
            'due': pay.paid_on,
            'amount': pay.amount,
            'collected_on': pay.paid_on,
            'status': 'وصول‌شده',
            'tone': check_status_tone('وصول‌شده'),
        })
    for chk in invoice.checks.all():
        status = (chk.status or 'در جریان').strip() or 'در جریان'
        tone = check_status_tone(status)
        rows.append({
            'title': f'چک {chk.number}' if chk.number else 'قسط',
            'due': chk.due_on,
            'amount': chk.amount,
            'collected_on': None,
            'status': status,
            'tone': tone,
        })
    rows.sort(key=lambda row: (row['due'] is None, row['due'] or date.min, row['title']))
    return rows


@page_required('customers')
def profile(request, pk):
    customer = get_object_or_404(visible_customers(request.user), pk=pk)
    invoices = list(
        visible_invoices(request.user).filter(customer=customer).prefetch_related('lines', 'payments', 'checks')
    )
    for inv in invoices:
        inv.item_rows = _invoice_item_rows(inv)
        inv.installment_rows = _installment_rows(inv)
    sales = sum(inv.sale_amount for inv in invoices)
    debt = sum(outstanding_of(inv) for inv in invoices)
    cust_types = list(CUST_TYPES)
    if customer.customer_type and customer.customer_type not in cust_types:
        cust_types.append(customer.customer_type)
    return render(request, 'panel/profile.html', {
        'customer': customer,
        'invoices': invoices,
        'sales': sales,
        'debt': debt,
        'received': sum(received_of(inv) for inv in invoices),
        'percent': profile_percent(customer),
        'missing': missing_profile_fields(customer)[:6],
        'documents': customer.documents.all(),
        'sections': _dossier_sections(customer),
        'contact_filled': sum(1 for value in (customer.phone, customer.customer_type, customer.city, customer.address) if str(value or '').strip()),
        'cust_types': cust_types,
        'banks': BANKS,
        'can_edit_dossier': request.user.role in {'superadmin', 'manager'},
    })


@require_POST
@page_required('customers')
def add_note(request, pk):
    customer = get_object_or_404(visible_customers(request.user), pk=pk)
    body = request.POST.get('body', '').strip()
    if not body:
        messages.error(request, 'متن یادداشت خالی است.')
        return redirect('customer_profile', pk=pk)
    CustomerNote.objects.create(
        customer=customer,
        author=request.user,
        kind=request.POST.get('kind') or 'note',
        body=body,
        result=request.POST.get('result', '').strip(),
    )
    messages.success(request, 'رویداد در پرونده ثبت شد.')
    return redirect('customer_profile', pk=pk)


@require_POST
@page_required('customers')
def save_dossier(request, pk):
    if request.user.role not in {'superadmin', 'manager'}:
        messages.error(request, 'ویرایش پرونده فقط برای مدیر است.')
        return redirect('customer_profile', pk=pk)
    customer = get_object_or_404(Customer, pk=pk)
    dossier = dict(customer.dossier or {})
    for group in CREDIT_SCHEMA:
        for field in group['fields']:
            dossier[field['k']] = request.POST.get(f"d_{field['k']}", '').strip()
    customer.dossier = dossier
    customer.phone = request.POST.get('phone', customer.phone).strip()
    customer.city = request.POST.get('city', customer.city).strip()
    customer.address = request.POST.get('address', customer.address).strip()
    customer.customer_type = request.POST.get('customer_type', customer.customer_type).strip()
    customer.save()
    take_snapshot('customers')
    messages.success(request, 'پرونده ذخیره شد. روی گوگل‌شیت نوشته نمی‌شود.')
    return redirect('customer_profile', pk=pk)


@require_POST
@page_required('customers')
def upload_doc(request, pk):
    customer = get_object_or_404(visible_customers(request.user), pk=pk)
    upload = request.FILES.get('file')
    if not upload:
        messages.error(request, 'فایلی انتخاب نشده است.')
        return redirect('customer_profile', pk=pk)
    CustomerDocument.objects.create(
        customer=customer,
        doc_type=request.POST.get('doc_type') or 'سایر مدارک',
        file=upload,
    )
    messages.success(request, 'مدرک به پرونده اضافه شد.')
    return redirect('customer_profile', pk=pk)
