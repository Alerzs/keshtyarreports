from django.db import migrations, models


def fill_sale_amount(apps, schema_editor):
    """مبلغ کل فروش هر فاکتور همان مجموع مبلغ اقلامش است."""
    Invoice = apps.get_model('panel', 'Invoice')
    Line = apps.get_model('panel', 'InvoiceLine')
    for invoice in Invoice.objects.all().iterator():
        total = 0
        for line in Line.objects.filter(invoice_id=invoice.pk):
            total += int(line.qty * line.unit_price)
        if invoice.sale_amount != total:
            invoice.sale_amount = total
            invoice.save(update_fields=['sale_amount'])


class Migration(migrations.Migration):

    dependencies = [
        ('panel', '0010_check_status_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='sale_amount',
            field=models.BigIntegerField(default=0, verbose_name='مبلغ کل فروش'),
        ),
        migrations.RunPython(fill_sale_amount, migrations.RunPython.noop),
    ]
