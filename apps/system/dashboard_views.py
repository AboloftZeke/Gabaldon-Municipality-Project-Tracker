"""Office review dashboards and the existing publisher's lifecycle index."""
from django.db.models import F
from django.urls import reverse
from django.views.generic import TemplateView, ListView

from .models import ProjectPublicationRevision
from .permissions import review_project_type
from .publication_service import publication_readiness
from .publication_views import OfficeHeadRequiredMixin, SuperuserRequiredMixin


def _revision_dashboard_item(revision, project_type, **extra):
    snapshot = (revision.snapshot_data or {}).get(project_type) or {}
    return {
        'revision': revision,
        'title': snapshot.get('title') or 'Untitled project',
        'status': revision.get_status_display(),
        'activity_at': (
            revision.published_at
            or revision.reviewed_at
            or revision.submitted_at
            or revision.created_at
        ),
        'detail_url': reverse(
            'publication_revision_detail',
            args=[revision.pk],
        ),
        **extra,
    }


class HeadDashboardView(OfficeHeadRequiredMixin, TemplateView):
    template_name = 'core/head_dashboard.html'
    project_type = None

    def test_func(self):
        return review_project_type(self.request.user) == self.project_type

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        revisions = ProjectPublicationRevision.objects.filter(
            project__project_type=self.project_type,
        ).select_related(
            'project',
            'submitted_by',
            'reviewed_by',
            'supersedes_revision',
        )

        pending_revisions = revisions.filter(
            status='pending_review',
        ).order_by('-submitted_at', '-created_at')
        operational_revisions = (
            revisions.filter(
                status='approved',
                supersedes_revision__isnull=False,
                submitted_by=F('reviewed_by'),
            )
            .select_related('supersedes_revision')
            .order_by('-reviewed_at', '-pk')
        )
        operational_ids = operational_revisions.values_list('pk', flat=True)
        approved_revisions = list(
            revisions.filter(status='approved')
            .exclude(pk__in=operational_ids)
            .order_by('-reviewed_at', '-pk')
        )
        needs_operational = []
        ready_to_publish = []
        for revision in approved_revisions:
            readiness = publication_readiness(revision)
            item = _revision_dashboard_item(
                revision,
                self.project_type,
                readiness=readiness,
            )
            if readiness['is_complete']:
                ready_to_publish.append(item)
            else:
                needs_operational.append(item)

        context['pending_review_items'] = [
            _revision_dashboard_item(revision, self.project_type)
            for revision in pending_revisions[:6]
        ]
        context['needs_operational_items'] = needs_operational[:6]
        context['ready_to_publish_items'] = ready_to_publish[:6]
        context['operational_update_items'] = [
            _revision_dashboard_item(revision, self.project_type)
            for revision in operational_revisions[:6]
        ]
        context['operational_revisions'] = operational_revisions[:5]
        context['operational_revision_count'] = operational_revisions.count()
        context['status_cards'] = [
            {
                'label': 'Pending Reviews',
                'count': pending_revisions.count(),
                'href': reverse('publication_review_queue')
                + '?status=pending_review',
            },
            {
                'label': 'Needs Operational Information',
                'count': len(needs_operational),
                'href': '#needs-operational-information',
            },
            {
                'label': 'Ready to Publish',
                'count': len(ready_to_publish),
                'href': '#ready-to-publish',
            },
            {
                'label': 'Updates Waiting to Publish',
                'count': context['operational_revision_count'],
                'href': '#updates-waiting-to-publish',
            },
        ]

        recent_revisions = revisions.filter(
            reviewed_at__isnull=False,
        ).exclude(status='approved').order_by('-reviewed_at', '-pk')[:8]
        context['recent_revisions'] = recent_revisions
        context['recent_activity_items'] = [
            _revision_dashboard_item(revision, self.project_type)
            for revision in recent_revisions
        ]
        current_public = revisions.filter(
            status='published',
            is_current_public_revision=True,
        ).order_by('-published_at', '-pk')[:5]
        if self.project_type == 'infrastructure':
            context['published_operational_projects'] = [
                {
                    'title': snapshot.get('title') or 'Untitled project',
                    'status': (
                        snapshot.get('award_status_label')
                        or 'Status not set'
                    ),
                    'update_url': reverse(
                        'engineering_projects:project_operations',
                        args=[snapshot['id']],
                    ),
                }
                for revision in current_public
                if (snapshot := (
                    revision.snapshot_data or {}
                ).get('infrastructure') or {}).get('id')
            ]
            context['operational_action_label'] = 'Update Status & Progress'
            context['project_list_url'] = reverse(
                'engineering_projects:project_list',
            )
        else:
            context['published_operational_projects'] = [
                {
                    'title': snapshot.get('title') or 'Untitled program',
                    'status': snapshot.get('status_label') or 'Status not set',
                    'update_url': reverse(
                        'mayor_projects:non_infrastructure_project_operations',
                        args=[snapshot['id']],
                    ),
                }
                for revision in current_public
                if (snapshot := (
                    revision.snapshot_data or {}
                ).get('non_infrastructure') or {}).get('id')
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
