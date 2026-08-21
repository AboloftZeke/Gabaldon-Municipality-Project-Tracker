"""Atomic application services for the project publication workflow."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import Project, ProjectPublicationRevision
from .publication_snapshots import build_project_publication_snapshot
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


def _require_admin(actor):
    _require_authenticated(actor)
    if not actor.is_superuser:
        raise PermissionDenied(
            'Only an administrator can review or publish revisions.',
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


@transaction.atomic
def create_publication_draft(project, actor):
    """Capture a new draft without changing the current public revision."""
    _require_authenticated(actor)
    project_id = getattr(project, 'pk', project)
    locked_project = Project.objects.select_for_update().get(pk=project_id)

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
    """Refresh a draft from working data and submit it for admin review."""
    _require_authenticated(actor)
    locked_revision = _locked_revision(revision)
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
    """Record an administrator's approval or return/rejection decision."""
    _require_admin(reviewer)
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

    locked_revision = _locked_revision(revision)
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
    _require_admin(publisher)
    locked_revision = _locked_project_revision(revision)
    validate_publication_transition(
        locked_revision.status,
        PublicationStatus.PUBLISHED,
    )

    previous_public = list(
        ProjectPublicationRevision.objects.select_for_update().filter(
            project_id=locked_revision.project_id,
            status=PublicationStatus.PUBLISHED,
            is_current_public_revision=True,
        ).exclude(pk=locked_revision.pk)
    )
    now = timezone.now()
    for previous in previous_public:
        previous.status = PublicationStatus.ARCHIVED
        previous.is_current_public_revision = False
        previous.save(update_fields=[
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


@transaction.atomic
def archive_publication_revision(revision, actor):
    """Remove a current published revision from all public read paths."""
    _require_admin(actor)
    locked_revision = _locked_project_revision(revision)
    validate_publication_transition(
        locked_revision.status,
        PublicationStatus.ARCHIVED,
    )
    if not locked_revision.is_current_public_revision:
        raise ValidationError('Only the current public revision can be archived.')

    locked_revision.status = PublicationStatus.ARCHIVED
    locked_revision.is_current_public_revision = False
    locked_revision.save(update_fields=[
        'status',
        'is_current_public_revision',
        'updated_at',
    ])
    Project.objects.filter(pk=locked_revision.project_id).update(
        is_published=False,
        is_visible_to_public=False,
    )
    return locked_revision
