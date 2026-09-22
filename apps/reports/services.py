"""Disclosed project data used by report previews."""

from collections import Counter
from decimal import Decimal

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


def _apply_common_filters(projects, filters, *, status_key, date_key):
    rows = projects
    if filters.get('barangay'):
        rows = [
            project for project in rows
            if project['address'].get('barangay') == filters['barangay']
        ]
    if filters.get('category'):
        rows = [
            project for project in rows
            if project['category'].get('code') == filters['category']
        ]
    if filters.get('status'):
        rows = [
            project for project in rows
            if project[status_key] == filters['status']
        ]
    if filters.get('project_type'):
        rows = [
            project for project in rows
            if project.get('project_type') == filters['project_type']
        ]
    if filters.get('date_from'):
        rows = [
            project for project in rows
            if project[date_key] is not None
            and project[date_key] >= filters['date_from']
        ]
    if filters.get('date_to'):
        rows = [
            project for project in rows
            if project[date_key] is not None
            and project[date_key] <= filters['date_to']
        ]
    return rows


def get_infrastructure_summary_report_data(filters):
    projects = disclosed_projects_for_report('infrastructure')
    rows = _apply_common_filters(
        projects,
        filters,
        status_key='status',
        date_key='planned_start_date',
    )
    contract_values = [
        project['financial'].get('contract_price')
        for project in rows
        if project['financial'].get('contract_price') is not None
    ]
    progress_values = [
        project['physical_progress_percentage']
        for project in rows
        if project['physical_progress_percentage'] is not None
    ]
    return {
        'rows': rows,
        'total_projects': len(rows),
        'status_counts': dict(Counter(
            project['status_label'] or 'Unspecified'
            for project in rows
        )),
        'total_contract_value': sum(contract_values, Decimal('0')),
        'average_physical_progress': (
            sum(progress_values, Decimal('0')) / len(progress_values)
            if progress_values else None
        ),
    }


def get_non_infrastructure_summary_report_data(filters):
    projects = disclosed_projects_for_report('non_infrastructure')
    rows = _apply_common_filters(
        projects,
        filters,
        status_key='status',
        date_key='report_date',
    )
    beneficiary_values = [
        project['beneficiaries']
        for project in rows
        if project['beneficiaries'] is not None
    ]
    return {
        'rows': rows,
        'total_projects': len(rows),
        'status_counts': dict(Counter(
            project['status_label'] or 'Unspecified'
            for project in rows
        )),
        'category_counts': dict(Counter(
            project['category'].get('name') or 'Uncategorized'
            for project in rows
        )),
        'total_beneficiaries': sum(beneficiary_values),
    }

