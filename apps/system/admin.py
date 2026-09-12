from django.contrib import admin
from django.core.exceptions import PermissionDenied
from .permissions import is_system_admin
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


class ProjectDataAdmin(admin.ModelAdmin):
    """Project data is managed by Staff through office-scoped application forms.

    Preserve the superuser maintenance exception, even when legacy Django
    permissions have been assigned to an office account.
    """
    def changelist_view(self, request, extra_context=None):
        if request.method == 'POST' and not is_system_admin(request.user):
            raise PermissionDenied('Project maintenance requires an administrator.')
        return super().changelist_view(request, extra_context)

    def has_add_permission(self, request):
        return is_system_admin(request.user) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return is_system_admin(request.user) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return is_system_admin(request.user) and super().has_delete_permission(request, obj)


@admin.register(Address)
class AddressAdmin(ProjectDataAdmin):
    list_display = ('address_id', 'barangay', 'municipality', 'province', 'country', 'is_active')
    list_filter = ('is_active', 'country', 'province')
    search_fields = ('barangay', 'municipality', 'province', 'street')


@admin.register(Project)
class ProjectAdmin(ProjectDataAdmin):
    list_display = ('project_id', 'project_type', 'is_visible_to_public', 'is_published', 'created_at')
    list_filter = ('project_type', 'is_visible_to_public', 'is_published')
    search_fields = ('project_type',)


@admin.register(InfrastructureCategory)
class InfrastructureCategoryAdmin(ProjectDataAdmin):
    list_display = ('infrastructure_category_id', 'category_code', 'category_name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('category_code', 'category_name')


@admin.register(NonInfrastructureCategory)
class NonInfrastructureCategoryAdmin(ProjectDataAdmin):
    list_display = ('non_infrastructure_category_id', 'type_code', 'type_name')
    search_fields = ('type_code', 'type_name')


@admin.register(Contractor)
class ContractorAdmin(ProjectDataAdmin):
    list_display = ('contractor_id', 'contractor_name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('contractor_name',)


@admin.register(ImplementingOffice)
class ImplementingOfficeAdmin(ProjectDataAdmin):
    list_display = ('office_id', 'office_name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('office_name',)


@admin.register(FundSource)
class FundSourceAdmin(ProjectDataAdmin):
    list_display = ('fund_source_id', 'fund_source_code', 'fund_source_name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('fund_source_code', 'fund_source_name')


@admin.register(Infrastructure_Project)
class InfrastructureProjectAdmin(ProjectDataAdmin):
    list_display = ('infrastructure_id', 'infrastructure_title', 'category', 'contractor', 'implementing_office', 'project')
    search_fields = ('infrastructure_title', 'infrastructure_code', 'category__category_name')


@admin.register(Non_Infrastructure_Project)
class NonInfrastructureProjectAdmin(ProjectDataAdmin):
    list_display = ('non_infra_id', 'non_infra_name', 'non_infra_category', 'address', 'project')
    search_fields = ('non_infra_name', 'venue_name', 'non_infra_category__type_name')


@admin.register(Infrastructure_Schedule)
class InfrastructureScheduleAdmin(ProjectDataAdmin):
    list_display = ('schedule_id', 'infrastructure', 'actual_start_date', 'actual_completion_date')
    search_fields = ('infrastructure__infrastructure_title',)


@admin.register(Financial)
class FinancialAdmin(ProjectDataAdmin):
    list_display = ('financial_id', 'infrastructure', 'approved_budget', 'bid_amount', 'actual_expenditure')
    search_fields = ('infrastructure__infrastructure_title', 'fund_source__fund_source_name')


@admin.register(Project_Inspection)
class ProjectInspectionAdmin(ProjectDataAdmin):
    list_display = ('inspection_id', 'project', 'inspection_date', 'completion_percentage', 'inspected_by_user')
    search_fields = ('project__project_id', 'remarks', 'findings')
