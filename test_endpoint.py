#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import UserProfile, InfrastructureProject
from core.views import ProjectCreateView
from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.auth.middleware import AuthenticationMiddleware

# Create a test user
username = 'test_engineer'
user = User.objects.filter(username=username).first() or User.objects.create_user(
    username=username,
    email='test@example.com',
    password='testpass123'
)

# Set up user profile
profile, _ = UserProfile.objects.get_or_create(user=user, defaults={'department': 'engineer'})

# Create a request with sessions and authentication
factory = RequestFactory()
request = factory.get('/projects/create/')

# Add session middleware
middleware = SessionMiddleware(lambda r: None)
middleware.process_request(request)
request.session.save()

# Add auth middleware
AuthenticationMiddleware(lambda r: None).process_request(request)
request.user = user

# Try to render the view
view = ProjectCreateView.as_view()
try:
    response = view(request)
    print(f"✅ View returned successfully!")
    print(f"   - Status Code: {response.status_code}")
    if response.status_code == 200:
        print(f"   - View type: TemplateResponse (expected)")
        print(f"✅ /projects/create/ endpoint is working without ValueError!")
    elif response.status_code == 302:
        print(f"   - Redirect to: {response.get('Location', 'unknown')}")
    else:
        print(f"   - Unexpected status code: {response.status_code}")
except ValueError as e:
    if "ModelForm has no model class specified" in str(e):
        print(f"❌ ValueError still present: {e}")
    else:
        raise
except Exception as e:
    print(f"❌ Other error: {e}")
    import traceback
    traceback.print_exc()
