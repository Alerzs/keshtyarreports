from django.test import Client, TestCase
from django.urls import NoReverseMatch, reverse

from .jalali import parse_jalali
from .models import Check, Customer, Invoice, InvoiceLine, Operator, Payment
from .perms import set_membership


class InvoiceEditTests(TestCase):
    def setUp(self):
        self.user = Operator.objects.create_user(username='boss', password='secret', full_name='مدیر')
        set_membership(self.user, 'manager', False)
        self.client = Client()
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(name='مشتری یک')
        self.other = Customer.objects.create(name='مشتری دو')
        self.invoice = Invoice.objects.create(
            number='1001', customer=self.customer, sold_on='2026-01-01',
            settlement='نقدی', status='تکمیل شده', purchase_amount=800,
        )
        InvoiceLine.objects.create(
            invoice=self.invoice, product_name='کود', qty=2, unit_price=1000, unit_cost=400,
        )
        Payment.objects.create(
            invoice=self.invoice, amount=500, method='کارت به کارت', paid_on='2026-01-02', note='اول',
        )
        self.check = Check.objects.create(
            invoice=self.invoice, number='55', amount=1500, due_on='2026-02-01', status='در جریان', note='ملت',
        )

    def _post(self, **extra):
        data = {
            'id': self.invoice.pk,
            'number': '1001',
            'customer': self.customer.pk,
            'expert': '',
            'sold_on': '1404/10/12',
            'settlement': 'نقدی',
            'status': 'تکمیل شده',
            'note': '',
            'product': ['کود'],
            'qty': ['2'],
            'unit_price': ['1000'],
            'unit_cost': ['400'],
            'pay_amount': [''],
            'pay_method': ['کارت به کارت'],
            'pay_date': [''],
            'pay_note': [''],
            'chk_id': [''],
            'chk_number': [''],
            'chk_amount': [''],
            'chk_date': [''],
            'chk_status': ['در جریان'],
            'chk_note': [''],
        }
        data.update(extra)
        return self.client.post(reverse('edit_invoice') + '?tab=invoices', data)

    def test_payment_and_check_tabs_are_gone(self):
        response = self.client.get(reverse('edit') + '?tab=payments')
        self.assertContains(response, 'ویرایش فاکتورها')
        self.assertNotContains(response, 'ویرایش پرداختی‌ها')
        self.assertNotContains(response, 'ویرایش چک‌ها')
        with self.assertRaises(NoReverseMatch):
            reverse('edit_payment')
        with self.assertRaises(NoReverseMatch):
            reverse('edit_check')

    def test_invoice_form_includes_lines_payments_and_checks(self):
        response = self.client.get(reverse('edit') + f'?tab=invoices&invoice={self.invoice.pk}')
        self.assertContains(response, 'name="product"')
        self.assertContains(response, '<option value="کود" selected>کود</option>')
        self.assertContains(response, 'اقلام فاکتور')
        self.assertContains(response, 'پرداختی‌ها')
        self.assertContains(response, 'name="chk_id"')
        self.assertContains(response, 'حذف فاکتور')
        self.assertContains(response, 'مشتری یک')
        self.assertNotContains(response, 'name="customer"')
        self.assertNotContains(response, 'name="status"')
        self.assertContains(response, 'value="55"')

    def test_full_edit_replaces_lines_payments_and_keeps_check(self):
        response = self._post(
            customer=self.other.pk,
            settlement='قسطی',
            status='در حال پیگیری',
            note='اصلاح شد',
            product=['کود', 'سم'],
            qty=['2', '1'],
            unit_price=['1500', '800'],
            unit_cost=['400', '100'],
            pay_amount=['700'],
            pay_method=['شبا'],
            pay_date=['1404/10/13'],
            pay_note=['دوم'],
            chk_id=[str(self.check.pk), ''],
            chk_number=['55', '77'],
            chk_amount=['1600', '200'],
            chk_date=['1404/11/01', '1404/12/01'],
            chk_status=['وصول‌شده', 'در جریان'],
            chk_note=['ملت', 'جدید'],
        )
        self.assertEqual(response.status_code, 302)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.customer_id, self.customer.pk)
        self.assertEqual(self.invoice.settlement, 'قسطی')
        self.assertEqual(self.invoice.status, 'تکمیل شده')
        self.assertEqual(self.invoice.note, 'اصلاح شد')
        self.assertEqual(self.invoice.sold_on, parse_jalali('1404/10/12'))
        self.assertEqual(self.invoice.sale_amount, 3800)
        self.assertEqual(self.invoice.purchase_amount, 900)
        self.assertEqual(
            list(self.invoice.lines.order_by('id').values_list('product_name', 'unit_price')),
            [('کود', 1500), ('سم', 800)],
        )
        payment = self.invoice.payments.get()
        self.assertEqual((payment.amount, payment.method, payment.note), (700, 'شبا', 'دوم'))
        kept = Check.objects.get(pk=self.check.pk)
        self.assertEqual((kept.amount, kept.status, kept.number), (1600, 'وصول‌شده', '55'))
        self.assertTrue(self.invoice.checks.filter(number='77', amount=200).exists())

    def test_covered_sale_becomes_settled(self):
        response = self._post(
            pay_amount=['500'],
            pay_method=['شبا'],
            pay_date=['1404/10/13'],
            pay_note=['پیش'],
            chk_id=[str(self.check.pk)],
            chk_number=['55'],
            chk_amount=['1500'],
            chk_date=['1404/11/01'],
            chk_status=['وصول‌شده'],
            chk_note=['ملت'],
        )
        self.assertEqual(response.status_code, 302)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, 'تسویه شده')

    def test_uncovered_settled_invoice_becomes_partial(self):
        self.invoice.status = 'تسویه شده'
        self.invoice.save(update_fields=['status'])
        response = self._post()
        self.assertEqual(response.status_code, 302)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, 'تسویه ناقص')

    def test_cancelled_invoice_stays_cancelled_when_covered(self):
        self.invoice.status = 'لغو شده'
        self.invoice.save(update_fields=['status'])
        response = self._post(
            pay_amount=['2000'],
            pay_method=['شبا'],
            pay_date=['1404/10/13'],
            pay_note=['کامل'],
        )
        self.assertEqual(response.status_code, 302)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, 'لغو شده')

    def test_clearing_rows_removes_payments_and_checks(self):
        response = self._post()
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.invoice.payments.exists())
        self.assertFalse(self.invoice.checks.exists())
        self.assertEqual(self.invoice.lines.count(), 1)

    def test_installment_without_check_is_rejected(self):
        response = self._post(settlement='قسطی')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'فروش قسطی حداقل یک چک می‌خواهد')
        self.assertTrue(Check.objects.filter(pk=self.check.pk).exists())
        self.assertTrue(self.invoice.payments.filter(amount=500).exists())

    def test_delete_invoice_removes_lines_payments_and_checks(self):
        response = self.client.post(reverse('edit_invoice_delete'), {'id': self.invoice.pk})
        self.assertRedirects(response, '/edit/?tab=invoices')
        self.assertFalse(Invoice.objects.filter(pk=self.invoice.pk).exists())
        self.assertFalse(InvoiceLine.objects.filter(invoice_id=self.invoice.pk).exists())
        self.assertFalse(Payment.objects.filter(invoice_id=self.invoice.pk).exists())
        self.assertFalse(Check.objects.filter(invoice_id=self.invoice.pk).exists())
