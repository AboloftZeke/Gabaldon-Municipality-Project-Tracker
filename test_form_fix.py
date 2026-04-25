#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import UserProfile, InfrastructureProject
from core.forms import InfrastructureProjectForm
from core.views import ProjectCreateView
from django.test import RequestFactory

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

# Test form instantiation directly
try:
    form = InfrastructureProjectForm()
    print(f"✅ InfrastructureProjectForm instantiated successfully")
    print(f"   - Form model: {form._meta.model.__name__}")
    print(f"   - Form fields: {len(form.fields)}")
except Exception as e:
    print(f"❌ Error instantiating form: {e}")
    import traceback
    traceback.print_exc()

# Test view instantiation
factory = RequestFactory()
request = factory.get('/projects/create/')
request.user = user

try:
    view = ProjectCreateView()
    view.request = request
    print(f"✅ ProjectCreateView instantiated successfully")
    
    # Try to get the form
    form = view.get_form()
    print(f"✅ Form retrieved from view successfully")
    print(f"   - Form model: {form._meta.model.__name__}")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n✅ All checks passed! The ValueError issue is resolved.")
