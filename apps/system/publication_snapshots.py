"""Build stable, JSON-safe snapshots for public project revisions."""

from .models import InfrastructureProject, NonInfrastructureProject


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


def build_progress_update_snapshot(progress_update):
    """Retain one Head progress decision and its selected inspection evidence."""
    inspections = []
    queryset = progress_update.supporting_inspections.select_related(
        'inspected_by_user',
    ).prefetch_related(
        'evidence__uploaded_by_user',
    ).order_by(
        '-inspection_date', '-created_at', '-inspection_id',
    )
    for inspection in queryset:
        evidence = [
            {
                'id': item.pk,
                'type': item.evidence_type,
                'type_label': item.get_evidence_type_display(),
                'original_name': item.original_name,
                'url': item.file_url or '',
                'content_type': item.content_type or '',
                'uploaded_by': _user_data(item.uploaded_by_user),
                'created_at': _isoformat(item.created_at),
            }
            for item in inspection.evidence.all()
        ]
        inspections.append({
            'id': inspection.pk,
            'inspection_date': _isoformat(inspection.inspection_date),
            'inspection_type': inspection.inspection_type,
            'inspection_type_label': inspection.get_inspection_type_display(),
            'completion_percentage': _decimal_string(
                inspection.completion_percentage,
            ),
            'findings': inspection.findings or '',
            'remarks': inspection.remarks or '',
            'inspected_by': _user_data(inspection.inspected_by_user),
            'evidence': evidence,
        })

    summary = '; '.join(
        f"{item['inspection_date']} · {item['inspection_type_label']}"
        for item in inspections
    )
    return {
        'id': progress_update.pk,
        'official_status': progress_update.new_official_status or '',
        'official_status_label': (
            progress_update.get_new_official_status_display() or ''
        ),
        'official_physical_progress': (
            format(progress_update.new_physical_progress, '.2f')
            if progress_update.new_physical_progress is not None else None
        ),
        'head_remarks': progress_update.head_remarks or '',
        'updated_by': _user_data(progress_update.updated_by),
        'created_at': _isoformat(progress_update.created_at),
        'supporting_inspections_summary': summary,
        'supporting_inspections': inspections,
    }


def build_non_infrastructure_progress_update_snapshot(progress_update):
    """Freeze one Mayor Head decision and its evidence as JSON-safe metadata."""
    evidence = [
        {
            'id': item.pk,
            'file_path': item.evidence_file.name,
            'description': item.description or '',
            'uploaded_by': _user_data(item.uploaded_by),
            'uploaded_at': _isoformat(item.uploaded_at),
        }
        for item in progress_update.evidence.select_related('uploaded_by').order_by(
            'created_at', 'evidence_id',
        )
    ]
    return {
        'id': progress_update.pk,
        'previous_status': progress_update.previous_status,
        'proposed_status': progress_update.proposed_status,
        'remarks': progress_update.remarks or '',
        'review_status': progress_update.review_status,
        'review_notes': progress_update.review_notes or '',
        'submitted_by': _user_data(progress_update.submitted_by),
        'submitted_at': _isoformat(progress_update.submitted_at),
        'reviewed_by': _user_data(progress_update.reviewed_by),
        'reviewed_at': _isoformat(progress_update.reviewed_at),
        'applied_by': _user_data(progress_update.applied_by),
        'applied_at': _isoformat(progress_update.applied_at),
        'evidence': evidence,
    }


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
            'title': infrastructure.title,
            'description': infrastructure.description or '',
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
            'status': infrastructure.status or '',
            'status_label': (
                infrastructure.get_status_display() or ''
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
        'title': non_infrastructure.title,
        'description': non_infrastructure.description or '',
        'project_type': non_infrastructure.project_type,
        'project_type_label': non_infrastructure.get_project_type_display(),
        'category': (
            {
                'id': non_infrastructure.category_id,
                'code': non_infrastructure.category.type_code,
                'name': non_infrastructure.category.type_name,
            }
            if non_infrastructure.category else None
        ),
        'status': non_infrastructure.status,
        'status_label': non_infrastructure.get_status_display(),
        'proponent': non_infrastructure.proponent or '',
        'beneficiaries': non_infrastructure.beneficiaries,
        'target_beneficiaries': non_infrastructure.target_beneficiaries or '',
        'implementation_start_date': _isoformat(
            non_infrastructure.implementation_start_date,
        ),
        'implementation_end_date': _isoformat(
            non_infrastructure.implementation_end_date,
        ),
        'event_date': _isoformat(non_infrastructure.event_date),
        'start_time': _isoformat(non_infrastructure.start_time),
        'end_time': _isoformat(non_infrastructure.end_time),
        'venue_name': non_infrastructure.venue_name or '',
        'project_cost': _decimal_string(non_infrastructure.project_cost),
        'fund_source': non_infrastructure.fund_source or '',
        'contractor_supplier': non_infrastructure.contractor_supplier or '',
        'procurement_description': non_infrastructure.procurement_description or '',
        'quantity': non_infrastructure.quantity,
        'expected_delivery_date': _isoformat(
            non_infrastructure.expected_delivery_date,
        ),
        'remarks': non_infrastructure.remarks or '',
        'address': _address_data(non_infrastructure.address),
    }
    return snapshot


def build_project_publication_snapshot(project):
    """Dispatch snapshot generation using the normalized project type."""
    if project.project_type == 'infrastructure':
        try:
            infrastructure = project.infrastructure_project
        except InfrastructureProject.DoesNotExist as exc:
            raise ValueError(
                'Infrastructure project details are missing.'
            ) from exc
        return build_infrastructure_snapshot(infrastructure)

    if project.project_type == 'non_infrastructure':
        try:
            non_infrastructure = project.non_infrastructure_project
        except NonInfrastructureProject.DoesNotExist as exc:
            raise ValueError(
                'Non-infrastructure project details are missing.'
            ) from exc
        return build_non_infrastructure_snapshot(non_infrastructure)

    raise ValueError(
        f'Unsupported project type: {project.project_type!r}.'
    )
