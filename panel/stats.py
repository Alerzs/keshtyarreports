"""تجمیع داشبورد از فاکتورهای پایگاه، معادل خواندن شیت در نسخه‌ی PHP."""
from collections import defaultdict
from datetime import date, timedelta

from django.utils import timezone

from .access import visible_invoices
from .jalali import (
    format_day_month,
    format_jalali,
    gregorian_to_jalali,
    month_axis_label,
    month_key,
    month_label,
    month_span,
    month_title,
    to_fa_digits,
)
from .levels import BASE_SALARY, SPECIALIST_LEVELS, level_for, next_level, payout, perks_up_to
from .models import Operator

TICKET_BUCKETS = [
    ('زیر ۵۰ میلیون', 0, 50_000_000),
    ('۵۰ تا ۱۵۰', 50_000_000, 150_000_000),
    ('۱۵۰ تا ۳۰۰', 150_000_000, 300_000_000),
    ('بالای ۳۰۰', 300_000_000, 10**15),
]


def check_is_cleared(status):
    """وصول با هر املایی، از جمله «وصول شد» و «وصول‌شده»."""
    compact = (status or '').replace('\u200c', '').replace(' ', '')
    return compact.startswith('وصول')


def received_of(invoice):
    cash = sum(p.amount for p in invoice.payments.all())
    cleared = sum(c.amount for c in invoice.checks.all() if c.status == 'وصول‌شده')
    return cash + cleared


def outstanding_of(invoice):
    return max(0, invoice.sale_amount - received_of(invoice))


def cash_due_of(invoice):
    """بخشی از فاکتور که نه پرداخت شده و نه با چک پوشش داده شده است."""
    checks = sum(c.amount for c in invoice.checks.all())
    paid = sum(p.amount for p in invoice.payments.all())
    return max(0, int(invoice.sale_amount) - int(checks) - int(paid))


def _range_start(key, today):
    if key == 'month':
        return today.replace(day=1)
    if key == 'quarter':
        return today - timedelta(days=90)
    if key == 'year':
        jy, _jm, _jd = gregorian_to_jalali(today.year, today.month, today.day)
        # اول فروردین همین سال جلالی
        from .jalali import jalali_to_gregorian
        gy, gm, gd = jalali_to_gregorian(jy, 1, 1)
        return date(gy, gm, gd)
    return None


def _month_bounds(range_key):
    """بازه میلادی یک ماه یا «از ماه تا ماه» به شکل ۱۴۰۴/۰۵..۱۴۰۴/۱۱."""
    text = str(range_key or '')
    if '..' in text:
        start_key, end_key = text.split('..', 1)
        start = month_span(start_key)
        end = month_span(end_key)
        if not start or not end:
            return None
        if start[0] > end[0]:
            start, end = end, start
        return start[0], end[1]
    return month_span(text)


def load_invoices(user, range_key):
    today = timezone.localdate()
    rows = [row for row in visible_invoices(user) if row.status != 'لغو شده' and row.sold_on]
    span = _month_bounds(range_key)
    if span:
        start, end = span
        return [row for row in rows if start <= row.sold_on < end]
    start = _range_start(range_key, today)
    if start:
        rows = [row for row in rows if row.sold_on >= start]
    return rows


def period_months(user):
    keys = sorted({
        month_key(row.sold_on)
        for row in visible_invoices(user)
        if row.status != 'لغو شده' and row.sold_on
    })
    return [{'key': key, 'label': month_title(key)} for key in reversed(keys)]


def repeat_customer_ids(user):
    """مشتری وفادار: بیش از یک فاکتور غیرلغو. مستقل از بازه نمودار است."""
    counts = defaultdict(int)
    for row in visible_invoices(user):
        if row.status != 'لغو شده' and row.sold_on:
            counts[row.customer_id] += 1
    return {cid for cid, n in counts.items() if n > 1}


def _split_bucket():
    return {'repeat': 0, 'once': 0}


def _series(bucket, labels):
    repeat = [bucket[label]['repeat'] for label in labels]
    once = [bucket[label]['once'] for label in labels]
    return {
        'labels': list(labels),
        'values': [repeat[i] + once[i] for i in range(len(labels))],
        'repeat': repeat,
        'once': once,
    }


def _fresh_sides():
    return {'repeat': {}, 'once': {}}


def _note_buyer(bucket, customer, amount):
    amount = int(amount or 0)
    if not amount or customer is None:
        return
    row = bucket.get(customer.id)
    if row is None:
        row = {'id': customer.id, 'name': customer.name, 'amount': 0}
        bucket[customer.id] = row
    row['amount'] += amount


def _buyer_rows(bucket):
    rows = list(bucket.values())
    rows.sort(key=lambda row: (-row['amount'], row['name']))
    return rows


def _side_buyers(book, labels):
    return {
        'repeatBuyers': [_buyer_rows(book[label]['repeat']) for label in labels],
        'onceBuyers': [_buyer_rows(book[label]['once']) for label in labels],
    }


def build_dashboard(user, range_key='all', person='', month='all', team_month='all'):
    invoices = load_invoices(user, range_key)
    repeat_ids = repeat_customer_ids(user)

    total_sales = sum(i.sale_amount for i in invoices)
    total_cost = sum(i.cost_amount for i in invoices)
    received = sum(received_of(i) for i in invoices)
    outstanding = sum(outstanding_of(i) for i in invoices)
    check_due = sum(
        int(chk.amount or 0)
        for inv in invoices
        for chk in inv.checks.all()
        if not check_is_cleared(chk.status)
    )
    loyal_count = len({inv.customer_id for inv in invoices if inv.customer_id in repeat_ids})
    cash_sales = sum(i.sale_amount for i in invoices if i.settlement == 'نقدی')
    inst_sales = sum(i.sale_amount for i in invoices if i.settlement == 'قسطی')

    kpis = [
        {'key': 'total', 'label': 'فروش کل', 'value': total_sales, 'note': 'کل مبلغ فاکتورهای ثبت شده', 'tone': 'c1'},
        {'key': 'received', 'label': 'کل دریافتی (نقد/کارت)', 'value': received, 'note': 'ورودی واقعی به حساب‌ها', 'tone': 'c4'},
        {'key': 'outstanding', 'label': 'مطالبات (بدهی مشتریان)', 'value': outstanding, 'note': 'پولی که هنوز وصول نشده', 'tone': 'c3'},
        {'key': 'profit', 'label': 'سود کل ناخالص', 'value': total_sales - total_cost, 'note': 'مابه‌التفاوت فروش و خرید', 'tone': 'c2'},
        {'key': 'count', 'label': 'تعداد فاکتورها', 'value': len(invoices), 'note': 'مجموع سفارشات موفق', 'tone': 'c6', 'plain': True},
        {'key': 'checks', 'label': 'مانده‌های چکی', 'value': check_due, 'note': 'چک‌هایی که هنوز وصول نشده', 'tone': 'c5'},
        {'key': 'loyal', 'label': 'تعداد مشتریان وفادار', 'value': loyal_count, 'note': 'مشتری با بیش از یک فاکتور', 'tone': 'c7', 'plain': True},
    ]

    by_day = defaultdict(lambda: {'sales': 0, 'profit': 0})
    by_month = defaultdict(lambda: {
        'cash': 0, 'inst': 0, 'sales': 0, 'profit': 0,
        'salesRepeat': 0, 'salesOnce': 0, 'profitRepeat': 0, 'profitOnce': 0,
        'cashRepeat': 0, 'cashOnce': 0, 'instRepeat': 0, 'instOnce': 0,
    })
    by_type = defaultdict(_split_bucket)
    by_province = defaultdict(_split_bucket)
    by_product = defaultdict(_split_bucket)
    by_customer = {}
    ticket = {label: _split_bucket() for label, _a, _b in TICKET_BUCKETS}
    ticket_buyers = {label: _fresh_sides() for label, _a, _b in TICKET_BUCKETS}
    type_buyers = defaultdict(_fresh_sides)
    city_buyers = defaultdict(_fresh_sides)
    product_buyers = defaultdict(_fresh_sides)
    sale_buyers = {'نقدی': _fresh_sides(), 'قسطی': _fresh_sides()}
    month_buyers = defaultdict(lambda: {
        'salesRepeat': {}, 'salesOnce': {},
        'profitRepeat': {}, 'profitOnce': {},
        'cashRepeat': {}, 'cashOnce': {},
        'instRepeat': {}, 'instOnce': {},
    })
    methods = defaultdict(_split_bucket)
    method_buyers = defaultdict(_fresh_sides)
    by_expert = defaultdict(lambda: {
        'name': '', 'mentor_id': None, 'mentor_name': '',
        'sales': 0, 'profit': 0, 'deals': 0, 'months': defaultdict(int),
        'salesRepeat': 0, 'salesOnce': 0, 'profitRepeat': 0, 'profitOnce': 0,
        'dealsRepeat': 0, 'dealsOnce': 0,
    })
    money = {
        'received': _split_bucket(),
        'outstanding': _split_bucket(),
        'cash': _split_bucket(),
        'inst': _split_bucket(),
    }
    money_buyers = {
        'received': _fresh_sides(),
        'outstanding': _fresh_sides(),
    }

    for inv in invoices:
        loyal = inv.customer_id in repeat_ids
        side = 'repeat' if loyal else 'once'
        side_cap = 'Repeat' if loyal else 'Once'
        buyer = inv.customer
        by_day[inv.sold_on.isoformat()]['sales'] += inv.sale_amount
        by_day[inv.sold_on.isoformat()]['profit'] += inv.profit
        mk = month_key(inv.sold_on)
        bucket = by_month[mk]
        bucket['sales'] += inv.sale_amount
        bucket['profit'] += inv.profit
        bucket['salesRepeat' if loyal else 'salesOnce'] += inv.sale_amount
        bucket['profitRepeat' if loyal else 'profitOnce'] += inv.profit
        _note_buyer(month_buyers[mk]['sales' + side_cap], buyer, inv.sale_amount)
        _note_buyer(month_buyers[mk]['profit' + side_cap], buyer, inv.profit)
        if inv.settlement == 'قسطی':
            bucket['inst'] += inv.sale_amount
            bucket['instRepeat' if loyal else 'instOnce'] += inv.sale_amount
            money['inst'][side] += inv.sale_amount
            _note_buyer(month_buyers[mk]['inst' + side_cap], buyer, inv.sale_amount)
            _note_buyer(sale_buyers['قسطی'][side], buyer, inv.sale_amount)
        else:
            bucket['cash'] += inv.sale_amount
            bucket['cashRepeat' if loyal else 'cashOnce'] += inv.sale_amount
            _note_buyer(month_buyers[mk]['cash' + side_cap], buyer, inv.sale_amount)
            if inv.settlement == 'نقدی':
                money['cash'][side] += inv.sale_amount
                _note_buyer(sale_buyers['نقدی'][side], buyer, inv.sale_amount)
        ctype = inv.customer.customer_type or 'نامشخص'
        by_type[ctype][side] += inv.sale_amount
        _note_buyer(type_buyers[ctype][side], buyer, inv.sale_amount)
        city = inv.customer.city or 'نامشخص'
        by_province[city][side] += inv.sale_amount
        _note_buyer(city_buyers[city][side], buyer, inv.sale_amount)
        for line in inv.lines.all():
            line_amount = int(line.qty * line.unit_price)
            by_product[line.product_name][side] += line_amount
            _note_buyer(product_buyers[line.product_name][side], buyer, line_amount)
        got = received_of(inv)
        debt = outstanding_of(inv)
        money['received'][side] += got
        money['outstanding'][side] += debt
        _note_buyer(money_buyers['received'][side], buyer, got)
        _note_buyer(money_buyers['outstanding'][side], buyer, debt)
        cust = by_customer.setdefault(inv.customer_id, {
            'id': inv.customer_id, 'name': inv.customer.name, 'count': 0, 'sales': 0, 'profit': 0,
            'repeat': loyal,
        })
        cust['count'] += 1
        cust['sales'] += inv.sale_amount
        cust['profit'] += inv.profit
        for label, low, high in TICKET_BUCKETS:
            if low <= inv.sale_amount < high:
                ticket[label][side] += 1
                _note_buyer(ticket_buyers[label][side], buyer, inv.sale_amount)
                break
        for pay in inv.payments.all():
            method = pay.method or 'سایر'
            methods[method][side] += pay.amount
            _note_buyer(method_buyers[method][side], buyer, pay.amount)
        if not inv.expert_id:
            continue
        ex = by_expert[inv.expert_id]
        if not ex['name']:
            mentor = inv.expert.mentor
            ex['mentor_id'] = mentor.pk if mentor else None
            ex['mentor_name'] = mentor.report_name() if mentor else ''
        ex['name'] = inv.expert.report_name()
        ex['sales'] += inv.sale_amount
        ex['profit'] += inv.profit
        ex['deals'] += 1
        ex['salesRepeat' if loyal else 'salesOnce'] += inv.sale_amount
        ex['profitRepeat' if loyal else 'profitOnce'] += inv.profit
        ex['dealsRepeat' if loyal else 'dealsOnce'] += 1
        ex['months'][mk] += inv.profit

    day_keys = sorted(by_day)
    month_keys = sorted(by_month)
    product_pairs = sorted(by_product.items(), key=lambda x: x[1]['repeat'] + x[1]['once'], reverse=True)[:15]
    province_pairs = sorted(by_province.items(), key=lambda x: x[1]['repeat'] + x[1]['once'], reverse=True)

    board = []
    for row in by_customer.values():
        margin = (row['profit'] / row['sales'] * 100) if row['sales'] else 0
        board.append({**row, 'margin': round(margin, 1)})
    board.sort(key=lambda r: r['sales'], reverse=True)

    checks = []
    for inv in invoices:
        for chk in inv.checks.all():
            checks.append({
                'customer': inv.customer.name,
                'customer_id': inv.customer_id,
                'invoice_id': inv.pk,
                'number': chk.number or inv.number,
                'due': chk.due_on,
                'amount': chk.amount,
                'status': chk.status,
                'id': chk.id,
            })
    checks.sort(key=lambda c: c['due'], reverse=True)

    real_experts = []
    for expert_id, row in by_expert.items():
        real_experts.append({
            'id': expert_id,
            'name': row['name'],
            'mentor_id': row['mentor_id'],
            'mentor_name': row['mentor_name'],
            **{k: row[k] for k in ('sales', 'profit', 'deals', 'dealsRepeat', 'dealsOnce')},
            'months': dict(row['months']),
        })
    real_experts.sort(key=lambda r: r['profit'], reverse=True)

    def month_profit(expert_row, which):
        if which == 'all':
            return expert_row['profit']
        return expert_row['months'].get(which, 0)

    team_rows = []
    for row in real_experts:
        profit = month_profit(row, team_month)
        pay = payout(profit if team_month != 'all' else _sum_monthly(row['months']))
        if team_month == 'all':
            profit = row['profit']
        shown_profit = row['profit'] if team_month == 'all' else profit
        commission = _monthly_commission(row['months']) if team_month == 'all' else pay['commission']
        level = level_for(shown_profit if team_month != 'all' else (max(row['months'].values()) if row['months'] else 0))
        sales_r, sales_o, profit_r, profit_o = _expert_loyalty(row['id'], invoices, repeat_ids, team_month)
        if shown_profit:
            commission_r = int(round(commission * profit_r / shown_profit))
        else:
            commission_r = 0
        sales = row['sales'] if team_month == 'all' else _sales_in_month(row['id'], team_month, invoices)
        team_rows.append({
            'id': row['id'],
            'name': row['name'],
            'mentor_id': row['mentor_id'],
            'mentor_name': row['mentor_name'],
            'sales': sales,
            'profit': shown_profit,
            'margin': round((shown_profit / sales * 100), 1) if sales else 0,
            'deals': row['deals'],
            'commission': commission,
            'salesRepeat': sales_r,
            'salesOnce': sales_o,
            'profitRepeat': profit_r,
            'profitOnce': profit_o,
            'dealsRepeat': row['dealsRepeat'],
            'dealsOnce': row['dealsOnce'],
            'commissionRepeat': commission_r,
            'commissionOnce': commission - commission_r,
            'bonus': pay['bonus'] if team_month != 'all' else sum(payout(v)['bonus'] for v in row['months'].values()),
            'level_name': level['name'] if level else 'هنوز وارد مسیر نشده',
            'level_color': level['color'] if level else '#94a3b8',
            'level_n': level['n'] if level else 0,
            'total_pay': BASE_SALARY + commission + (pay['bonus'] if team_month != 'all' else sum(payout(v)['bonus'] for v in row['months'].values())),
        })
    _assign_team_names(team_rows)

    people = _people(user)
    if user.role == 'specialist':
        selected_id = user.pk
    elif str(person).isdigit():
        selected_id = int(person)
    else:
        selected_id = None
    months = sorted({month_key(i.sold_on) for i in invoices})
    detail = _person_detail(selected_id, invoices, month, repeat_ids, months) if selected_id else None
    selected_name = detail['name'] if detail else ''
    type_labels = list(by_type)
    product_labels = [p[0] for p in product_pairs]
    province_labels = [p[0] for p in province_pairs]
    ticket_labels = list(ticket)

    def month_buyer(key):
        return [_buyer_rows(month_buyers[k][key]) for k in month_keys]

    charts = {
        'daily': {
            'labels': [format_day_month(date.fromisoformat(k)) for k in day_keys],
            'monthKeys': [month_key(date.fromisoformat(k)) for k in day_keys],
            'sales': [by_day[k]['sales'] for k in day_keys],
            'profit': [by_day[k]['profit'] for k in day_keys],
        },
        'ticket': {**_series(ticket, ticket_labels), **_side_buyers(ticket_buyers, ticket_labels)},
        'saleType': {
            'labels': ['نقدی', 'قسطی'],
            'values': [cash_sales, inst_sales],
            'repeat': [money['cash']['repeat'], money['inst']['repeat']],
            'once': [money['cash']['once'], money['inst']['once']],
            **_side_buyers(sale_buyers, ['نقدی', 'قسطی']),
        },
        'customerType': {**_series(by_type, type_labels), **_side_buyers(type_buyers, type_labels)},
        'province': {
            'labels': province_labels,
            'values': [p[1]['repeat'] + p[1]['once'] for p in province_pairs],
            'repeat': [p[1]['repeat'] for p in province_pairs],
            'once': [p[1]['once'] for p in province_pairs],
            **_side_buyers(city_buyers, province_labels),
        },
        'product': {
            'labels': product_labels,
            'values': [p[1]['repeat'] + p[1]['once'] for p in product_pairs],
            'repeat': [p[1]['repeat'] for p in product_pairs],
            'once': [p[1]['once'] for p in product_pairs],
            **_side_buyers(product_buyers, product_labels),
        },
        'monthlyType': {
            'labels': [month_label(k) for k in month_keys],
            'cash': [by_month[k]['cash'] for k in month_keys],
            'inst': [by_month[k]['inst'] for k in month_keys],
            'cashRepeat': [by_month[k]['cashRepeat'] for k in month_keys],
            'cashOnce': [by_month[k]['cashOnce'] for k in month_keys],
            'instRepeat': [by_month[k]['instRepeat'] for k in month_keys],
            'instOnce': [by_month[k]['instOnce'] for k in month_keys],
            'cashRepeatBuyers': month_buyer('cashRepeat'),
            'cashOnceBuyers': month_buyer('cashOnce'),
            'instRepeatBuyers': month_buyer('instRepeat'),
            'instOnceBuyers': month_buyer('instOnce'),
        },
        'monthlyProfit': {
            'labels': [month_label(k) for k in month_keys],
            'axis': [month_axis_label(k) for k in month_keys],
            'sales': [by_month[k]['sales'] for k in month_keys],
            'profit': [by_month[k]['profit'] for k in month_keys],
            'salesRepeat': [by_month[k]['salesRepeat'] for k in month_keys],
            'salesOnce': [by_month[k]['salesOnce'] for k in month_keys],
            'profitRepeat': [by_month[k]['profitRepeat'] for k in month_keys],
            'profitOnce': [by_month[k]['profitOnce'] for k in month_keys],
            'salesRepeatBuyers': month_buyer('salesRepeat'),
            'salesOnceBuyers': month_buyer('salesOnce'),
            'profitRepeatBuyers': month_buyer('profitRepeat'),
            'profitOnceBuyers': month_buyer('profitOnce'),
        },
        'experts': {
            'labels': [r['name'] for r in team_rows],
            'profit': [r['profit'] for r in team_rows],
            'sales': [r['sales'] for r in team_rows],
            'deals': [r['deals'] for r in team_rows],
            'commission': [r['commission'] for r in team_rows],
            'salesRepeat': [r['salesRepeat'] for r in team_rows],
            'salesOnce': [r['salesOnce'] for r in team_rows],
            'profitRepeat': [r['profitRepeat'] for r in team_rows],
            'profitOnce': [r['profitOnce'] for r in team_rows],
            'dealsRepeat': [r['dealsRepeat'] for r in team_rows],
            'dealsOnce': [r['dealsOnce'] for r in team_rows],
            'commissionRepeat': [r['commissionRepeat'] for r in team_rows],
            'commissionOnce': [r['commissionOnce'] for r in team_rows],
        },
        'methods': {
            **_series(methods, list(methods)),
            **_side_buyers(method_buyers, list(methods)),
        },
        'collection': {
            'labels': ['وصول‌شده', 'مطالبات'],
            'values': [received, outstanding],
            'repeat': [money['received']['repeat'], money['outstanding']['repeat']],
            'once': [money['received']['once'], money['outstanding']['once']],
            'repeatBuyers': [
                _buyer_rows(money_buyers['received']['repeat']),
                _buyer_rows(money_buyers['outstanding']['repeat']),
            ],
            'onceBuyers': [
                _buyer_rows(money_buyers['received']['once']),
                _buyer_rows(money_buyers['outstanding']['once']),
            ],
        },
        'checkDue': _check_calendar(checks),
        'invoices': _recent_invoices(invoices),
        'trend': detail['trend'] if detail else {'labels': [], 'values': [], 'colors': [], 'repeat': [], 'once': []},
    }

    return {
        'kpis': kpis,
        'board': board[:10],
        'checks': checks,
        'check_summary': _check_summary(checks),
        'team_rows': team_rows,
        'team_groups': _team_groups(team_rows),
        'team_kpis': _team_kpis(team_rows),
        'months': months,
        'people': people,
        'selected_name': selected_name,
        'detail': detail,
        'levels': SPECIALIST_LEVELS,
        'charts': charts,
        'kpi_tables': _kpi_details(invoices, repeat_ids),
        'base_salary': BASE_SALARY,
    }


def _sum_monthly(months):
    return sum(payout(v)['total'] for v in months.values())


def _monthly_commission(months):
    return sum(payout(v)['commission'] for v in months.values())


def _sales_in_month(expert_id, team_month, invoices):
    return sum(i.sale_amount for i in invoices if i.expert_id == expert_id and month_key(i.sold_on) == team_month)


def _expert_loyalty(expert_id, invoices, repeat_ids, team_month):
    sales_r = sales_o = profit_r = profit_o = 0
    for inv in invoices:
        if inv.expert_id != expert_id:
            continue
        if team_month != 'all' and month_key(inv.sold_on) != team_month:
            continue
        if inv.customer_id in repeat_ids:
            sales_r += inv.sale_amount
            profit_r += inv.profit
        else:
            sales_o += inv.sale_amount
            profit_o += inv.profit
    return sales_r, sales_o, profit_r, profit_o


def _people(user):
    qs = Operator.objects.filter(is_active=True).exclude(expert_name='').order_by('full_name')
    if user.role == 'mentor':
        qs = qs.filter(pk__in=[user.pk, *user.mentees.values_list('pk', flat=True)])
    elif user.role == 'specialist':
        qs = qs.filter(pk=user.pk)
    return list(qs)


def _person_detail(expert_id, invoices, month, repeat_ids=None, span_months=None):
    repeat_ids = repeat_ids or set()
    operator = Operator.objects.filter(pk=expert_id).first()
    if operator is None:
        return None
    mine = [i for i in invoices if i.expert_id == expert_id]
    if month != 'all':
        period = [i for i in mine if month_key(i.sold_on) == month]
    else:
        period = mine
    by_month = defaultdict(int)
    repeat_profit = defaultdict(int)
    once_profit = defaultdict(int)
    for inv in mine:
        mk = month_key(inv.sold_on)
        by_month[mk] += inv.profit
        if inv.customer_id in repeat_ids:
            repeat_profit[mk] += inv.profit
        else:
            once_profit[mk] += inv.profit
    if month == 'all':
        profit = sum(by_month.values())
        pay = {
            'level': level_for(max(by_month.values(), default=0)),
            'commission': _monthly_commission(by_month),
            'bonus': sum(payout(v)['bonus'] for v in by_month.values()),
            'base': BASE_SALARY,
            'total': BASE_SALARY + _monthly_commission(by_month) + sum(payout(v)['bonus'] for v in by_month.values()),
        }
        # برای نمایش سطح، ماه آخر را ملاک می‌گیریم تا سطح از جمع چندماه پرت نشود
        last_profit = by_month[sorted(by_month)[-1]] if by_month else 0
        pay['level'] = level_for(last_profit)
        progress_profit = last_profit
    else:
        profit = sum(i.profit for i in period)
        pay = payout(profit)
        progress_profit = profit
    level = pay['level']
    nxt = next_level(level)
    target = nxt['min'] if nxt else (level['min'] if level else SPECIALIST_LEVELS[0]['min'])
    base = level['min'] if level else 0
    span = max(target - base, 1)
    pct = 100 if not nxt and level else max(0, min(100, int((progress_profit - base) * 100 / span)))
    paid = sum(int(i.profit * (level['rate'] if level else 0)) for i in period if i.commission_paid)
    commission_rows = []
    rate = level['rate'] if level else 0
    for inv in period:
        amount = int(inv.profit * rate)
        commission_rows.append({
            'number': inv.number,
            'profit': inv.profit,
            'rate': int(rate * 100),
            'amount': amount,
            'paid': inv.commission_paid,
        })
    keys = list(span_months) if span_months else sorted(by_month)
    colors = []
    level_names = []
    for key in keys:
        lvl = level_for(by_month.get(key, 0))
        colors.append(lvl['color'] if lvl else '#94a3b8')
        level_names.append(lvl['name'] if lvl else 'هنوز وارد مسیر نشده')
    return {
        'name': operator.report_name(),
        'profit': profit,
        'pay': pay,
        'level': level,
        'next': nxt,
        'pct': pct,
        'perks': perks_up_to(level),
        'paid': paid,
        'unpaid': max(0, pay['commission'] - paid),
        'commission_rows': commission_rows,
        'progress_profit': progress_profit,
        'target': target,
        'trend': {
            'labels': [month_axis_label(k) for k in keys],
            'values': [by_month.get(k, 0) for k in keys],
            'colors': colors,
            'levelNames': level_names,
            'legend': [
                {'name': 'هنوز وارد مسیر نشده', 'color': '#94a3b8'},
                *[{'name': level['name'], 'color': level['color']} for level in SPECIALIST_LEVELS],
            ],
            'repeat': [repeat_profit.get(k, 0) for k in keys],
            'once': [once_profit.get(k, 0) for k in keys],
        },
    }


def _assign_team_names(rows):
    lead_ids = {row['mentor_id'] for row in rows if row.get('mentor_id')}
    for row in rows:
        if row.get('mentor_id'):
            row['team_name'] = row['mentor_name'] or 'تیم'
        elif row['id'] in lead_ids:
            row['team_name'] = row['name']
        else:
            row['team_name'] = 'بدون تیم'


def _team_groups(rows):
    buckets = {}
    order = []
    for row in rows:
        name = row.get('team_name') or 'بدون تیم'
        if name not in buckets:
            buckets[name] = {
                'name': name,
                'people': 0,
                'sales': 0,
                'profit': 0,
                'deals': 0,
                'commission': 0,
            }
            order.append(name)
        bucket = buckets[name]
        bucket['people'] += 1
        bucket['sales'] += row['sales']
        bucket['profit'] += row['profit']
        bucket['deals'] += row['deals']
        bucket['commission'] += row['commission']
    total_sales = sum(row['sales'] for row in rows)
    groups = []
    for name in order:
        bucket = buckets[name]
        sales = bucket['sales']
        bucket['margin'] = round((bucket['profit'] / sales * 100), 1) if sales else 0
        bucket['share'] = round((sales / total_sales * 100), 1) if total_sales else 0
        groups.append(bucket)
    groups.sort(key=lambda group: group['sales'], reverse=True)
    return groups


def _team_kpis(rows):
    return {
        'sales': sum(r['sales'] for r in rows),
        'profit': sum(r['profit'] for r in rows),
        'deals': sum(r['deals'] for r in rows),
        'people': len(rows),
        'commission': sum(r['commission'] for r in rows),
    }


def _shift_jalali_month(year, month, steps):
    index = year * 12 + (month - 1) + steps
    return index // 12, index % 12 + 1


def _check_calendar(checks):
    """چک‌ها روی روز خودشان؛ تقویم از اولین سررسید تا ده سال بعد از ماه جاری باز است."""
    marks = defaultdict(list)
    dates = []
    for chk in checks:
        due = chk.get('due')
        if not due:
            continue
        dates.append(due)
        jy, jm, jd = gregorian_to_jalali(due.year, due.month, due.day)
        marks[f'{jy}-{jm}-{jd}'].append({
            'name': chk['customer'],
            'amount': int(chk['amount'] or 0),
            'invoice': chk.get('invoice_id'),
            'status': chk.get('status') or '',
        })
    for rows in marks.values():
        rows.sort(key=lambda row: (-row['amount'], row['name']))
    today = timezone.localdate()
    today_y, today_m, _today_d = gregorian_to_jalali(today.year, today.month, today.day)
    start_y, start_m = today_y, today_m
    end_y, end_m = _shift_jalali_month(today_y, today_m, 10 * 12)
    if dates:
        first_y, first_m, _first_d = gregorian_to_jalali(min(dates).year, min(dates).month, min(dates).day)
        last_y, last_m, _last_d = gregorian_to_jalali(max(dates).year, max(dates).month, max(dates).day)
        if (first_y, first_m) < (start_y, start_m):
            start_y, start_m = first_y, first_m
        if (last_y, last_m) > (end_y, end_m):
            end_y, end_m = last_y, last_m
    return {
        'start': [start_y, start_m],
        'end': [end_y, end_m],
        'focus': [today_y, today_m],
        'marks': dict(marks),
    }


def _kpi_stamp(value):
    if not value:
        return ''
    return value.isoformat()


def _kpi_details(invoices, repeat_ids):
    """ردیف‌هایی که جمع‌شان همان شاخص‌های بالای داشبورد است."""
    invoice_rows = []
    receipt_rows = []
    check_rows = []
    loyal = {}
    for inv in invoices:
        got = int(received_of(inv))
        debt = int(outstanding_of(inv))
        invoice_rows.append({
            'id': inv.pk,
            'number': inv.number,
            'customer': inv.customer.name,
            'customerId': inv.customer_id,
            'date': format_jalali(inv.sold_on),
            'settlement': inv.settlement or '',
            'expert': inv.expert_label,
            'sale': int(inv.sale_amount),
            'cost': int(inv.cost_amount),
            'profit': int(inv.profit),
            'received': got,
            'outstanding': debt,
            'cashDue': int(cash_due_of(inv)),
            '_sort': _kpi_stamp(inv.sold_on),
        })
        if inv.customer_id in repeat_ids:
            person = loyal.get(inv.customer_id)
            if person is None:
                person = {
                    'id': inv.pk,
                    'customer': inv.customer.name,
                    'customerId': inv.customer_id,
                    'invoices': 0,
                    'sale': 0,
                    'outstanding': 0,
                }
                loyal[inv.customer_id] = person
            person['invoices'] += 1
            person['sale'] += int(inv.sale_amount)
            person['outstanding'] += debt
        for pay in inv.payments.all():
            receipt_rows.append({
                'id': inv.pk,
                'number': inv.number,
                'customer': inv.customer.name,
                'customerId': inv.customer_id,
                'method': pay.method or 'سایر',
                'date': format_jalali(pay.paid_on),
                'amount': int(pay.amount or 0),
                '_sort': _kpi_stamp(pay.paid_on),
            })
        for chk in inv.checks.all():
            amount = int(chk.amount or 0)
            if chk.status == 'وصول‌شده':
                receipt_rows.append({
                    'id': inv.pk,
                    'number': inv.number,
                    'customer': inv.customer.name,
                    'customerId': inv.customer_id,
                    'method': 'چک وصول‌شده',
                    'date': format_jalali(chk.due_on),
                    'amount': amount,
                    '_sort': _kpi_stamp(chk.due_on),
                })
            if check_is_cleared(chk.status):
                continue
            check_rows.append({
                'id': inv.pk,
                'number': inv.number,
                'customer': inv.customer.name,
                'customerId': inv.customer_id,
                'checkNumber': chk.number or '—',
                'status': chk.status or 'در جریان',
                'date': format_jalali(chk.due_on),
                'amount': amount,
                '_sort': _kpi_stamp(chk.due_on),
            })
    invoice_rows.sort(key=lambda row: row['_sort'], reverse=True)
    receipt_rows.sort(key=lambda row: (row['_sort'], row['amount']), reverse=True)
    check_rows.sort(key=lambda row: (row['amount'], row['_sort']), reverse=True)
    customer_rows = sorted(loyal.values(), key=lambda row: row['sale'], reverse=True)
    for row in invoice_rows:
        row.pop('_sort', None)
    for row in receipt_rows:
        row.pop('_sort', None)
    for row in check_rows:
        row.pop('_sort', None)
    return {
        'invoices': invoice_rows,
        'receipts': receipt_rows,
        'checks': check_rows,
        'customers': customer_rows,
    }


def _recent_invoices(invoices):
    rows = sorted(invoices, key=lambda i: (i.sold_on, i.id))
    return {
        'labels': [i.number for i in rows],
        'customers': [i.customer.name for i in rows],
        'ids': [i.pk for i in rows],
        'received': [received_of(i) for i in rows],
        'outstanding': [outstanding_of(i) for i in rows],
    }


def _check_summary(checks):
    summary = defaultdict(lambda: {'count': 0, 'amount': 0})
    for chk in checks:
        summary[chk['status']]['count'] += 1
        summary[chk['status']]['amount'] += chk['amount']
    return dict(summary)
