from django.db import migrations


def drop_legacy_profile_tables(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP TABLE IF EXISTS system_passwordchangehistory;')
        cursor.execute('DROP TABLE IF EXISTS system_userprofile;')


class Migration(migrations.Migration):
    dependencies = [
        ('system', '0012_archive_legacy_user_profile_tables'),
    ]

    operations = [
        migrations.RunPython(drop_legacy_profile_tables, reverse_code=migrations.RunPython.noop),
    ]
