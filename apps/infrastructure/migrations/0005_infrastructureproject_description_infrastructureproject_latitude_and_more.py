from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('infrastructure', '0004_remove_infrastructureproject_bidding_date_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='infrastructureproject',
            name='description',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='infrastructureproject',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='infrastructureproject',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='infrastructureproject',
            name='is_public',
            field=models.BooleanField(default=True),
        ),
    ]