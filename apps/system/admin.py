from django.contrib import admin
from .models import UserProfile, PasswordChangeHistory


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'department', 'updated_at')
    list_filter = ('department', 'created_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(PasswordChangeHistory)
class PasswordChangeHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'method', 'changed_at', 'changed_by')
    list_filter = ('method', 'changed_at')
    search_fields = ('user__username', 'changed_by__username')
    readonly_fields = ('changed_at',)
