"""Office review dashboards and the existing publisher's lifecycle index."""
from django.db.models import Count, F
from django.views.generic import TemplateView, ListView

from .models import ProjectPublicationRevision
from .permissions import review_project_type
from .publication_views import OfficeHeadRequiredMixin, SuperuserRequiredMixin


class HeadDashboardView(OfficeHeadRequiredMixin, TemplateView):
    template_name = 'core/head_dashboard.html'
    project_type = None

    def test_func(self):
        return review_project_type(self.request.user) == self.project_type

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        revisions = ProjectPublicationRevision.objects.filter(project__project_type=self.project_type)
        counts = dict(revisions.values('status').annotate(total=Count('pk')).values_list('status', 'total'))
        context['status_cards'] = [
            {'status': status, 'label': label, 'count': counts.get(status, 0)}
            for status, label in [('pending_review', 'Pending reviews'),
                                  ('needs_revision', 'Needs revision'),
                                  ('approved', 'Approved awaiting publication')]
        ]
        context['recent_revisions'] = revisions.filter(reviewed_at__isnull=False).order_by('-reviewed_at', '-pk')[:10]
        operational_revisions = (
            revisions.filter(
                status='approved',
                supersedes_revision__isnull=False,
                submitted_by=F('reviewed_by'),
            )
            .select_related('supersedes_revision')
            .order_by('-reviewed_at', '-pk')
        )
        context['operational_revisions'] = operational_revisions[:5]
        context['operational_revision_count'] = operational_revisions.count()
        return context


class PublicationLifecycleView(SuperuserRequiredMixin, ListView):
    template_name = 'core/publication_lifecycle.html'
    context_object_name = 'revisions'
    paginate_by = 20

    def get_queryset(self):
        return ProjectPublicationRevision.objects.filter(
            status__in=['approved', 'published', 'archived'],
        ).order_by('-created_at', '-pk')
