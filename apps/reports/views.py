from django.shortcuts import redirect, resolve_url
from django.urls import reverse
from django.views.generic import FormView, RedirectView, TemplateView

from apps.system.permissions import review_project_type
from apps.system.publication_views import OfficeHeadRequiredMixin

from .forms import (
    IndividualProjectReportRequestForm,
    InfrastructureSummaryReportFilterForm,
    NonInfrastructureSummaryReportFilterForm,
)
from .services import (
    get_infrastructure_project_report_data,
    get_infrastructure_summary_report_data,
    get_non_infrastructure_project_report_data,
    get_non_infrastructure_summary_report_data,
)


REPORT_DESTINATIONS = {
    'infrastructure': 'reports:infrastructure',
    'non_infrastructure': 'reports:non_infrastructure',
}

REPORT_LABELS = {
    'infrastructure': 'Infrastructure',
    'non_infrastructure': 'Non-Infrastructure',
}

REPORT_PREVIEW_DESTINATIONS = {
    'infrastructure': 'reports:infrastructure_project',
    'non_infrastructure': 'reports:non_infrastructure_project',
}

REPORT_DATA_GETTERS = {
    'infrastructure': get_infrastructure_project_report_data,
    'non_infrastructure': get_non_infrastructure_project_report_data,
}

REPORT_PREVIEW_TEMPLATES = {
    'infrastructure': 'reports/infrastructure_project_report.html',
    'non_infrastructure': 'reports/non_infrastructure_project_report.html',
}

SUMMARY_FORMS = {
    'infrastructure': InfrastructureSummaryReportFilterForm,
    'non_infrastructure': NonInfrastructureSummaryReportFilterForm,
}

SUMMARY_DATA_GETTERS = {
    'infrastructure': get_infrastructure_summary_report_data,
    'non_infrastructure': get_non_infrastructure_summary_report_data,
}

SUMMARY_TEMPLATES = {
    'infrastructure': 'reports/infrastructure_summary_report.html',
    'non_infrastructure': 'reports/non_infrastructure_summary_report.html',
}


class ReportDashboardRedirectView(OfficeHeadRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        report_type = review_project_type(self.request.user)
        return resolve_url(REPORT_DESTINATIONS[report_type])


class ScopedReportDashboardView(OfficeHeadRequiredMixin, FormView):
    template_name = 'reports/report_dashboard.html'
    form_class = IndividualProjectReportRequestForm
    report_type = None

    def test_func(self):
        return review_project_type(self.request.user) == self.report_type

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report_type'] = self.report_type
        context['report_type_label'] = REPORT_LABELS[self.report_type]
        context['summary_url'] = reverse(
            f'reports:{self.report_type}_summary',
        )
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['report_type'] = self.report_type
        return kwargs

    def form_valid(self, form):
        return redirect(
            REPORT_PREVIEW_DESTINATIONS[self.report_type],
            project_id=form.cleaned_data['project_id'],
        )


class ScopedIndividualProjectReportView(
    OfficeHeadRequiredMixin,
    TemplateView,
):
    report_type = None

    def test_func(self):
        return review_project_type(self.request.user) == self.report_type

    def get_template_names(self):
        return [REPORT_PREVIEW_TEMPLATES[self.report_type]]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report_type'] = self.report_type
        context['report_type_label'] = REPORT_LABELS[self.report_type]
        context['report'] = REPORT_DATA_GETTERS[self.report_type](
            self.kwargs['project_id'],
        )
        return context


class ScopedSummaryReportView(OfficeHeadRequiredMixin, TemplateView):
    report_type = None

    def test_func(self):
        return review_project_type(self.request.user) == self.report_type

    def get_template_names(self):
        return [SUMMARY_TEMPLATES[self.report_type]]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = SUMMARY_FORMS[self.report_type](self.request.GET)
        context['report_type'] = self.report_type
        context['report_type_label'] = REPORT_LABELS[self.report_type]
        context['form'] = form
        context['active_filters'] = [
            (field.label, field.value())
            for field in form
            if field.value()
        ]
        context['summary'] = (
            SUMMARY_DATA_GETTERS[self.report_type](form.cleaned_data)
            if form.is_valid() else None
        )
        return context

