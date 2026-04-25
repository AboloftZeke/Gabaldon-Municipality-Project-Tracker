from django.contrib import admin
from .models import UserProfile, PasswordChangeHistory, InfrastructureProject


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


@admin.register(InfrastructureProject)
class InfrastructureProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'location', 'category', 'award_status', 'created_by', 'created_at')
    list_filter = ('category', 'award_status', 'created_at', 'created_by')
    search_fields = ('title', 'location', 'implementing_office', 'contractor')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'location', 'implementing_office', 'category')
        }),
        ('Contractor & Procurement', {
            'fields': ('contractor', 'procurement_method')
        }),
        ('Procurement Dates', {
            'fields': ('posting_date', 'prebid_date', 'bidding_date', 'noa_date', 'ntp_date'),
            'classes': ('collapse',)
        }),
        ('Financial Information', {
            'fields': ('award_status', 'source_of_fund', 'abc_amount', 'contract_price')
        }),
        ('Contract Adjustments', {
            'fields': ('variation_orders',),
            'classes': ('collapse',)
        }),
        ('Disbursements', {
            'fields': ('disbursements_to_date', 'disbursement_details'),
            'classes': ('collapse',)
        }),
        ('Project Schedule', {
            'fields': ('planned_start_date', 'planned_end_date', 'actual_start_date', 'revised_completion_date')
        }),
        ('Progress Tracking', {
            'fields': ('cost_progress_percentage', 'physical_progress_percentage')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_by', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
