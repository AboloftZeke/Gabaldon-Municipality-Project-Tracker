"""Atomic application services for the project publication workflow."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import Project, ProjectPublicationRevision
from .publication_snapshots import build_project_publication_snapshot
from .permissions import (
    can_review_revision, can_publish_revision, can_manage_infrastructure,
    can_manage_non_infrastructure, can_update_infrastructure_operations,
    can_update_non_infrastructure_operations, is_system_admin,
)
from .publication_workflow import (
    PublicationStatus,
    validate_publication_transition,
)


OPEN_REVISION_STATUSES = (
    PublicationStatus.DRAFT,
    PublicationStatus.PENDING_REVIEW,
    PublicationStatus.NEEDS_REVISION,
    PublicationStatus.APPROVED,
)


def _require_authenticated(actor):
    if actor is None or not actor.is_authenticated:
        raise PermissionDenied('An authenticated user is required.')


def _require_project_manager(project, actor):
    # Keep the existing internal superuser maintenance exception.
    allowed = is_system_admin(actor) or {
        'infrastructure': can_manage_infrastructure,
        'non_infrastructure': can_manage_non_infrastructure,
    }.get(project.project_type, lambda user: False)(actor)
    if not allowed:
        raise PermissionDenied('Only the responsible office Staff can submit project content.')


def _require_head_operational_authority(project, actor):
    allowed = {
        'infrastructure': can_update_infrastructure_operations,
        'non_infrastructure': can_update_non_infrastructure_operations,
    }.get(project.project_type, lambda user: False)(actor)
    if not allowed:
        raise PermissionDenied(
            'Only the responsible office Head can authorize an operational update.',
        )


def _locked_revision(revision):
    revision_id = getattr(revision, 'pk', revision)
    return ProjectPublicationRevision.objects.select_for_update().select_related(
        'project',
    ).get(pk=revision_id)


def _locked_project_revision(revision):
    """Lock in project-then-revision order for project-wide mutations."""
    revision_id = getattr(revision, 'pk', revision)
    project_id = ProjectPublicationRevision.objects.only(
        'project_id',
    ).get(pk=revision_id).project_id
    Project.objects.select_for_update().get(pk=project_id)
    return _locked_revision(revision_id)


def revision_targets_current_public(revision, current_public):
    """Return whether a revision still replaces the public version it captured."""
    return revision.supersedes_revision_id == getattr(current_public, 'pk', None)


@transaction.atomic
def create_publication_draft(project, actor):
    """Capture a new draft without changing the current public revision."""
    _require_authenticated(actor)
    project_id = getattr(project, 'pk', project)
    locked_project = Project.objects.select_for_update().get(pk=project_id)
    _require_project_manager(locked_project, actor)

    if locked_project.publication_revisions.filter(
        status__in=OPEN_REVISION_STATUSES,
    ).exists():
        raise ValidationError(
            'This project already has an active publication revision.',
        )

    latest_number = (
        locked_project.publication_revisions.aggregate(
            highest=Max('revision_number'),
        )['highest']
        or 0
    )
    current_public = locked_project.publication_revisions.filter(
        status=PublicationStatus.PUBLISHED,
        is_current_public_revision=True,
    ).first()

    return ProjectPublicationRevision.objects.create(
        project=locked_project,
        revision_number=latest_number + 1,
        status=PublicationStatus.DRAFT,
        snapshot_data=build_project_publication_snapshot(locked_project),
        source_updated_at=locked_project.updated_at,
        supersedes_revision=current_public,
    )


@transaction.atomic
def submit_publication_revision(revision, actor):
    """Refresh a draft from working data and submit it for office Head review."""
    _require_authenticated(actor)
    locked_revision = _locked_revision(revision)
    _require_project_manager(locked_revision.project, actor)
    validate_publication_transition(
        locked_revision.status,
        PublicationStatus.PENDING_REVIEW,
    )

    locked_revision.snapshot_data = build_project_publication_snapshot(
        locked_revision.project,
    )
    locked_revision.source_updated_at = locked_revision.project.updated_at
    locked_revision.status = PublicationStatus.PENDING_REVIEW
    locked_revision.submitted_by = actor
    locked_revision.submitted_at = timezone.now()
    locked_revision.reviewed_by = None
    locked_revision.reviewed_at = None
    locked_revision.review_notes = ''
    locked_revision.save(update_fields=[
        'snapshot_data',
        'source_updated_at',
        'status',
        'submitted_by',
        'submitted_at',
        'reviewed_by',
        'reviewed_at',
        'review_notes',
        'updated_at',
    ])
    return locked_revision


@transaction.atomic
def review_publication_revision(revision, reviewer, decision, notes=''):
    """Record the responsible office Head's review, excluding self-review."""
    locked_revision = _locked_revision(revision)
    if not can_review_revision(reviewer, locked_revision):
        raise PermissionDenied('You cannot review this publication submission.')
    allowed_decisions = {
        PublicationStatus.APPROVED,
        PublicationStatus.NEEDS_REVISION,
        PublicationStatus.REJECTED,
    }
    try:
        normalized_decision = PublicationStatus(decision)
    except ValueError as exc:
        raise ValidationError('Unknown publication review decision.') from exc
    if normalized_decision not in allowed_decisions:
        raise ValidationError('That status is not a review decision.')

    normalized_notes = (notes or '').strip()
    if (
        normalized_decision in {
            PublicationStatus.NEEDS_REVISION,
            PublicationStatus.REJECTED,
        }
        and not normalized_notes
    ):
        raise ValidationError(
            'Review notes are required when returning or rejecting a revision.',
        )

    validate_publication_transition(
        locked_revision.status,
        normalized_decision,
    )
    locked_revision.status = normalized_decision
    locked_revision.reviewed_by = reviewer
    locked_revision.reviewed_at = timezone.now()
    locked_revision.review_notes = normalized_notes
    locked_revision.save(update_fields=[
        'status',
        'reviewed_by',
        'reviewed_at',
        'review_notes',
        'updated_at',
    ])
    return locked_revision


@transaction.atomic
def publish_publication_revision(revision, publisher):
    """Atomically replace the project's current public revision."""
    locked_revision = _locked_project_revision(revision)
    if not can_publish_revision(publisher, locked_revision):
        raise PermissionDenied("Only the responsible office Head can publish an approved revision.")
    validate_publication_transition(
        locked_revision.status,
        PublicationStatus.PUBLISHED,
    )

    current_public = (
        ProjectPublicationRevision.objects.select_for_update().filter(
            project_id=locked_revision.project_id,
            status=PublicationStatus.PUBLISHED,
            is_current_public_revision=True,
        )
        .exclude(pk=locked_revision.pk)
        .first()
    )
    if not revision_targets_current_public(locked_revision, current_public):
        raise ValidationError(
            'The current public revision changed after this update was created. '
            'This revision cannot replace it.',
        )

    now = timezone.now()
    if current_public is not None:
        current_public.status = PublicationStatus.ARCHIVED
        current_public.is_current_public_revision = False
        current_public.save(update_fields=[
            'status',
            'is_current_public_revision',
            'updated_at',
        ])

    locked_revision.status = PublicationStatus.PUBLISHED
    locked_revision.published_by = publisher
    locked_revision.published_at = now
    locked_revision.is_current_public_revision = True
    locked_revision.save(update_fields=[
        'status',
        'published_by',
        'published_at',
        'is_current_public_revision',
        'updated_at',
    ])
    Project.objects.filter(pk=locked_revision.project_id).update(
        is_published=True,
        is_visible_to_public=True,
    )
    return locked_revision


def archive_publication_revision(revision, actor):
    """Legacy entry point: manual archival is no longer available."""
    raise PermissionDenied('Manual publication archival is disabled.')


def publication_state(project):
    """Return presentation-ready workflow state for an employee project page."""
    project_id = getattr(project, 'pk', project)
    revisions = ProjectPublicationRevision.objects.filter(
        project_id=project_id,
    ).order_by('-revision_number')
    active = revisions.filter(status__in=OPEN_REVISION_STATUSES).first()
    current_public = revisions.filter(
        status=PublicationStatus.PUBLISHED,
        is_current_public_revision=True,
    ).first()
    latest = revisions.first()
    displayed = active or latest

    if displayed is None:
        status_key = 'not_submitted'
        status_label = 'Not Submitted'
        review_notes = ''
        revision_number = None
    else:
        status_key = displayed.status
        status_label = displayed.get_status_display()
        review_notes = displayed.review_notes
        revision_number = displayed.revision_number

    can_submit = active is None or active.status in {
        PublicationStatus.DRAFT,
        PublicationStatus.NEEDS_REVISION,
    }
    if active and active.status == PublicationStatus.NEEDS_REVISION:
        action_label = 'Resubmit for Review'
    elif current_public:
        action_label = 'Submit Updated Version'
    else:
        action_label = 'Submit for Public Review'

    return {
        'status_key': status_key,
        'status_label': status_label,
        'revision_number': revision_number,
        'review_notes': review_notes,
        'can_submit': can_submit,
        'action_label': action_label,
        'has_current_public_revision': current_public is not None,
        'current_public_revision_number': (
            current_public.revision_number if current_public else None
        ),
    }


@transaction.atomic
def submit_project_for_review(project, actor):
    """Create or reuse an editable revision and submit it in one employee action."""
    _require_authenticated(actor)
    project_id = getattr(project, 'pk', project)
    locked_project = Project.objects.select_for_update().get(pk=project_id)
    _require_project_manager(locked_project, actor)
    active = (
        locked_project.publication_revisions.select_for_update()
        .filter(status__in=OPEN_REVISION_STATUSES)
        .order_by('-revision_number')
        .first()
    )
    if active and active.status not in {
        PublicationStatus.DRAFT,
        PublicationStatus.NEEDS_REVISION,
    }:
        raise ValidationError(
            'This project already has a revision awaiting review or publication.',
        )
    revision = active or create_publication_draft(locked_project, actor)
    return submit_publication_revision(revision, actor)


@transaction.atomic
def create_head_operational_revision(project, actor):
    """Snapshot a Head update for later publication when a public version exists."""
    project_id = getattr(project, 'pk', project)
    locked_project = Project.objects.select_for_update().get(pk=project_id)
    _require_head_operational_authority(locked_project, actor)

    current_public = (
        locked_project.publication_revisions.select_for_update()
        .filter(
            status=PublicationStatus.PUBLISHED,
            is_current_public_revision=True,
        )
        .first()
    )
    if current_public is None:
        return None

    if locked_project.publication_revisions.select_for_update().filter(
        status__in=OPEN_REVISION_STATUSES,
    ).exists():
        raise ValidationError(
            'This project already has an active unpublished revision. '
            'The operational update was not saved.',
        )

    latest_number = (
        locked_project.publication_revisions.aggregate(
            highest=Max('revision_number'),
        )['highest']
        or 0
    )
    now = timezone.now()
    return ProjectPublicationRevision.objects.create(
        project=locked_project,
        revision_number=latest_number + 1,
        status=PublicationStatus.APPROVED,
        snapshot_data=build_project_publication_snapshot(locked_project),
        source_updated_at=locked_project.updated_at,
        supersedes_revision=current_public,
        submitted_by=actor,
        submitted_at=now,
        reviewed_by=actor,
        reviewed_at=now,
        review_notes='Operational update authorized by the responsible office Head.',
    )
