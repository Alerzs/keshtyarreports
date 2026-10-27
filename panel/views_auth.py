from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .perms import can_page


def _home_for(user):
    if user.role == 'superadmin' and can_page(user, 'users'):
        return redirect('users')
    return redirect('dashboard')


@require_http_methods(['GET', 'POST'])
def login_view(request):
    if request.user.is_authenticated:
        return _home_for(request.user)
    error = ''
    username = ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        if not username or not password:
            error = 'لطفاً اطلاعات هر دو فیلد را وارد کنید.'
        else:
            user = authenticate(request, username=username, password=password)
            if user is None or not user.is_active:
                error = 'نام کاربری یا رمز عبور اشتباه است.'
            else:
                login(request, user)
                return _home_for(user)
    return render(request, 'panel/login.html', {'error': error, 'username': username})


def logout_view(request):
    logout(request)
    messages.success(request, 'از سامانه خارج شدید.')
    return redirect('login')
