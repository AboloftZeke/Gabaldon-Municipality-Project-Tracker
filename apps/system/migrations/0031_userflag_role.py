from django.db import migrations, models


def populate_roles(apps, schema_editor):
    UserFlag = apps.get_model('system', 'UserFlag')
    flags = UserFlag.objects.using(schema_editor.connection.alias)
    if flags.exclude(department__in=['admin', 'engineer', 'mayor', '']).exists():
        raise RuntimeError(
            'UserFlag contains unknown departments. Review those accounts before '
            'applying migration 0031; no departments will be changed automatically.'
        )
    flags.filter(department='admin').update(role='admin')
    flags.filter(department__in=['engineer', 'mayor', '']).update(role='staff')


class Migration(migrations.Migration):
    dependencies = [('system', '0030_remove_must_change_password')]

    operations = [
        migrations.AddField(
            model_name='userflag',
            name='role',
            field=models.CharField(
                max_length=10,
                choices=[('staff', 'Staff'), ('head', 'Head'), ('admin', 'Admin')],
                default='', blank=True,
                help_text='Office responsibility; currently not used for authorization.',
            ),
        ),
        migrations.RunPython(populate_roles, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='userflag',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(department='admin', role='admin')
                    | models.Q(department__in=['engineer', 'mayor'], role__in=['staff', 'head'])
                    | models.Q(department='', role='staff')
                ),
                name='userflag_valid_department_role',
            ),
        ),
    ]
