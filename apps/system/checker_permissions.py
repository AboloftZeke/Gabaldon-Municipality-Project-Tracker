"""Centralized authorization for type-scoped project review."""
from django.core.exceptions import PermissionDenied

from .models import UserFlag

INFRASTRUCTURE_CHECKER = "infra_checker"
NONINFRASTRUCTURE_CHECKER = "noninfra_checker"

CHECKER_DEPARTMENT_BY_PROJECT_TYPE = {
    "infrastructure": INFRASTRUCTURE_CHECKER,
    "non_infrastructure": NONINFRASTRUCTURE_CHECKER,
}


def department_for_user(user):
    """Return the persisted department without granting implicit admin review access."""
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return "admin"

    flag = UserFlag.objects.filter(user=user).only("department").first()
    return flag.department if flag else None


def revision_project_type(revision):
    """Resolve type from the server-side immutable revision snapshot."""
    snapshot = revision.snapshot_data or {}
    project_type = (snapshot.get("project") or {}).get("type")
    if project_type in CHECKER_DEPARTMENT_BY_PROJECT_TYPE:
        return project_type

    project_type = getattr(revision.project, "project_type", None)
    return project_type if project_type in CHECKER_DEPARTMENT_BY_PROJECT_TYPE else None


def can_review_project_type(user, project_type):
    """True only for the checker explicitly assigned to this project type."""
    required_department = CHECKER_DEPARTMENT_BY_PROJECT_TYPE.get(project_type)
    return bool(
        required_department
        and department_for_user(user) == required_department
    )


def require_project_checker(user, project_type):
    """Raise 403 unless the user is the correct checker for the real project type."""
    if not can_review_project_type(user, project_type):
        raise PermissionDenied("You are not authorized to review this project type.")
