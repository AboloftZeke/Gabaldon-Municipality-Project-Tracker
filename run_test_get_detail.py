import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.test import Client
from django.conf import settings
from types import SimpleNamespace

# allow testserver
hosts = list(settings.ALLOWED_HOSTS or [])
if 'testserver' not in hosts:
    hosts.append('testserver')
    settings.ALLOWED_HOSTS = hosts

User = get_user_model()
user, created = User.objects.get_or_create(username='copilot_test_user')
if created:
    user.set_password('testpass')
    user.is_staff = True
    user.is_superuser = False
    user.save()
else:
    if user.is_superuser:
        user.is_superuser = False
        user.save()

# attach profile in-memory
user.__dict__['_profile'] = SimpleNamespace(department='engineer')

client = Client()
client.force_login(user)

resp = client.get('/engineering/dashboard/infrastructure/4/')
print('STATUS', resp.status_code)
try:
    print(resp.content.decode('utf-8')[:4000])
except Exception as e:
    print('could not decode response', e)
