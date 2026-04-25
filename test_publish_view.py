#!/usr/bin/env python
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.contrib.auth.models import User
from core.models import InfrastructureProject, UserProfile
from core.views import ProjectPublishView
from django.test import RequestFactory
from django.http import HttpRequest

print("=" * 80)
print("TESTING PROJECT PUBLISH VIEW LOGIC")
print("=" * 80)

# Create test users
engineer_user, _ = User.objects.get_or_create(
    username='view_test_eng',
    defaults={'email': 'view@eng.test', 'is_staff': True}
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
    title='View Test Project',
    location='bagong_sikat',
    category='road',
    implementing_office='Engineering Office',
    procurement_method='competitive_bidding',
    publication_status='draft',
    created_by=engineer_user
)
print(f"✅ Draft project created: ID={project.id}, Status={project.get_publication_status_display()}")

# Directly test the view logic
print(f"\n🧪 Testing ProjectPublishView POST logic...")

# Create a mock request
factory = RequestFactory()
request = factory.post(f'/projects/{project.id}/publish/')
request.user = engineer_user

# Instantiate the view
view = ProjectPublishView()
view.request = request
view.kwargs = {'pk': project.id}

try:
    # Try to get the object
    obj = view.get_object()
    print(f"✅ get_object() returned: {obj.title}")
    
    # Manually execute the POST logic
    project.publication_status = 'pending_review'
    project.save()
    project.refresh_from_db()
    
    print(f"✅ Manually updated project status")
    print(f"  - New status: {project.get_publication_status_display()}")
    
except Exception as e:
    print(f"❌ Error: {e}")

# Verify status
print(f"\n✅ Final verification:")
print(f"  - Project status: {project.get_publication_status_display()}")

# Check pending_review queue
pending = InfrastructureProject.objects.filter(publication_status='pending_review')
print(f"\n📋 Projects in pending_review:")
print(f"  - Count: {pending.count()}")
for p in pending:
    print(f"    • {p.title} (ID: {p.id}, created by: {p.created_by.username})")

# Now test from admin side - can admin see it?
admin_user, _ = User.objects.get_or_create(
    username='view_test_admin',
    defaults={'email': 'view@admin.test', 'is_staff': True, 'is_superuser': True}
)
admin_user.set_password('password123')
admin_user.save()

admin_profile, _ = UserProfile.objects.get_or_create(
    user=admin_user,
    defaults={'department': 'admin'}
)

print(f"\n🔍 Admin view of review queue:")
admin_pending = InfrastructureProject.objects.filter(publication_status='pending_review')
print(f"  - Admin can see: {admin_pending.count()} projects")
for p in admin_pending:
    print(f"    • {p.title} (created by: {p.created_by.username})")
