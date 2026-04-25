#!/usr/bin/env python
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.contrib.auth.models import User
from core.models import InfrastructureProject, UserProfile
from django.test import Client

print("=" * 80)
print("TESTING PROJECT SUBMISSION FOR REVIEW")
print("=" * 80)

# Create test users
engineer_user, _ = User.objects.get_or_create(
    username='submit_test_eng',
    defaults={'email': 'submit@eng.test', 'is_staff': True}
)
engineer_user.set_password('password123')
engineer_user.save()

eng_profile, _ = UserProfile.objects.get_or_create(
    user=engineer_user,
    defaults={'department': 'engineer'}
)
if eng_profile.department != 'engineer':
    eng_profile.department = 'engineer'
    eng_profile.save()

print(f"✅ Engineer user: {engineer_user.username}")

# Create a draft project
project = InfrastructureProject.objects.create(
    title='Submit Test Project',
    location='bagong_sikat',
    category='road',
    implementing_office='Engineering Office',
    procurement_method='competitive_bidding',
    publication_status='draft',
    created_by=engineer_user
)
print(f"✅ Draft project created: ID={project.id}, Status={project.get_publication_status_display()}")

# Test the submission using Django test client
client = Client()

# Login as engineer
login_success = client.login(username='submit_test_eng', password='password123')
print(f"\n🔐 Login result: {'SUCCESS' if login_success else 'FAILED'}")

# Try to POST to the publish endpoint
print(f"\n📤 Submitting project {project.id} for review...")
response = client.post(f'/projects/{project.id}/publish/')

print(f"  - Response status code: {response.status_code}")
print(f"  - Response URL: {response.url if hasattr(response, 'url') else 'N/A'}")

# Check if project status was updated
project.refresh_from_db()
print(f"\n🔍 Project status after submission attempt:")
print(f"  - Current status: {project.get_publication_status_display()}")
print(f"  - Expected status: Pending Review")
print(f"  - Status correct: {'✅ YES' if project.publication_status == 'pending_review' else '❌ NO'}")

# Check what's in pending_review
print(f"\n📋 Projects in pending_review status:")
pending = InfrastructureProject.objects.filter(publication_status='pending_review')
print(f"  - Count: {pending.count()}")
for p in pending:
    print(f"    • {p.title} (ID: {p.id})")

if project.publication_status != 'pending_review':
    print(f"\n⚠️  Status was not updated! Checking project details...")
    print(f"  - project.publication_status value: {project.publication_status}")
    print(f"  - PUBLICATION_STATUS_CHOICES: {InfrastructureProject.PUBLICATION_STATUS_CHOICES}")
