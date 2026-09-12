from django.db import migrations
from django.utils import timezone


BACKFILL_NOTE = 'Automatically published during approval workflow migration.'

PROCUREMENT_METHOD_LABELS = {
    'competitive_bidding': 'Competitive Bidding / Public Bidding',
    'svp': 'SVP (Small Value Procurement)',
    'nq': 'NQ (Negotiated Quotation)',
    'shopping': 'Shopping',
    'direct_contracting': 'Direct Contracting',
    'force_account': 'Force Account',
}

AWARD_STATUS_LABELS = {
    'awarded': 'Awarded',
    'ongoing_bidding': 'Ongoing Bidding',
    'cancelled': 'Cancelled',
    'rebid': 'Re-bid',
    'completed': 'Completed',
}

NON_INFRASTRUCTURE_STATUS_LABELS = {
    'planned': 'Planned',
    'ongoing': 'Ongoing',
    'completed': 'Completed',
}


def _isoformat(value):
    return value.isoformat() if value is not None else None


def _decimal_string(value):
    return str(value) if value is not None else None


def _user_data(user):
    if user is None:
        return None
    display_name = ' '.join(filter(None, [user.first_name, user.last_name]))
    return {
        'id': user.pk,
        'username': user.username,
        'display_name': display_name or user.username,
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


def _image_data(ProjectImage, project):
    images = ProjectImage.objects.filter(
        project_id=project.pk,
        is_active=True,
    ).order_by('-is_cover', '-created_at')
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
        'schema_version': 1,
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


def _infrastructure_snapshot(apps, project, infrastructure):
    ProjectImage = apps.get_model('system', 'Project_Image')
    Financial = apps.get_model('system', 'Financial')
    InfrastructureSchedule = apps.get_model(
        'system',
        'Infrastructure_Schedule',
    )
    ProjectInspection = apps.get_model('system', 'Project_Inspection')

    images = _image_data(ProjectImage, project)
    snapshot = _base_snapshot(project, images)
    financial = Financial.objects.filter(
        infrastructure_id=infrastructure.pk,
    ).select_related('fund_source').order_by('-financial_id').first()
    schedule = InfrastructureSchedule.objects.filter(
        infrastructure_id=infrastructure.pk,
    ).order_by('-schedule_id').first()
    inspection = ProjectInspection.objects.filter(
        project_id=project.pk,
    ).select_related('inspected_by_user').order_by(
        '-inspection_date',
        '-created_at',
    ).first()

    procurement_method = infrastructure.procurement_method or ''
    award_status = infrastructure.award_status or ''
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
                if infrastructure.category_id else None
            ),
            'address': _address_data(
                infrastructure.address if infrastructure.address_id else None,
            ),
            'contractor': (
                {
                    'id': infrastructure.contractor_id,
                    'name': infrastructure.contractor.contractor_name,
                }
                if infrastructure.contractor_id else None
            ),
            'implementing_office': (
                {
                    'id': infrastructure.implementing_office_id,
                    'name': infrastructure.implementing_office.office_name,
                }
                if infrastructure.implementing_office_id else None
            ),
            'procurement_method': procurement_method,
            'procurement_method_label': PROCUREMENT_METHOD_LABELS.get(
                procurement_method,
                procurement_method,
            ),
            'award_status': award_status,
            'award_status_label': AWARD_STATUS_LABELS.get(
                award_status,
                award_status,
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
                'approved_budget': _decimal_string(financial.approved_budget),
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
                    if financial.fund_source_id else None
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
                'notice_award_date': _isoformat(schedule.notice_award_date),
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


def _non_infrastructure_snapshot(apps, project, non_infrastructure):
    ProjectImage = apps.get_model('system', 'Project_Image')
    images = _image_data(ProjectImage, project)
    snapshot = _base_snapshot(project, images)
    status = non_infrastructure.status or ''
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
            if non_infrastructure.non_infra_category_id else None
        ),
        'status': status,
        'status_label': NON_INFRASTRUCTURE_STATUS_LABELS.get(status, status),
        'proponent': non_infrastructure.proponent or '',
        'beneficiaries': non_infrastructure.beneficiaries,
        'event_date': _isoformat(non_infrastructure.event_date),
        'start_time': _isoformat(non_infrastructure.start_time),
        'end_time': _isoformat(non_infrastructure.end_time),
        'venue_name': non_infrastructure.venue_name or '',
        'address': _address_data(
            non_infrastructure.address
            if non_infrastructure.address_id else None,
        ),
    }
    return snapshot


def backfill_published_revisions(apps, schema_editor):
    Project = apps.get_model('system', 'Project')
    InfrastructureProject = apps.get_model(
        'system',
        'Infrastructure_Project',
    )
    NonInfrastructureProject = apps.get_model(
        'system',
        'Non_Infrastructure_Project',
    )
    Revision = apps.get_model('system', 'ProjectPublicationRevision')
    migration_time = timezone.now()

    for project in Project.objects.select_related(
        'created_by_user',
    ).order_by('project_id').iterator(chunk_size=200):
        if Revision.objects.filter(project_id=project.pk).exists():
            continue

        if project.project_type == 'infrastructure':
            infrastructure = InfrastructureProject.objects.filter(
                project_id=project.pk,
            ).select_related(
                'category',
                'address',
                'contractor',
                'implementing_office',
            ).first()
            if infrastructure is None:
                continue
            snapshot = _infrastructure_snapshot(
                apps,
                project,
                infrastructure,
            )
        elif project.project_type == 'non_infrastructure':
            non_infrastructure = NonInfrastructureProject.objects.filter(
                project_id=project.pk,
            ).select_related(
                'non_infra_category',
                'address',
            ).first()
            if non_infrastructure is None:
                continue
            snapshot = _non_infrastructure_snapshot(
                apps,
                project,
                non_infrastructure,
            )
        else:
            continue

        Revision.objects.create(
            project_id=project.pk,
            revision_number=1,
            status='published',
            snapshot_data=snapshot,
            source_updated_at=project.updated_at,
            review_notes=BACKFILL_NOTE,
            published_at=migration_time,
            is_current_public_revision=True,
        )
        Project.objects.filter(pk=project.pk).update(
            is_published=True,
            is_visible_to_public=True,
        )


def remove_backfilled_revisions(apps, schema_editor):
    Project = apps.get_model('system', 'Project')
    Revision = apps.get_model('system', 'ProjectPublicationRevision')
    generated = Revision.objects.filter(
        revision_number=1,
        status='published',
        review_notes=BACKFILL_NOTE,
        submitted_by_id__isnull=True,
        reviewed_by_id__isnull=True,
        published_by_id__isnull=True,
    )
    project_ids = list(generated.values_list('project_id', flat=True))
    generated.delete()
    Project.objects.filter(pk__in=project_ids).update(
        is_published=False,
        is_visible_to_public=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('system', '0026_protect_revision_images'),
    ]

    operations = [
        migrations.RunPython(
            backfill_published_revisions,
            remove_backfilled_revisions,
        ),
    ]
