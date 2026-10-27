from django.db import migrations


def assign_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Operator = apps.get_model('panel', 'Operator')
    names = ('superadmin', 'manager', 'mentor', 'specialist', 'finance')
    groups = {}
    for name in names:
        groups[name], _created = Group.objects.get_or_create(name=name)
    for user in Operator.objects.all():
        role = user.role if user.role in groups else 'specialist'
        user.groups.add(groups[role])
        if role == 'superadmin':
            user.groups.add(groups['finance'])


class Migration(migrations.Migration):

    dependencies = [
        ('panel', '0002_drop_duplicate_fields'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(assign_groups, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='operator',
            name='role',
        ),
        migrations.DeleteModel(
            name='FinanceGate',
        ),
    ]
