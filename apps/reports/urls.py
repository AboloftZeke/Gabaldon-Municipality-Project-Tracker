from django.urls import path

from .views import (
    ReportDashboardRedirectView,
    ScopedIndividualProjectReportView,
    ScopedReportDashboardView,
    ScopedSummaryReportView,
)


app_name = 'reports'

urlpatterns = [
    path('', ReportDashboardRedirectView.as_view(), name='dashboard'),
    path(
        'infrastructure/',
        ScopedReportDashboardView.as_view(report_type='infrastructure'),
        name='infrastructure',
    ),
    path(
        'infrastructure/individual/<int:project_id>/',
        ScopedIndividualProjectReportView.as_view(
            report_type='infrastructure',
        ),
        name='infrastructure_project',
    ),
    path(
        'infrastructure/summary/',
        ScopedSummaryReportView.as_view(report_type='infrastructure'),
        name='infrastructure_summary',
    ),
    path(
        'non-infrastructure/',
        ScopedReportDashboardView.as_view(report_type='non_infrastructure'),
        name='non_infrastructure',
    ),
    path(
        'non-infrastructure/individual/<int:project_id>/',
        ScopedIndividualProjectReportView.as_view(
            report_type='non_infrastructure',
        ),
        name='non_infrastructure_project',
    ),
    path(
        'non-infrastructure/summary/',
        ScopedSummaryReportView.as_view(report_type='non_infrastructure'),
        name='non_infrastructure_summary',
    ),
]

