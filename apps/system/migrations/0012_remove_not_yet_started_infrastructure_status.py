from copy import deepcopy

from django.db import migrations, models


def forwards(apps, schema_editor):
    InfrastructureProject = apps.get_model('system', 'InfrastructureProject')
    InfrastructureProgressUpdate = apps.get_model(
        'system',
        'InfrastructureProgressUpdate',
    )
    ProjectRevision = apps.get_model('system', 'ProjectRevision')

    InfrastructureProject.objects.filter(
        status='not_yet_started',
    ).update(status='ongoing')
    InfrastructureProgressUpdate.objects.filter(
        previous_official_status='not_yet_started',
    ).update(previous_official_status='ongoing')
    InfrastructureProgressUpdate.objects.filter(
        new_official_status='not_yet_started',
    ).update(new_official_status='ongoing')

    for revision in ProjectRevision.objects.all().iterator():
        if not isinstance(revision.snapshot, dict):
            continue
        snapshot = deepcopy(revision.snapshot)
        changed = False

        infrastructure = snapshot.get('infrastructure')
        if isinstance(infrastructure, dict):
            if infrastructure.get('status') == 'not_yet_started':
                infrastructure['status'] = 'ongoing'
                infrastructure['status_label'] = 'Ongoing'
                changed = True

        progress_update = snapshot.get('progress_update')
        if isinstance(progress_update, dict):
            if progress_update.get('official_status') == 'not_yet_started':
                progress_update['official_status'] = 'ongoing'
                progress_update['official_status_label'] = 'Ongoing'
                changed = True

        if changed:
            revision.snapshot = snapshot
            revision.save(update_fields=['snapshot'])


class Migration(migrations.Migration):

    dependencies = [
        ('system', '0011_remove_noninfrastructureproject_project_type'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='infrastructureprogressupdate',
            name='new_official_status',
            field=models.CharField(
                blank=True,
                choices=[
                    ('ongoing', 'Ongoing'),
                    ('on_hold', 'On Hold'),
                    ('completed', 'Completed'),
                ],
                default='',
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name='infrastructureprogressupdate',
            name='previous_official_status',
            field=models.CharField(
                blank=True,
                choices=[
                    ('ongoing', 'Ongoing'),
                    ('on_hold', 'On Hold'),
                    ('completed', 'Completed'),
                ],
                default='',
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name='infrastructureproject',
            name='status',
            field=models.CharField(
                blank=True,
                choices=[
                    ('ongoing', 'Ongoing'),
                    ('on_hold', 'On Hold'),
                    ('completed', 'Completed'),
                ],
                db_column='award_status',
                max_length=50,
                null=True,
            ),
        ),
    ]
