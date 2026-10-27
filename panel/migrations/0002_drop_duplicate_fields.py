import django.db.models.deletion
from django.db import migrations, models


def attach_operators(apps, schema_editor):
    Invoice = apps.get_model('panel', 'Invoice')
    SaleRequest = apps.get_model('panel', 'SaleRequest')
    Operator = apps.get_model('panel', 'Operator')
    by_expert = {}
    by_full = {}
    for operator in Operator.objects.all():
        if (operator.expert_name or '').strip():
            by_expert.setdefault(operator.expert_name.strip(), operator.pk)
        if (operator.full_name or '').strip():
            by_full.setdefault(operator.full_name.strip(), operator.pk)
    for invoice in Invoice.objects.filter(expert__isnull=True).exclude(expert_name=''):
        name = invoice.expert_name.strip()
        operator_id = by_expert.get(name) or by_full.get(name)
        if operator_id:
            invoice.expert_id = operator_id
            invoice.save(update_fields=['expert'])
    for request_row in SaleRequest.objects.filter(seller__isnull=True).exclude(seller_name=''):
        name = request_row.seller_name.strip()
        operator_id = by_expert.get(name) or by_full.get(name)
        if operator_id:
            request_row.seller_id = operator_id
            request_row.save(update_fields=['seller'])


def drop_unlinked_checks(apps, schema_editor):
    Check = apps.get_model('panel', 'Check')
    Check.objects.filter(invoice__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('panel', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(attach_operators, migrations.RunPython.noop),
        migrations.RunPython(drop_unlinked_checks, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='invoice',
            name='expert_name',
        ),
        migrations.RemoveField(
            model_name='salerequest',
            name='seller_name',
        ),
        migrations.RemoveField(
            model_name='payment',
            name='customer',
        ),
        migrations.AlterField(
            model_name='check',
            name='invoice',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='checks', to='panel.invoice'),
        ),
        migrations.RemoveField(
            model_name='check',
            name='customer',
        ),
        migrations.DeleteModel(
            name='ArchivedExpert',
        ),
    ]
