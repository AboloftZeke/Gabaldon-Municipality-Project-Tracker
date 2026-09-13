"""Persisted account capabilities; no legacy profile or staff-flag fallbacks.

Management helpers describe office Staff only. Existing Admin exceptions remain
explicit at their call sites because create and edit permissions differ today.
Review capabilities are scoped to the Head's office, never to superuser status.
"""

from .models import UserFlag


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
    # Query persisted data, not a potentially stale user.flags/profile cache.
    pair = UserFlag.objects.filter(user_id=user.pk).values_list('department', 'role').first()
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
    creator = ((revision.snapshot_data or {}).get('project') or {}).get('creator') or {}
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
