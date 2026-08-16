from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('system', '0019_remove_project_image_caption_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='userflag',
            name='department',
            field=models.CharField(
                blank=True,
                choices=[('engineer', 'Engineering Office'), ('mayor', "Mayor's Office"), ('admin', 'Administration')],
                default='admin',
                max_length=20,
            ),
        ),
    ]
