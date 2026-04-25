from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('infrastructure', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='InfrastructureProject',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('location', models.CharField(choices=[('bagong_sikat', 'Bagong Sikat'), ('bagting', 'Bagting'), ('bantug', 'Bantug'), ('bitulok', 'Bitulok (North Poblacion)'), ('bugnan', 'Bugnan'), ('calabasa', 'Calabasa'), ('camachile', 'Camachile'), ('cuyapa', 'Cuyapa'), ('ligaya', 'Ligaya'), ('macasandal', 'Macasandal'), ('malinao', 'Malinao'), ('pantoc', 'Pantoc'), ('pinamalisan', 'Pinamalisan'), ('south_poblacion', 'South Poblacion'), ('sawmill', 'Sawmill'), ('tagumpay', 'Tagumpay')], help_text='Select barangay location', max_length=50)),
                ('implementing_office', models.CharField(help_text='Office/Agency responsible for implementation', max_length=255)),
                ('category', models.CharField(choices=[('road', 'Road & Bridge'), ('water', 'Water Supply'), ('sanitation', 'Sanitation'), ('health', 'Health Facility'), ('education', 'Education Facility'), ('energy', 'Energy'), ('ict', 'ICT/Telecommunications'), ('agriculture', 'Agriculture'), ('environment', 'Environment'), ('sports', 'Sports/Recreation'), ('other', 'Other')], max_length=50)),
                ('contractor', models.CharField(blank=True, help_text='Company name', max_length=255)),
                ('procurement_method', models.CharField(choices=[('competitive_bidding', 'Competitive Bidding / Public Bidding'), ('svp', 'SVP (Small Value Procurement)'), ('nq', 'NQ (Negotiated Quotation)'), ('shopping', 'Shopping'), ('direct_contracting', 'Direct Contracting'), ('force_account', 'Force Account')], max_length=50)),
                ('posting_date', models.DateField(blank=True, null=True, verbose_name='Posting Date')),
                ('prebid_date', models.DateField(blank=True, null=True, verbose_name='Pre-bid Conference Date')),
                ('bidding_date', models.DateField(blank=True, null=True, verbose_name='Bidding Date')),
                ('noa_date', models.DateField(blank=True, null=True, verbose_name='Notice of Award (NOA) Date')),
                ('ntp_date', models.DateField(blank=True, null=True, verbose_name='Notice to Proceed (NTP) Date')),
                ('award_status', models.CharField(choices=[('awarded', 'Awarded'), ('ongoing_bidding', 'Ongoing Bidding'), ('cancelled', 'Cancelled'), ('rebid', 'Re-bid'), ('completed', 'Completed')], default='ongoing_bidding', max_length=50)),
                ('source_of_fund', models.CharField(blank=True, help_text='e.g., 20% Development Fund', max_length=255)),
                ('abc_amount', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name='Approved Budget for Contract (ABC)')),
                ('contract_price', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name='Contract Price / Bid Amount')),
                ('variation_orders', models.TextField(blank=True, help_text='Record of variation orders with amounts, reasons, and approval dates')),
                ('disbursements_to_date', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name='Total Disbursements/Payments to Date')),
                ('disbursement_details', models.TextField(blank=True, help_text='Breakdown by milestone or payment schedule')),
                ('planned_start_date', models.DateField(blank=True, null=True)),
                ('planned_end_date', models.DateField(blank=True, null=True)),
                ('actual_start_date', models.DateField(blank=True, null=True)),
                ('revised_completion_date', models.DateField(blank=True, null=True, help_text='Extension of time')),
                ('cost_progress_percentage', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='Cost Progress (%)')),
                ('physical_progress_percentage', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='Physical Progress (%)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('publication_status', models.CharField(choices=[('draft', 'Draft'), ('pending_review', 'Pending Review'), ('published', 'Published'), ('needs_revision', 'Needs Revision'), ('rejected', 'Rejected')], default='draft', max_length=50)),
                ('review_comments', models.TextField(blank=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='projects_created', to=settings.AUTH_USER_MODEL)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='projects_reviewed', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='projects_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at'], 'verbose_name': 'Infrastructure Project', 'verbose_name_plural': 'Infrastructure Projects'},
        ),
    ]
