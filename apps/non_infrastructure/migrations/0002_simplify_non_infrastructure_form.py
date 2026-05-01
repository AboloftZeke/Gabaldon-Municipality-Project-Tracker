# Generated migration for non_infrastructure app simplification

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('non_infrastructure', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='noninfrastructureproject',
            name='description',
            field=models.TextField(blank=True, help_text='Project description and objectives'),
        ),
        migrations.AddField(
            model_name='noninfrastructureproject',
            name='overall_progress_percentage',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='Overall Progress (%)'),
        ),
        migrations.RemoveField(
            model_name='noninfrastructureproject',
            name='contractor',
        ),
        migrations.RemoveField(
            model_name='noninfrastructureproject',
            name='procurement_method',
        ),
        migrations.RemoveField(
            model_name='noninfrastructureproject',
            name='posting_date',
        ),
        migrations.RemoveField(
            model_name='noninfrastructureproject',
            name='prebid_date',
        ),
        migrations.RemoveField(
            model_name='noninfrastructureproject',
            name='bidding_date',
        ),
        migrations.RemoveField(
            model_name='noninfrastructureproject',
            name='noa_date',
        ),
        migrations.RemoveField(
            model_name='noninfrastructureproject',
            name='ntp_date',
        ),
        migrations.RemoveField(
            model_name='noninfrastructureproject',
            name='award_status',
        ),
        migrations.RemoveField(
            model_name='noninfrastructureproject',
            name='abc_amount',
        ),
        migrations.RemoveField(
            model_name='noninfrastructureproject',
            name='contract_price',
        ),
        migrations.RemoveField(
            model_name='noninfrastructureproject',
            name='variation_orders',
        ),
        migrations.RemoveField(
            model_name='noninfrastructureproject',
            name='disbursements_to_date',
        ),
        migrations.RemoveField(
            model_name='noninfrastructureproject',
            name='disbursement_details',
        ),
        migrations.RemoveField(
            model_name='noninfrastructureproject',
            name='cost_progress_percentage',
        ),
        migrations.RemoveField(
            model_name='noninfrastructureproject',
            name='physical_progress_percentage',
        ),
    ]
