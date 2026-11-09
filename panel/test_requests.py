from datetime import date
from unittest.mock import patch

import requests
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .keshttamin import CHECK_SALE_URL, KeshttaminError, send_check_sale
from .models import Customer, Invoice, Operator, SaleRequest
from .perms import set_membership


def _sale(**extra):
    fields = {
        'sold_on': date(2026, 10, 22),
        'settlement': 'قسطی',
        'customer_type': 'کشاورز',
        'customer_name': 'علی رضایی',
        'phone': '09120000000',
        'city': 'کرمان',
        'address': 'رفسنجان',
        'note': 'یادداشت فروش',
        'credit': {'fatherName': 'حسین', 'nationalId': '0012345678'},
        'guarantees': [{'type': 'چک صیادی', 'holder': 'علی رضایی', 'amount': 1500}],
        'references': [{'name': 'رضا', 'relation': 'همکار صنفی', 'phone': '09121111111'}],
        'docs': ['کپی کارت ملی'],
        'lines': [{'product_name': 'کود', 'qty': 2, 'unit_price': 1000, 'unit_cost': 400}],
        'payments': [{'amount': 500, 'method': 'شبا', 'paid_on': '2026-10-22', 'note': 'پیش'}],
        'checks': [{
            'number': '123', 'amount': 1500, 'due_on': '2026-12-01',
            'bank': 'ملت', 'status': 'در جریان',
        }],
    }
    fields.update(extra)
    return fields


class _Response:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@override_settings(KESHTTAMIN_API_KEY='secret', KESHTTAMIN_TIMEOUT=20)
class KeshttaminSendTests(TestCase):
    @patch('panel.keshttamin.requests.post')
    def test_success_posts_utf8_json(self, post):
        post.return_value = _Response(200, {'ok': True, 'id': 9})
        result = send_check_sale({'sale_request_id': 4, 'customer': {'name': 'علی'}})
        self.assertEqual(result['id'], 9)
        args, kwargs = post.call_args
        self.assertEqual(args[0], CHECK_SALE_URL)
        self.assertEqual(CHECK_SALE_URL, 'https://keshttamin.ir/api/keshtyar/check-sales')
        self.assertEqual(kwargs['headers']['X-Api-Key'], 'secret')
        self.assertEqual(kwargs['headers']['Content-Type'], 'application/json; charset=utf-8')
        self.assertIn('علی'.encode('utf-8'), kwargs['data'])
        self.assertFalse(kwargs['allow_redirects'])
        self.assertEqual(kwargs['timeout'], (5, 20))

    @patch('panel.keshttamin.requests.post')
    def test_http_error_is_failure(self, post):
        post.return_value = _Response(422, {'ok': False, 'error': 'بدنه درخواست ناقص است'})
        with self.assertRaises(KeshttaminError):
            send_check_sale({'sale_request_id': 4})

    @patch('panel.keshttamin.requests.post')
    def test_ok_false_is_failure(self, post):
        post.return_value = _Response(200, {'ok': False, 'error': 'رد شد'})
        with self.assertRaises(KeshttaminError):
            send_check_sale({'sale_request_id': 4})

    @patch('panel.keshttamin.requests.post')
    def test_unreadable_body_is_failure(self, post):
        post.return_value = _Response(200, ValueError('bad'))
        with self.assertRaises(KeshttaminError):
            send_check_sale({'sale_request_id': 4})

    @patch('panel.keshttamin.requests.post', side_effect=requests.ConnectionError('down'))
    def test_connection_error_is_failure(self, post):
        with self.assertRaises(KeshttaminError):
            send_check_sale({'sale_request_id': 4})
        post.assert_called_once()

    @override_settings(KESHTTAMIN_API_KEY='')
    @patch('panel.keshttamin.requests.post')
    def test_missing_key_does_not_send(self, post):
        with self.assertRaises(KeshttaminError):
            send_check_sale({'sale_request_id': 4})
        post.assert_not_called()


class RequestListPaginationTests(TestCase):
    def setUp(self):
        self.admin = Operator.objects.create_user(username='boss', password='secret', full_name='مدیر')
        set_membership(self.admin, 'manager', False)
        self.seller = Operator.objects.create_user(username='seller', password='secret', full_name='فروشنده')
        self.client = Client()
        self.client.force_login(self.admin)
        for index in range(21):
            SaleRequest.objects.create(seller=self.seller, **_sale(customer_name=f'مشتری {index:02d}'))

    def test_lists_twenty_per_page(self):
        first = self.client.get(reverse('requests'))
        self.assertEqual(len(first.context['requests']), 20)
        self.assertContains(first, 'بعدی')
        second = self.client.get(reverse('requests') + '?status=all&page=2')
        self.assertEqual(len(second.context['requests']), 1)
        self.assertContains(second, 'قبلی')
        pending = self.client.get(reverse('requests') + '?status=pending&page=2')
        self.assertEqual(len(pending.context['requests']), 1)
        self.assertContains(pending, 'status=pending&page=1')


class SaleApprovalTests(TestCase):
    def setUp(self):
        self.seller = Operator.objects.create_user(username='seller', password='secret', full_name='فروشنده')
        self.admin = Operator.objects.create_user(username='boss', password='secret', full_name='مدیر')
        set_membership(self.admin, 'manager', False)
        self.client = Client()
        self.client.force_login(self.admin)
        self.req = SaleRequest.objects.create(seller=self.seller, **_sale())

    def _approve(self):
        return self.client.post(
            reverse('request_review', args=[self.req.pk]),
            {'action': 'approve', 'review_note': 'تایید شد'},
            follow=True,
        )

    @patch('panel.views_requests.send_check_sale', return_value={'ok': True})
    def test_check_sale_is_approved_only_after_send(self, send):
        response = self._approve()
        self.assertContains(response, 'به کشت‌تأمین ارسال شد')
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, 'approved')
        self.assertIsNotNone(self.req.invoice_id)
        payload = send.call_args.args[0]
        self.assertEqual(payload, {
            'sale_amount': 2000,
            'check_count': 1,
            'check_due_dates': ['2026-12-01'],
        })

    @patch('panel.views_requests.send_check_sale', side_effect=KeshttaminError('ارتباط با کشت‌تأمین برقرار نشد.'))
    def test_failed_send_keeps_sale_pending(self, send):
        response = self._approve()
        self.assertContains(response, 'اعلام فروش تایید نشد')
        self.assertContains(response, 'ارتباط با کشت‌تأمین برقرار نشد')
        send.assert_called_once()
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, 'pending')
        self.assertIsNone(self.req.invoice_id)
        self.assertEqual(Invoice.objects.count(), 0)
        self.assertFalse(Customer.objects.filter(name='علی رضایی').exists())

    @patch('panel.views_requests.send_check_sale')
    def test_cash_sale_skips_keshttamin(self, send):
        self.req.settlement = 'نقدی'
        self.req.checks = []
        self.req.save(update_fields=['settlement', 'checks'])
        response = self._approve()
        self.assertContains(response, 'فروش تایید شد')
        send.assert_not_called()
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, 'approved')
        self.assertEqual(self.req.invoice.settlement, 'نقدی')
