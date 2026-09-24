"""Apply an approved Mayor update through the existing publication workflow."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.system.models import NonInfrastructureProgressUpdate, NonInfrastructureProject, Project
from apps.system.permissions import can_update_non_infrastructure_operations
from apps.system.publication_service import create_head_operational_revision
from apps.system.publication_workflow import PublicationStatus


@transaction.atomic
def apply_approved_progress_update(update_id, actor):
    """Apply once; roll back the status if no operational revision can be made."""
    if not can_update_non_infrastructure_operations(actor):
        raise PermissionDenied('Only the Mayor Head can apply an approved progress update.')

    update = NonInfrastructureProgressUpdate.objects.select_for_update().get(pk=update_id)
    if update.review_status != NonInfrastructureProgressUpdate.ReviewStatus.APPROVED:
        raise ValidationError('Only Approved progress updates can be applied.')
    if update.applied_at is not None or update.publication_revision_id is not None:
        raise ValidationError('This progress update has already been applied.')

    # Lock the base record in the same order as the publication service, then
    # re-read the official status while holding the project lock.
    base_project_id = update.non_infrastructure.project_id
    base_project = Project.objects.select_for_update().get(pk=base_project_id)
    project = NonInfrastructureProject.objects.select_for_update().get(pk=update.non_infrastructure_id)

    if not base_project.revisions.filter(
        status=PublicationStatus.PUBLISHED,
        is_current_public=True,
    ).exists():
        raise ValidationError(
            'Publish this project first before applying an operational progress update.',
        )
    valid_statuses = dict(NonInfrastructureProject.STATUS_CHOICES)
    if project.status not in valid_statuses:
        raise ValidationError('The current official project status is invalid.')
    if project.status != update.previous_status:
        raise ValidationError(
            'The official status changed since this draft was created. '
            'This update cannot be applied.',
        )
    if (
        update.proposed_status not in valid_statuses
        or update.proposed_status == project.status
    ):
        raise ValidationError('The proposed status must be a different valid project status.')
    if not update.evidence.exists():
        raise ValidationError('Supporting evidence is required before applying this update.')

    project.status = update.proposed_status
    project.save(update_fields=['status', 'updated_at'])
    revision = create_head_operational_revision(base_project, actor)
    if revision is None:
        raise ValidationError('An operational publication revision could not be created.')

    update.applied_at = timezone.now()
    update.applied_by = actor
    update.publication_revision = revision
    update.save(update_fields=['applied_at', 'applied_by', 'publication_revision', 'updated_at'])
    return update
