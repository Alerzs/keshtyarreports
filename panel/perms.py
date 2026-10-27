"""دسترسی نقش‌ها. همان جدول auth.php است تا منتور داده زیرمجموعه را ببیند."""

ADMIN_ROLES = frozenset({'superadmin', 'manager'})
FINANCE_PAGES = ('sales', 'commissions')

ROLE_META = {
    'superadmin': {
        'label': 'مدیر کل سیستم',
        'tabs': ['overview', 'team', 'specialist'],
        'pages': ['dashboard', 'customers', 'edit', 'users', 'requests', 'backups'],
        'scope': 'all',
    },
    'manager': {
        'label': 'مدیر',
        'tabs': ['overview', 'team', 'specialist'],
        'pages': ['dashboard', 'customers', 'edit', 'users', 'requests', 'backups'],
        'scope': 'all',
    },
    'mentor': {
        'label': 'منتور فروش',
        'tabs': ['team', 'specialist'],
        'pages': ['dashboard', 'customers', 'requests'],
        'scope': 'team',
    },
    'specialist': {
        'label': 'کارشناس فروش',
        'tabs': ['specialist'],
        'pages': ['dashboard', 'customers', 'requests'],
        'scope': 'self',
    },
}

ROLE_GROUP_NAMES = ('superadmin', 'manager', 'mentor', 'specialist')
FINANCE_GROUP = 'finance'


def group_names(user):
    cached = getattr(user, '_kr_groups', None)
    if cached is None:
        if not getattr(user, 'pk', None):
            cached = set()
        else:
            cached = {group.name for group in user.groups.all()}
        user._kr_groups = cached
    return cached


def role_of(user):
    names = group_names(user)
    for name in ROLE_GROUP_NAMES:
        if name in names:
            return name
    return 'specialist'


def has_finance(user):
    return FINANCE_GROUP in group_names(user)


def ensure_groups():
    from django.contrib.auth.models import Group
    for name in (*ROLE_GROUP_NAMES, FINANCE_GROUP):
        Group.objects.get_or_create(name=name)


def set_membership(user, role, finance):
    """یک گروه جایگاه و عضویت اختیاری در گروه مالی."""
    from django.contrib.auth.models import Group
    if role not in ROLE_META:
        role = 'specialist'
    ensure_groups()
    current = list(Group.objects.filter(name__in=ROLE_GROUP_NAMES))
    if current:
        user.groups.remove(*current)
    user.groups.add(Group.objects.get(name=role))
    finance_group = Group.objects.get(name=FINANCE_GROUP)
    if finance:
        user.groups.add(finance_group)
    else:
        user.groups.remove(finance_group)
    if hasattr(user, '_kr_groups'):
        del user._kr_groups
    user.is_staff = role == 'superadmin'
    user.is_superuser = role == 'superadmin'
    user.save(update_fields=['is_staff', 'is_superuser'])


def perms_for(user):
    role = role_of(user)
    meta = ROLE_META[role]
    pages = list(meta['pages'])
    tabs = list(meta['tabs'])
    if role in ADMIN_ROLES or has_finance(user):
        if 'finance' not in tabs:
            tabs.append('finance')
        for page in FINANCE_PAGES:
            if page not in pages:
                pages.append(page)
    return {**meta, 'pages': pages, 'tabs': tabs}


def can_page(user, page):
    return page in perms_for(user)['pages']


def can_review(user):
    return role_of(user) in {'superadmin', 'manager'}


def scope_ids(user):
    """None یعنی بدون محدودیت. وگرنه شناسه‌ی اپراتورهایی که این کاربر می‌بیند."""
    meta = perms_for(user)
    if meta['scope'] == 'all':
        return None
    ids = [user.pk]
    if meta['scope'] == 'team':
        ids.extend(user.mentees.filter(is_active=True).values_list('pk', flat=True))
    return ids
