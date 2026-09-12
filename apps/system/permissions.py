"""Persisted account capabilities; no legacy profile or staff-flag fallbacks.

Management helpers describe office Staff only. Existing Admin exceptions remain
explicit at their call sites because create and edit permissions differ today.
Head predicates do not grant publication-review access.
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
