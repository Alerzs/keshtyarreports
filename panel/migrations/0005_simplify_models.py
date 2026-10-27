import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _iso(value):
    if value is None:
        return ''
    return value.isoformat()


def copy_into_simpler_models(apps, schema_editor):
    SaleRequest = apps.get_model('panel', 'SaleRequest')
    Line = apps.get_model('panel', 'SaleRequestLine')
    Pay = apps.get_model('panel', 'SaleRequestPayment')
    Chk = apps.get_model('panel', 'SaleRequestCheck')
    for req in SaleRequest.objects.all():
        req.line_rows = [
            {
                'product_name': row.product_name,
                'qty': str(row.qty),
                'unit_price': row.unit_price,
                'unit_cost': row.unit_cost,
            }
            for row in Line.objects.filter(request_id=req.pk)
        ]
        req.payment_rows = [
            {
                'amount': row.amount,
                'method': row.method,
                'paid_on': _iso(row.paid_on),
                'note': row.note,
            }
            for row in Pay.objects.filter(request_id=req.pk)
        ]
        req.check_rows = [
            {
                'number': row.number,
                'amount': row.amount,
                'due_on': _iso(row.due_on),
                'bank': row.bank,
                'status': row.status,
            }
            for row in Chk.objects.filter(request_id=req.pk)
        ]
        req.save(update_fields=['line_rows', 'payment_rows', 'check_rows'])

    Plan = apps.get_model('panel', 'FinancePlan')
    Txn = apps.get_model('panel', 'FinanceTransaction')
    for plan in Plan.objects.all():
        Txn.objects.create(
            section_id=plan.section_id,
            kind='plan',
            title=plan.title,
            amount=plan.amount,
            happened_at=None,
            planned_on=plan.planned_on,
            note=plan.note,
        )

    Edit = apps.get_model('panel', 'EditLog')
    Restore = apps.get_model('panel', 'RestoreLog')
    Log = apps.get_model('panel', 'Log')
    for row in Edit.objects.all():
        log = Log.objects.create(
            kind='edit', actor_id=row.actor_id, entity=row.entity, message=row.summary,
        )
        Log.objects.filter(pk=log.pk).update(created_at=row.created_at)
    for row in Restore.objects.all():
        log = Log.objects.create(kind='restore', message=row.message)
        Log.objects.filter(pk=log.pk).update(created_at=row.created_at)


def drop_copied_rows(apps, schema_editor):
    apps.get_model('panel', 'FinanceTransaction').objects.filter(kind='plan').delete()
    apps.get_model('panel', 'Log').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('panel', '0004_admin_labels'),
    ]

    operations = [
        migrations.AddField(
            model_name='salerequest',
            name='line_rows',
            field=models.JSONField(blank=True, default=list, verbose_name='اقلام'),
        ),
        migrations.AddField(
            model_name='salerequest',
            name='payment_rows',
            field=models.JSONField(blank=True, default=list, verbose_name='پرداخت\u200cها'),
        ),
        migrations.AddField(
            model_name='salerequest',
            name='check_rows',
            field=models.JSONField(blank=True, default=list, verbose_name='چک\u200cها'),
        ),
        migrations.AddField(
            model_name='financetransaction',
            name='kind',
            field=models.CharField(
                choices=[('posted', 'تراکنش'), ('plan', 'برنامه')],
                default='posted', max_length=12, verbose_name='نوع',
            ),
        ),
        migrations.AddField(
            model_name='financetransaction',
            name='planned_on',
            field=models.DateField(blank=True, null=True, verbose_name='تاریخ برنامه'),
        ),
        migrations.AlterField(
            model_name='financetransaction',
            name='happened_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='زمان'),
        ),
        migrations.CreateModel(
            name='Log',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('edit', 'ویرایش'), ('restore', 'بازگردانی')], default='edit', max_length=12, verbose_name='نوع')),
                ('entity', models.CharField(blank=True, max_length=40, verbose_name='موجودیت')),
                ('message', models.TextField(verbose_name='پیام')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='زمان')),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='کاربر')),
            ],
            options={
                'verbose_name': 'گزارش',
                'verbose_name_plural': 'گزارش\u200cها',
                'ordering': ['-created_at'],
            },
        ),
        migrations.RunPython(copy_into_simpler_models, drop_copied_rows),
        migrations.RemoveField(model_name='invoice', name='sale_amount'),
        migrations.RemoveField(model_name='invoice', name='cost_amount'),
        migrations.DeleteModel(name='SaleRequestLine'),
        migrations.DeleteModel(name='SaleRequestPayment'),
        migrations.DeleteModel(name='SaleRequestCheck'),
        migrations.DeleteModel(name='FinancePlan'),
        migrations.DeleteModel(name='EditLog'),
        migrations.DeleteModel(name='RestoreLog'),
        migrations.RenameField(model_name='salerequest', old_name='line_rows', new_name='lines'),
        migrations.RenameField(model_name='salerequest', old_name='payment_rows', new_name='payments'),
        migrations.RenameField(model_name='salerequest', old_name='check_rows', new_name='checks'),
    ]
