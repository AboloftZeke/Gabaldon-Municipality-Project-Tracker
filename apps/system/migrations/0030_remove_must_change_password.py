from django.contrib.auth.hashers import make_password
from django.db import migrations


def disable_temporary_passwords(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    UserFlag = apps.get_model('system', 'UserFlag')

    pending_user_ids = UserFlag.objects.filter(
        must_change_password=True,
    ).values_list('user_id', flat=True)

    for user in User.objects.filter(pk__in=pending_user_ids).iterator():
        user.password = make_password(None)
        user.save(update_fields=['password'])


class Migration(migrations.Migration):
    dependencies = [
        ('system', '0029_remove_password_change_history'),
    ]

    operations = [
        migrations.RunPython(
            disable_temporary_passwords,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name='userflag',
            name='must_change_password',
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name='userprofile',
                    name='must_change_password',
                ),
            ],
            database_operations=[],
        ),
    ]
