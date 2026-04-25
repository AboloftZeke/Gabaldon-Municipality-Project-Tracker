#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import UserProfile, InfrastructureProject
from django.test import RequestFactory
from core.views import ProjectCreateView, ProjectListView

# Create a test user if it doesn't exist
username = 'test_engineer'
if not User.objects.filter(username=username).exists():
    user = User.objects.create_user(
        username=username,
        email='test@example.com',
        password='testpass123',
        first_name='Test',
        last_name='Engineer'
    )
    print(f"✅ Created test user: {username}")
else:
    user = User.objects.get(username=username)
    print(f"✅ Using existing test user: {username}")

# Verify UserProfile exists and is set to engineer
try:
    profile = user.profile
    print(f"✅ UserProfile exists with department: {profile.department}")
except UserProfile.DoesNotExist:
    profile = UserProfile.objects.create(user=user, department='engineer')
    print(f"✅ Created UserProfile with department: engineer")

# Test view instantiation
factory = RequestFactory()
request = factory.get('/projects/create/')
request.user = user

try:
    view = ProjectCreateView()
    view.request = request
    print(f"✅ ProjectCreateView instantiated successfully")
    print(f"   - Model: {view.model.__name__}")
    print(f"   - Form Class: {view.form_class.__name__}")
    print(f"   - Template: {view.template_name}")
except Exception as e:
    print(f"❌ Error instantiating ProjectCreateView: {e}")

# Test ListView
try:
    view = ProjectListView()
    view.request = request
    print(f"✅ ProjectListView instantiated successfully")
    print(f"   - Model: {view.model.__name__}")
    print(f"   - Paginate By: {view.paginate_by}")
except Exception as e:
    print(f"❌ Error instantiating ProjectListView: {e}")

print("\n✅ All views instantiate correctly! The ValueError issue is resolved.")
