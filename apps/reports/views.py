from django.shortcuts import resolve_url
from django.views.generic import RedirectView, TemplateView

from apps.system.permissions import review_project_type
from apps.system.publication_views import OfficeHeadRequiredMixin


REPORT_DESTINATIONS = {
    'infrastructure': 'reports:infrastructure',
    'non_infrastructure': 'reports:non_infrastructure',
}

REPORT_LABELS = {
    'infrastructure': 'Infrastructure',
    'non_infrastructure': 'Non-Infrastructure',
}


class ReportDashboardRedirectView(OfficeHeadRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        report_type = review_project_type(self.request.user)
        return resolve_url(REPORT_DESTINATIONS[report_type])


class ScopedReportDashboardView(OfficeHeadRequiredMixin, TemplateView):
    template_name = 'reports/report_dashboard.html'
    report_type = None

    def test_func(self):
        return review_project_type(self.request.user) == self.report_type

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report_type'] = self.report_type
        context['report_type_label'] = REPORT_LABELS[self.report_type]
        return context
