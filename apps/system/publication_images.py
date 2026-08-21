"""Safely remove working-copy images without breaking revision snapshots."""

from django.db import transaction
from django.utils import timezone

from .models import Project_Image


def revision_snapshot_references_image(snapshot_data, image):
    """Return whether a snapshot contains an image by stable ID or URL."""
    if not isinstance(snapshot_data, dict):
        return False

    for snapshot_image in snapshot_data.get('images', []):
        if not isinstance(snapshot_image, dict):
            continue
        if snapshot_image.get('id') == image.pk:
            return True
        if image.image_url and snapshot_image.get('url') == image.image_url:
            return True
    return False


def image_is_referenced_by_revision(image):
    """Check all retained revisions, including pending and archived ones."""
    revisions = image.project.publication_revisions.only('snapshot_data')
    return any(
        revision_snapshot_references_image(revision.snapshot_data, image)
        for revision in revisions.iterator()
    )


@transaction.atomic
def retire_project_images(project, image_ids):
    """
    Remove images from the working copy while retaining revision dependencies.

    Referenced image rows are soft-deleted so their metadata and files remain
    available to previews, published snapshots, audit history, and restoration.
    Unreferenced rows are removed, while physical file cleanup is deliberately
    deferred to a separate reference-aware maintenance process.
    """
    normalized_ids = {
        int(image_id)
        for image_id in image_ids
        if str(image_id).isdigit()
    }
    if not normalized_ids:
        return {'retired': 0, 'deleted': 0}

    images = list(
        Project_Image.all_objects.select_for_update().filter(
            project=project,
            pk__in=normalized_ids,
            is_active=True,
        )
    )
    retired = 0
    deleted = 0
    removed_at = timezone.now()

    for image in images:
        if image_is_referenced_by_revision(image):
            image.is_active = False
            image.is_cover = False
            image.removed_at = removed_at
            image.save(update_fields=['is_active', 'is_cover', 'removed_at'])
            retired += 1
        else:
            image.delete()
            deleted += 1

    return {'retired': retired, 'deleted': deleted}
