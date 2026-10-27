from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.contrib import messages
from django.shortcuts import redirect

from .perms import can_page, perms_for


def page_required(page):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), login_url='login')
            if not can_page(request.user, page):
                messages.error(request, 'به این بخش دسترسی ندارید.')
                if can_page(request.user, 'dashboard'):
                    return redirect('dashboard')
                return redirect('login')
            request.crm = perms_for(request.user)
            return view(request, *args, **kwargs)
        return wrapper
    return decorator
