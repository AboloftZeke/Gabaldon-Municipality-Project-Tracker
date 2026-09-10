from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('system', '0030_remove_must_change_password'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userflag',
            name='department',
            field=models.CharField(
                blank=True,
                choices=[
                    ('engineer', 'Engineering Office'),
                    ('mayor', "Mayor's Office"),
                    ('infra_checker', 'Infrastructure Project Checker'),
                    (
                        'noninfra_checker',
                        'Non-Infrastructure Project Checker',
                    ),
                    ('admin', 'Administration'),
                ],
                default='admin',
                max_length=20,
            ),
        ),
    ]
