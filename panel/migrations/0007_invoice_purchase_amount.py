from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('panel', '0006_sale_documents'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='purchase_amount',
            field=models.BigIntegerField(default=0, verbose_name='مبلغ خرید'),
        ),
    ]
