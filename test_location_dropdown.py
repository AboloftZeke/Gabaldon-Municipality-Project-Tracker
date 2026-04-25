#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.forms import InfrastructureProjectForm
from core.models import InfrastructureProject

# Create a test form
form = InfrastructureProjectForm()

print("✅ InfrastructureProjectForm instantiated successfully")
print()

# Check location field widget type
location_field = form.fields.get('location')
print(f"Location field widget type: {type(location_field.widget).__name__}")
print(f"Location field required: {location_field.required}")
print()

# Display available location choices
print("Location choices available:")
for value, label in InfrastructureProject.LOCATION_CHOICES:
    print(f"  • {label}")
print()

# Verify the widget is Select
from django.forms import Select
if isinstance(location_field.widget, Select):
    print("✅ Location field is correctly configured as a Select dropdown")
else:
    print(f"❌ Location field widget is {type(location_field.widget).__name__}, expected Select")
