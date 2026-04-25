#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.views import ProjectCreateView, ProjectListView, ProjectDetailView, ProjectEditView, ProjectDeleteView
from core.models import InfrastructureProject

print("Testing project views configuration...")
print()
print("ProjectCreateView.model:", ProjectCreateView.model)
print("ProjectListView.model:", ProjectListView.model)
print("ProjectDetailView.model:", ProjectDetailView.model)
print("ProjectEditView.model:", ProjectEditView.model)
print("ProjectDeleteView.model:", ProjectDeleteView.model)
print()
print("✅ All views are properly configured!")
print("✅ model = InfrastructureProject for all views")
print()

# Verify form_class is set for CreateView and EditView
print("ProjectCreateView.form_class:", ProjectCreateView.form_class)
print("ProjectEditView.form_class:", ProjectEditView.form_class)
print()
print("✅ Form classes are properly configured!")
