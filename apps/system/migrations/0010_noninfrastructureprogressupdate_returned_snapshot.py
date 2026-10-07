from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('system', '0009_noninfrastructureprogressupdate_applied_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='noninfrastructureprogressupdate',
            name='returned_snapshot',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
