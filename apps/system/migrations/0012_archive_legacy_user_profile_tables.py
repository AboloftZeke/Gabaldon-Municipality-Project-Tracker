from django.db import migrations


def archive_legacy_user_profile_tables(apps, schema_editor):
    db = schema_editor.connection.alias

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS system_legacy_userprofile_archive (
                id BIGSERIAL PRIMARY KEY,
                user_id integer NOT NULL,
                department varchar(20) NOT NULL,
                must_change_password boolean NOT NULL DEFAULT false,
                created_at timestamp with time zone NOT NULL,
                updated_at timestamp with time zone NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS system_legacy_passwordchangehistory_archive (
                id BIGSERIAL PRIMARY KEY,
                user_id integer NOT NULL,
                changed_at timestamp with time zone NOT NULL,
                changed_by_id integer NULL,
                method varchar(20) NOT NULL,
                notes text NOT NULL
            );
            """
        )

        cursor.execute(
            """
            INSERT INTO system_legacy_userprofile_archive (
                id, user_id, department, must_change_password, created_at, updated_at
            )
            SELECT id, user_id, department, must_change_password, created_at, updated_at
            FROM system_userprofile
            ON CONFLICT (id) DO NOTHING;
            """
        )

        cursor.execute(
            """
            INSERT INTO system_legacy_passwordchangehistory_archive (
                id, user_id, changed_at, changed_by_id, method, notes
            )
            SELECT id, user_id, changed_at, changed_by_id, method, notes
            FROM system_passwordchangehistory
            ON CONFLICT (id) DO NOTHING;
            """
        )


def reverse_archive_legacy_user_profile_tables(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP TABLE IF EXISTS system_legacy_passwordchangehistory_archive;")
        cursor.execute("DROP TABLE IF EXISTS system_legacy_userprofile_archive;")


class Migration(migrations.Migration):
    dependencies = [
        ('system', '0011_migrate_infrastructure_finance_schedule_inspection'),
    ]

    operations = [
        migrations.RunPython(
            archive_legacy_user_profile_tables,
            reverse_code=reverse_archive_legacy_user_profile_tables,
        ),
    ]
