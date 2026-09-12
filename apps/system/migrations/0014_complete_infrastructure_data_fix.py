import django.db.models.deletion
from django.db import migrations, models


def backfill_missing_infrastructure_data(apps, schema_editor):
    Address = apps.get_model('system', 'Address')
    Infrastructure_Project = apps.get_model('system', 'Infrastructure_Project')
    InfrastructureCategory = apps.get_model('system', 'InfrastructureCategory')
    LegacyProject = apps.get_model('infrastructure', 'InfrastructureProject')

    for old in LegacyProject.objects.all().order_by('id'):
        infra = Infrastructure_Project.objects.filter(infrastructure_title=old.title).order_by('infrastructure_id').first()
        if infra is None:
            continue

        if infra.category_id is None and old.category:
            category_code = str(old.category).strip().lower()
            category = InfrastructureCategory.objects.filter(category_code=category_code).first()
            if category is None:
                category = InfrastructureCategory.objects.filter(category_name__iexact=str(old.category)).first()
            if category is None:
                category = InfrastructureCategory.objects.create(
                    category_code=category_code or 'other',
                    category_name=(str(old.category).replace('_', ' ').title() or 'Other'),
                    description='Migrated from legacy infrastructure project.',
                    is_active=True,
                )
            infra.category = category

        address = infra.address
        if address is None and (old.location or old.latitude is not None or old.longitude is not None):
            address = Address.objects.create(
                street='',
                barangay=str(old.location).strip() or None,
                municipality='Gabaldon',
                province='Nueva Ecija',
                country='Philippines',
                postal_code='',
                latitude=old.latitude,
                longitude=old.longitude,
                is_active=True,
            )
            infra.address = address
        elif address is not None:
            updates = []
            if not address.barangay and old.location:
                address.barangay = str(old.location).strip() or None
                updates.append('barangay')
            if address.latitude is None and old.latitude is not None:
                address.latitude = old.latitude
                updates.append('latitude')
            if address.longitude is None and old.longitude is not None:
                address.longitude = old.longitude
                updates.append('longitude')
            if updates:
                address.save(update_fields=updates)

        infra.procurement_method = old.procurement_method or None
        infra.award_status = old.award_status or None
        infra.planned_start_date = old.planned_start_date or None
        infra.planned_end_date = old.planned_end_date or None
        infra.cost_progress_percentage = old.cost_progress_percentage or None
        infra.physical_progress_percentage = old.physical_progress_percentage or None
        infra.save()


class Migration(migrations.Migration):

    dependencies = [
        ('system', '0013_remove_legacy_user_profile_tables'),
        ('infrastructure', '0005_infrastructureproject_description_infrastructureproject_latitude_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='address',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name='address',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='infrastructure_project',
            name='award_status',
            field=models.CharField(blank=True, choices=[('awarded', 'Awarded'), ('ongoing_bidding', 'Ongoing Bidding'), ('cancelled', 'Cancelled'), ('rebid', 'Re-bid'), ('completed', 'Completed')], max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='infrastructure_project',
            name='cost_progress_percentage',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name='infrastructure_project',
            name='physical_progress_percentage',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name='infrastructure_project',
            name='planned_end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='infrastructure_project',
            name='planned_start_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='infrastructure_project',
            name='procurement_method',
            field=models.CharField(blank=True, choices=[('competitive_bidding', 'Competitive Bidding / Public Bidding'), ('svp', 'SVP (Small Value Procurement)'), ('nq', 'NQ (Negotiated Quotation)'), ('shopping', 'Shopping'), ('direct_contracting', 'Direct Contracting'), ('force_account', 'Force Account')], max_length=50, null=True),
        ),
        migrations.CreateModel(
            name='Project_Image',
            fields=[
                ('project_image_id', models.BigAutoField(primary_key=True, serialize=False)),
                ('image_url', models.URLField(blank=True, max_length=500, null=True)),
                ('image_name', models.CharField(blank=True, max_length=255, null=True)),
                ('caption', models.CharField(blank=True, max_length=255, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='images', to='system.project')),
            ],
            options={
                'verbose_name': 'Project Image',
                'verbose_name_plural': 'Project Images',
            },
        ),
        migrations.CreateModel(
            name='Reports',
            fields=[
                ('report_id', models.BigAutoField(primary_key=True, serialize=False)),
                ('report_name', models.CharField(max_length=255)),
                ('report_type', models.CharField(blank=True, max_length=100, null=True)),
                ('file_url', models.URLField(blank=True, max_length=500, null=True)),
                ('notes', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='system.project')),
            ],
            options={
                'verbose_name': 'Report',
                'verbose_name_plural': 'Reports',
            },
        ),
        migrations.CreateModel(
            name='Reports_Template',
            fields=[
                ('template_id', models.BigAutoField(primary_key=True, serialize=False)),
                ('template_name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, default='')),
                ('file_url', models.URLField(blank=True, max_length=500, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Report Template',
                'verbose_name_plural': 'Report Templates',
            },
        ),
        migrations.RunPython(backfill_missing_infrastructure_data, reverse_code=migrations.RunPython.noop),
    ]
