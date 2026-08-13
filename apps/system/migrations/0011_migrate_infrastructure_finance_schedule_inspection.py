from django.db import migrations


def migrate_infrastructure_details(apps, schema_editor):
    Infrastructure_Project = apps.get_model('system', 'Infrastructure_Project')
    Infrastructure_Schedule = apps.get_model('system', 'Infrastructure_Schedule')
    Financial = apps.get_model('system', 'Financial')
    Project_Inspection = apps.get_model('system', 'Project_Inspection')
    FundSource = apps.get_model('system', 'FundSource')
    LegacyProject = apps.get_model('infrastructure', 'InfrastructureProject')

    for old in LegacyProject.objects.all().order_by('id'):
        infra = Infrastructure_Project.objects.filter(project__project_id__isnull=False).filter(infrastructure_title=old.title).order_by('infrastructure_id').first()
        if infra is None:
            continue

        schedule = Infrastructure_Schedule.objects.create(
            infrastructure=infra,
            pre_bid_date=None,
            bidding_date=None,
            notice_award_date=None,
            notice_proceed_date=None,
            posting_date=None,
            duration_days=None,
            contract_expiry_date=None,
            actual_start_date=old.actual_start_date,
            actual_completion_date=None,
        )

        fund_source = None
        fund_name = (old.source_of_fund or '').strip()
        if fund_name:
            fund_source, _ = FundSource.objects.get_or_create(
                fund_source_name=fund_name,
                defaults={'fund_source_code': 'legacy-fund-source', 'description': fund_name, 'is_active': True},
            )

        Financial.objects.create(
            infrastructure=infra,
            fund_source=fund_source,
            approved_budget=old.abc_amount,
            bid_amount=old.contract_price,
            actual_expenditure=0.00,
            is_visible_to_public=bool(old.is_public),
        )

        inspection_date = old.actual_start_date or old.planned_end_date or old.created_at.date() if hasattr(old, 'created_at') else None
        if inspection_date:
            completion = old.physical_progress_percentage or old.cost_progress_percentage or 0
            Project_Inspection.objects.create(
                project=infra.project,
                inspection_date=inspection_date,
                inspected_by_user=old.updated_by or old.created_by,
                completion_percentage=completion,
                findings='',
                remarks='Migrated from legacy infrastructure project record.',
            )


def reverse_migration(apps, schema_editor):
    Infrastructure_Schedule = apps.get_model('system', 'Infrastructure_Schedule')
    Financial = apps.get_model('system', 'Financial')
    Project_Inspection = apps.get_model('system', 'Project_Inspection')
    Infrastructure_Schedule.objects.all().delete()
    Financial.objects.all().delete()
    Project_Inspection.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('system', '0010_financial_infrastructure_schedule_project_inspection'),
        ('infrastructure', '0005_infrastructureproject_description_infrastructureproject_latitude_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_infrastructure_details, reverse_code=reverse_migration),
    ]
