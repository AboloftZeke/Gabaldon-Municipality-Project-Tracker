"""Persisted account capabilities; no legacy profile or staff-flag fallbacks.

Management helpers describe office Staff only. Existing Admin exceptions remain
explicit at their call sites because create and edit permissions differ today.
Review capabilities are scoped to the Head's office, never to superuser status.
"""

from .models import NonInfrastructureProgressUpdate, ProjectRevision, UserRole
from django.db.models import Q
from .publication_workflow import PublicationStatus


VALID_ASSIGNMENTS = {
    ('admin', 'admin'),
    ('engineer', 'staff'), ('engineer', 'head'),
    ('mayor', 'staff'), ('mayor', 'head'),
}


def _active_user(user):
    return bool(user and user.is_authenticated and user.is_active and user.pk)


def is_system_admin(user):
    """Preserve the existing superuser exception during the staged redesign."""
    return _active_user(user) and user.is_superuser


def _assignment(user):
    if not _active_user(user):
        return None
    # Query persisted data, not a potentially stale user.role_assignment/profile cache.
    pair = UserRole.objects.filter(user_id=user.pk).values_list('department', 'role').first()
    return pair if pair in VALID_ASSIGNMENTS else None


def department_for_user(user):
    if is_system_admin(user):
        return 'admin'
    pair = _assignment(user)
    return pair[0] if pair else None


def can_manage_infrastructure(user):
    return not is_system_admin(user) and _assignment(user) == ('engineer', 'staff')


def can_manage_non_infrastructure(user):
    return not is_system_admin(user) and _assignment(user) == ('mayor', 'staff')


def is_engineering_head(user):
    return not is_system_admin(user) and _assignment(user) == ('engineer', 'head')


def is_mayor_head(user):
    return not is_system_admin(user) and _assignment(user) == ('mayor', 'head')


def can_update_infrastructure_operations(user):
    return is_engineering_head(user)


def can_update_non_infrastructure_operations(user):
    return is_mayor_head(user)


def has_active_publication_revision(project):
    if not project or project.project_id is None:
        return False
    # Import lazily because publication_service imports these permission helpers.
    from .publication_service import OPEN_REVISION_STATUSES

    return ProjectRevision.objects.filter(
        project_id=project.project_id,
        status__in=OPEN_REVISION_STATUSES,
    ).exists()


def has_active_non_infrastructure_progress_update(project):
    if not project or project.pk is None:
        return False
    from .publication_service import OPEN_REVISION_STATUSES

    return NonInfrastructureProgressUpdate.objects.filter(
        non_infrastructure_id=project.pk,
    ).filter(
        Q(review_status__in=(
            NonInfrastructureProgressUpdate.ReviewStatus.PENDING_REVIEW,
            NonInfrastructureProgressUpdate.ReviewStatus.RETURNED,
        ))
        | Q(
            review_status=NonInfrastructureProgressUpdate.ReviewStatus.APPROVED,
            applied_at__isnull=True,
        )
        | Q(
            applied_at__isnull=False,
            publication_revision__status__in=OPEN_REVISION_STATUSES,
        ),
    ).exists()


def can_create_non_infrastructure_progress_update(user, project):
    """Allow Mayor Staff to draft later operational updates after publication."""
    if not can_manage_non_infrastructure(user):
        return False
    if not project or project.project_id is None:
        return False
    if has_active_publication_revision(project):
        return False
    if has_active_non_infrastructure_progress_update(project):
        return False
    latest_revision = ProjectRevision.objects.filter(
        project_id=project.project_id,
    ).order_by('-revision_number', '-pk').first()
    return bool(
        latest_revision
        and latest_revision.status == PublicationStatus.PUBLISHED
        and latest_revision.is_current_public
    )


def can_review_infrastructure(user):
    return is_engineering_head(user)


def can_review_non_infrastructure(user):
    return is_mayor_head(user)


def review_project_type(user):
    if can_review_infrastructure(user):
        return 'infrastructure'
    if can_review_non_infrastructure(user):
        return 'non_infrastructure'
    return None


def can_access_publication_review(user, revision):
    project_type = review_project_type(user)
    return project_type is not None and revision.project.project_type == project_type


def can_review_revision(user, revision):
    if not can_access_publication_review(user, revision):
        return False
    creator = ((revision.snapshot or {}).get('project') or {}).get('creator') or {}
    return user.pk not in {
        revision.submitted_by_id,
        revision.project.created_by_user_id,
        creator.get('id'),
    }


def can_publish_infrastructure(user):
    return is_engineering_head(user)


def can_publish_non_infrastructure(user):
    return is_mayor_head(user)


def can_publish_revision(user, revision):
    if revision.status != 'approved':
        return False
    return {
        'infrastructure': can_publish_infrastructure,
        'non_infrastructure': can_publish_non_infrastructure,
    }.get(revision.project.project_type, lambda user: False)(user)
