"""بیکار ماندن ۱۵ دقیقه‌ای همان قفل نسخه‌ی PHP است."""
import time

from django.contrib.auth import logout
from django.shortcuts import redirect


class IdleTimeoutMiddleware:
    TIMEOUT = 15 * 60

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now = time.time()
            last = request.session.get('last_touch')
            if last and now - float(last) > self.TIMEOUT:
                logout(request)
                return redirect('login')
            request.session['last_touch'] = now
        return self.get_response(request)
