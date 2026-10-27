from django.db.models import Q

from .models import Customer, Invoice, Operator, SaleRequest
from .perms import scope_ids


def visible_operator_qs(user):
    ids = scope_ids(user)
    if ids is None:
        return Operator.objects.all()
    return Operator.objects.filter(pk__in=ids)


def visible_invoices(user):
    qs = Invoice.objects.select_related('customer', 'expert', 'expert__mentor').prefetch_related('lines', 'payments', 'checks')
    ids = scope_ids(user)
    if ids is None:
        return qs
    return qs.filter(expert_id__in=ids)


def visible_customers(user):
    ids = scope_ids(user)
    qs = Customer.objects.select_related('expert')
    if ids is None:
        return qs
    return qs.filter(Q(expert_id__in=ids) | Q(invoices__expert_id__in=ids)).distinct()


def visible_requests(user):
    qs = SaleRequest.objects.select_related('seller', 'reviewed_by')
    ids = scope_ids(user)
    if ids is None:
        return qs
    return qs.filter(seller_id__in=ids)


def seller_choices(user):
    """مدیر فروشنده را انتخاب می‌کند. منتور و کارشناس فقط خودشان ثبت می‌شوند."""
    role = user.role
    if role in {'superadmin', 'manager'}:
        leads = Operator.objects.filter(groups__name__in=['superadmin', 'manager']).values('pk')
        people = list(
            Operator.objects.filter(is_active=True).exclude(expert_name='').exclude(pk__in=leads)
        )
        people += list(
            Operator.objects.filter(is_active=True, pk__in=leads).exclude(expert_name='').distinct()
        )
        return people
    return [user]
