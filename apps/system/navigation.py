"""Persisted account destinations shared by login and templates."""
from .permissions import (can_manage_infrastructure, can_manage_non_infrastructure,
                          is_engineering_head, is_mayor_head, is_system_admin)


def dashboard_name(user):
    for check, name in [
        (is_system_admin, 'admin_dashboard'),
        (is_engineering_head, 'engineering_head_dashboard'),
        (is_mayor_head, 'mayor_head_dashboard'),
        (can_manage_infrastructure, 'engineering_dashboard'),
        (can_manage_non_infrastructure, 'mayor_dashboard'),
    ]:
        if check(user):
            return name
    return 'public_dashboard'


def account_navigation(request):
    name = dashboard_name(request.user)
    labels = {
        'engineering_head_dashboard': 'Engineering Head',
        'mayor_head_dashboard': "Mayor's Office Head",
    }
    return {'account_navigation': {
        'dashboard': name,
        'is_head': name in labels,
        'label': labels.get(name, 'Dashboard'),
    }}
