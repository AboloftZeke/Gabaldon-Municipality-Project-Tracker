from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('system', '0028_loginotpchallenge'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name='PasswordChangeHistory',
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'DROP TABLE IF EXISTS '
                        'system_legacy_passwordchangehistory_archive;'
                    ),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
