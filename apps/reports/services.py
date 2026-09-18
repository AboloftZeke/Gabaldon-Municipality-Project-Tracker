"""Disclosed project data used by individual report previews."""

from apps.system.publication_public import (
    current_public_revisions,
    get_public_project,
    infrastructure_public_data,
    non_infrastructure_public_data,
)


PUBLIC_DATA_ADAPTERS = {
    'infrastructure': infrastructure_public_data,
    'non_infrastructure': non_infrastructure_public_data,
}


def disclosed_projects_for_report(report_type):
    """Return selectable projects from current published snapshots only."""
    adapter = PUBLIC_DATA_ADAPTERS[report_type]
    projects = []
    for revision in current_public_revisions():
        snapshot_type = (revision.snapshot or {}).get('project', {}).get('type')
        if snapshot_type != report_type:
            continue
        project = adapter(revision)
        if project:
            projects.append(project)
    return sorted(projects, key=lambda project: project['title'].casefold())


def get_infrastructure_project_report_data(project_id):
    return get_public_project('infrastructure', project_id)


def get_non_infrastructure_project_report_data(project_id):
    return get_public_project('non_infrastructure', project_id)

