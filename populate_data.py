import os
import django
from datetime import datetime, timedelta
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Project, ProjectUpdate
from django.contrib.auth.models import User, Group

# Create sample users and groups if they don't exist
admin_user, _ = User.objects.get_or_create(
    username='admin',
    defaults={'is_staff': True, 'is_superuser': True, 'email': 'admin@gabaldon.gov'}
)
admin_user.set_password('admin123')
admin_user.save()

mayor_user, _ = User.objects.get_or_create(
    username='mayor_office',
    defaults={'email': 'mayor@gabaldon.gov'}
)
mayor_user.set_password('password123')
mayor_user.save()

eng_user, _ = User.objects.get_or_create(
    username='engineering_office',
    defaults={'email': 'engineering@gabaldon.gov'}
)
eng_user.set_password('password123')
eng_user.save()

# Create groups
admin_group, _ = Group.objects.get_or_create(name='Admin')
mayor_group, _ = Group.objects.get_or_create(name='Office of the Mayor')
eng_group, _ = Group.objects.get_or_create(name='Municipal Engineering Office')

admin_user.groups.add(admin_group)
mayor_user.groups.add(mayor_group)
eng_user.groups.add(eng_group)

# Sample projects
projects_data = [
    {
        'title': 'Main Street Rehabilitation',
        'project_type': 'infra',
        'status': 'in_progress',
        'description': 'Complete rehabilitation of Main Street including new pavement, utilities upgrade, and pedestrian pathways.',
        'location': 'Main Street, Downtown',
        'implementing_office': 'engineering',
        'progress_percent': 65,
        'public_visible': True,
        'budget': Decimal('2500000.00'),
        'start_date': datetime.now().date() - timedelta(days=180),
        'target_completion': datetime.now().date() + timedelta(days=120),
    },
    {
        'title': 'City Hall Renovation',
        'project_type': 'infra',
        'status': 'in_progress',
        'description': 'Structural renovation and modernization of City Hall building including HVAC, electrical systems, and accessibility upgrades.',
        'location': 'City Hall Building',
        'implementing_office': 'engineering',
        'progress_percent': 40,
        'public_visible': True,
        'budget': Decimal('1800000.00'),
        'start_date': datetime.now().date() - timedelta(days=90),
        'target_completion': datetime.now().date() + timedelta(days=270),
    },
    {
        'title': 'Public Park Development',
        'project_type': 'non_infra',
        'status': 'planned',
        'description': 'Development of a new 5-hectare public park with playgrounds, sports facilities, and green spaces.',
        'location': 'North Barangay',
        'implementing_office': 'mayor',
        'progress_percent': 10,
        'public_visible': True,
        'budget': Decimal('850000.00'),
        'start_date': datetime.now().date() + timedelta(days=30),
        'target_completion': datetime.now().date() + timedelta(days=365),
    },
    {
        'title': 'Water Supply System Upgrade',
        'project_type': 'infra',
        'status': 'completed',
        'description': 'Upgrade of water distribution pipes and treatment facilities to improve water quality and reduce leakage.',
        'location': 'City-wide',
        'implementing_office': 'engineering',
        'progress_percent': 100,
        'public_visible': True,
        'budget': Decimal('3200000.00'),
        'start_date': datetime.now().date() - timedelta(days=540),
        'target_completion': datetime.now().date() - timedelta(days=30),
    },
    {
        'title': 'Community Health Center Construction',
        'project_type': 'non_infra',
        'status': 'in_progress',
        'description': 'Construction of a new state-of-the-art community health center with modern medical facilities.',
        'location': 'East District',
        'implementing_office': 'mayor',
        'progress_percent': 75,
        'public_visible': True,
        'budget': Decimal('1500000.00'),
        'start_date': datetime.now().date() - timedelta(days=150),
        'target_completion': datetime.now().date() + timedelta(days=60),
    },
    {
        'title': 'Street Lighting Installation',
        'project_type': 'infra',
        'status': 'completed',
        'description': 'Installation of 500 LED street lights in residential areas for improved public safety.',
        'location': 'Various residential areas',
        'implementing_office': 'engineering',
        'progress_percent': 100,
        'public_visible': True,
        'budget': Decimal('650000.00'),
        'start_date': datetime.now().date() - timedelta(days=180),
        'target_completion': datetime.now().date() - timedelta(days=15),
    },
    {
        'title': 'Agricultural Training Program',
        'project_type': 'non_infra',
        'status': 'in_progress',
        'description': 'Annual agricultural training and assistance program for local farmers to improve productivity.',
        'location': 'Municipal Extension Office',
        'implementing_office': 'mayor',
        'progress_percent': 50,
        'public_visible': False,
        'budget': Decimal('250000.00'),
        'start_date': datetime.now().date() - timedelta(days=60),
        'target_completion': datetime.now().date() + timedelta(days=90),
    },
    {
        'title': 'Emergency Response System',
        'project_type': 'infra',
        'status': 'on_hold',
        'description': 'Implementation of an integrated emergency response and disaster management system.',
        'location': 'Municipal Building',
        'implementing_office': 'engineering',
        'progress_percent': 25,
        'public_visible': False,
        'budget': Decimal('500000.00'),
        'start_date': datetime.now().date() - timedelta(days=45),
        'target_completion': datetime.now().date() + timedelta(days=200),
    },
]

# Create projects
created_count = 0
for proj_data in projects_data:
    project, created = Project.objects.get_or_create(
        title=proj_data['title'],
        defaults=proj_data
    )
    if created:
        created_count += 1
        # Create an initial update
        ProjectUpdate.objects.create(
            project=project,
            updated_by=admin_user,
            status=project.status,
            progress_percent=project.progress_percent,
            note='Initial project record created.'
        )
        print(f"[OK] Created: {project.title}")

print(f"\n[OK] Total projects created: {created_count}")
print(f"[OK] Total projects in database: {Project.objects.count()}")
print(f"[OK] Total project updates: {ProjectUpdate.objects.count()}")
print(f"\n[USERS] Sample users created:")
print(f"   - admin / admin123 (Superuser)")
print(f"   - mayor_office / password123 (Mayor's Office)")
print(f"   - engineering_office / password123 (Engineering Office)")
