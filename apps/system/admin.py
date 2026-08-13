from django.contrib import admin
from .models import (
    Address,
    Project,
    InfrastructureCategory,
    NonInfrastructureCategory,
    Contractor,
    ImplementingOffice,
    FundSource,
    Infrastructure_Project,
    Non_Infrastructure_Project,
    Infrastructure_Schedule,
    Financial,
    Project_Inspection,
)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('address_id', 'barangay', 'municipality', 'province', 'country', 'is_active')
    list_filter = ('is_active', 'country', 'province')
    search_fields = ('barangay', 'municipality', 'province', 'street')


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('project_id', 'project_type', 'is_visible_to_public', 'is_published', 'created_at')
    list_filter = ('project_type', 'is_visible_to_public', 'is_published')
    search_fields = ('project_type',)


@admin.register(InfrastructureCategory)
class InfrastructureCategoryAdmin(admin.ModelAdmin):
    list_display = ('infrastructure_category_id', 'category_code', 'category_name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('category_code', 'category_name')


@admin.register(NonInfrastructureCategory)
class NonInfrastructureCategoryAdmin(admin.ModelAdmin):
    list_display = ('non_infrastructure_category_id', 'type_code', 'type_name')
    search_fields = ('type_code', 'type_name')


@admin.register(Contractor)
class ContractorAdmin(admin.ModelAdmin):
    list_display = ('contractor_id', 'contractor_name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('contractor_name',)


@admin.register(ImplementingOffice)
class ImplementingOfficeAdmin(admin.ModelAdmin):
    list_display = ('office_id', 'office_name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('office_name',)


@admin.register(FundSource)
class FundSourceAdmin(admin.ModelAdmin):
    list_display = ('fund_source_id', 'fund_source_code', 'fund_source_name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('fund_source_code', 'fund_source_name')


@admin.register(Infrastructure_Project)
class InfrastructureProjectAdmin(admin.ModelAdmin):
    list_display = ('infrastructure_id', 'infrastructure_title', 'category', 'contractor', 'implementing_office', 'project')
    search_fields = ('infrastructure_title', 'infrastructure_code', 'category__category_name')


@admin.register(Non_Infrastructure_Project)
class NonInfrastructureProjectAdmin(admin.ModelAdmin):
    list_display = ('non_infra_id', 'non_infra_name', 'non_infra_category', 'address', 'project')
    search_fields = ('non_infra_name', 'venue_name', 'non_infra_category__type_name')


@admin.register(Infrastructure_Schedule)
class InfrastructureScheduleAdmin(admin.ModelAdmin):
    list_display = ('schedule_id', 'infrastructure', 'actual_start_date', 'actual_completion_date')
    search_fields = ('infrastructure__infrastructure_title',)


@admin.register(Financial)
class FinancialAdmin(admin.ModelAdmin):
    list_display = ('financial_id', 'infrastructure', 'approved_budget', 'bid_amount', 'actual_expenditure')
    search_fields = ('infrastructure__infrastructure_title', 'fund_source__fund_source_name')


@admin.register(Project_Inspection)
class ProjectInspectionAdmin(admin.ModelAdmin):
    list_display = ('inspection_id', 'project', 'inspection_date', 'completion_percentage', 'inspected_by_user')
    search_fields = ('project__project_id', 'remarks', 'findings')
