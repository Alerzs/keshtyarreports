from django.db import migrations, models

CHECK_STATES = ['در جریان', 'وصول‌شده', 'برگشتی', 'سررسید گذشته']


def canonical_check_status(status):
    text = (status or '').strip()
    if text in CHECK_STATES:
        return text
    compact = text.replace('\u200c', '').replace(' ', '')
    if compact.startswith('وصول'):
        return 'وصول‌شده'
    if 'برگشت' in compact:
        return 'برگشتی'
    if compact.startswith('سررسید'):
        return 'سررسید گذشته'
    return 'در جریان'


def normalize_check_statuses(apps, schema_editor):
    Check = apps.get_model('panel', 'Check')
    for chk in Check.objects.all().iterator():
        status = canonical_check_status(chk.status)
        if chk.status != status:
            chk.status = status
            chk.save(update_fields=['status'])

    SaleRequest = apps.get_model('panel', 'SaleRequest')
    for req in SaleRequest.objects.all().iterator():
        rows = req.checks or []
        cleaned = []
        changed = False
        for item in rows:
            if isinstance(item, dict):
                status = canonical_check_status(item.get('status'))
                if item.get('status') != status:
                    item = {**item, 'status': status}
                    changed = True
            cleaned.append(item)
        if changed:
            req.checks = cleaned
            req.save(update_fields=['checks'])


class Migration(migrations.Migration):

    dependencies = [
        ('panel', '0009_delete_finance'),
    ]

    operations = [
        migrations.RunPython(normalize_check_statuses, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='check',
            name='status',
            field=models.CharField(
                choices=[(state, state) for state in CHECK_STATES],
                default='در جریان',
                max_length=40,
                verbose_name='وضعیت',
            ),
        ),
        migrations.AddConstraint(
            model_name='check',
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=CHECK_STATES),
                name='panel_check_status_valid',
            ),
        ),
    ]
