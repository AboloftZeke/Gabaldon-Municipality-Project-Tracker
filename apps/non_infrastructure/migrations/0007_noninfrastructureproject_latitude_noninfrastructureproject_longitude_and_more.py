from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('non_infrastructure', '0006_remove_noninfrastructureproject_publication_status_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='noninfrastructureproject',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='noninfrastructureproject',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='noninfrastructureproject',
            name='is_public',
            field=models.BooleanField(default=True),
        ),
    ]