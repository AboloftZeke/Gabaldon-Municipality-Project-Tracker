from django.contrib import admin
from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'location', 'start_date', 'end_date', 'budget', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('title', 'description', 'location')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Project Information', {
            'fields': ('title', 'description', 'status', 'location')
        }),
        ('Financial', {
            'fields': ('budget',)
        }),
        ('Timeline', {
            'fields': ('start_date', 'end_date')
        }),
        ('Assignment', {
            'fields': ('assigned_to', 'created_by')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
