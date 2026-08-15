import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.test import Client
from django.conf import settings
from types import SimpleNamespace

# Ensure the test client's default host is allowed in ALLOWED_HOSTS
try:
    hosts = list(settings.ALLOWED_HOSTS or [])
except Exception:
    hosts = []
if 'testserver' not in hosts:
    hosts.append('testserver')
    settings.ALLOWED_HOSTS = hosts

User = get_user_model()
user, created = User.objects.get_or_create(username='copilot_test_user', defaults={'email':'test@example.com'})
if created:
    user.set_password('testpass')
    user.is_staff = True
    user.is_superuser = False
    user.save()
# Ensure existing test user is not a superuser (EngineerOnlyMixin excludes superusers)
if user.is_superuser:
    user.is_superuser = False
    user.save()

client = Client()
# Attach a lightweight `profile` object with department 'engineer' so
# the `EngineerOnlyMixin` test_func will allow this simulated user.
# The User model may have a OneToOneDescriptor for `profile` so set the
# cached value directly in `__dict__` to avoid descriptor setter issues.
user.__dict__['_profile'] = SimpleNamespace(department='engineer')
client.force_login(user)

post_url = '/engineering/dashboard/infrastructure/create/'
post_data = {
    'title': 'COPILOT TEST CREATE',
    'description': 'Test create via automated client',
    'street': '123 Test St',
    'barangay': '',
    'municipality': 'Gabaldon',
    'province': 'Nueva Ecija',
}

resp = client.post(post_url, post_data)
print('STATUS:', resp.status_code)
print('\nRESPONSE START')
try:
    print(resp.content.decode('utf-8')[:5000])
except Exception as e:
    print('Cannot decode response content:', e)
print('\nRESPONSE END')
