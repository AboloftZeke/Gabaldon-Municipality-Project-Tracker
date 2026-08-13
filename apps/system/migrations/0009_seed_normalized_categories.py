from django.db import migrations


INFRASTRUCTURE_CATEGORY_MAP = {
    'road': {'category_name': 'Road & Bridge', 'description': 'Road & Bridge'},
    'water': {'category_name': 'Water Supply', 'description': 'Water Supply'},
    'sanitation': {'category_name': 'Sanitation', 'description': 'Sanitation'},
    'health': {'category_name': 'Health Facility', 'description': 'Health Facility'},
    'education': {'category_name': 'Education Facility', 'description': 'Education Facility'},
    'energy': {'category_name': 'Energy', 'description': 'Energy'},
    'ict': {'category_name': 'ICT/Telecommunications', 'description': 'ICT/Telecommunications'},
    'agriculture': {'category_name': 'Agriculture', 'description': 'Agriculture'},
    'environment': {'category_name': 'Environment', 'description': 'Environment'},
    'sports': {'category_name': 'Sports/Recreation', 'description': 'Sports/Recreation'},
    'other': {'category_name': 'Other', 'description': 'Other'},
}

NON_INFRASTRUCTURE_CATEGORY_MAP = {
    'social_services': {'type_name': 'Social Services', 'description': 'Social Services'},
    'community_development': {'type_name': 'Community Development', 'description': 'Community Development'},
    'livelihood': {'type_name': 'Livelihood Programs', 'description': 'Livelihood Programs'},
    'governance': {'type_name': 'Governance', 'description': 'Governance'},
    'education_support': {'type_name': 'Education Support', 'description': 'Education Support'},
    'health_support': {'type_name': 'Health Support', 'description': 'Health Support'},
    'cultural': {'type_name': 'Cultural & Heritage', 'description': 'Cultural & Heritage'},
    'tourism': {'type_name': 'Tourism Development', 'description': 'Tourism Development'},
    'disaster_management': {'type_name': 'Disaster Management', 'description': 'Disaster Management'},
    'other': {'type_name': 'Other', 'description': 'Other'},
}


def seed_categories(apps, schema_editor):
    InfrastructureCategory = apps.get_model('system', 'InfrastructureCategory')
    NonInfrastructureCategory = apps.get_model('system', 'NonInfrastructureCategory')

    for code, defaults in INFRASTRUCTURE_CATEGORY_MAP.items():
        InfrastructureCategory.objects.get_or_create(
            category_code=code,
            defaults={'category_name': defaults['category_name'], 'description': defaults['description'], 'is_active': True},
        )

    for code, defaults in NON_INFRASTRUCTURE_CATEGORY_MAP.items():
        NonInfrastructureCategory.objects.get_or_create(
            type_code=code,
            defaults={'type_name': defaults['type_name'], 'description': defaults['description']},
        )


def reverse_seed_categories(apps, schema_editor):
    InfrastructureCategory = apps.get_model('system', 'InfrastructureCategory')
    NonInfrastructureCategory = apps.get_model('system', 'NonInfrastructureCategory')
    InfrastructureCategory.objects.all().delete()
    NonInfrastructureCategory.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('system', '0008_migrate_legacy_projects_to_normalized_models'),
    ]

    operations = [
        migrations.RunPython(seed_categories, reverse_code=reverse_seed_categories),
    ]
