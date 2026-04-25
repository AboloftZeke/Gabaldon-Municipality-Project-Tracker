from django.contrib import admin
from .models import InfrastructureProject


@admin.register(InfrastructureProject)
class InfrastructureProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'location', 'category', 'award_status', 'created_by', 'created_at')
    list_filter = ('award_status', 'category', 'location', 'created_at')
    search_fields = ('title', 'location', 'implementing_office')
    readonly_fields = ('created_at', 'updated_at')
