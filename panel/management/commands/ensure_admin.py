import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from panel.perms import set_membership


class Command(BaseCommand):
    help = 'اگر DJANGO_SUPERUSER_USERNAME تازه باشد، یک مدیر کل می‌سازد.'

    def handle(self, *args, **options):
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', '').strip()
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')
        if not username or not password:
            self.stdout.write('DJANGO_SUPERUSER_USERNAME is unset; skipping.')
            return
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f'{username} already exists; password and role left unchanged.')
            return
        user = User(
            username=username,
            email=os.environ.get('DJANGO_SUPERUSER_EMAIL', ''),
            full_name=os.environ.get('DJANGO_SUPERUSER_NAME', 'مدیر کل'),
        )
        user.set_password(password)
        user.save()
        set_membership(user, 'superadmin', True)
        self.stdout.write(self.style.SUCCESS(f'Created superadmin {username}.'))
