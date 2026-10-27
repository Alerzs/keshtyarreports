"""شِمای اعتبارسنجی مشتری — همان گروه‌های فرم اعلام فروش PHP.

فیلدها اختیاری‌اند. نبودشان جلوی ثبت را نمی‌گیرد؛ فقط درصد تکمیل
و هشدارهای اعتبار را پایین می‌آورد.
"""

CREDIT_SCHEMA = [
    {
        'k': 'identity',
        't': 'هویت و اطلاعات فردی',
        'd': 'آنچه روی کارت ملی و شناسنامه نوشته شده',
        'fields': [
            {'k': 'fullName', 't': 'نام و نام خانوادگی (طبق کارت ملی)', 'type': 'text'},
            {'k': 'fatherName', 't': 'نام پدر', 'type': 'text'},
            {'k': 'nationalId', 't': 'کد ملی', 'type': 'digits', 'max': 10, 'ph': '۱۰ رقم', 'hint': 'صحت آن خودکار بررسی می‌شود'},
            {'k': 'birthDate', 't': 'تاریخ تولد', 'type': 'date'},
        ],
    },
    {
        'k': 'contact',
        't': 'تماس و نشانی',
        'd': 'راه‌های رسیدن به مشتری وقتی شماره‌ی اصلی جواب نمی‌دهد',
        'fields': [
            {'k': 'landline', 't': 'تلفن ثابت', 'type': 'digits', 'max': 11, 'ph': '۰۲۱…'},
            {'k': 'altPhone', 't': 'شماره تماس دوم', 'type': 'digits', 'max': 11, 'ph': '۰۹…'},
            {'k': 'emergency', 't': 'تماس اضطراری (نام و شماره)', 'type': 'text', 'ph': 'مثلاً: حسن رضایی ۰۹۱۲…'},
            {'k': 'postalCode', 't': 'کد پستی', 'type': 'digits', 'max': 10, 'ph': '۱۰ رقم'},
            {'k': 'province', 't': 'استان', 'type': 'text'},
            {'k': 'residence', 't': 'وضعیت محل سکونت', 'type': 'select', 'opts': ['ملکی', 'استیجاری', 'منزل پدری', 'سازمانی', 'سایر']},
            {'k': 'mapLink', 't': 'لینک موقعیت مکانی', 'type': 'text', 'hint': 'گوگل‌مپ یا نشان', 'wide': True},
        ],
    },
    {
        'k': 'business',
        't': 'کسب‌وکار و درآمد',
        'd': 'توان مالی مشتری از همین‌جا برآورد می‌شود',
        'fields': [
            {'k': 'businessName', 't': 'نام فروشگاه / واحد', 'type': 'text'},
            {'k': 'businessRole', 't': 'سمت', 'type': 'select', 'opts': ['مالک', 'شریک', 'مدیر', 'اجاره‌دار', 'کارمند']},
            {'k': 'businessYears', 't': 'سابقه فعالیت (سال)', 'type': 'int'},
            {'k': 'licenseNo', 't': 'شماره جواز کسب / پروانه', 'type': 'text'},
            {'k': 'farmArea', 't': 'سطح زیر کشت / متراژ گلخانه', 'type': 'text', 'ph': 'مثلاً ۳ هکتار یا ۱۲۰۰ متر'},
            {'k': 'cropTypes', 't': 'محصولات / زمینه فعالیت', 'type': 'text'},
        ],
    },
    {
        'k': 'banking',
        't': 'وضعیت بانکی و اعتباری',
        'd': 'مهم‌ترین بخش امتیاز — سابقه‌ی چک برگشتی بیشترین وزن را دارد',
        'fields': [
            {'k': 'mainBank', 't': 'بانک اصلی', 'type': 'text'},
            {'k': 'accountNo', 't': 'شماره حساب', 'type': 'digits', 'max': 20},
            {'k': 'iban', 't': 'شماره شبا', 'type': 'text', 'ph': 'IR…', 'hint': '۲۴ رقم بعد از IR'},
            {'k': 'creditRank', 't': 'رتبه اعتباری', 'type': 'select', 'opts': ['A1', 'A2', 'B1', 'B2', 'C1', 'C2', 'D1', 'D2', 'E1', 'E2', 'نامشخص']},
            {'k': 'bouncedCheck', 't': 'سابقه چک برگشتی', 'type': 'select', 'opts': ['ندارد', 'دارد (تسویه شده)', 'دارد (باز)', 'نامشخص']},
            {'k': 'bouncedCount', 't': 'تعداد چک برگشتی', 'type': 'int'},
            {'k': 'bouncedAmount', 't': 'مبلغ چک‌های برگشتی (تومان)', 'type': 'money'},
            {'k': 'bankDebt', 't': 'مانده تسهیلات / بدهی بانکی', 'type': 'money'},
            {'k': 'loanInstall', 't': 'قسط ماهانه تسهیلات', 'type': 'money'},
            {'k': 'inquiryDate', 't': 'تاریخ استعلام', 'type': 'date'},
            {'k': 'disputeHistory', 't': 'سابقه اختلاف یا شکایت', 'type': 'select', 'opts': ['ندارد', 'دارد', 'نامشخص']},
            {'k': 'historyNote', 't': 'توضیحات اختلاف', 'type': 'textarea', 'wide': True},
        ],
    },
]

GUARANTEE_TYPES = ['چک صیادی', 'سفته', 'ضامن معتبر', 'وثیقه ملکی', 'ضمانت‌نامه بانکی', 'قرارداد رسمی', 'سایر']
REFERENCE_RELATIONS = ['تامین‌کننده', 'همکار صنفی', 'مشتری او', 'بستگان', 'همسایه کسب‌وکار', 'سایر']
CREDIT_DOCS = [
    'کپی کارت ملی', 'کپی شناسنامه', 'جواز کسب / پروانه', 'سند مالکیت', 'اجاره‌نامه',
    'گردش حساب بانکی', 'نمونه چک', 'عکس محل کسب', 'فرم تعهد امضاشده', 'برگه استعلام اعتباری',
]
BANKS = [
    'ملی', 'ملت', 'صادرات', 'تجارت', 'سپه', 'کشاورزی', 'مسکن', 'رفاه کارگران', 'پارسیان',
    'پاسارگاد', 'سامان', 'سینا', 'اقتصاد نوین', 'شهر', 'دی', 'آینده', 'گردشگری', 'کارآفرین',
    'صنعت و معدن', 'توسعه صادرات', 'پست بانک', 'مهر ایران', 'رسالت', 'خاورمیانه',
]

SETTLEMENTS = ['نقدی', 'قسطی']
CUST_TYPES = ['فروشگاه‌دار', 'کشاورز', 'گلخانه‌دار']
PAY_METHODS = ['واریزی به حساب یوسف', 'کارت به کارت', 'شبا']
CHECK_STATES = ['در جریان', 'وصول‌شده', 'برگشتی', 'سررسید گذشته']


def check_status_tone(status):
    """رنگ برچسب وضعیت چک. وصول (با هر املایی) سبز است و برگشتی قرمز."""
    compact = (status or '').replace('\u200c', '').replace(' ', '')
    if compact.startswith('وصول'):
        return 'bg-emerald-50 text-emerald-700'
    if 'برگشت' in compact or compact == 'سررسیدگذشته':
        return 'bg-red-50 text-red-600'
    return 'bg-amber-50 text-amber-700'
INVOICE_STATUSES = ['تکمیل شده', 'در حال پیگیری', 'تسویه نشده', 'معلق', 'لغو شده']

# وزن تکمیل پرونده؛ کد ملی از بقیه سنگین‌تر است.
PROFILE_WEIGHTS = {
    'name': 4, 'phone': 5, 'city': 3, 'address': 5, 'customer_type': 2,
    'nationalId': 6, 'fatherName': 3, 'birthDate': 2, 'fullName': 2,
    'province': 2, 'postalCode': 2,
    'businessName': 2, 'mainBank': 2,
}


def iter_fields():
    for group in CREDIT_SCHEMA:
        for field in group['fields']:
            yield group, field


def profile_percent(customer):
    dossier = customer.dossier or {}
    values = {
        'name': customer.name,
        'phone': customer.phone,
        'city': customer.city,
        'address': customer.address,
        'customer_type': customer.customer_type,
        **{k: dossier.get(k, '') for k in PROFILE_WEIGHTS},
    }
    total = sum(PROFILE_WEIGHTS.values())
    got = 0
    for key, weight in PROFILE_WEIGHTS.items():
        if str(values.get(key) or '').strip():
            got += weight
    return int(round(got * 100 / total)) if total else 0


def missing_profile_fields(customer):
    dossier = customer.dossier or {}
    labels = {f['k']: f['t'] for _g, f in iter_fields()}
    labels.update({
        'name': 'نام مشتری', 'phone': 'شماره تماس', 'city': 'شهر',
        'address': 'نشانی', 'customer_type': 'نوع مشتری',
    })
    missing = []
    for key in PROFILE_WEIGHTS:
        source = customer if key in {'name', 'phone', 'city', 'address', 'customer_type'} else None
        value = getattr(source, key, None) if source is not None else dossier.get(key, '')
        if key == 'customer_type' and source is not None:
            value = customer.customer_type
        if not str(value or '').strip():
            missing.append(labels.get(key, key))
    return missing
