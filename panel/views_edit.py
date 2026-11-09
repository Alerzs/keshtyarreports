import re
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .access import seller_choices, visible_customers, visible_invoices
from .credit import CHECK_STATES, PAY_METHODS, SETTLEMENTS
from .decorators import page_required
from .jalali import parse_jalali, parse_money, to_en_digits
from .models import Check, Invoice, InvoiceLine, Payment


def _qty_text(qty):
    text = format(Decimal(qty).normalize(), 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text or '0'


def _parse_qty(raw):
    text = to_en_digits(raw).replace('٬', '').replace(',', '').replace('٫', '.')
    text = re.sub(r'[^\d.]', '', text)
    if not text:
        return Decimal('0')
    try:
        qty = Decimal(text)
    except InvalidOperation:
        return Decimal('0')
    return qty.quantize(Decimal('0.01'))


def _at(rows, idx):
    return rows[idx] if idx < len(rows) else ''


def _blank_line():
    return {'product': '', 'qty': '1', 'unit_price': '', 'unit_cost': ''}


def _blank_payment():
    return {'amount': '', 'method': PAY_METHODS[0], 'paid_on': '', 'note': ''}


def _blank_check():
    return {
        'id': '', 'number': '', 'amount': '', 'due_on': '',
        'status': CHECK_STATES[0], 'note': '',
    }


def _experts_for(user, invoice):
    people = []
    seen = set()
    for person in seller_choices(user):
        if person.pk in seen:
            continue
        seen.add(person.pk)
        people.append(person)
    if invoice is not None and invoice.expert_id and invoice.expert_id not in seen:
        people.append(invoice.expert)
    people.sort(key=lambda person: person.report_name())
    return people


def _form_from_invoice(invoice):
    lines = [
        {
            'product': line.product_name,
            'qty': _qty_text(line.qty),
            'unit_price': line.unit_price or '',
            'unit_cost': line.unit_cost or '',
        }
        for line in invoice.lines.all()
    ]
    payments = [
        {
            'amount': pay.amount,
            'method': pay.method,
            'paid_on': pay.paid_on,
            'note': pay.note,
        }
        for pay in invoice.payments.all()
    ]
    checks = []
    for chk in invoice.checks.all():
        checks.append({
            'id': str(chk.pk),
            'number': chk.number,
            'amount': chk.amount,
            'due_on': chk.due_on,
            'status': chk.status,
            'note': chk.note,
        })
    return {
        'id': invoice.pk,
        'number': invoice.number,
        'customer_name': invoice.customer.name,
        'expert_id': str(invoice.expert_id or ''),
        'sold_on': invoice.sold_on,
        'settlement': invoice.settlement,
        'status': invoice.status,
        'note': invoice.note,
        'commission_paid': invoice.commission_paid,
        'lines': lines or [_blank_line()],
        'payments': payments or [_blank_payment()],
        'checks': checks or [_blank_check()],
    }


def _form_from_post(request, invoice):
    products = request.POST.getlist('product')
    qtys = request.POST.getlist('qty')
    prices = request.POST.getlist('unit_price')
    costs = request.POST.getlist('unit_cost')
    line_count = max(len(products), len(qtys), len(prices), len(costs), 1)
    lines = [
        {
            'product': _at(products, idx),
            'qty': _at(qtys, idx) or '1',
            'unit_price': _at(prices, idx),
            'unit_cost': _at(costs, idx),
        }
        for idx in range(line_count)
    ]

    amounts = request.POST.getlist('pay_amount')
    methods = request.POST.getlist('pay_method')
    dates = request.POST.getlist('pay_date')
    notes = request.POST.getlist('pay_note')
    pay_count = max(len(amounts), len(methods), len(dates), len(notes), 1)
    payments = [
        {
            'amount': _at(amounts, idx),
            'method': _at(methods, idx) or PAY_METHODS[0],
            'paid_on': _at(dates, idx),
            'note': _at(notes, idx),
        }
        for idx in range(pay_count)
    ]

    ids = request.POST.getlist('chk_id')
    numbers = request.POST.getlist('chk_number')
    chk_amounts = request.POST.getlist('chk_amount')
    chk_dates = request.POST.getlist('chk_date')
    statuses = request.POST.getlist('chk_status')
    chk_notes = request.POST.getlist('chk_note')
    chk_count = max(len(ids), len(numbers), len(chk_amounts), len(chk_dates), len(statuses), len(chk_notes), 1)
    checks = [
        {
            'id': _at(ids, idx).strip(),
            'number': _at(numbers, idx),
            'amount': _at(chk_amounts, idx),
            'due_on': _at(chk_dates, idx),
            'status': _at(statuses, idx) or CHECK_STATES[0],
            'note': _at(chk_notes, idx),
        }
        for idx in range(chk_count)
    ]
    return {
        'id': invoice.pk,
        'number': request.POST.get('number', ''),
        'customer_name': invoice.customer.name,
        'expert_id': request.POST.get('expert', ''),
        'sold_on': request.POST.get('sold_on', ''),
        'settlement': request.POST.get('settlement', ''),
        'status': invoice.status,
        'note': request.POST.get('note', ''),
        'commission_paid': request.POST.get('commission_paid') == '1',
        'lines': lines,
        'payments': payments,
        'checks': checks,
    }


def _clean_invoice(request, invoice, form, experts):
    errors = []

    def add(message):
        if message not in errors:
            errors.append(message)

    number = (form['number'] or '').strip()
    if not number:
        add('شماره فاکتور را وارد کنید.')
    elif len(number) > 40:
        add('شماره فاکتور حداکثر ۴۰ حرف است.')
    elif Invoice.objects.exclude(pk=invoice.pk).filter(number=number).exists():
        add('این شماره فاکتور قبلاً ثبت شده است.')

    expert = None
    expert_raw = (form['expert_id'] or '').strip()
    allowed = {person.pk: person for person in experts}
    if expert_raw:
        if expert_raw.isdigit() and int(expert_raw) in allowed:
            expert = allowed[int(expert_raw)]
        else:
            add('کارشناس معتبر نیست.')

    sold_on = parse_jalali(form['sold_on'])
    if sold_on is None:
        add('تاریخ فروش باید مثل ۱۴۰۵/۰۶/۱۲ باشد.')
    if form['settlement'] not in SETTLEMENTS:
        add('نوع تسویه معتبر نیست.')

    lines = []
    missing_product = bad_qty = bad_price = False
    for row in form['lines']:
        product = (row['product'] or '').strip()
        price = parse_money(row['unit_price'])
        cost = parse_money(row['unit_cost'])
        if not product and price == 0 and cost == 0:
            continue
        qty = _parse_qty(row['qty'])
        if not product:
            missing_product = True
        elif len(product) > 160:
            add('نام کالا حداکثر ۱۶۰ حرف است.')
        if qty < 1:
            bad_qty = True
        if price == 0:
            bad_price = True
        if price < 0 or cost < 0:
            add('مبلغ قلم فاکتور نمی‌تواند منفی باشد.')
        lines.append({
            'product_name': product,
            'qty': qty,
            'unit_price': max(price, 0),
            'unit_cost': max(cost, 0),
        })
    if not lines:
        add('حداقل یک قلم فاکتور لازم است.')
    if missing_product:
        add('نام کالای هر قلم را وارد کنید.')
    if bad_qty:
        add('تعداد هر قلم باید حداقل ۱ باشد.')
    if bad_price:
        add('قیمت فروش هر واحد لازم است.')

    payments = []
    bad_pay_date = bad_method = False
    for row in form['payments']:
        amount = parse_money(row['amount'])
        note = (row['note'] or '').strip()
        paid_on = parse_jalali(row['paid_on']) if (row['paid_on'] or '').strip() else None
        if amount == 0 and not note and paid_on is None:
            continue
        if amount <= 0:
            add('مبلغ هر پرداختی را وارد کنید.')
        method = (row['method'] or '').strip()
        if method not in PAY_METHODS:
            bad_method = True
        if paid_on is None:
            bad_pay_date = True
        payments.append({
            'amount': max(amount, 0),
            'method': method,
            'paid_on': paid_on,
            'note': note[:240],
        })
    if bad_method:
        add('روش پرداخت معتبر نیست.')
    if bad_pay_date:
        add('تاریخ هر پرداختی باید مثل ۱۴۰۵/۰۶/۱۲ باشد.')

    existing = {str(chk.pk): chk for chk in invoice.checks.all()}
    checks = []
    bad_due = bad_status = foreign = False
    for row in form['checks']:
        amount = parse_money(row['amount'])
        number_text = (row['number'] or '').strip()
        note = (row['note'] or '').strip()
        due_text = (row['due_on'] or '').strip()
        due_on = parse_jalali(due_text) if due_text else None
        chk_id = (row['id'] or '').strip()
        empty = amount == 0 and not number_text and not note and due_on is None
        if empty and not chk_id:
            continue
        if chk_id and chk_id not in existing:
            foreign = True
        if amount <= 0:
            add('مبلغ هر چک را وارد کنید.')
        if len(number_text) > 40:
            add('شماره چک حداکثر ۴۰ حرف است.')
        if due_on is None:
            bad_due = True
        status = (row['status'] or '').strip()
        if status not in CHECK_STATES:
            bad_status = True
            status = CHECK_STATES[0]
        checks.append({
            'id': int(chk_id) if chk_id in existing else None,
            'number': number_text,
            'amount': max(amount, 0),
            'due_on': due_on,
            'status': status,
            'note': note[:240],
        })
    if foreign:
        add('چک انتخاب‌شده متعلق به این فاکتور نیست.')
    if bad_due:
        add('تاریخ سررسید هر چک باید مثل ۱۴۰۵/۰۶/۱۲ باشد.')
    if bad_status:
        add('وضعیت چک معتبر نیست.')
    if form['settlement'] == 'قسطی' and not checks:
        add('فروش قسطی حداقل یک چک می‌خواهد.')

    cleaned = {
        'number': number,
        'expert': expert,
        'sold_on': sold_on,
        'settlement': form['settlement'],
        'note': form['note'] or '',
        'commission_paid': bool(form['commission_paid']),
        'lines': lines,
        'payments': payments,
        'checks': checks,
    }
    return cleaned, errors


def _apply_invoice(invoice, cleaned):
    invoice.number = cleaned['number']
    invoice.expert = cleaned['expert']
    invoice.sold_on = cleaned['sold_on']
    invoice.settlement = cleaned['settlement']
    invoice.note = cleaned['note']
    invoice.commission_paid = cleaned['commission_paid']
    invoice.sale_amount = sum(int(line['qty'] * line['unit_price']) for line in cleaned['lines'])
    invoice.purchase_amount = sum(int(line['qty'] * line['unit_cost']) for line in cleaned['lines'])
    invoice.save()

    invoice.lines.all().delete()
    InvoiceLine.objects.bulk_create([
        InvoiceLine(
            invoice=invoice,
            product_name=line['product_name'],
            qty=line['qty'],
            unit_price=line['unit_price'],
            unit_cost=line['unit_cost'],
        )
        for line in cleaned['lines']
    ])

    invoice.payments.all().delete()
    if cleaned['payments']:
        Payment.objects.bulk_create([
            Payment(
                invoice=invoice,
                amount=pay['amount'],
                method=pay['method'],
                paid_on=pay['paid_on'],
                note=pay['note'],
            )
            for pay in cleaned['payments']
        ])

    existing = {chk.pk: chk for chk in invoice.checks.all()}
    kept = set()
    for row in cleaned['checks']:
        if row['id'] and row['id'] in existing:
            chk = existing[row['id']]
            chk.number = row['number']
            chk.amount = row['amount']
            chk.due_on = row['due_on']
            chk.status = row['status']
            chk.note = row['note']
            chk.save()
            kept.add(chk.pk)
        else:
            Check.objects.create(
                invoice=invoice,
                number=row['number'],
                amount=row['amount'],
                due_on=row['due_on'],
                status=row['status'],
                note=row['note'],
            )
    for pk, chk in existing.items():
        if pk not in kept:
            chk.delete()


def _context(request, selected_invoice=None, invoice_form=None, invoice_errors=None, tab=None):
    if not tab:
        tab = request.GET.get('tab') or 'customers'
    if tab in {'payments', 'checks'}:
        tab = 'invoices'
    if tab not in {'customers', 'invoices'}:
        tab = 'customers'
    q = (request.GET.get('q') or '').strip()
    customers = visible_customers(request.user)
    invoices = visible_invoices(request.user)
    if q:
        customers = customers.filter(name__icontains=q)
        invoices = invoices.filter(Q(number__icontains=q) | Q(customer__name__icontains=q))
    selected_customer = None
    if request.GET.get('customer'):
        selected_customer = visible_customers(request.user).filter(pk=request.GET['customer']).first()
    if selected_invoice is None and request.GET.get('invoice'):
        selected_invoice = visible_invoices(request.user).filter(pk=request.GET['invoice']).first()
    if invoice_form is None and selected_invoice is not None:
        invoice_form = _form_from_invoice(selected_invoice)
    products = list(
        InvoiceLine.objects.exclude(product_name='')
        .order_by('product_name')
        .values_list('product_name', flat=True)
        .distinct()
    )
    return {
        'tab': tab,
        'q': q,
        'customers': customers[:30],
        'invoices': invoices[:30],
        'selected_customer': selected_customer,
        'selected_invoice': selected_invoice,
        'invoice_form': invoice_form,
        'invoice_errors': invoice_errors or [],
        'experts': _experts_for(request.user, selected_invoice),
        'products': products,
        'settlements': SETTLEMENTS,
        'pay_methods': PAY_METHODS,
        'check_states': CHECK_STATES,
    }


@page_required('edit')
def editor(request):
    return render(request, 'panel/edit.html', _context(request))


@require_POST
@page_required('edit')
def save_customer(request):
    customer = get_object_or_404(visible_customers(request.user), pk=request.POST.get('id'))
    customer.phone = request.POST.get('phone', '').strip()
    customer.customer_type = request.POST.get('customer_type', '').strip()
    customer.city = request.POST.get('city', '').strip()
    customer.address = request.POST.get('address', '').strip()
    customer.save()
    messages.success(request, 'اطلاعات مشتری ذخیره شد.')
    return redirect(f"/edit/?tab=customers&customer={customer.pk}")


@require_POST
@page_required('edit')
def save_invoice(request):
    invoice = get_object_or_404(visible_invoices(request.user), pk=request.POST.get('id'))
    experts = _experts_for(request.user, invoice)
    form = _form_from_post(request, invoice)
    cleaned, errors = _clean_invoice(request, invoice, form, experts)
    if errors or cleaned['sold_on'] is None:
        return render(request, 'panel/edit.html', _context(
            request,
            selected_invoice=invoice,
            invoice_form=form,
            invoice_errors=errors or ['فاکتور ذخیره نشد.'],
            tab='invoices',
        ))
    try:
        with transaction.atomic():
            _apply_invoice(invoice, cleaned)
    except IntegrityError:
        return render(request, 'panel/edit.html', _context(
            request,
            selected_invoice=invoice,
            invoice_form=form,
            invoice_errors=['این شماره فاکتور قبلاً ثبت شده است.'],
            tab='invoices',
        ))
    messages.success(request, 'فاکتور ذخیره شد.')
    return redirect(f"/edit/?tab=invoices&invoice={invoice.pk}")


@require_POST
@page_required('edit')
def delete_invoice(request):
    invoice = get_object_or_404(visible_invoices(request.user), pk=request.POST.get('id'))
    number = invoice.number
    invoice.delete()
    messages.success(request, f'فاکتور {number} حذف شد.')
    return redirect('/edit/?tab=invoices')
