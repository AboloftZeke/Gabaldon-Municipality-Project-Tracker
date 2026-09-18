from django.urls import path

from .views import ReportDashboardRedirectView, ScopedReportDashboardView


app_name = 'reports'

urlpatterns = [
    path('', ReportDashboardRedirectView.as_view(), name='dashboard'),
    path(
        'infrastructure/',
        ScopedReportDashboardView.as_view(report_type='infrastructure'),
        name='infrastructure',
    ),
    path(
        'non-infrastructure/',
        ScopedReportDashboardView.as_view(report_type='non_infrastructure'),
        name='non_infrastructure',
    ),
]

