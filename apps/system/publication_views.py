from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import DetailView, ListView

from .checker_permissions import (
    can_review_project_type,
    revision_project_type,
)
from .models import ProjectPublicationRevision
from .publication_forms import PublicationReviewForm
from .publication_public import (
    infrastructure_public_data,
    non_infrastructure_public_data,
)
from .publication_service import review_publication_revision
from .publication_workflow import PublicationStatus


def _revision_preview(revision):
    """Return a display-only submitted snapshot for the authorized checker."""
    project_type = revision_project_type(revision)
    if project_type == 'infrastructure':
        data = infrastructure_public_data(revision)
    elif project_type == 'non_infrastructure':
        data = non_infrastructure_public_data(revision)
    else:
        data = None
    return project_type, data

class ScopedProjectCheckerMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Apply one project-type scope to every checker queue, page, and POST."""

    login_url = 'login'
    raise_exception = True
    review_project_type = None
    checker_label = ''
    queue_url_name = ''
    detail_url_name = ''
    review_url_name = ''

    def test_func(self):
        return can_review_project_type(
            self.request.user,
            self.review_project_type,
        )

    def _revision_or_denied(self, revision_id):
        revision = get_object_or_404(
            ProjectPublicationRevision.objects.select_related(
                'project',
                'submitted_by',
                'reviewed_by',
                'published_by',
                'supersedes_revision',
            ),
            pk=revision_id,
        )
        # This is deliberately checked against server-side revision data.
        # It prevents URL or form manipulation from crossing checker scopes.
        if revision_project_type(revision) != self.review_project_type:
            raise PermissionDenied(
                'You are not authorized to review this project type.',
            )
        return revision

    def _detail_context(self, revision, review_form=None):
        project_type, preview = _revision_preview(revision)
        return {
            'revision': revision,
            'project_type': project_type,
            'preview': preview,
            'review_form': review_form or PublicationReviewForm(),
            'can_review': revision.status == PublicationStatus.PENDING_REVIEW,
            'can_publish': False,
            'can_archive': False,
            'checker_label': self.checker_label,
            'review_queue_url': self.queue_url_name,
            'review_action_url': self.review_url_name,
        }


class ProjectCheckerReviewQueueView(ScopedProjectCheckerMixin, ListView):
    model = ProjectPublicationRevision
    template_name = 'core/publication_review_queue.html'
    context_object_name = 'revisions'
    paginate_by = 20

    def get_queryset(self):
        requested_status = self.request.GET.get('status', '').strip()
        valid_statuses = {value for value, _ in PublicationStatus.choices}
        if requested_status not in valid_statuses:
            requested_status = PublicationStatus.PENDING_REVIEW
        self.selected_status = requested_status
        return (
            ProjectPublicationRevision.objects.filter(
                status=requested_status,
                snapshot_data__project__type=self.review_project_type,
            )
            .select_related('project', 'submitted_by', 'reviewed_by')
            .order_by('-submitted_at', '-created_at')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = []
        for revision in context['revisions']:
            project_type, preview = _revision_preview(revision)
            rows.append({
                'revision': revision,
                'project_type': project_type,
                'preview': preview,
            })

        scoped_revisions = ProjectPublicationRevision.objects.filter(
            snapshot_data__project__type=self.review_project_type,
        )
        counts = {
            item['status']: item['total']
            for item in scoped_revisions.values('status').annotate(
                total=Count('pk'),
            )
        }
        context.update({
            'revision_rows': rows,
            'selected_status': self.selected_status,
            'status_filters': [
                {
                    'value': value,
                    'label': label,
                    'count': counts.get(value, 0),
                }
                for value, label in PublicationStatus.choices
            ],
            'status_counts': counts,
            'pending_count': counts.get(PublicationStatus.PENDING_REVIEW, 0),
            'approved_count': counts.get(PublicationStatus.APPROVED, 0),
            'checker_label': self.checker_label,
            'review_detail_url': self.detail_url_name,
            'review_queue_url': self.queue_url_name,
        })
        return context


class ProjectCheckerRevisionDetailView(
    ScopedProjectCheckerMixin,
    DetailView,
):
    model = ProjectPublicationRevision
    pk_url_kwarg = 'revision_id'
    template_name = 'core/publication_revision_detail.html'
    context_object_name = 'revision'

    def get_object(self, queryset=None):
        return self._revision_or_denied(self.kwargs['revision_id'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self._detail_context(self.object))
        return context


class ProjectCheckerRevisionReviewView(ScopedProjectCheckerMixin, View):
    def post(self, request, revision_id):
        revision = self._revision_or_denied(revision_id)
        form = PublicationReviewForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                'core/publication_revision_detail.html',
                self._detail_context(revision, form),
                status=400,
            )
        try:
            reviewed = review_publication_revision(
                revision,
                request.user,
                form.cleaned_data['decision'],
                form.cleaned_data['notes'],
            )
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            messages.success(
                request,
                f'Revision {reviewed.revision_number} is now '
                f'{reviewed.get_status_display().lower()}.',
            )
        return redirect(self.detail_url_name, revision_id=revision_id)


class InfrastructureCheckerReviewQueueView(ProjectCheckerReviewQueueView):
    review_project_type = 'infrastructure'
    checker_label = 'Infrastructure Project Approvals'
    queue_url_name = 'infrastructure_checker_review_queue'
    detail_url_name = 'infrastructure_checker_revision_detail'
    review_url_name = 'infrastructure_checker_revision_review'


class InfrastructureCheckerRevisionDetailView(ProjectCheckerRevisionDetailView):
    review_project_type = 'infrastructure'
    checker_label = 'Infrastructure Project Approvals'
    queue_url_name = 'infrastructure_checker_review_queue'
    detail_url_name = 'infrastructure_checker_revision_detail'
    review_url_name = 'infrastructure_checker_revision_review'


class InfrastructureCheckerRevisionReviewView(ProjectCheckerRevisionReviewView):
    review_project_type = 'infrastructure'
    checker_label = 'Infrastructure Project Approvals'
    queue_url_name = 'infrastructure_checker_review_queue'
    detail_url_name = 'infrastructure_checker_revision_detail'
    review_url_name = 'infrastructure_checker_revision_review'


class NonInfrastructureCheckerReviewQueueView(ProjectCheckerReviewQueueView):
    review_project_type = 'non_infrastructure'
    checker_label = 'Non-Infrastructure Project Approvals'
    queue_url_name = 'noninfrastructure_checker_review_queue'
    detail_url_name = 'noninfrastructure_checker_revision_detail'
    review_url_name = 'noninfrastructure_checker_revision_review'


class NonInfrastructureCheckerRevisionDetailView(
    ProjectCheckerRevisionDetailView,
):
    review_project_type = 'non_infrastructure'
    checker_label = 'Non-Infrastructure Project Approvals'
    queue_url_name = 'noninfrastructure_checker_review_queue'
    detail_url_name = 'noninfrastructure_checker_revision_detail'
    review_url_name = 'noninfrastructure_checker_revision_review'


class NonInfrastructureCheckerRevisionReviewView(
    ProjectCheckerRevisionReviewView,
):
    review_project_type = 'non_infrastructure'
    checker_label = 'Non-Infrastructure Project Approvals'
    queue_url_name = 'noninfrastructure_checker_review_queue'
    detail_url_name = 'noninfrastructure_checker_revision_detail'
    review_url_name = 'noninfrastructure_checker_revision_review'
