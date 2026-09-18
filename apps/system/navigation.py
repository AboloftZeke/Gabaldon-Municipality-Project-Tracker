"""Persisted account destinations shared by login and templates."""
from django.urls import reverse

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
    resolver = getattr(request, 'resolver_match', None)
    current_name = resolver.url_name if resolver else ''
    current_namespace = resolver.namespace if resolver else ''

    def item(label, view_name, icon, *, active_names=(), namespace=''):
        return {
            'label': label,
            'url': reverse(view_name),
            'icon': icon,
            'active': (
                current_name in active_names
                or bool(namespace and current_namespace == namespace)
            ),
        }

    groups = []
    if request.user.is_authenticated:
        groups.append({
            'label': 'Overview',
            'items': [item(
                'Dashboard', name, 'dashboard', active_names=(name,),
            )],
        })

        if name in {'engineering_dashboard', 'engineering_head_dashboard'}:
            groups.append({
                'label': 'Projects',
                'items': [item(
                    'Infrastructure Projects',
                    'engineering_projects:project_list',
                    'projects',
                    namespace='engineering_projects',
                )],
            })
        elif name in {'mayor_dashboard', 'mayor_head_dashboard'}:
            groups.append({
                'label': 'Projects',
                'items': [item(
                    'Non-Infrastructure Projects',
                    'mayor_projects:non_infrastructure_project_list',
                    'projects',
                    namespace='mayor_projects',
                )],
            })

        if name in {'engineering_head_dashboard', 'mayor_head_dashboard'}:
            groups.extend([
                {
                    'label': 'Review & Publication',
                    'items': [item(
                        'Publication Review',
                        'publication_review_queue',
                        'review',
                        active_names=(
                            'publication_review_queue',
                            'publication_revision_detail',
                            'publication_revision_review',
                            'publication_revision_publish',
                            'publication_revision_archive',
                        ),
                    )],
                },
                {
                    'label': 'Reports',
                    'items': [item(
                        'Reports', 'reports:dashboard', 'reports',
                        namespace='reports',
                    )],
                },
            ])

        if name == 'admin_dashboard':
            groups.extend([
                {
                    'label': 'Review & Publication',
                    'items': [item(
                        'Publication Lifecycle',
                        'publication_lifecycle',
                        'review',
                        active_names=('publication_lifecycle',),
                    )],
                },
                {
                    'label': 'Administration',
                    'items': [item(
                        'User Management', 'user_list', 'users',
                        active_names=(
                            'user_list', 'user_create', 'user_create_confirm',
                            'user_edit', 'user_edit_confirm',
                            'user_deactivate', 'user_activate',
                            'user_resend_account_setup',
                        ),
                    )],
                },
            ])

        groups.append({
            'label': 'Account',
            'is_account': True,
            'items': [
                item(
                    'Profile & Password', 'password_change', 'account',
                    active_names=('password_change',),
                ),
                item('Logout', 'logout', 'logout', active_names=('logout',)),
            ],
        })

    role_labels = {
        'admin_dashboard': 'System Administrator',
        'engineering_dashboard': 'Engineering Staff',
        'engineering_head_dashboard': 'Engineering Head',
        'mayor_dashboard': "Mayor's Office Staff",
        'mayor_head_dashboard': "Mayor's Office Head",
    }
    embedded_sidebar_names = {
        'admin_dashboard', 'engineering_dashboard', 'engineering_head_dashboard',
        'mayor_dashboard', 'mayor_head_dashboard',
        'user_list', 'user_create', 'user_edit', 'user_activate',
        'user_deactivate',
        'project_dashboard', 'non_infrastructure_project_dashboard',
    }
    show_sidebar = request.user.is_authenticated and name != 'public_dashboard'
    return {'account_navigation': {
        'dashboard': name,
        'is_head': name in labels,
        'label': labels.get(name, 'Dashboard'),
        'role_label': role_labels.get(name, 'Account'),
        'groups': groups,
        'show_sidebar': show_sidebar,
        'render_sidebar_in_base': show_sidebar and current_name not in embedded_sidebar_names,
    }}
