from django.contrib import admin
from .models import InfrastructureProject


# InfrastructureProject is not registered in admin
# Admins cannot manage projects through Django admin
# Only engineering office users can create/edit/delete projects through the web interface
