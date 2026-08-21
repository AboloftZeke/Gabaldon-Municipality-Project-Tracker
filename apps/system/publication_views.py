from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView

from .models import ProjectPublicationRevision
from .publication_forms import PublicationReviewForm
from .publication_public import (
    infrastructure_public_data,
    non_infrastructure_public_data,
)
from .publication_service import (
    archive_publication_revision,
    publish_publication_revision,
    review_publication_revision,
)
from .publication_workflow import PublicationStatus


class SuperuserRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        return self.request.user.is_superuser


def _revision_preview(revision):
    project_type = (revision.snapshot_data or {}).get('project', {}).get('type')
    if project_type == 'infrastructure':
        data = infrastructure_public_data(revision)
        detail_url_name = 'engineering_projects:project_detail'
    elif project_type == 'non_infrastructure':
        data = non_infrastructure_public_data(revision)
        detail_url_name = (
            'mayor_projects:non_infrastructure_project_detail'
        )
    else:
        data = None
        detail_url_name = None
    if data and detail_url_name:
        data['working_detail_url'] = reverse(
            detail_url_name,
            args=[data['record_id']],
        )
    return project_type, data


class PublicationReviewQueueView(SuperuserRequiredMixin, ListView):
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
            ProjectPublicationRevision.objects.filter(status=requested_status)
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
        counts = {
            item['status']: item['total']
            for item in ProjectPublicationRevision.objects.values('status')
            .annotate(total=Count('pk'))
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
        })
        return context


class PublicationRevisionDetailView(SuperuserRequiredMixin, DetailView):
    model = ProjectPublicationRevision
    pk_url_kwarg = 'revision_id'
    template_name = 'core/publication_revision_detail.html'
    context_object_name = 'revision'

    def get_queryset(self):
        return ProjectPublicationRevision.objects.select_related(
            'project',
            'submitted_by',
            'reviewed_by',
            'published_by',
            'supersedes_revision',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project_type, preview = _revision_preview(self.object)
        context.update({
            'project_type': project_type,
            'preview': preview,
            'review_form': PublicationReviewForm(),
            'can_review': self.object.status == PublicationStatus.PENDING_REVIEW,
            'can_publish': self.object.status == PublicationStatus.APPROVED,
            'can_archive': (
                self.object.status == PublicationStatus.PUBLISHED
                and self.object.is_current_public_revision
            ),
        })
        return context


class PublicationRevisionReviewView(SuperuserRequiredMixin, View):
    def post(self, request, revision_id):
        revision = get_object_or_404(
            ProjectPublicationRevision,
            pk=revision_id,
        )
        form = PublicationReviewForm(request.POST)
        if not form.is_valid():
            project_type, preview = _revision_preview(revision)
            return render(
                request,
                'core/publication_revision_detail.html',
                {
                    'revision': revision,
                    'project_type': project_type,
                    'preview': preview,
                    'review_form': form,
                    'can_review': (
                        revision.status == PublicationStatus.PENDING_REVIEW
                    ),
                    'can_publish': False,
                    'can_archive': False,
                },
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
        return redirect(
            'publication_revision_detail',
            revision_id=revision_id,
        )


class PublicationRevisionPublishView(SuperuserRequiredMixin, View):
    def post(self, request, revision_id):
        revision = get_object_or_404(
            ProjectPublicationRevision,
            pk=revision_id,
        )
        try:
            published = publish_publication_revision(revision, request.user)
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            messages.success(
                request,
                f'Revision {published.revision_number} is now public.',
            )
        return redirect(
            'publication_revision_detail',
            revision_id=revision_id,
        )


class PublicationRevisionArchiveView(SuperuserRequiredMixin, View):
    def post(self, request, revision_id):
        revision = get_object_or_404(
            ProjectPublicationRevision,
            pk=revision_id,
        )
        try:
            archived = archive_publication_revision(revision, request.user)
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            messages.success(
                request,
                f'Revision {archived.revision_number} was removed from the '
                'public dashboard.',
            )
        return redirect(
            'publication_revision_detail',
            revision_id=revision_id,
        )
