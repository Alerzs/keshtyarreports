from django.test import Client, TestCase
from django.urls import reverse

from .perms import set_membership
from .models import Operator


class CommissionAccessTests(TestCase):
    def test_manager_without_finance_opens_paid_commissions(self):
        user = Operator.objects.create_user(username='chief', password='secret', full_name='مدیر')
        set_membership(user, 'manager', False)
        client = Client()
        client.force_login(user)
        response = client.get(reverse('commissions') + '?paid=yes')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'پورسانت')

    def test_finance_specialist_keeps_commissions(self):
        user = Operator.objects.create_user(username='pay', password='secret', full_name='مالی')
        set_membership(user, 'specialist', True)
        client = Client()
        client.force_login(user)
        response = client.get(reverse('commissions'))
        self.assertEqual(response.status_code, 200)

    def test_specialist_without_finance_cannot_open_commissions(self):
        user = Operator.objects.create_user(username='seller', password='secret', full_name='کارشناس')
        set_membership(user, 'specialist', False)
        client = Client()
        client.force_login(user)
        response = client.get(reverse('commissions') + '?paid=yes')
        self.assertEqual(response.status_code, 302)

    def test_overview_card_links_to_paid_commissions(self):
        user = Operator.objects.create_user(username='boss', password='secret', full_name='مدیر کل')
        set_membership(user, 'manager', False)
        client = Client()
        client.force_login(user)
        response = client.get(reverse('dashboard') + '?tab=overview')
        self.assertContains(response, 'پورسانت‌های پرداخت‌شده')
        self.assertContains(response, reverse('commissions') + '?paid=yes')
