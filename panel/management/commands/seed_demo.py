from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from panel.backup import take_snapshot
from panel.perms import set_membership
from panel.models import (
    Check, Customer, CustomerNote, Invoice, InvoiceLine, Operator, Payment, SaleRequest,
)


class Command(BaseCommand):
    help = 'داده‌ی نمونه‌ی CRM کشت‌یار را می‌سازد.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true')

    def handle(self, *args, **options):
        if Operator.objects.filter(username='NOTadmin').exists() and not options['force']:
            self.stdout.write('Demo data already exists. Re-run with --force to rebuild.')
            return
        if options['force']:
            self._wipe()
        self._build()
        take_snapshot('users')
        take_snapshot('customers')
        take_snapshot('requests')
        self.stdout.write(self.style.SUCCESS('Demo data ready.'))
        self.stdout.write('CRM login: NOTadmin / Keshtyar@1405   admin / Keshtyar@1405')
        self.stdout.write('Seller: ali / Seller@1405    Mentor: sara / Mentor@1405')
        self.stdout.write('Finance group: NOTadmin and admin')

    def _wipe(self):
        SaleRequest.objects.all().delete()
        Check.objects.all().delete()
        Payment.objects.all().delete()
        Invoice.objects.all().delete()
        Customer.objects.all().delete()
        Operator.objects.all().delete()

    def _user(self, username, password, full_name, role, expert='', mentor=None, active=True, finance=False):
        user = Operator(
            username=username, full_name=full_name, expert_name=expert,
            mentor=mentor, is_active=active,
        )
        user.set_password(password)
        user.save()
        set_membership(user, role, finance)
        return user

    def _build(self):
        root = self._user('NOTadmin', 'Keshtyar@1405', 'مدیر کل سیستم', 'superadmin', finance=True)
        self._user('admin', 'Keshtyar@1405', 'مدیر فروش', 'manager', expert='مدیر فروش', finance=True)
        sara = self._user('sara', 'Mentor@1405', 'سارا احمدی', 'mentor', expert='سارا احمدی')
        ali = self._user('ali', 'Seller@1405', 'علی رضایی', 'specialist', expert='علی رضایی', mentor=sara)
        reza = self._user('reza', 'Seller@1405', 'رضا محمدی', 'specialist', expert='رضا محمدی', mentor=sara)
        maryam = self._user('maryam', 'Seller@1405', 'مریم کاظمی', 'specialist', expert='مریم کاظمی', mentor=sara)
        nima = self._user('nima', 'Seller@1405', 'نیما جعفری', 'specialist', expert='نیما جعفری', mentor=sara)
        self._user('old_user', 'Seller@1405', 'کارشناس سابق', 'specialist', expert='کارشناس سابق', active=False)

        people = [
            ('حسین کشاورز', '09121234001', 'کشاورز', 'مشهد', 'جاده کلات، کیلومتر ۱۲', ali, {'nationalId': '0499370899', 'fatherName': 'احمد', 'cropTypes': 'گندم و جو', 'sayadColor': 'سفید'}),
            ('گلخانه سبز دشت', '09131234002', 'گلخانه‌دار', 'اصفهان', 'خمینی‌شهر، خیابان گل‌ها', maryam, {'businessName': 'سبز دشت', 'staffCount': '8', 'farmArea': '۱۵۰۰ متر'}),
            ('فروشگاه نهاده پارس', '09141234003', 'فروشگاه‌دار', 'تبریز', 'بازار نهاده، پلاک ۱۸', reza, {'businessName': 'نهاده پارس', 'mainBank': 'ملی'}),
            ('مزرعه برزگر', '09151234004', 'کشاورز', 'شیراز', 'مرودشت، روستای کناره', ali, {'fatherName': 'کریم', 'province': 'فارس'}),
            ('تعاونی زیتون', '09161234005', 'فروشگاه‌دار', 'گرگان', 'خیابان ولیعصر', sara, {}),
            ('گلخانه آفتاب', '09171234006', 'گلخانه‌دار', 'یزد', 'اشکذر، جاده تفت', maryam, {'social': 'aftab.gh'}),
            ('باغ پسته کرمان', '09181234007', 'کشاورز', 'کرمان', 'رفسنجان، خیابان بهشتی', reza, {'cropTypes': 'پسته', 'nationalId': '0123456789'}),
            ('کشت و صنعت دز', '09191234008', 'فروشگاه‌دار', 'اهواز', 'کیانپارس، خیابان ۱۶', nima, {}),
            ('نهالستان شمال', '09351234009', 'فروشگاه‌دار', 'رشت', 'فلکه گاز', sara, {'businessYears': '12'}),
            ('مزرعه زعفران', '09361234010', 'کشاورز', 'مشهد', 'تربت حیدریه', ali, {}),
            ('گلخانه دماوند', '09371234011', 'گلخانه‌دار', 'تهران', 'جاده دماوند، کیلومتر ۴۰', maryam, {}),
            ('تعاونی همدان', '09381234012', 'فروشگاه‌دار', 'همدان', 'بلوار مدنی', nima, {}),
        ]
        customers = []
        for name, phone, kind, city, address, expert, dossier in people:
            customers.append(Customer.objects.create(
                name=name, phone=phone, customer_type=kind, city=city, address=address,
                expert=expert,
                dossier=dossier,
            ))
        Customer.objects.create(name='سرنخ: مهدی نادری', phone='09001234013', customer_type='کشاورز', city='زاهدان', address='در انتظار بازدید', expert=ali, is_lead=True)

        catalog = [
            ('کود اوره', 850000, 620000),
            ('کود فسفات', 920000, 700000),
            ('سم کنه‌کش', 1400000, 980000),
            ('بذر گندم پیشگام', 2100000, 1500000),
            ('سیستم آبیاری قطره‌ای', 4800000, 3200000),
            ('نهال پسته', 650000, 400000),
            ('توری سایبان', 1750000, 1100000),
        ]
        plan = [
            (customers[0], ali, date(2026, 10, 4), 'نقدی', 0, True),
            (customers[0], ali, date(2026, 10, 18), 'قسطی', 1, False),
            (customers[3], ali, date(2026, 10, 11), 'نقدی', 3, True),
            (customers[9], ali, date(2026, 9, 16), 'نقدی', 4, True),
            (customers[1], maryam, date(2026, 10, 7), 'قسطی', 4, False),
            (customers[5], maryam, date(2026, 10, 21), 'نقدی', 6, True),
            (customers[10], maryam, date(2026, 8, 12), 'نقدی', 2, True),
            (customers[2], reza, date(2026, 10, 9), 'نقدی', 0, False),
            (customers[6], reza, date(2026, 9, 3), 'قسطی', 5, False),
            (customers[4], sara, date(2026, 10, 2), 'نقدی', 1, True),
            (customers[8], sara, date(2026, 7, 19), 'نقدی', 3, True),
            (customers[7], nima, date(2026, 10, 14), 'نقدی', 2, False),
            (customers[11], nima, date(2026, 6, 8), 'قسطی', 0, False),
            (customers[6], None, date(2026, 5, 20), 'نقدی', 5, False),
        ]
        seq = 1001
        for cust, expert, sold_on, settlement, product_index, paid in plan:
            product, price, cost = catalog[product_index % len(catalog)]
            qty = 40 if product_index in {4, 6} else 80
            sale = price * qty
            invoice = Invoice.objects.create(
                number=f'KY-1405-{seq}', customer=cust, expert=expert,
                sold_on=sold_on, settlement=settlement,
                status='تکمیل شده' if settlement == 'نقدی' else 'در حال پیگیری',
                commission_paid=paid,
                note='فاکتور نمونه‌ی کشت‌یار',
            )
            InvoiceLine.objects.create(invoice=invoice, product_name=product, qty=Decimal(qty), unit_price=price, unit_cost=cost)
            if settlement == 'نقدی':
                Payment.objects.create(invoice=invoice, amount=sale, method='کارت به کارت', paid_on=sold_on)
            else:
                Payment.objects.create(invoice=invoice, amount=sale // 3, method='واریزی به حساب یوسف', paid_on=sold_on)
                Check.objects.create(
                    invoice=invoice, number=f'{seq}18', amount=sale - sale // 3,
                    due_on=date(2026, 11, 15) if seq % 2 else date(2026, 9, 1),
                    status='در جریان' if seq % 2 else 'سررسید گذشته', note='بانک کشاورزی',
                )
            seq += 1
        Check.objects.create(invoice=Invoice.objects.get(number='KY-1405-1001'), number='44821', amount=25000000, due_on=date(2026, 8, 1), status='وصول‌شده')
        Check.objects.create(invoice=Invoice.objects.get(number='KY-1405-1008'), number='90211', amount=18000000, due_on=date(2026, 12, 1), status='برگشتی', note='بانک ملت')

        CustomerNote.objects.create(customer=customers[0], author=ali, kind='call', body='برای کود پاییزه هماهنگ شد.', result='سفارش بعدی هفته‌ی بعد')
        CustomerNote.objects.create(customer=customers[1], author=maryam, kind='visit', body='گلخانه بازدید شد. سیستم آبیاری نیاز به توسعه دارد.', result='پیشنهاد پیش‌فاکتور')

        pending = SaleRequest.objects.create(
            seller=ali, sold_on=date(2026, 10, 22), settlement='قسطی',
            customer_type='کشاورز', customer_name='مزرعه‌ی نمونه شرق', phone='09120001122',
            city='مشهد', address='طرقبه، جاده جاغرق', note='مشتری معرفی تعاونی است.', status='pending',
            credit={'fatherName': 'جواد', 'sayadColor': 'زرد', 'recommend': 'تایید مشروط'},
            lines=[{'product_name': 'بذر گندم پیشگام', 'qty': '20', 'unit_price': 2100000, 'unit_cost': 1500000}],
            checks=[{'number': '77120', 'amount': 28000000, 'due_on': '2026-12-20', 'bank': 'کشاورزی', 'status': 'در جریان'}],
        )
        incomplete = SaleRequest.objects.create(
            seller=nima, sold_on=date(2026, 10, 20), settlement='نقدی',
            customer_type='فروشگاه‌دار', customer_name='فروشگاه ناتمام', phone='09123334455',
            city='اهواز', address='در حال تکمیل', status='pending', incomplete=True,
            lines=[{'product_name': 'سم کنه‌کش', 'qty': '5', 'unit_price': 1400000, 'unit_cost': 980000}],
        )
        rejected = SaleRequest.objects.create(
            seller=reza, sold_on=date(2026, 10, 1), settlement='نقدی',
            customer_type='کشاورز', customer_name='خریدار ردشده', phone='09125556677',
            city='کرمان', address='رفسنجان', status='rejected', review_note='چک برگشتی باز دارد.',
            lines=[{'product_name': 'نهال پسته', 'qty': '100', 'unit_price': 650000, 'unit_cost': 400000}],
            payments=[{'amount': 10000000, 'method': 'شبا', 'paid_on': '2026-10-01', 'note': ''}],
        )
        root.full_name = root.full_name
        root.save()
