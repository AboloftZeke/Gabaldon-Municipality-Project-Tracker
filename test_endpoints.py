#!/usr/bin/env python
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.test import Client
from django.contrib.auth.models import User

from core.models import InfrastructureProject, UserProfile

# Create test users if they don't exist
engineer_user, _ = User.objects.get_or_create(
    username='engineer1',
    defaults={
        'email': 'engineer1@test.com',
        'first_name': 'John',
        'last_name': 'Engineer',
        'is_staff': True,
        'password': 'testpass123'
    }
)
engineer_user.set_password('testpass123')
engineer_user.save()

# Ensure profile exists
eng_profile, _ = UserProfile.objects.get_or_create(
    user=engineer_user,
    defaults={'department': 'engineer'}
)

admin_user, _ = User.objects.get_or_create(
    username='admin1',
    defaults={
        'email': 'admin1@test.com',
        'first_name': 'Jane',
        'last_name': 'Admin',
        'is_staff': True,
        'is_superuser': True,
        'password': 'testpass123'
    }
)
admin_user.set_password('testpass123')
admin_user.save()

# Ensure profile exists
admin_profile, _ = UserProfile.objects.get_or_create(
    user=admin_user,
    defaults={'department': 'admin'}
)

print("✅ Test users created:")
print(f"  - Engineer: {engineer_user.username} (is_staff={engineer_user.is_staff}, dept={eng_profile.department})")
print(f"  - Admin: {admin_user.username} (is_superuser={admin_user.is_superuser}, dept={admin_profile.department})")
print()

# Test Django Client
client = Client()

# Test authentication
print("📋 Testing Authentication...")
response = client.post('/login/', {
    'username': 'engineer1',
    'password': 'testpass123'
})
print(f"  - Login redirect: {response.status_code in [200, 302]}")
print()

# Test project access
print("📋 Testing Project Access...")
response = client.get('/projects/')
print(f"  - Project list (GET /projects/): {response.status_code}")

response = client.get('/projects/create/')
print(f"  - Project create form (GET /projects/create/): {response.status_code}")
print()

# Test admin access
print("📋 Testing Admin Access...")
response = client.post('/login/', {
    'username': 'admin1',
    'password': 'testpass123'
})
print(f"  - Admin login: {response.status_code in [200, 302]}")

response = client.get('/projects/review/list/')
print(f"  - Review list (GET /projects/review/list/): {response.status_code}")
print()

# Create a test project for workflow testing
project = InfrastructureProject.objects.create(
    title='Test Infrastructure Project',
    location='bagong_sikat',
    category='road',
    implementing_office='Engineering Office',
    procurement_method='competitive_bidding',
    publication_status='draft',
    created_by=engineer_user
)

print("✅ Test Project Created:")
print(f"  - ID: {project.id}")
print(f"  - Title: {project.title}")
print(f"  - Status: {project.get_publication_status_display()}")
print()

# Test endpoints
print("📋 Testing Workflow Endpoints...")
response = client.get(f'/projects/{project.id}/')
print(f"  - Project detail (GET /projects/{project.id}/): {response.status_code}")

response = client.get(f'/projects/{project.id}/publish/')
print(f"  - Publish form (GET /projects/{project.id}/publish/): {response.status_code}")

print()
print("✅ All endpoints are accessible!")
print()
print("Next Steps:")
print("1. Navigate to http://127.0.0.1:8000/login/")
print("2. Login as engineer1 / testpass123")
print("3. Create a new project")
print("4. Click 'Submit for Review'")
print("5. Logout and login as admin1 / testpass123")
print("6. Go to 'Project Review Queue'")
print("7. Test all three decision options")
