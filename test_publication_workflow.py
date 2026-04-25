#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import InfrastructureProject, UserProfile
from django.utils import timezone

# Create test users
engineer_user, _ = User.objects.get_or_create(
    username='eng_test',
    defaults={
        'email': 'eng@test.com',
        'first_name': 'Engineer',
        'last_name': 'Test',
        'is_staff': True
    }
)

admin_user, _ = User.objects.get_or_create(
    username='admin_test',
    defaults={
        'email': 'admin@test.com',
        'first_name': 'Admin',
        'last_name': 'Test',
        'is_staff': True,
        'is_superuser': True
    }
)

# Create profiles
eng_profile, _ = UserProfile.objects.get_or_create(
    user=engineer_user,
    defaults={'department': 'engineer'}
)

admin_profile, _ = UserProfile.objects.get_or_create(
    user=admin_user,
    defaults={'department': 'admin'}
)

# Create a test project
project, created = InfrastructureProject.objects.get_or_create(
    title='Test Infrastructure Project',
    created_by=engineer_user,
    defaults={
        'location': 'bagong_sikat',
        'category': 'road',
        'implementing_office': 'Engineering Office',
        'procurement_method': 'competitive_bidding',
        'publication_status': 'draft',
    }
)

print("✅ Test setup complete!")
print()
print("Test Users:")
print(f"  - Engineer: {engineer_user.username} (dept: {eng_profile.department})")
print(f"  - Admin: {admin_user.username} (dept: {admin_profile.department})")
print()
print("Test Project:")
print(f"  - Title: {project.title}")
print(f"  - Status: {project.get_publication_status_display()}")
print(f"  - Created by: {project.created_by.username}")
print()

print("Publication Status Choices:")
for value, label in InfrastructureProject.PUBLICATION_STATUS_CHOICES:
    print(f"  • {label} ({value})")
print()

print("✅ All publication workflow fields are configured!")
print()
print("Workflow Summary:")
print("1. Engineer creates project (status: Draft)")
print("2. Engineer submits for review (status: Pending Review)")
print("3. Admin reviews and chooses:")
print("   - Approve & Publish (status: Published)")
print("   - Return for Revision (status: Needs Revision + comments)")
print("   - Reject (status: Rejected + reason)")
