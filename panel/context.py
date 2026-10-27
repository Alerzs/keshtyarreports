from .perms import perms_for


def money_unit_of(request):
    unit = request.COOKIES.get('money_unit', 'auto')
    return unit if unit in {'auto', 'million', 'billion'} else 'auto'


def panel(request):
    unit = money_unit_of(request)
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'money_unit': unit}
    meta = perms_for(user)
    return {
        'crm_pages': meta['pages'],
        'crm_tabs': meta['tabs'],
        'crm_scope': meta['scope'],
        'crm_role_label': meta['label'],
        'money_unit': unit,
    }
