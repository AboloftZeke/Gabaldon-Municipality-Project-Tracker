"""Read models for the public site, backed only by published snapshots."""

from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from django.http import Http404
from django.urls import reverse

from .models import ProjectPublicationRevision
from .publication_workflow import PublicationStatus


def current_public_revisions():
    return ProjectPublicationRevision.objects.filter(
        status=PublicationStatus.PUBLISHED,
        is_current_public_revision=True,
    ).select_related('project')


def _decimal(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _time(value):
    if not value:
        return None
    try:
        return time.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _location_key(value):
    key = (value or '').strip().lower().replace(' ', '_')
    return 'bitulok' if key.startswith('bitulok') else key


def _status_key(value):
    return {
        'ongoing_bidding': 'ongoing',
        'awarded': 'ongoing',
    }.get(value, value or 'planned')


def _creator_name(snapshot):
    creator = snapshot.get('project', {}).get('creator') or {}
    return creator.get('display_name') or creator.get('username') or ''


def infrastructure_public_data(revision):
    snapshot = revision.snapshot_data or {}
    infrastructure = snapshot.get('infrastructure') or {}
    financial = snapshot.get('financial') or {}
    schedule = snapshot.get('schedule') or {}
    inspection = snapshot.get('inspection') or {}
    address = infrastructure.get('address') or {}
    category = infrastructure.get('category') or {}
    office = infrastructure.get('implementing_office') or {}
    contractor = infrastructure.get('contractor') or {}
    fund_source = financial.get('fund_source') or {}
    project = snapshot.get('project') or {}

    approved_budget = _decimal(financial.get('approved_budget'))
    contract_price = _decimal(financial.get('contract_price'))
    cost_progress = _decimal(
        infrastructure.get('cost_progress_percentage'),
    )
    physical_progress = _decimal(
        infrastructure.get('physical_progress_percentage'),
    )
    record_id = infrastructure.get('id')
    if record_id is None:
        return None

    images = [
        {
            'id': image.get('id'),
            'image_url': image.get('url') or '',
            'is_cover': bool(image.get('is_cover')),
        }
        for image in snapshot.get('images', [])
        if image.get('url')
    ]
    return {
        'revision': revision,
        'record_id': record_id,
        'project_id': project.get('id') or revision.project_id,
        'code': infrastructure.get('code') or f'INF-{record_id:05d}',
        'title': infrastructure.get('title') or '',
        'description': infrastructure.get('description') or '',
        'category': category,
        'address': address,
        'contractor': contractor,
        'implementing_office': office,
        'procurement_method': infrastructure.get('procurement_method') or '',
        'procurement_method_label': (
            infrastructure.get('procurement_method_label') or ''
        ),
        'award_status': infrastructure.get('award_status') or '',
        'award_status_label': (
            infrastructure.get('award_status_label') or 'Planned'
        ),
        'planned_start_date': _date(
            infrastructure.get('planned_start_date'),
        ),
        'planned_end_date': _date(infrastructure.get('planned_end_date')),
        'cost_progress_percentage': cost_progress,
        'physical_progress_percentage': physical_progress,
        'financial': {
            **financial,
            'approved_budget': approved_budget,
            'contract_price': contract_price,
            'fund_source': fund_source,
        } if financial else {},
        'schedule': {
            **schedule,
            'actual_start_date': _date(schedule.get('actual_start_date')),
            'actual_completion_date': _date(
                schedule.get('actual_completion_date'),
            ),
        } if schedule else {},
        'inspection': {
            **inspection,
            'inspection_date': _date(inspection.get('inspection_date')),
            'completion_percentage': _decimal(
                inspection.get('completion_percentage'),
            ),
        } if inspection else {},
        'images': images,
        'cover_image_url': (
            project.get('cover_image_url')
            or (images[0]['image_url'] if images else '')
        ),
        'created_by_name': _creator_name(snapshot),
        'created_at': _datetime(project.get('created_at')) or revision.created_at,
        'updated_at': _datetime(project.get('updated_at')) or revision.updated_at,
    }


def non_infrastructure_public_data(revision):
    snapshot = revision.snapshot_data or {}
    noninfra = snapshot.get('non_infrastructure') or {}
    project = snapshot.get('project') or {}
    record_id = noninfra.get('id')
    if record_id is None:
        return None
    images = [
        {
            'id': image.get('id'),
            'image_url': image.get('url') or '',
            'is_cover': bool(image.get('is_cover')),
        }
        for image in snapshot.get('images', [])
        if image.get('url')
    ]
    return {
        'revision': revision,
        'record_id': record_id,
        'project_id': project.get('id') or revision.project_id,
        'code': noninfra.get('code') or f'NINF-{record_id:05d}',
        'title': noninfra.get('title') or '',
        'description': noninfra.get('description') or '',
        'category': noninfra.get('category') or {},
        'status': noninfra.get('status') or 'planned',
        'status_label': noninfra.get('status_label') or 'Planned',
        'proponent': noninfra.get('proponent') or '',
        'beneficiaries': noninfra.get('beneficiaries'),
        'event_date': _date(noninfra.get('event_date')),
        'start_time': _time(noninfra.get('start_time')),
        'end_time': _time(noninfra.get('end_time')),
        'venue_name': noninfra.get('venue_name') or '',
        'address': noninfra.get('address') or {},
        'images': images,
        'cover_image_url': (
            project.get('cover_image_url')
            or (images[0]['image_url'] if images else '')
        ),
        'created_by_name': _creator_name(snapshot),
        'created_at': _datetime(project.get('created_at')) or revision.created_at,
        'updated_at': _datetime(project.get('updated_at')) or revision.updated_at,
    }


def public_projects():
    infrastructure = []
    non_infrastructure = []
    for revision in current_public_revisions():
        project_type = (revision.snapshot_data or {}).get('project', {}).get('type')
        if project_type == 'infrastructure':
            data = infrastructure_public_data(revision)
            if data:
                infrastructure.append(data)
        elif project_type == 'non_infrastructure':
            data = non_infrastructure_public_data(revision)
            if data:
                non_infrastructure.append(data)
    return infrastructure, non_infrastructure


def get_public_project(project_type, record_id):
    adapter = (
        infrastructure_public_data
        if project_type == 'infrastructure'
        else non_infrastructure_public_data
    )
    for revision in current_public_revisions():
        snapshot = revision.snapshot_data or {}
        if snapshot.get('project', {}).get('type') != project_type:
            continue
        data = adapter(revision)
        if data and data['record_id'] == record_id:
            return data
    raise Http404('Published project revision not found.')


def infrastructure_dashboard_row(data):
    category = data['category']
    address = data['address']
    financial = data['financial']
    fund_source = financial.get('fund_source') or {}
    approved_budget = financial.get('approved_budget')
    contract_price = financial.get('contract_price')
    cost_progress = data['cost_progress_percentage']
    physical_progress = data['physical_progress_percentage']
    budget = approved_budget or contract_price or Decimal('0')
    progress = physical_progress if physical_progress is not None else cost_progress
    return {
        'record_id': f"infra-{data['record_id']}",
        'category': 'infra',
        'project_category_key': f"infra:{category.get('code', '')}",
        'project_category_label': f"Infrastructure - {category.get('name', '')}",
        'type_label': 'Infrastructure',
        'title': data['title'],
        'cover_image_url': data['cover_image_url'],
        'location_key': _location_key(address.get('barangay')),
        'location': address.get('barangay') or '',
        'status_key': _status_key(data['award_status']),
        'status_label': data['award_status_label'],
        'office': data['implementing_office'].get('name') or '',
        'implementing_office': data['implementing_office'].get('name') or '',
        'category_label': category.get('name') or '',
        'contractor': data['contractor'].get('name') or '',
        'procurement_method': data['procurement_method_label'],
        'source_of_fund': fund_source.get('name') or '',
        'budget': budget,
        'has_financial': approved_budget is not None or contract_price is not None,
        'budget_amount': budget,
        'abc_amount': approved_budget if approved_budget is not None else '',
        'contract_price': contract_price if contract_price is not None else '',
        'progress': progress or Decimal('0'),
        'has_progress': physical_progress is not None or cost_progress is not None,
        'progress_percentage': progress or Decimal('0'),
        'overall_progress_percentage': progress or Decimal('0'),
        'cost_progress_percentage': cost_progress if cost_progress is not None else '',
        'physical_progress_percentage': physical_progress if physical_progress is not None else '',
        'description': data['description'],
        'planned_start_date': data['planned_start_date'],
        'planned_end_date': data['planned_end_date'],
        'actual_start_date': data['schedule'].get('actual_start_date'),
        'created_by_name': data['created_by_name'],
        'created_at': data['created_at'],
        'updated_at': data['updated_at'],
        'detail_url': reverse('public_infrastructure_project_detail', args=[data['record_id']]),
        'hide_financial': False,
    }


def non_infrastructure_dashboard_row(data):
    category = data['category']
    return {
        'record_id': f"noninfra-{data['record_id']}",
        'category': 'noninfra',
        'project_category_key': f"noninfra:{category.get('code', '')}",
        'project_category_label': (
            f"Non-Infrastructure - {category.get('name', '')}"
            if category.get('name') else 'Non-Infrastructure'
        ),
        'type_label': 'Non-Infrastructure',
        'title': data['title'],
        'cover_image_url': data['cover_image_url'],
        'location_key': '', 'location': '',
        'status_key': data['status'], 'status_label': data['status_label'],
        'office': '', 'implementing_office': '',
        'category_label': category.get('name') or '',
        'proponent': data['proponent'], 'beneficiaries': data['beneficiaries'],
        'contractor': '', 'procurement_method': '', 'source_of_fund': '',
        'budget': 0, 'has_financial': False, 'budget_amount': 0,
        'abc_amount': '', 'contract_price': '', 'progress': 0,
        'has_progress': False, 'progress_percentage': 0,
        'overall_progress_percentage': '', 'cost_progress_percentage': '',
        'physical_progress_percentage': '', 'description': data['description'],
        'venue_name': data['venue_name'], 'event_date': data['event_date'],
        'start_time': data['start_time'].strftime('%H:%M') if data['start_time'] else '',
        'end_time': data['end_time'].strftime('%H:%M') if data['end_time'] else '',
        'planned_start_date': data['event_date'], 'planned_end_date': None,
        'actual_start_date': None, 'created_by_name': data['created_by_name'],
        'created_at': data['created_at'], 'updated_at': data['updated_at'],
        'detail_url': reverse('public_non_infrastructure_project_detail', args=[data['record_id']]),
        'hide_financial': False,
    }
