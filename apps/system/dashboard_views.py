"""Office review dashboards and the existing publisher's lifecycle index."""
from django.db.models import Count, F
from django.urls import reverse
from django.views.generic import TemplateView, ListView

from .models import (
    Infrastructure_Project,
    Non_Infrastructure_Project,
    ProjectPublicationRevision,
)
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
        if self.project_type == 'infrastructure':
            projects = Infrastructure_Project.objects.filter(
                project__publication_revisions__status='published',
                project__publication_revisions__is_current_public_revision=True,
            ).distinct().order_by('-updated_at')[:5]
            context['published_operational_projects'] = [
                {
                    'title': project.infrastructure_title,
                    'status': project.get_award_status_display()
                    or 'Status not set',
                    'update_url': reverse(
                        'engineering_projects:project_operations',
                        args=[project.pk],
                    ),
                }
                for project in projects
            ]
            context['operational_action_label'] = 'Update Status & Progress'
            context['project_list_url'] = reverse(
                'engineering_projects:project_list',
            )
        else:
            projects = Non_Infrastructure_Project.objects.filter(
                project__publication_revisions__status='published',
                project__publication_revisions__is_current_public_revision=True,
            ).distinct().order_by('-updated_at')[:5]
            context['published_operational_projects'] = [
                {
                    'title': project.non_infra_name,
                    'status': project.get_status_display(),
                    'update_url': reverse(
                        'mayor_projects:non_infrastructure_project_operations',
                        args=[project.pk],
                    ),
                }
                for project in projects
            ]
            context['operational_action_label'] = 'Update Status'
            context['project_list_url'] = reverse(
                'mayor_projects:non_infrastructure_project_list',
            )
        return context


class PublicationLifecycleView(SuperuserRequiredMixin, ListView):
    template_name = 'core/publication_lifecycle.html'
    context_object_name = 'revisions'
    paginate_by = 20

    def get_queryset(self):
        return ProjectPublicationRevision.objects.filter(
            status__in=['approved', 'published', 'archived'],
        ).order_by('-created_at', '-pk')
