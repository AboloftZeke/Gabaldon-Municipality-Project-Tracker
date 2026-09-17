"""Isolated SQLite database for local schema verification and tests."""
import os
from .settings import *

DATABASES = {'default': {
    'ENGINE': 'django.db.backends.sqlite3',
    'NAME': os.environ.get('TEST_DATABASE_PATH', BASE_DIR / 'db.sqlite3'),
}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
LOGIN_OTP_ENABLED = True
