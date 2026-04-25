#!/usr/bin/env python
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.contrib.auth.models import User
from core.models import InfrastructureProject, UserProfile

print("=" * 80)
print("DATABASE STATE ANALYSIS")
print("=" * 80)

# Check users and their profiles
print("\n📋 USERS AND PROFILES:")
for user in User.objects.all():
    profile = user.profile if hasattr(user, 'profile') else None
    dept = profile.department if profile else "NO PROFILE"
    print(f"  - {user.username}: is_superuser={user.is_superuser}, department={dept}")

# Check all projects
print("\n📋 ALL PROJECTS IN DATABASE:")
for project in InfrastructureProject.objects.all():
    print(f"  - ID: {project.id}")
    print(f"    Title: {project.title}")
    print(f"    Created by: {project.created_by.username}")
    print(f"    Status: {project.get_publication_status_display()}")
    print(f"    Reviewed by: {project.reviewed_by.username if project.reviewed_by else 'None'}")
    print()

# Check projects filtered by status
print("\n📋 PROJECTS BY PUBLICATION STATUS:")
for status_val, status_label in InfrastructureProject.PUBLICATION_STATUS_CHOICES:
    count = InfrastructureProject.objects.filter(publication_status=status_val).count()
    print(f"  - {status_label}: {count} projects")

# What an admin would see
admin = User.objects.filter(is_superuser=True).first()
if admin:
    print(f"\n📋 WHAT ADMIN '{admin.username}' SEES:")
    if admin.is_superuser:
        projects = InfrastructureProject.objects.all()
    else:
        projects = InfrastructureProject.objects.filter(created_by=admin)
    print(f"  - Total visible: {projects.count()}")
    for proj in projects[:5]:
        print(f"    • {proj.title} (status: {proj.get_publication_status_display()}, created by: {proj.created_by.username})")
