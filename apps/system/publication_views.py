from datetime import date
from pathlib import PurePosixPath

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView

from .models import NonInfrastructureProgressUpdate, NonInfrastructureProject, ProjectRevision
from .publication_forms import PublicationReviewForm
from .publication_diff import revision_comparison
from .publication_public import (
    infrastructure_public_data,
    non_infrastructure_public_data,
)
from .publication_service import (
    confirm_head_operational_information,
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

    def test_func(self):
        return self.request.user.is_superuser


class OfficeHeadRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = 'login'

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
        update_label = 'Confirm Operational Information'
    else:
        non_infrastructure = snapshot.get('non_infrastructure') or {}
        controlled.append({
            'label': (
                'Initial Official Status'
                if readiness.get('is_first_publication')
                else 'Official Status'
            ),
            'value': non_infrastructure.get('status_label'),
            'is_percentage': False,
        })
        can_update = can_update_non_infrastructure_operations(user)
        update_url_name = (
            'mayor_projects:non_infrastructure_project_operations'
        )
        set_label = 'Set Project Status'
        update_label = (
            'Confirm Initial Status'
            if readiness.get('is_first_publication')
            else 'Confirm Operational Information'
        )

    update_url = None
    if can_update and preview and preview.get('record_id'):
        if project_type == 'infrastructure':
            update_url = reverse(update_url_name, args=[preview['record_id']])
        elif readiness.get('is_first_publication'):
            update_url = reverse(update_url_name, args=[preview['record_id']])
    return {
        **readiness,
        'controlled_fields': controlled,
        'reference_fields': reference,
        'update_url': update_url,
        'update_label': update_label,
    }


def _revision_page_context(revision, user, review_form=None):
    project_type, preview = _revision_preview(revision)
    comparison = revision_comparison(revision)
    project_information = {
        'essential_fields': [],
        'populated_optional_fields': [],
        'empty_optional_fields': [],
    }
    project_section_labels = {'Project Information', 'Program Information'}
    publication_comparison_sections = []
    essential_roots = {
        'category', 'address', 'status', 'project_type',
    }
    for section in comparison['sections']:
        if section['label'] not in project_section_labels:
            publication_comparison_sections.append(section)
            continue
        for field in section['fields']:
            root = field['path'].split('.', 1)[0]
            if root in {'title', 'code', 'description'}:
                # These are already visible in the immutable snapshot hero.
                continue
            if root in essential_roots:
                project_information['essential_fields'].append(field)
            elif field['after'] == 'Not provided':
                project_information['empty_optional_fields'].append(field)
            else:
                project_information['populated_optional_fields'].append(field)

    operational = _operational_information(
        revision,
        project_type,
        preview,
        user,
    )
    mayor_progress_update = (revision.snapshot or {}).get(
        'non_infrastructure_progress_update',
    )
    mayor_evidence_items = []
    source = None
    if mayor_progress_update:
        source = NonInfrastructureProgressUpdate.objects.filter(
            pk=mayor_progress_update.get('id'),
            publication_revision=revision,
        ).first()
        current_evidence = {
            item.pk: item
            for item in source.evidence.all()
        } if source else {}
        for frozen in mayor_progress_update.get('evidence', []):
            item = current_evidence.get(frozen.get('id'))
            file_path = frozen.get('file_path') or ''
            mayor_evidence_items.append({
                **frozen,
                # A stored file path is durable; resolve a link only when
                # the same evidence record still has that exact path.
                'url': (
                    item.evidence_file.url
                    if item and item.evidence_file.name == file_path
                    else None
                ),
                'is_image': PurePosixPath(file_path).suffix.lower() in {
                    '.jpg', '.jpeg', '.png', '.gif', '.webp',
                },
            })
        labels = dict(NonInfrastructureProject.STATUS_CHOICES)
        mayor_progress_update = {
            **mayor_progress_update,
            'previous_status_label': labels.get(
                mayor_progress_update.get('previous_status'),
                mayor_progress_update.get('previous_status'),
            ),
            'proposed_status_label': labels.get(
                mayor_progress_update.get('proposed_status'),
                mayor_progress_update.get('proposed_status'),
            ),
        }
    return {
        'project_type': project_type,
        'preview': preview,
        'review_form': (
            review_form if review_form is not None else PublicationReviewForm(
                correction_only=revision.status == PublicationStatus.APPROVED,
            )
        ),
        'comparison': comparison,
        'publication_comparison_sections': publication_comparison_sections,
        'project_information': project_information,
        'operational': operational,
        'progress_update': (
            (revision.snapshot or {}).get('progress_update')
        ),
        'mayor_progress_update': mayor_progress_update,
        'mayor_evidence_items': mayor_evidence_items,
        'mayor_progress_detail_url': (
            reverse(
                'mayor_projects:non_infrastructure_progress_review_detail',
                args=[mayor_progress_update['id']],
            )
            if source
            and can_update_non_infrastructure_operations(user)
            else None
        ),
        'can_review': (
            revision.status == PublicationStatus.PENDING_REVIEW
            and can_review_revision(user, revision)
        ),
        'can_request_corrections': (
            revision.status == PublicationStatus.APPROVED
            and not revision.is_current_public
            and can_review_revision(user, revision)
        ),
        'can_publish': (
            operational['is_complete']
            and can_publish_revision(user, revision)
            and revision_targets_current_public(revision, comparison['baseline'])
        ),
        'can_publish_initial_non_infrastructure': (
            project_type == 'non_infrastructure'
            and revision.status == PublicationStatus.APPROVED
            and operational['is_first_publication']
            and not operational['is_complete']
            and can_update_non_infrastructure_operations(user)
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
    model = ProjectRevision
    pk_url_kwarg = 'revision_id'
    template_name = 'core/publication_revision_detail.html'
    context_object_name = 'revision'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if review_project_type(request.user) is None and not is_system_admin(request.user):
            raise PermissionDenied('You cannot view publication submissions.')
        return super().dispatch(request, *args, **kwargs)

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
        correction_only = revision.status == PublicationStatus.APPROVED
        form = PublicationReviewForm(
            request.POST,
            correction_only=correction_only,
        )
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
        readiness = publication_readiness(revision)
        initial_non_infrastructure = (
            revision.project.project_type == 'non_infrastructure'
            and revision.status == PublicationStatus.APPROVED
            and readiness['is_first_publication']
            and not readiness['is_complete']
            and can_update_non_infrastructure_operations(request.user)
            and revision_targets_current_public(revision, None)
        )
        if not can_publish_revision(request.user, revision) and not initial_non_infrastructure:
            raise PermissionDenied('You cannot publish this revision.')
        try:
            with transaction.atomic():
                if initial_non_infrastructure:
                    revision = confirm_head_operational_information(
                        revision,
                        request.user,
                    )
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


class PublicationRevisionArchiveView(LoginRequiredMixin, View):
    login_url = 'login'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        raise PermissionDenied('Manual publication archival is disabled.')
