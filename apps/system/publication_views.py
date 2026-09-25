from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView

from .models import NonInfrastructureProject, ProjectRevision
from .publication_forms import PublicationReviewForm
from .publication_diff import revision_comparison
from .publication_public import (
    infrastructure_public_data,
    non_infrastructure_public_data,
)
from .publication_service import (
    publication_readiness,
    publish_publication_revision,
    revision_targets_current_public,
    review_publication_revision,
)
from .progress import (
    derived_cost_progress,
    expected_progress,
    progress_variance,
)
from .publication_workflow import PublicationStatus
from .permissions import (
    can_access_publication_review, can_review_revision, can_publish_revision,
    can_update_infrastructure_operations,
    can_update_non_infrastructure_operations,
    is_system_admin, review_project_type,
)


class SuperuserRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        return self.request.user.is_superuser


class OfficeHeadRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        return review_project_type(self.request.user) is not None


def _revision_preview(revision):
    project_type = (revision.snapshot or {}).get('project', {}).get('type')
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


def _snapshot_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _operational_information(revision, project_type, preview, user):
    """Build display data from the retained snapshot and shared readiness."""
    snapshot = revision.snapshot or {}
    readiness = publication_readiness(revision)
    controlled = []
    reference = []

    if project_type == 'infrastructure':
        infrastructure = snapshot.get('infrastructure') or {}
        inspection = snapshot.get('inspection')
        financial = snapshot.get('financial') or {}
        schedule = snapshot.get('schedule') or {}
        actual = infrastructure.get('physical_progress_percentage')
        scheduled = expected_progress(
            _snapshot_date(infrastructure.get('planned_start_date')),
            _snapshot_date(infrastructure.get('planned_end_date')),
            revised_end_date=_snapshot_date(
                schedule.get('contract_expiry_date'),
            ),
        )
        controlled.extend([
            {
                'label': 'Official Status',
                'value': infrastructure.get('status_label'),
                'is_percentage': False,
            },
            {
                'label': 'Actual Physical Progress',
                'value': actual,
                'is_percentage': True,
            },
        ])
        if inspection is not None:
            controlled.append({
                'label': 'Inspection Completion',
                'value': inspection.get('completion_percentage'),
                'is_percentage': True,
            })
        if infrastructure.get('cost_progress_percentage') not in (None, ''):
            controlled.append({
                'label': 'Entered Cost Progress',
                'value': infrastructure.get('cost_progress_percentage'),
                'is_percentage': True,
            })
        reference.extend([
            {
                'label': 'Expected / Scheduled Progress',
                'value': scheduled,
                'is_percentage': True,
            },
            {
                'label': 'Variance',
                'value': progress_variance(actual, scheduled),
                'is_percentage': True,
            },
            {
                'label': 'Calculated Cost Progress',
                'value': derived_cost_progress(
                    financial.get('actual_expenditure'),
                    financial.get('contract_price'),
                ),
                'is_percentage': True,
            },
        ])
        can_update = can_update_infrastructure_operations(user)
        update_url_name = 'engineering_projects:project_operations'
        set_label = 'Set Status & Progress'
        update_label = 'Update Status & Progress'
    else:
        non_infrastructure = snapshot.get('non_infrastructure') or {}
        controlled.append({
            'label': 'Official Status',
            'value': non_infrastructure.get('status_label'),
            'is_percentage': False,
        })
        can_update = can_update_non_infrastructure_operations(user)
        update_url_name = (
            'mayor_projects:non_infrastructure_project_operations'
        )
        set_label = 'Set Project Status'
        update_label = 'Update Project Status'

    update_url = None
    if can_update and preview and preview.get('record_id'):
        update_url = reverse(update_url_name, args=[preview['record_id']])
    return {
        **readiness,
        'controlled_fields': controlled,
        'reference_fields': reference,
        'update_url': update_url,
        'update_label': (
            update_label
            if readiness['is_confirmed'] or not readiness['is_first_publication']
            else set_label
        ),
    }


def _revision_page_context(revision, user, review_form=None):
    project_type, preview = _revision_preview(revision)
    comparison = revision_comparison(revision)
    operational = _operational_information(
        revision,
        project_type,
        preview,
        user,
    )
    return {
        'project_type': project_type,
        'preview': preview,
        'review_form': (
            review_form if review_form is not None else PublicationReviewForm()
        ),
        'comparison': comparison,
        'operational': operational,
        'progress_update': (
            (revision.snapshot or {}).get('progress_update')
        ),
        'can_review': (
            revision.status == PublicationStatus.PENDING_REVIEW
            and can_review_revision(user, revision)
        ),
        'can_publish': (
            operational['is_complete']
            and can_publish_revision(user, revision)
            and revision_targets_current_public(revision, comparison['baseline'])
        ),
        'can_archive': False,
    }


class PublicationReviewQueueView(OfficeHeadRequiredMixin, ListView):
    model = ProjectRevision
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
            ProjectRevision.objects.filter(
                status=requested_status,
                project__project_type=review_project_type(self.request.user),
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
                'readiness': publication_readiness(revision),
            })
        counts = {
            item['status']: item['total']
            for item in ProjectRevision.objects.filter(
                project__project_type=review_project_type(self.request.user),
            ).values('status')
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
            'has_any_revisions': bool(counts),
            'pending_count': counts.get(PublicationStatus.PENDING_REVIEW, 0),
            'approved_count': counts.get(PublicationStatus.APPROVED, 0),
        })
        return context


class PublicationRevisionDetailView(LoginRequiredMixin, DetailView):
    login_url = 'login'
    raise_exception = True
    model = ProjectRevision
    pk_url_kwarg = 'revision_id'
    template_name = 'core/publication_revision_detail.html'
    context_object_name = 'revision'

    def get_object(self, queryset=None):
        revision = super().get_object(queryset)
        # Keep the existing publisher's lifecycle page without granting review.
        publisher_record = is_system_admin(self.request.user) and revision.status in {
            PublicationStatus.APPROVED, PublicationStatus.PUBLISHED, PublicationStatus.ARCHIVED,
        }
        if not publisher_record and not can_access_publication_review(self.request.user, revision):
            raise PermissionDenied('This submission belongs to another review office.')
        return revision

    def get_queryset(self):
        return ProjectRevision.objects.select_related(
            'project',
            'submitted_by',
            'reviewed_by',
            'published_by',
            'previous_revision',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_revision_page_context(self.object, self.request.user))
        return context


class PublicationRevisionReviewView(OfficeHeadRequiredMixin, View):
    def post(self, request, revision_id):
        revision = get_object_or_404(
            ProjectRevision,
            pk=revision_id,
        )
        if not can_review_revision(request.user, revision):
            raise PermissionDenied('You cannot review this publication submission.')
        form = PublicationReviewForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                'core/publication_revision_detail.html',
                {
                    'revision': revision,
                    **_revision_page_context(
                        revision,
                        request.user,
                        review_form=form,
                    ),
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


class PublicationRevisionPublishView(OfficeHeadRequiredMixin, View):
    raise_exception = False

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied('You cannot publish this revision.')
        return super().handle_no_permission()

    def post(self, request, revision_id):
        revision = get_object_or_404(
            ProjectRevision,
            pk=revision_id,
        )
        if not can_publish_revision(request.user, revision):
            raise PermissionDenied('You cannot publish this revision.')
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


class PublicationRevisionArchiveView(View):
    def dispatch(self, request, *args, **kwargs):
        raise PermissionDenied('Manual publication archival is disabled.')
