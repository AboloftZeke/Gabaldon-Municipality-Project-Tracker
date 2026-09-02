"""Build stable, JSON-safe snapshots for public project revisions."""

from .models import Infrastructure_Project, Non_Infrastructure_Project


SNAPSHOT_SCHEMA_VERSION = 1


def _isoformat(value):
    return value.isoformat() if value is not None else None


def _decimal_string(value):
    return str(value) if value is not None else None


def _user_data(user):
    if user is None:
        return None
    return {
        'id': user.pk,
        'username': user.username,
        'display_name': user.get_full_name() or user.username,
    }


def _address_data(address):
    if address is None:
        return None
    return {
        'id': address.pk,
        'street': address.street or '',
        'barangay': address.barangay or '',
        'municipality': address.municipality or '',
        'province': address.province or '',
        'country': address.country or '',
        'postal_code': address.postal_code or '',
        'latitude': _decimal_string(address.latitude),
        'longitude': _decimal_string(address.longitude),
    }


def _image_data(project):
    images = project.images.filter(is_active=True).order_by(
        '-is_cover',
        '-created_at',
    )
    return [
        {
            'id': image.pk,
            'url': image.image_url or '',
            'is_cover': image.is_cover,
            'created_at': _isoformat(image.created_at),
        }
        for image in images
    ]


def _base_snapshot(project, images):
    cover = next((image for image in images if image['is_cover']), None)
    return {
        'schema_version': SNAPSHOT_SCHEMA_VERSION,
        'project': {
            'id': project.pk,
            'type': project.project_type,
            'creator': _user_data(project.created_by_user),
            'created_at': _isoformat(project.created_at),
            'updated_at': _isoformat(project.updated_at),
            'cover_image_url': cover['url'] if cover else '',
        },
        'images': images,
    }


def build_infrastructure_snapshot(infrastructure):
    project = infrastructure.project
    images = _image_data(project)
    snapshot = _base_snapshot(project, images)

    financial = (
        infrastructure.financial_records.select_related('fund_source')
        .order_by('-financial_id')
        .first()
    )
    schedule = infrastructure.schedules.order_by('-schedule_id').first()
    inspection = (
        project.inspections.select_related('inspected_by_user')
        .order_by('-inspection_date', '-created_at')
        .first()
    )

    snapshot.update({
        'infrastructure': {
            'id': infrastructure.pk,
            'code': infrastructure.infrastructure_code or '',
            'title': infrastructure.infrastructure_title,
            'description': infrastructure.infrastructure_description or '',
            'category': (
                {
                    'id': infrastructure.category_id,
                    'code': infrastructure.category.category_code,
                    'name': infrastructure.category.category_name,
                }
                if infrastructure.category else None
            ),
            'address': _address_data(infrastructure.address),
            'contractor': (
                {
                    'id': infrastructure.contractor_id,
                    'name': infrastructure.contractor.contractor_name,
                }
                if infrastructure.contractor else None
            ),
            'implementing_office': (
                {
                    'id': infrastructure.implementing_office_id,
                    'name': infrastructure.implementing_office.office_name,
                }
                if infrastructure.implementing_office else None
            ),
            'procurement_method': infrastructure.procurement_method or '',
            'procurement_method_label': (
                infrastructure.get_procurement_method_display() or ''
            ),
            'award_status': infrastructure.award_status or '',
            'award_status_label': (
                infrastructure.get_award_status_display() or ''
            ),
            'planned_start_date': _isoformat(
                infrastructure.planned_start_date,
            ),
            'planned_end_date': _isoformat(
                infrastructure.planned_end_date,
            ),
            'cost_progress_percentage': _decimal_string(
                infrastructure.cost_progress_percentage,
            ),
            'physical_progress_percentage': _decimal_string(
                infrastructure.physical_progress_percentage,
            ),
        },
        'financial': (
            {
                'id': financial.pk,
                'approved_budget': _decimal_string(
                    financial.approved_budget,
                ),
                'contract_price': _decimal_string(financial.bid_amount),
                'actual_expenditure': _decimal_string(
                    financial.actual_expenditure,
                ),
                'fund_source': (
                    {
                        'id': financial.fund_source_id,
                        'code': financial.fund_source.fund_source_code,
                        'name': financial.fund_source.fund_source_name,
                        'percentage': _decimal_string(
                            financial.fund_source.fund_percentage,
                        ),
                    }
                    if financial.fund_source else None
                ),
            }
            if financial else None
        ),
        'schedule': (
            {
                'id': schedule.pk,
                'posting_date': _isoformat(schedule.posting_date),
                'pre_bid_date': _isoformat(schedule.pre_bid_date),
                'bidding_date': _isoformat(schedule.bidding_date),
                'notice_award_date': _isoformat(
                    schedule.notice_award_date,
                ),
                'notice_to_proceed_date': _isoformat(
                    schedule.notice_proceed_date,
                ),
                'duration_days': schedule.duration_days,
                'contract_expiry_date': _isoformat(
                    schedule.contract_expiry_date,
                ),
                'actual_start_date': _isoformat(schedule.actual_start_date),
                'actual_completion_date': _isoformat(
                    schedule.actual_completion_date,
                ),
            }
            if schedule else None
        ),
        'inspection': (
            {
                'id': inspection.pk,
                'inspection_date': _isoformat(inspection.inspection_date),
                'completion_percentage': _decimal_string(
                    inspection.completion_percentage,
                ),
                'findings': inspection.findings or '',
                'remarks': inspection.remarks or '',
                'inspected_by': _user_data(inspection.inspected_by_user),
            }
            if inspection else None
        ),
    })
    return snapshot


def build_non_infrastructure_snapshot(non_infrastructure):
    project = non_infrastructure.project
    images = _image_data(project)
    snapshot = _base_snapshot(project, images)
    snapshot['non_infrastructure'] = {
        'id': non_infrastructure.pk,
        'code': f'NINF-{non_infrastructure.pk:05d}',
        'title': non_infrastructure.non_infra_name,
        'description': non_infrastructure.description or '',
        'category': (
            {
                'id': non_infrastructure.non_infra_category_id,
                'code': non_infrastructure.non_infra_category.type_code,
                'name': non_infrastructure.non_infra_category.type_name,
            }
            if non_infrastructure.non_infra_category else None
        ),
        'status': non_infrastructure.status,
        'status_label': non_infrastructure.get_status_display(),
        'proponent': non_infrastructure.proponent or '',
        'beneficiaries': non_infrastructure.beneficiaries,
        'event_date': _isoformat(non_infrastructure.event_date),
        'start_time': _isoformat(non_infrastructure.start_time),
        'end_time': _isoformat(non_infrastructure.end_time),
        'venue_name': non_infrastructure.venue_name or '',
        'address': _address_data(non_infrastructure.address),
    }
    return snapshot


def build_project_publication_snapshot(project):
    """Dispatch snapshot generation using the normalized project type."""
    if project.project_type == 'infrastructure':
        try:
            infrastructure = project.infrastructure_project
        except Infrastructure_Project.DoesNotExist as exc:
            raise ValueError(
                'Infrastructure project details are missing.'
            ) from exc
        return build_infrastructure_snapshot(infrastructure)

    if project.project_type == 'non_infrastructure':
        try:
            non_infrastructure = project.non_infrastructure_project
        except Non_Infrastructure_Project.DoesNotExist as exc:
            raise ValueError(
                'Non-infrastructure project details are missing.'
            ) from exc
        return build_non_infrastructure_snapshot(non_infrastructure)

    raise ValueError(
        f'Unsupported project type: {project.project_type!r}.'
    )
