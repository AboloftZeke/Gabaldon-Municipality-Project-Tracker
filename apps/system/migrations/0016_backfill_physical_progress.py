from django.db import migrations


def backfill_physical_progress(apps, schema_editor):
    Legacy = apps.get_model('infrastructure', 'InfrastructureProject')
    Infra = apps.get_model('system', 'Infrastructure_Project')

    for old in Legacy.objects.all().order_by('id'):
        try:
            new = Infra.objects.filter(infrastructure_title=old.title).order_by('infrastructure_id').first()
        except Exception:
            new = None
        if not new:
            continue
        if new.physical_progress_percentage is None and old.physical_progress_percentage is not None:
            new.physical_progress_percentage = old.physical_progress_percentage
            new.save(update_fields=['physical_progress_percentage'])


class Migration(migrations.Migration):

    dependencies = [
        ('system', '0015_alter_passwordchangehistory_options_and_more'),
        ('infrastructure', '0005_infrastructureproject_description_infrastructureproject_latitude_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_physical_progress, reverse_code=migrations.RunPython.noop),
    ]
