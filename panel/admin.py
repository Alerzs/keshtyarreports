from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .jalali import format_jalali
from .models import (
    Check, Customer, CustomerDocument, CustomerNote, Invoice, InvoiceLine,
    Operator, Payment, SaleDocument, SaleRequest, Snapshot,
)
from .perms import FINANCE_GROUP, ROLE_META

admin.site.site_header = 'مدیریت کشت‌یار'
admin.site.site_title = 'کشت‌یار'
admin.site.index_title = 'داده‌های سامانه'


def money(value):
    return f'{int(value or 0):,}'


class CustomerNoteInline(admin.TabularInline):
    model = CustomerNote
    extra = 0
    autocomplete_fields = ('author',)
    fields = ('kind', 'author', 'body', 'result', 'created_at')
    readonly_fields = ('created_at',)


class CustomerDocumentInline(admin.TabularInline):
    model = CustomerDocument
    extra = 0
    fields = ('doc_type', 'file', 'uploaded_at')
    readonly_fields = ('uploaded_at',)


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


class CheckInline(admin.TabularInline):
    model = Check
    extra = 0


@admin.register(Operator)
class OperatorAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('کشت‌یار', {
            'fields': ('full_name', 'expert_name', 'mentor'),
            'description': 'جایگاه از گروه‌هاست: superadmin، manager، mentor، specialist. مدیر و مدیر کل، و همچنین گروه finance، بخش‌های چک و وصول، فروش‌ها و پورسانت‌ها را می‌بینند.',
        }),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'usable_password', 'password1', 'password2', 'full_name', 'expert_name'),
        }),
        ('دسترسی', {'fields': ('groups', 'is_active', 'is_staff', 'is_superuser')}),
        ('تیم', {'fields': ('mentor',)}),
    )
    list_display = ('username', 'full_name', 'role_label', 'finance_member', 'expert_name', 'mentor', 'is_active')
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'groups')
    search_fields = ('username', 'full_name', 'expert_name', 'email')
    ordering = ('full_name', 'username')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('mentor').prefetch_related('groups')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'mentor':
            kwargs['queryset'] = Operator.objects.filter(groups__name='mentor')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description='جایگاه')
    def role_label(self, obj):
        return ROLE_META[obj.role]['label']

    @admin.display(description='مالی', boolean=True)
    def finance_member(self, obj):
        return FINANCE_GROUP in {group.name for group in obj.groups.all()}


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'customer_type', 'city', 'expert', 'is_lead', 'created_at')
    list_filter = ('is_lead', 'customer_type', 'city')
    search_fields = ('name', 'phone', 'city', 'address', 'expert__full_name', 'expert__username')
    autocomplete_fields = ('expert',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = (CustomerNoteInline, CustomerDocumentInline)
    list_select_related = ('expert',)


@admin.register(CustomerNote)
class CustomerNoteAdmin(admin.ModelAdmin):
    list_display = ('customer', 'kind', 'author', 'created_at')
    list_filter = ('kind', 'created_at')
    search_fields = ('body', 'result', 'customer__name', 'author__full_name')
    autocomplete_fields = ('customer', 'author')
    readonly_fields = ('created_at',)
    list_select_related = ('customer', 'author')


@admin.register(CustomerDocument)
class CustomerDocumentAdmin(admin.ModelAdmin):
    list_display = ('customer', 'doc_type', 'uploaded_at')
    search_fields = ('doc_type', 'customer__name')
    autocomplete_fields = ('customer',)
    readonly_fields = ('uploaded_at',)
    list_select_related = ('customer',)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'number', 'customer', 'expert', 'sold_label', 'settlement', 'status',
        'sale_label', 'profit_label', 'commission_paid',
    )
    list_filter = ('settlement', 'status', 'commission_paid', 'sold_on')
    search_fields = ('number', 'customer__name', 'expert__full_name', 'expert__expert_name', 'note')
    date_hierarchy = 'sold_on'
    autocomplete_fields = ('customer', 'expert')
    readonly_fields = ('created_at', 'profit_label')
    inlines = (InvoiceLineInline, PaymentInline, CheckInline)
    list_select_related = ('customer', 'expert')

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('lines')

    @admin.display(description='تاریخ فروش', ordering='sold_on')
    def sold_label(self, obj):
        return format_jalali(obj.sold_on)

    @admin.display(description='فروش')
    def sale_label(self, obj):
        return money(obj.sale_amount)

    @admin.display(description='سود')
    def profit_label(self, obj):
        return money(obj.profit)


@admin.register(InvoiceLine)
class InvoiceLineAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'product_name', 'qty', 'unit_price', 'unit_cost')
    search_fields = ('product_name', 'invoice__number')
    autocomplete_fields = ('invoice',)
    list_select_related = ('invoice',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'customer_name', 'amount_label', 'method', 'paid_label')
    list_filter = ('method', 'paid_on')
    search_fields = ('invoice__number', 'invoice__customer__name', 'method', 'note')
    date_hierarchy = 'paid_on'
    autocomplete_fields = ('invoice',)
    list_select_related = ('invoice__customer',)

    @admin.display(description='مشتری')
    def customer_name(self, obj):
        return obj.invoice.customer

    @admin.display(description='مبلغ', ordering='amount')
    def amount_label(self, obj):
        return money(obj.amount)

    @admin.display(description='تاریخ', ordering='paid_on')
    def paid_label(self, obj):
        return format_jalali(obj.paid_on)


@admin.register(Check)
class CheckAdmin(admin.ModelAdmin):
    list_display = ('number', 'invoice', 'customer_name', 'amount_label', 'due_label', 'status')
    list_filter = ('status', 'due_on')
    search_fields = ('number', 'invoice__number', 'invoice__customer__name', 'note')
    date_hierarchy = 'due_on'
    autocomplete_fields = ('invoice',)
    list_select_related = ('invoice__customer',)

    @admin.display(description='مشتری')
    def customer_name(self, obj):
        return obj.invoice.customer

    @admin.display(description='مبلغ', ordering='amount')
    def amount_label(self, obj):
        return money(obj.amount)

    @admin.display(description='سررسید', ordering='due_on')
    def due_label(self, obj):
        return format_jalali(obj.due_on)


class SaleDocumentInline(admin.TabularInline):
    model = SaleDocument
    extra = 0
    fields = ('file', 'name', 'uploaded_at')
    readonly_fields = ('uploaded_at',)


@admin.register(SaleRequest)
class SaleRequestAdmin(admin.ModelAdmin):
    list_display = (
        'customer_name', 'seller', 'status', 'incomplete', 'sold_label',
        'settlement', 'sale_label', 'invoice',
    )
    list_filter = ('status', 'incomplete', 'settlement', 'customer_type')
    search_fields = ('customer_name', 'phone', 'city', 'seller__full_name', 'seller__username')
    date_hierarchy = 'sold_on'
    autocomplete_fields = ('seller', 'reviewed_by', 'invoice')
    readonly_fields = ('created_at', 'updated_at', 'sale_label', 'cost_label')
    inlines = (SaleDocumentInline,)
    save_on_top = True
    fieldsets = (
        ('فروش', {'fields': ('seller', 'sold_on', 'settlement', 'status', 'incomplete', 'note')}),
        ('مشتری', {'fields': ('customer_name', 'phone', 'city', 'address', 'customer_type')}),
        ('فاکتور درخواستی', {'fields': ('lines', 'payments', 'checks')}),
        ('اعتبار', {'fields': ('credit', 'guarantees', 'references', 'docs', 'warnings')}),
        ('بررسی', {'fields': ('review_note', 'reviewed_by', 'reviewed_at', 'invoice', 'sale_label', 'cost_label', 'created_at', 'updated_at')}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('seller', 'invoice', 'reviewed_by')

    @admin.display(description='تاریخ فروش', ordering='sold_on')
    def sold_label(self, obj):
        return format_jalali(obj.sold_on)

    @admin.display(description='مبلغ فروش')
    def sale_label(self, obj):
        return money(obj.sale_amount)

    @admin.display(description='بهای تمام‌شده')
    def cost_label(self, obj):
        return money(obj.cost_amount)


@admin.register(Snapshot)
class SnapshotAdmin(admin.ModelAdmin):
    list_display = ('tag', 'rev', 'summary', 'created_label')
    list_filter = ('tag',)
    search_fields = ('tag', 'summary')
    readonly_fields = ('tag', 'rev', 'summary', 'payload', 'created_at')

    @admin.display(description='زمان', ordering='created_at')
    def created_label(self, obj):
        return format_jalali(obj.created_at, with_time=True)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
