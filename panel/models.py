from datetime import date
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models

from .perms import has_finance, role_of


def _as_date(value):
    if isinstance(value, date):
        return value
    text = str(value or '')[:10]
    if not text:
        return None
    return date.fromisoformat(text)


class _Row:
    def __init__(self, data):
        self._data = data

    def __getattr__(self, name):
        if name in self._data:
            return self._data[name]
        raise AttributeError(name)


class Operator(AbstractUser):
    full_name = models.CharField('نام', max_length=120, blank=True)
    expert_name = models.CharField('نام در گزارش فروش', max_length=120, blank=True)
    mentor = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='mentees', verbose_name='منتور',)

    class Meta:
        verbose_name = 'اپراتور'
        verbose_name_plural = 'اپراتورها'

    def __str__(self):
        return self.full_name or self.username

    def report_name(self):
        return (self.expert_name or self.full_name or self.username).strip()

    @property
    def role(self):
        return role_of(self)

    @property
    def in_finance(self):
        return has_finance(self)

    @property
    def status_label(self):
        return 'فعال' if self.is_active else 'غیرفعال'


class Customer(models.Model):
    name = models.CharField('نام', max_length=160)
    phone = models.CharField('تلفن', max_length=20, blank=True)
    customer_type = models.CharField('نوع مشتری', max_length=40, blank=True)
    city = models.CharField('شهر', max_length=80, blank=True)
    address = models.TextField('آدرس', blank=True)
    is_favorite = models.BooleanField('ویژه', default=False)
    is_lead = models.BooleanField('سرنخ', default=False)
    expert = models.ForeignKey(Operator, null=True, blank=True, on_delete=models.SET_NULL, related_name='customers', verbose_name='کارشناس')
    dossier = models.JSONField('پرونده اعتبار', default=dict, blank=True)
    created_at = models.DateTimeField('ایجاد', auto_now_add=True)
    updated_at = models.DateTimeField('به‌روزرسانی', auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'مشتری'
        verbose_name_plural = 'مشتریان'

    def __str__(self):
        return self.name


class CustomerNote(models.Model):
    KIND_CHOICES = [('call', 'گزارش تماس'), ('note', 'یادداشت'), ('visit', 'بازدید حضوری')]
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='notes', verbose_name='مشتری')
    author = models.ForeignKey(Operator, null=True, on_delete=models.SET_NULL, related_name='notes', verbose_name='نویسنده')
    kind = models.CharField('نوع', max_length=12, choices=KIND_CHOICES, default='note')
    body = models.TextField('متن')
    result = models.CharField('نتیجه', max_length=200, blank=True)
    created_at = models.DateTimeField('زمان', auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'یادداشت مشتری'
        verbose_name_plural = 'یادداشت‌های مشتری'

    def __str__(self):
        return f'{self.get_kind_display()} — {self.customer}'


class CustomerDocument(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='documents', verbose_name='مشتری')
    doc_type = models.CharField('نوع مدرک', max_length=80)
    file = models.FileField('فایل', upload_to='customer_docs/%Y/%m/')
    uploaded_at = models.DateTimeField('بارگذاری', auto_now_add=True)

    class Meta:
        verbose_name = 'مدرک مشتری'
        verbose_name_plural = 'مدارک مشتری'

    def __str__(self):
        return f'{self.doc_type} — {self.customer}'


class Invoice(models.Model):
    number = models.CharField('شماره', max_length=40, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='invoices', verbose_name='مشتری')
    expert = models.ForeignKey(
        Operator, null=True, blank=True, on_delete=models.SET_NULL, related_name='invoices', verbose_name='کارشناس',
    )
    sold_on = models.DateField('تاریخ فروش')
    settlement = models.CharField('تسویه', max_length=20, default='نقدی')
    status = models.CharField('وضعیت', max_length=40, default='تکمیل شده')
    note = models.TextField('یادداشت', blank=True)
    purchase_amount = models.BigIntegerField('مبلغ خرید', default=0)
    commission_paid = models.BooleanField('پورسانت پرداخت شده', default=False)
    created_at = models.DateTimeField('ایجاد', auto_now_add=True)

    class Meta:
        ordering = ['-sold_on', '-id']
        verbose_name = 'فاکتور'
        verbose_name_plural = 'فاکتورها'

    def __str__(self):
        return self.number

    def totals(self):
        cached = getattr(self, '_totals', None)
        if cached is None:
            sale = cost = 0
            for line in self.lines.all():
                sale += int(line.qty * line.unit_price)
                cost += int(line.qty * line.unit_cost)
            cached = (sale, cost)
            self._totals = cached
        return cached

    @property
    def sale_amount(self):
        return self.totals()[0]

    @property
    def cost_amount(self):
        return self.totals()[1]

    @property
    def profit(self):
        sale, cost = self.totals()
        return sale - cost

    @property
    def expert_label(self):
        if self.expert_id is None:
            return 'عمومی'
        return self.expert.report_name() or 'عمومی'


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines', verbose_name='فاکتور')
    product_name = models.CharField('کالا', max_length=160)
    qty = models.DecimalField('تعداد', max_digits=10, decimal_places=2, default=1)
    unit_price = models.BigIntegerField('قیمت واحد', default=0)
    unit_cost = models.BigIntegerField('بهای واحد', default=0)

    class Meta:
        verbose_name = 'قلم فاکتور'
        verbose_name_plural = 'اقلام فاکتور'

    def __str__(self):
        return self.product_name


class Payment(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments', verbose_name='فاکتور')
    amount = models.BigIntegerField('مبلغ')
    method = models.CharField('روش', max_length=80)
    paid_on = models.DateField('تاریخ')
    note = models.CharField('یادداشت', max_length=240, blank=True)

    class Meta:
        verbose_name = 'پرداخت'
        verbose_name_plural = 'پرداخت‌ها'

    def __str__(self):
        return f'{self.invoice.number} — {self.amount}'


class Check(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='checks', verbose_name='فاکتور')
    number = models.CharField('شماره چک', max_length=40, blank=True)
    amount = models.BigIntegerField('مبلغ')
    due_on = models.DateField('سررسید')
    status = models.CharField('وضعیت', max_length=40, default='در جریان')
    image = models.FileField('تصویر', upload_to='checks/%Y/%m/', blank=True)
    note = models.CharField('یادداشت', max_length=240, blank=True)

    class Meta:
        verbose_name = 'چک'
        verbose_name_plural = 'چک‌ها'

    def __str__(self):
        return self.number or f'چک {self.pk}'


class SaleRequest(models.Model):
    STATUS = [('pending', 'در انتظار تایید'), ('approved', 'تاییدشده'), ('rejected', 'ردشده')]
    seller = models.ForeignKey(Operator, null=True, on_delete=models.SET_NULL, related_name='sale_requests', verbose_name='فروشنده')
    sold_on = models.DateField('تاریخ فروش')
    settlement = models.CharField('تسویه', max_length=20)
    customer_type = models.CharField('نوع مشتری', max_length=40)
    customer_name = models.CharField('نام مشتری', max_length=160)
    phone = models.CharField('تلفن', max_length=20)
    city = models.CharField('شهر', max_length=80)
    address = models.TextField('آدرس')
    note = models.TextField('یادداشت', blank=True)
    status = models.CharField('وضعیت', max_length=20, choices=STATUS, default='pending')
    incomplete = models.BooleanField('ناقص', default=False)
    credit = models.JSONField('اعتبارسنجی', default=dict, blank=True)
    guarantees = models.JSONField('تضامین', default=list, blank=True)
    references = models.JSONField('معرف‌ها', default=list, blank=True)
    docs = models.JSONField('مدارک', default=list, blank=True)
    warnings = models.JSONField('هشدارها', default=list, blank=True)
    lines = models.JSONField('اقلام', default=list, blank=True)
    payments = models.JSONField('پرداخت‌ها', default=list, blank=True)
    checks = models.JSONField('چک‌ها', default=list, blank=True)
    review_note = models.TextField('یادداشت بررسی', blank=True)
    reviewed_by = models.ForeignKey(
        Operator, null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_requests', verbose_name='بررسی‌کننده',
    )
    reviewed_at = models.DateTimeField('زمان بررسی', null=True, blank=True)
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.SET_NULL, related_name='source_requests', verbose_name='فاکتور')
    created_at = models.DateTimeField('ایجاد', auto_now_add=True)
    updated_at = models.DateTimeField('به‌روزرسانی', auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'درخواست فروش'
        verbose_name_plural = 'درخواست‌های فروش'

    def __str__(self):
        return f'{self.customer_name} — {self.get_status_display()}'

    @property
    def line_list(self):
        return [_Row(row) for row in self.lines or []]

    @property
    def payment_list(self):
        rows = []
        for raw in self.payments or []:
            rows.append(_Row({**raw, 'paid_on': _as_date(raw.get('paid_on'))}))
        return rows

    @property
    def check_list(self):
        rows = []
        for raw in self.checks or []:
            rows.append(_Row({**raw, 'due_on': _as_date(raw.get('due_on'))}))
        return rows

    def _line_totals(self):
        sale = cost = 0
        for raw in self.lines or []:
            qty = Decimal(str(raw.get('qty') or 0))
            sale += int(qty * int(raw.get('unit_price') or 0))
            cost += int(qty * int(raw.get('unit_cost') or 0))
        return sale, cost

    @property
    def sale_amount(self):
        return self._line_totals()[0]

    @property
    def cost_amount(self):
        return self._line_totals()[1]


class SaleDocument(models.Model):
    request = models.ForeignKey(SaleRequest, on_delete=models.CASCADE, related_name='files', verbose_name='درخواست')
    file = models.FileField('فایل', upload_to='sale_docs/%Y/%m/')
    name = models.CharField('نام فایل', max_length=160, blank=True)
    uploaded_at = models.DateTimeField('بارگذاری', auto_now_add=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'مدرک فروش'
        verbose_name_plural = 'مدارک فروش'

    def __str__(self):
        return self.name or self.file.name


class Snapshot(models.Model):
    tag = models.CharField('بخش', max_length=32)
    rev = models.PositiveIntegerField('نسخه')
    summary = models.CharField('خلاصه', max_length=240)
    payload = models.JSONField('داده')
    created_at = models.DateTimeField('زمان', auto_now_add=True)

    class Meta:
        ordering = ['-rev', '-id']
        verbose_name = 'نسخه پشتیبان'
        verbose_name_plural = 'نسخه‌های پشتیبان'

    def __str__(self):
        return f'{self.tag} r{self.rev}'
