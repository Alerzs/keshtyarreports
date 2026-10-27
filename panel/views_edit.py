from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .access import visible_customers, visible_invoices
from .credit import CHECK_STATES, INVOICE_STATUSES, PAY_METHODS
from .decorators import page_required
from .jalali import parse_jalali, parse_money
from .models import Check, Payment


@page_required('edit')
def editor(request):
    tab = request.GET.get('tab') or 'customers'
    if tab not in {'customers', 'invoices', 'payments', 'checks'}:
        tab = 'customers'
    q = (request.GET.get('q') or '').strip()
    customers = visible_customers(request.user)
    invoices = visible_invoices(request.user)
    if q:
        customers = customers.filter(name__icontains=q)
        invoices = invoices.filter(number__icontains=q) | invoices.filter(customer__name__icontains=q)
    selected_customer = None
    selected_invoice = None
    selected_payment = None
    selected_check = None
    if request.GET.get('customer'):
        selected_customer = visible_customers(request.user).filter(pk=request.GET['customer']).first()
    if request.GET.get('invoice'):
        selected_invoice = visible_invoices(request.user).filter(pk=request.GET['invoice']).first()
    if request.GET.get('payment'):
        selected_payment = Payment.objects.filter(pk=request.GET['payment'], invoice__in=visible_invoices(request.user)).first()
    if request.GET.get('check'):
        selected_check = Check.objects.filter(pk=request.GET['check'], invoice__in=visible_invoices(request.user)).first()
    return render(request, 'panel/edit.html', {
        'tab': tab,
        'q': q,
        'customers': customers[:30],
        'invoices': invoices[:30],
        'payments': Payment.objects.filter(invoice__in=visible_invoices(request.user)).select_related('invoice', 'invoice__customer')[:40],
        'checks': Check.objects.filter(invoice__in=visible_invoices(request.user)).select_related('invoice', 'invoice__customer')[:40],
        'selected_customer': selected_customer,
        'selected_invoice': selected_invoice,
        'selected_payment': selected_payment,
        'selected_check': selected_check,
        'invoice_statuses': INVOICE_STATUSES,
        'pay_methods': PAY_METHODS,
        'check_states': CHECK_STATES,
    })


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
    invoice.settlement = request.POST.get('settlement', invoice.settlement).strip() or invoice.settlement
    invoice.status = request.POST.get('status', invoice.status)
    invoice.note = request.POST.get('note', '')
    invoice.commission_paid = request.POST.get('commission_paid') == '1'
    invoice.save()
    messages.success(request, 'فاکتور ذخیره شد.')
    return redirect(f"/edit/?tab=invoices&invoice={invoice.pk}")


@require_POST
@page_required('edit')
def save_payment(request):
    payment = get_object_or_404(
        Payment.objects.filter(invoice__in=visible_invoices(request.user)), pk=request.POST.get('id'),
    )
    payment.amount = parse_money(request.POST.get('amount'))
    payment.method = request.POST.get('method') or payment.method
    parsed = parse_jalali(request.POST.get('paid_on', ''))
    if parsed:
        payment.paid_on = parsed
    payment.note = request.POST.get('note', '')
    payment.save()
    messages.success(request, 'پرداختی ذخیره شد.')
    return redirect(f"/edit/?tab=payments&payment={payment.pk}")


@require_POST
@page_required('edit')
def save_check(request):
    check = get_object_or_404(
        Check.objects.filter(invoice__in=visible_invoices(request.user)), pk=request.POST.get('id'),
    )
    check.number = request.POST.get('number', '').strip()
    check.amount = parse_money(request.POST.get('amount'))
    check.status = request.POST.get('status') or check.status
    parsed = parse_jalali(request.POST.get('due_on', ''))
    if parsed:
        check.due_on = parsed
    if request.FILES.get('image'):
        check.image = request.FILES['image']
    check.save()
    messages.success(request, 'چک ذخیره شد.')
    return redirect(f"/edit/?tab=checks&check={check.pk}")
