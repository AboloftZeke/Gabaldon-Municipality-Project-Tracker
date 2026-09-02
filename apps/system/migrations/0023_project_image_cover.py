from django.db import migrations, models


def set_initial_cover_images(apps, schema_editor):
    ProjectImage = apps.get_model('system', 'Project_Image')

    project_ids = (
        ProjectImage.objects
        .values_list('project_id', flat=True)
        .distinct()
    )

    for project_id in project_ids:
        cover = (
            ProjectImage.objects
            .filter(project_id=project_id)
            .order_by('-created_at', '-project_image_id')
            .first()
        )
        if cover:
            ProjectImage.objects.filter(pk=cover.pk).update(is_cover=True)


class Migration(migrations.Migration):

    dependencies = [
        ('system', '0022_non_infrastructure_project_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='project_image',
            name='is_cover',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(
            set_initial_cover_images,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='project_image',
            constraint=models.UniqueConstraint(
                fields=('project',),
                condition=models.Q(is_cover=True),
                name='unique_cover_image_per_project',
            ),
        ),
    ]
