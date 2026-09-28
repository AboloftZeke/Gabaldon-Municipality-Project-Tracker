"""Import the accompanying fictional CSV rows into a development Django DB.

Place this script and the two CSV files in the repository root, then run:
    python import_gabaldon_samples.py
For a local SQLite database (the repository's SQLite settings):
    python import_gabaldon_samples.py --settings config.test_settings
"""

import argparse
import csv
import os
import sys
from datetime import date, time
from decimal import Decimal
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--settings', default='config.settings',
                    help='Django settings module (default: config.settings / PostgreSQL)')
parser.add_argument('--repo', type=Path, default=Path.cwd(),
                    help='Repository root; default is the current directory')
args = parser.parse_args()
ROOT = Path(__file__).resolve().parent
REPO = args.repo.resolve()
sys.path.insert(0, str(REPO))
os.environ['DJANGO_SETTINGS_MODULE'] = args.settings

import django  # noqa: E402
django.setup()

from django.contrib.auth.models import User  # noqa: E402
from django.conf import settings  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import transaction  # noqa: E402
from apps.system.models import (  # noqa: E402
    Address, Contractor, FinancialRecord, FundSource, ImplementingOffice,
    InfrastructureCategory, InfrastructureProject, InfrastructureSchedule,
    NonInfrastructureCategory, NonInfrastructureProject, Project, UserRole,
)


def rows(name):
    with (ROOT / name).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def optional_date(raw):
    return date.fromisoformat(raw) if raw else None


def optional_time(raw):
    return time.fromisoformat(raw) if raw else None


def staff(username, department):
    user, created = User.objects.get_or_create(
        username=username,
        defaults={'first_name': 'Demo', 'last_name': department.title(), 'is_active': True},
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=['password'])
    elif user.has_usable_password():
        raise RuntimeError(f'Refusing to reuse existing login account: {username}')
    UserRole.objects.update_or_create(
        user=user, defaults={'department': department, 'role': UserRole.Role.STAFF},
    )
    return user


def address(row, *, infra):
    return Address.objects.create(
        street=row['street'],
        barangay=row['barangay'] if infra else BARANGAY_NAMES[row['barangay']],
        municipality=row['municipality'], province=row['province'],
        country='Philippines', postal_code='DEMO-CSV',
        latitude=Decimal(row['latitude']) if infra and row['latitude'] else None,
        longitude=Decimal(row['longitude']) if infra and row['longitude'] else None,
    )


BARANGAY_NAMES = {
    'bagting': 'Bagting', 'bantug': 'Bantug', 'bugnan': 'Bugnan',
    'calabasa': 'Calabasa', 'camachile': 'Camachile', 'cuyapa': 'Cuyapa',
    'ligaya': 'Ligaya', 'macasandal': 'Macasandal', 'malinao': 'Malinao',
    'pantoc': 'Pantoc',
}


def create_infra(row, actor):
    if InfrastructureProject.objects.filter(title=row['title']).exists():
        return False
    category = InfrastructureCategory.objects.get(category_code=row['category_code'])
    contractor, _ = Contractor.objects.get_or_create(contractor_name=row['contractor'])
    office, _ = ImplementingOffice.objects.get_or_create(office_name=row['implementing_office'])
    source, _ = FundSource.objects.get_or_create(
        fund_source_name=row['fund_source'],
        defaults={'fund_source_code': 'csv_demo_' + str(FundSource.objects.count() + 1)},
    )
    project = Project.objects.create(
        project_type='infrastructure', created_by_user=actor, updated_by_user=actor,
        is_published=False, is_visible_to_public=False,
    )
    infra = InfrastructureProject(
        project=project, title=row['title'], description=row['description'],
        category=category, address=address(row, infra=True), contractor=contractor,
        implementing_office=office, procurement_method=row['procurement_method'],
        planned_start_date=optional_date(row['planned_start_date']),
        planned_end_date=optional_date(row['planned_end_date']),
        # Staff creation does not assign the Head-controlled official status.
    )
    infra.full_clean()
    infra.save()
    schedule = InfrastructureSchedule(
        infrastructure=infra,
        posting_date=optional_date(row['posting_date']),
        pre_bid_date=optional_date(row['pre_bid_date']),
        bidding_date=optional_date(row['bidding_date']),
        notice_award_date=optional_date(row['notice_award_date']),
        notice_proceed_date=optional_date(row['notice_to_proceed_date']),
        duration_days=int(row['duration_days']),
    )
    schedule.full_clean()
    schedule.save()
    financial = FinancialRecord(
        infrastructure=infra, fund_source=source,
        approved_budget=Decimal(row['abc_amount']), bid_amount=Decimal(row['contract_price']),
        # This field is non-nullable; 0.00 is the model's initial default, not a spending claim.
        actual_expenditure=Decimal(row['actual_expenditure'] or '0.00'),
        is_visible_to_public=False,
    )
    financial.full_clean()
    financial.save()
    return True


def create_noninfra(row, actor):
    if NonInfrastructureProject.objects.filter(title=row['title']).exists():
        return False
    category = NonInfrastructureCategory.objects.get(type_code=row['category_type_code'])
    project = Project.objects.create(
        project_type='non_infrastructure', created_by_user=actor, updated_by_user=actor,
        is_published=False, is_visible_to_public=False,
    )
    non = NonInfrastructureProject(
        project=project, title=row['title'], description=row['description'],
        category=category, project_type=row['project_type'],
        proponent=row['proponent'], target_beneficiaries=row['target_beneficiaries'],
        beneficiaries=int(row['beneficiaries']),
        implementation_start_date=optional_date(row['implementation_start_date']),
        implementation_end_date=optional_date(row['implementation_end_date']),
        event_date=optional_date(row['event_date']),
        start_time=optional_time(row['start_time']),
        end_time=optional_time(row['end_time']), venue_name=row['venue_name'],
        project_cost=Decimal(row['project_cost']), fund_source=row['fund_source'],
        contractor_supplier=row['contractor_supplier'],
        procurement_description=row['procurement_description'],
        quantity=int(row['quantity']) if row['quantity'] else None,
        expected_delivery_date=optional_date(row['expected_delivery_date']),
        remarks=row['remarks'], address=address(row, infra=False),
    )
    non.full_clean()
    non.save()
    return True


def main():
    if not settings.DEBUG:
        raise RuntimeError('This importer is for local development only (DEBUG must be true).')
    call_command('check', verbosity=0)
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
    print('Target database:', settings.DATABASES['default']['ENGINE'],
          settings.DATABASES['default']['NAME'])
    infra_rows = rows('Gabaldon_Infrastructure_Sample_10.csv')
    non_rows = rows('Gabaldon_NonInfrastructure_Sample_10.csv')
    if len(infra_rows) != 10 or len(non_rows) != 10:
        raise RuntimeError('Expected exactly 10 examples for each project type.')
    with transaction.atomic():
        engineer = staff('csv_demo_engineering_staff', 'engineer')
        mayor = staff('csv_demo_mayor_staff', 'mayor')
        created_infra = sum(create_infra(row, engineer) for row in infra_rows)
        created_non = sum(create_noninfra(row, mayor) for row in non_rows)
    print(f'Created {created_infra} infrastructure and {created_non} non-infrastructure records.')
    print('Current demo counts:', InfrastructureProject.objects.filter(title__startswith='Demo —').count(),
          NonInfrastructureProject.objects.filter(title__startswith='Demo —').count())
    print('Public revisions:', Project.objects.filter(is_published=True).count())


if __name__ == '__main__':
    main()
