from django.db import migrations
from django.utils.text import slugify


INFRASTRUCTURE_CATEGORY_MAP = {
    'road': ('road', 'Road & Bridge'),
    'water': ('water', 'Water Supply'),
    'sanitation': ('sanitation', 'Sanitation'),
    'health': ('health', 'Health Facility'),
    'education': ('education', 'Education Facility'),
    'energy': ('energy', 'Energy'),
    'ict': ('ict', 'ICT/Telecommunications'),
    'agriculture': ('agriculture', 'Agriculture'),
    'environment': ('environment', 'Environment'),
    'sports': ('sports', 'Sports/Recreation'),
    'other': ('other', 'Other'),
}

NON_INFRASTRUCTURE_CATEGORY_MAP = {
    'social_services': ('social_services', 'Social Services'),
    'community_development': ('community_development', 'Community Development'),
    'livelihood': ('livelihood', 'Livelihood Programs'),
    'governance': ('governance', 'Governance'),
    'education_support': ('education_support', 'Education Support'),
    'health_support': ('health_support', 'Health Support'),
    'cultural': ('cultural', 'Cultural & Heritage'),
    'tourism': ('tourism', 'Tourism Development'),
    'disaster_management': ('disaster_management', 'Disaster Management'),
    'other': ('other', 'Other'),
}


def ensure_unique_code(model, field_name, base_value, max_length=100):
    value = slugify(base_value or 'record')[:max_length] or 'record'
    candidate = value
    index = 1
    while model.objects.filter(**{field_name: candidate}).exists():
        suffix = f'-{index}'
        candidate = (value[: max_length - len(suffix)] + suffix)[:max_length]
        index += 1
    return candidate


def ensure_lookup_records(apps):
    InfrastructureCategory = apps.get_model('system', 'InfrastructureCategory')
    NonInfrastructureCategory = apps.get_model('system', 'NonInfrastructureCategory')
    Contractor = apps.get_model('system', 'Contractor')
    ImplementingOffice = apps.get_model('system', 'ImplementingOffice')
    FundSource = apps.get_model('system', 'FundSource')

    for code, (_, label) in INFRASTRUCTURE_CATEGORY_MAP.items():
        InfrastructureCategory.objects.get_or_create(
            category_code=code,
            defaults={'category_name': label, 'description': label, 'is_active': True},
        )

    for code, (_, label) in NON_INFRASTRUCTURE_CATEGORY_MAP.items():
        NonInfrastructureCategory.objects.get_or_create(
            type_code=code,
            defaults={'type_name': label, 'description': label},
        )

    return InfrastructureCategory, NonInfrastructureCategory, Contractor, ImplementingOffice, FundSource


def migrate_legacy_projects(apps, schema_editor):
    Address = apps.get_model('system', 'Address')
    Project = apps.get_model('system', 'Project')
    InfrastructureCategory = apps.get_model('system', 'InfrastructureCategory')
    Contractor = apps.get_model('system', 'Contractor')
    ImplementingOffice = apps.get_model('system', 'ImplementingOffice')
    FundSource = apps.get_model('system', 'FundSource')
    Infrastructure_Project = apps.get_model('system', 'Infrastructure_Project')

    LegacyInfrastructureProject = apps.get_model('infrastructure', 'InfrastructureProject')

    for old in LegacyInfrastructureProject.objects.all().order_by('id'):
        project = Project.objects.create(
            project_type='infrastructure',
            created_by_user=old.created_by,
            updated_by_user=old.updated_by,
            is_published=False,
            is_visible_to_public=bool(old.is_public),
        )

        address = None
        location_value = (old.location or '').strip()
        if location_value or old.latitude is not None or old.longitude is not None:
            address = Address.objects.create(
                street='',
                barangay=location_value or None,
                municipality='Gabaldon',
                province='Nueva Ecija',
                country='Philippines',
                postal_code='',
                latitude=old.latitude,
                longitude=old.longitude,
                is_active=True,
            )

        contractor_name = (old.contractor or '').strip()
        contractor = None
        if contractor_name:
            contractor, _ = Contractor.objects.get_or_create(
                contractor_name=contractor_name,
                defaults={'is_active': True},
            )

        office_name = (old.implementing_office or '').strip()
        office = None
        if office_name:
            office, _ = ImplementingOffice.objects.get_or_create(
                office_name=office_name,
                defaults={'is_active': True},
            )

        category = None
        if old.category:
            category = InfrastructureCategory.objects.filter(category_code=old.category).first()

        fund_source_name = (old.source_of_fund or '').strip()
        fund_source = None
        if fund_source_name:
            code = ensure_unique_code(FundSource, 'fund_source_code', fund_source_name, max_length=100)
            fund_source, _ = FundSource.objects.get_or_create(
                fund_source_name=fund_source_name,
                defaults={
                    'fund_source_code': code,
                    'fund_percentage': None,
                    'description': fund_source_name,
                    'is_active': True,
                },
            )

        Infrastructure_Project.objects.create(
            project=project,
            infrastructure_code=f'INF-{project.project_id:05d}',
            infrastructure_title=old.title,
            infrastructure_description=old.description or '',
            category=category,
            address=address,
            contractor=contractor,
            implementing_office=office,
        )


def reverse_migration(apps, schema_editor):
    Project = apps.get_model('system', 'Project')
    Infrastructure_Project = apps.get_model('system', 'Infrastructure_Project')
    Address = apps.get_model('system', 'Address')
    Infrastructure_Project.objects.all().delete()
    Project.objects.all().delete()
    Address.objects.filter(municipality='Gabaldon', province='Nueva Ecija', country='Philippines').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('system', '0007_infrastructure_project_non_infrastructure_project'),
        ('infrastructure', '0005_infrastructureproject_description_infrastructureproject_latitude_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_legacy_projects, reverse_code=reverse_migration),
    ]
