from copy import deepcopy

from django.db import migrations, models


STATUS_MAP = {
    'pre_construction': 'not_yet_started',
    'suspended': 'on_hold',
    'for_inspection': 'completed',
    'for_turnover': 'completed',
    'turned_over': 'completed',
    'cancelled': 'on_hold',
    'awarded': 'not_yet_started',
    'ongoing_bidding': 'not_yet_started',
    'rebid': 'not_yet_started',
}
STATUS_LABELS = {
    'not_yet_started': 'Not Yet Started',
    'ongoing': 'Ongoing',
    'on_hold': 'On Hold',
    'completed': 'Completed',
}


def normalize(value, unknown_values):
    if value in (None, ''):
        return value
    if value in STATUS_MAP:
        return STATUS_MAP[value]
    if value in STATUS_LABELS:
        return value
    unknown_values.add(str(value))
    return 'on_hold'


def forwards(apps, schema_editor):
    InfrastructureProject = apps.get_model('system', 'InfrastructureProject')
    InfrastructureProgressUpdate = apps.get_model('system', 'InfrastructureProgressUpdate')
    ProjectRevision = apps.get_model('system', 'ProjectRevision')
    unknown_values = set()

    for project in InfrastructureProject.objects.all().iterator():
        value = normalize(project.status, unknown_values)
        if value != project.status:
            project.status = value
            project.save(update_fields=['status'])

    for update in InfrastructureProgressUpdate.objects.all().iterator():
        previous = normalize(update.previous_official_status, unknown_values)
        new = normalize(update.new_official_status, unknown_values)
        changed = []
        if previous != update.previous_official_status:
            update.previous_official_status = previous
            changed.append('previous_official_status')
        if new != update.new_official_status:
            update.new_official_status = new
            changed.append('new_official_status')
        if changed:
            update.save(update_fields=changed)

    for revision in ProjectRevision.objects.all().iterator():
        snapshot = deepcopy(revision.snapshot or {})
        infrastructure = snapshot.get('infrastructure')
        if not isinstance(infrastructure, dict):
            continue
        changed = False
        if 'award_status' in infrastructure and 'status' not in infrastructure:
            infrastructure['status'] = infrastructure.pop('award_status')
            changed = True
        value = normalize(infrastructure.get('status'), unknown_values)
        if value != infrastructure.get('status'):
            infrastructure['status'] = value
            changed = True
        label = STATUS_LABELS.get(value)
        if label and infrastructure.get('status_label') != label:
            infrastructure['status_label'] = label
            changed = True
        if 'award_status_label' in infrastructure:
            infrastructure.pop('award_status_label')
            changed = True
        if changed:
            revision.snapshot = snapshot
            revision.save(update_fields=['snapshot'])

    if unknown_values:
        print(
            'Infrastructure status migration mapped unknown values to On Hold: '
            + ', '.join(sorted(unknown_values))
        )


def backwards(apps, schema_editor):
    InfrastructureProject = apps.get_model('system', 'InfrastructureProject')
    ProjectRevision = apps.get_model('system', 'ProjectRevision')
    for revision in ProjectRevision.objects.all().iterator():
        snapshot = deepcopy(revision.snapshot or {})
        infrastructure = snapshot.get('infrastructure')
        if not isinstance(infrastructure, dict) or 'status' not in infrastructure:
            continue
        infrastructure['award_status'] = infrastructure.pop('status')
        infrastructure['award_status_label'] = infrastructure.pop('status_label', '')
        revision.snapshot = snapshot
        revision.save(update_fields=['snapshot'])


class Migration(migrations.Migration):
    dependencies = [
        ('system', '0005_noninfrastructureproject_contractor_supplier_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='infrastructureproject',
            name='award_status',
            field=models.CharField(
                blank=True,
                choices=[
                    ('not_yet_started', 'Not Yet Started'),
                    ('ongoing', 'Ongoing'),
                    ('on_hold', 'On Hold'),
                    ('completed', 'Completed'),
                ],
                db_column='award_status',
                max_length=50,
                null=True,
            ),
        ),
        migrations.RenameField(
            model_name='infrastructureproject',
            old_name='award_status',
            new_name='status',
        ),
        migrations.AlterField(
            model_name='infrastructureprogressupdate',
            name='previous_official_status',
            field=models.CharField(
                blank=True,
                choices=[
                    ('not_yet_started', 'Not Yet Started'),
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
            name='new_official_status',
            field=models.CharField(
                blank=True,
                choices=[
                    ('not_yet_started', 'Not Yet Started'),
                    ('ongoing', 'Ongoing'),
                    ('on_hold', 'On Hold'),
                    ('completed', 'Completed'),
                ],
                default='',
                max_length=50,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
