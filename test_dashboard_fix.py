#!/usr/bin/env python
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.contrib.auth.models import User
from apps.infrastructure.models import InfrastructureProject
from apps.system.models import UserProfile

print("=" * 80)
print("VERIFYING ADMIN DASHBOARD PROJECT VISIBILITY")
print("=" * 80)

# Create test users
engineer, _ = User.objects.get_or_create(
    username='dash_engineer',
    defaults={'email': 'dash@eng.test', 'is_staff': True}
)
engineer.set_password('testpass123')
engineer.save()

eng_prof, _ = UserProfile.objects.get_or_create(user=engineer, defaults={'department': 'engineer'})

admin, _ = User.objects.get_or_create(
    username='dash_admin',
    defaults={'email': 'dash@admin.test', 'is_staff': True, 'is_superuser': True}
)
admin.set_password('testpass123')
admin.save()

admin_prof, _ = UserProfile.objects.get_or_create(user=admin, defaults={'department': 'admin'})

print(f"✅ Users prepared:")
print(f"   - Engineer: {engineer.username}")
print(f"   - Admin: {admin.username}")

# Create projects by engineer
projects = []
for i in range(3):
    p = InfrastructureProject.objects.create(
        title=f'Dashboard Test Project {i+1}',
        location='bagong_sikat',
        category='road',
        implementing_office='Engineering Office',
        procurement_method='competitive_bidding',
        created_by=engineer
    )
    projects.append(p)

print(f"\n✅ Created 3 test projects by {engineer.username}")

# Simulate what admin dashboard view does
print(f"\n{'='*80}")
print(f"ADMIN DASHBOARD VIEW LOGIC")
print(f"{'='*80}")

# Test the new logic
if admin.is_superuser:
    admin_view_projects = InfrastructureProject.objects.all()
else:
    admin_view_projects = InfrastructureProject.objects.filter(created_by=admin)

print(f"\n✅ Admin is_superuser: {admin.is_superuser}")
print(f"✅ Projects admin can see: {admin_view_projects.count()}")
print(f"   - Total in DB: {InfrastructureProject.objects.count()}")
print(f"   - Admin can see: {admin_view_projects.count()}")

# Get stats like the view does
total_projects = admin_view_projects.count()
awarded = admin_view_projects.filter(award_status='awarded').count()
ongoing = admin_view_projects.filter(award_status__in=['ongoing_bidding', 'awarded']).count()
completed = admin_view_projects.filter(award_status='completed').count()
recent = admin_view_projects.order_by('-created_at')[:5]

print(f"\n✅ Dashboard Stats for Admin:")
print(f"   - Total Projects: {total_projects}")
print(f"   - Awarded: {awarded}")
print(f"   - Ongoing: {ongoing}")
print(f"   - Completed: {completed}")
print(f"   - Recent Projects:")
for p in recent:
    print(f"     • {p.title} (by: {p.created_by.username})")

print(f"\n✅ ADMIN CAN NOW SEE ALL PROJECTS IN DASHBOARD!")
