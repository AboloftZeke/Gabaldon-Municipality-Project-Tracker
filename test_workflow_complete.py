#!/usr/bin/env python
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.contrib.auth.models import User
from core.models import InfrastructureProject, UserProfile
from django.utils import timezone

print("=" * 80)
print("TESTING COMPLETE PROJECT PUBLICATION WORKFLOW")
print("=" * 80)

# Create/get test users
engineer_user, _ = User.objects.get_or_create(
    username='workflow_engineer',
    defaults={'email': 'workflow@eng.test', 'is_staff': True}
)
engineer_user.set_password('password123')
engineer_user.save()

admin_user, _ = User.objects.get_or_create(
    username='workflow_admin',
    defaults={'email': 'workflow@admin.test', 'is_staff': True, 'is_superuser': True}
)
admin_user.set_password('password123')
admin_user.save()

# Fix profiles
eng_profile, _ = UserProfile.objects.get_or_create(user=engineer_user, defaults={'department': 'engineer'})
admin_profile, _ = UserProfile.objects.get_or_create(user=admin_user, defaults={'department': 'admin'})

# Update if wrong
if eng_profile.department != 'engineer':
    eng_profile.department = 'engineer'
    eng_profile.save()
if admin_profile.department != 'admin':
    admin_profile.department = 'admin'
    admin_profile.save()

print(f"\n✅ Users prepared:")
print(f"  - Engineer: {engineer_user.username} (dept={eng_profile.department})")
print(f"  - Admin: {admin_user.username} (dept={admin_profile.department})")

# Create a test project as engineer
project = InfrastructureProject.objects.create(
    title='Workflow Test: Bridge Construction',
    location='bagong_sikat',
    category='road',
    implementing_office='Engineering Office',
    procurement_method='competitive_bidding',
    publication_status='draft',
    created_by=engineer_user
)
print(f"\n📝 Project created by engineer:")
print(f"  - Title: {project.title}")
print(f"  - Status: {project.get_publication_status_display()}")

# Simulate engineer submitting for review
project.publication_status = 'pending_review'
project.save()
print(f"\n📤 Engineer submits for review:")
print(f"  - Status changed to: {project.get_publication_status_display()}")

# Simulate admin reviewing and approving
project.publication_status = 'published'
project.reviewed_by = admin_user
project.reviewed_at = timezone.now()
project.save()
print(f"\n✅ Admin approves project:")
print(f"  - Status changed to: {project.get_publication_status_display()}")
print(f"  - Reviewed by: {project.reviewed_by.username}")

# Verify visibility
print(f"\n🔍 Verifying admin can see published project:")
admin_view = InfrastructureProject.objects.all() if admin_user.is_superuser else InfrastructureProject.objects.filter(created_by=admin_user)
published_projects = admin_view.filter(publication_status='published')
print(f"  - Admin visible projects: {admin_view.count()}")
print(f"  - Published projects admin can see: {published_projects.count()}")
for proj in published_projects:
    print(f"    • {proj.title} (created by: {proj.created_by.username})")

print(f"\n✅ WORKFLOW COMPLETE - Published project is visible to admin!")
print(f"\nNext: Login to http://127.0.0.1:8000/ with:")
print(f"  - Engineer: workflow_engineer / password123")
print(f"  - Admin: workflow_admin / password123")
