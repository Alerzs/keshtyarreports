"""پشتیبان بعد از هر نوشتن. بازگردانی، وضعیت فعلی را هم قبل از جایگزینی نگه می‌دارد."""
from django.db import transaction

from .models import Customer, Operator, SaleRequest, Snapshot
from .perms import FINANCE_GROUP, set_membership

MAX_SNAPSHOTS = 15


def _next_rev(tag):
    last = Snapshot.objects.filter(tag=tag).order_by('-rev').first()
    return (last.rev if last else 0) + 1


def summarize_users():
    rows = list(Operator.objects.prefetch_related('groups'))
    counts = {}
    for row in rows:
        counts[row.role] = counts.get(row.role, 0) + 1
    labels = {
        'superadmin': 'مدیر کل', 'manager': 'مدیر', 'mentor': 'منتور', 'specialist': 'کارشناس',
    }
    parts = [f'{counts[k]} {labels[k]}' for k in labels if counts.get(k)]
    return f'{len(rows)} حساب — ' + ('، '.join(parts) if parts else 'بدون حساب')


def summarize_requests():
    total = SaleRequest.objects.count()
    pending = SaleRequest.objects.filter(status='pending').count()
    return f'{total} درخواست — {pending} در انتظار'


def summarize_customers():
    total = Customer.objects.count()
    leads = Customer.objects.filter(is_lead=True).count()
    return f'{total} پرونده — {leads} سرنخ'


def dump_users():
    return [
        {
            'username': u.username,
            'full_name': u.full_name,
            'groups': [group.name for group in u.groups.all()],
            'expert_name': u.expert_name,
            'mentor': u.mentor.username if u.mentor_id else '',
            'is_active': u.is_active,
            'password': u.password,
            'is_staff': u.is_staff,
            'is_superuser': u.is_superuser,
        }
        for u in Operator.objects.select_related('mentor').prefetch_related('groups')
    ]


def dump_customers():
    return [
        {
            'name': c.name,
            'phone': c.phone,
            'customer_type': c.customer_type,
            'city': c.city,
            'address': c.address,
            'is_favorite': c.is_favorite,
            'is_lead': c.is_lead,
            'expert': c.expert.username if c.expert_id else '',
            'dossier': c.dossier or {},
        }
        for c in Customer.objects.select_related('expert')
    ]


def dump_requests():
    payload = []
    for req in SaleRequest.objects.select_related('seller'):
        payload.append({
            'seller': req.seller.username if req.seller_id else '',
            'sold_on': req.sold_on.isoformat(),
            'settlement': req.settlement,
            'customer_type': req.customer_type,
            'customer_name': req.customer_name,
            'phone': req.phone,
            'city': req.city,
            'address': req.address,
            'note': req.note,
            'status': req.status,
            'incomplete': req.incomplete,
            'credit': req.credit,
            'guarantees': req.guarantees,
            'references': req.references,
            'docs': req.docs,
            'review_note': req.review_note,
            'lines': req.lines or [],
            'payments': req.payments or [],
            'checks': req.checks or [],
        })
    return payload


def prune_snapshots(tag, keep=MAX_SNAPSHOTS):
    """از هر بخش فقط جدیدترین نسخه‌ها می‌مانند."""
    qs = Snapshot.objects.filter(tag=tag)
    if qs.count() <= keep:
        return
    keep_ids = list(qs.order_by('-rev', '-id').values_list('pk', flat=True)[:keep])
    qs.exclude(pk__in=keep_ids).delete()


def take_snapshot(tag, manual=False):
    builders = {
        'users': (dump_users, summarize_users),
        'requests': (dump_requests, summarize_requests),
        'customers': (dump_customers, summarize_customers),
    }
    dump, summary = builders[tag]
    prefix = 'پشتیبان دستی — ' if manual else ''
    with transaction.atomic():
        snap = Snapshot.objects.create(
            tag=tag,
            rev=_next_rev(tag),
            summary=prefix + summary(),
            payload=dump(),
        )
        prune_snapshots(tag)
    return snap


def _restore_users(payload, actor):
    keep = actor.username
    mentors = {}
    for row in payload:
        user, _created = Operator.objects.update_or_create(
            username=row['username'],
            defaults={
                'full_name': row.get('full_name', ''),
                'expert_name': row.get('expert_name', ''),
                'is_active': row.get('is_active', True),
                'password': row.get('password') or '',
            },
        )
        names = row.get('groups')
        if names is None:
            names = [row.get('role') or 'specialist']
        role = next((name for name in ('superadmin', 'manager', 'mentor', 'specialist') if name in names), 'specialist')
        set_membership(user, role, FINANCE_GROUP in names)
        mentors[user.username] = row.get('mentor') or ''
    names = {row['username'] for row in payload}
    names.add(keep)
    Operator.objects.exclude(username__in=names).delete()
    by_name = {u.username: u for u in Operator.objects.all()}
    for username, mentor_name in mentors.items():
        user = by_name.get(username)
        if not user:
            continue
        user.mentor = by_name.get(mentor_name) if mentor_name else None
        user.save(update_fields=['mentor'])


def _restore_customers(payload):
    Customer.objects.all().delete()
    by_name = {u.username: u for u in Operator.objects.all()}
    for row in payload:
        Customer.objects.create(
            name=row['name'],
            phone=row.get('phone', ''),
            customer_type=row.get('customer_type', ''),
            city=row.get('city', ''),
            address=row.get('address', ''),
            is_favorite=row.get('is_favorite', False),
            is_lead=row.get('is_lead', False),
            expert=by_name.get(row.get('expert') or ''),
            dossier=row.get('dossier') or {},
        )


def _restore_requests(payload):
    SaleRequest.objects.all().delete()
    by_name = {u.username: u for u in Operator.objects.all()}
    for row in payload:
        seller = by_name.get(row.get('seller') or '')
        if seller is None and row.get('seller_name'):
            legacy = row['seller_name']
            seller = next((op for op in by_name.values() if op.expert_name == legacy or op.full_name == legacy), None)
        req = SaleRequest.objects.create(
            seller=seller,
            sold_on=row['sold_on'],
            settlement=row.get('settlement', 'نقدی'),
            customer_type=row.get('customer_type', ''),
            customer_name=row.get('customer_name', ''),
            phone=row.get('phone', ''),
            city=row.get('city', ''),
            address=row.get('address', ''),
            note=row.get('note', ''),
            status=row.get('status', 'pending'),
            incomplete=row.get('incomplete', False),
            credit=row.get('credit') or {},
            guarantees=row.get('guarantees') or [],
            references=row.get('references') or [],
            docs=row.get('docs') or [],
            review_note=row.get('review_note', ''),
            lines=row.get('lines') or [],
            payments=row.get('payments') or [],
            checks=row.get('checks') or [],
        )


@transaction.atomic
def restore_snapshot(snapshot, actor):
    """وضعیت فعلی قبل از جایگزینی پشتیبان می‌شود تا بازگردانی خودش برگشت‌پذیر بماند."""
    take_snapshot(snapshot.tag)
    if snapshot.tag == 'users':
        _restore_users(snapshot.payload, actor)
    elif snapshot.tag == 'customers':
        _restore_customers(snapshot.payload)
    elif snapshot.tag == 'requests':
        _restore_requests(snapshot.payload)
    else:
        raise ValueError('این نسخه قابل بازگردانی نیست.')
