"""Canonical states and transitions for public project revisions."""

from django.core.exceptions import ValidationError
from django.db import models


class PublicationStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    PENDING_REVIEW = 'pending_review', 'Pending Review'
    NEEDS_REVISION = 'needs_revision', 'Needs Revision'
    APPROVED = 'approved', 'Approved'
    PUBLISHED = 'published', 'Published'
    REJECTED = 'rejected', 'Rejected'
    ARCHIVED = 'archived', 'Archived'


ALLOWED_PUBLICATION_TRANSITIONS = {
    PublicationStatus.DRAFT: frozenset({
        PublicationStatus.PENDING_REVIEW,
    }),
    PublicationStatus.PENDING_REVIEW: frozenset({
        PublicationStatus.APPROVED,
        PublicationStatus.NEEDS_REVISION,
        PublicationStatus.REJECTED,
    }),
    PublicationStatus.NEEDS_REVISION: frozenset({
        PublicationStatus.PENDING_REVIEW,
    }),
    PublicationStatus.APPROVED: frozenset({
        PublicationStatus.PUBLISHED,
        PublicationStatus.NEEDS_REVISION,
    }),
    PublicationStatus.PUBLISHED: frozenset({
        PublicationStatus.ARCHIVED,
    }),
    PublicationStatus.REJECTED: frozenset(),
    PublicationStatus.ARCHIVED: frozenset(),
}


def available_publication_transitions(status):
    """Return the immutable set of states reachable from ``status``."""
    normalized_status = PublicationStatus(status)
    return ALLOWED_PUBLICATION_TRANSITIONS[normalized_status]


def can_transition_publication(current_status, target_status):
    """Return whether a publication revision may move to ``target_status``."""
    try:
        normalized_target = PublicationStatus(target_status)
        return normalized_target in available_publication_transitions(
            current_status,
        )
    except ValueError:
        return False


def validate_publication_transition(current_status, target_status):
    """Raise a validation error when a requested transition is not legal."""
    try:
        normalized_current = PublicationStatus(current_status)
        normalized_target = PublicationStatus(target_status)
    except ValueError as exc:
        raise ValidationError('Unknown publication workflow status.') from exc

    if not can_transition_publication(normalized_current, normalized_target):
        raise ValidationError(
            'Publication status cannot change from '
            f'{normalized_current.label} to {normalized_target.label}.'
        )
