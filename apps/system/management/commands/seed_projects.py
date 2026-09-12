from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.system.models import (
    Address,
    Contractor,
    Financial,
    FundSource,
    ImplementingOffice,
    InfrastructureCategory,
    Infrastructure_Project,
    Infrastructure_Schedule,
    NonInfrastructureCategory,
    Non_Infrastructure_Project,
    Project,
    UserFlag,
)
from apps.system.publication_service import (
    publish_publication_revision,
    review_publication_revision,
    submit_project_for_review,
)
from apps.system.publication_workflow import PublicationStatus


SEED_USERNAMES = {
    'engineer': 'seed_projects_engineer',
    'mayor': 'seed_projects_mayor',
    'admin': 'seed_projects_admin',
}
SEED_POSTAL_MARKER = 'SEED-DATA'

BARANGAYS = [
    'Bagong Sikat',
    'Baterya',
    'Cuyapa',
    'Ligaya',
    'Macasandal',
    'Malinao',
    'Pantoc',
    'Pinamalisan',
    'Sawmill',
    'South Poblacion',
    'Tagumpay',
    'North Poblacion',
    'Bugnan',
    'Calabasa',
    'Camachile',
    'Dimanpudso',
]

INFRA_TITLES = [
    'Barangay Road Rehabilitation and Drainage Improvement',
    'Farm-to-Market Road Concreting Project',
    'Municipal Water Supply Line Improvement',
    'Multi-Purpose Evacuation Center Construction',
    'Flood Control and Creek Protection Works',
    'Barangay Bridge Rehabilitation Project',
    'Public Market Access Road Improvement',
    'Rural Health Center Building Improvement',
    'Street Drainage Rehabilitation Project',
    'Municipal Covered Court Improvement',
    'Slope Protection and Road Safety Improvement',
    'Local Government Facility Rehabilitation',
]

NON_INFRA_TITLES = [
    'Community Health and Wellness Outreach Program',
    'Educational Assistance and School Support Program',
    'Senior Citizens Social Support Activity',
    'Youth Sports Development Program',
    'Barangay Clean-Up and Environmental Awareness Drive',
    'Livelihood Skills Training for Local Residents',
    'Nutrition and Feeding Program for Children',
    'Disaster Preparedness and Community Orientation',
    'Women Empowerment and Skills Development Seminar',
    'Agricultural Information and Farmer Support Program',
    'Cultural Heritage and Community Arts Activity',
    'Digital Literacy Training for Residents',
]

CONTRACTOR_NAMES = [
    'Gabaldon Builders and Construction Services',
    'Sierra Madre Construction and Trading',
    'Nueva Ecija Development Builders',
    'Central Luzon General Construction',
]

FUND_SOURCES = [
    ('GF', 'General Fund'),
    ('LDF', '20% Local Development Fund'),
    ('NGA', 'National Government Assistance'),
    ('SEF', 'Special Education Fund'),
]

INFRA_CATEGORY_FALLBACKS = [
    ('road', 'Road Construction / Rehabilitation'),
    ('water', 'Water System'),
    ('building', 'Public Building'),
    ('flood_control', 'Flood Control'),
    ('bridge', 'Bridge'),
]

NON_INFRA_CATEGORY_FALLBACKS = [
    ('health', 'Health'),
    ('education', 'Education'),
    ('social_services', 'Social Services'),
    ('environment', 'Environment'),
    ('sports', 'Sports'),
]


class Command(BaseCommand):
    help = (
        'Create realistic normalized infrastructure and non-infrastructure '
        'test projects. Seeded records can be safely removed with --clear.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--infra',
            type=int,
            default=None,
            metavar='N',
            help='Number of infrastructure projects to create (default: 10).',
        )
        parser.add_argument(
            '--non-infra',
            dest='non_infra',
            type=int,
            default=None,
            metavar='N',
            help='Number of non-infrastructure projects to create (default: 10).',
        )
        parser.add_argument(
            '--publish',
            action='store_true',
            help=(
                'Submit, approve, and publish every generated project through '
                'the real publication workflow.'
            ),
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help=(
                'Delete only records created by this command. When used alone, '
                'no new projects are created.'
            ),
        )

    def handle(self, *args, **options):
        infra_requested = options['infra']
        non_infra_requested = options['non_infra']
        clear_requested = options['clear']
        publish_requested = options['publish']

        for label, value in (
            ('--infra', infra_requested),
            ('--non-infra', non_infra_requested),
        ):
            if value is not None and value < 0:
                raise CommandError(f'{label} cannot be negative.')

        if clear_requested:
            self._clear_seed_data()
            if infra_requested is None and non_infra_requested is None:
                return
            infra_count = infra_requested or 0
            non_infra_count = non_infra_requested or 0
        else:
            infra_count = 10 if infra_requested is None else infra_requested
            non_infra_count = (
                10 if non_infra_requested is None else non_infra_requested
            )

        if infra_count == 0 and non_infra_count == 0:
            self.stdout.write(self.style.WARNING('No projects requested.'))
            return

        with transaction.atomic():
            actors = self._get_seed_actors()
            infra_categories = self._get_infrastructure_categories()
            non_infra_categories = self._get_non_infrastructure_categories()
            office = self._get_implementing_office()
            contractors = self._get_contractors()
            fund_sources = self._get_fund_sources()

            infrastructure_projects = [
                self._create_infrastructure_project(
                    index=index,
                    actor=actors['engineer'],
                    categories=infra_categories,
                    office=office,
                    contractors=contractors,
                    fund_sources=fund_sources,
                )
                for index in range(infra_count)
            ]

            non_infrastructure_projects = [
                self._create_non_infrastructure_project(
                    index=index,
                    actor=actors['mayor'],
                    categories=non_infra_categories,
                )
                for index in range(non_infra_count)
            ]

            if publish_requested:
                for project in infrastructure_projects:
                    self._publish_project(
                        project,
                        employee=actors['engineer'],
                        admin=actors['admin'],
                    )
                for project in non_infrastructure_projects:
                    self._publish_project(
                        project,
                        employee=actors['mayor'],
                        admin=actors['admin'],
                    )

        visibility = 'published' if publish_requested else 'working/draft'
        self.stdout.write(
            self.style.SUCCESS(
                f'Created {infra_count} infrastructure and '
                f'{non_infra_count} non-infrastructure projects ({visibility}).'
            )
        )
        if not publish_requested:
            self.stdout.write(
                'They remain off the public dashboard until submitted and '
                'published through the approval workflow.'
            )

    def _get_seed_actors(self):
        engineer = self._seed_user(
            username=SEED_USERNAMES['engineer'],
            first_name='Seed',
            last_name='Engineering Office',
            department='engineer',
        )
        mayor = self._seed_user(
            username=SEED_USERNAMES['mayor'],
            first_name='Seed',
            last_name="Mayor's Office",
            department='mayor',
        )
        admin = self._seed_user(
            username=SEED_USERNAMES['admin'],
            first_name='Seed',
            last_name='Administrator',
            department='admin',
            is_superuser=True,
            is_staff=True,
        )
        return {'engineer': engineer, 'mayor': mayor, 'admin': admin}

    def _seed_user(
        self,
        *,
        username,
        first_name,
        last_name,
        department,
        is_superuser=False,
        is_staff=False,
    ):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'first_name': first_name,
                'last_name': last_name,
                'is_active': True,
                'is_superuser': is_superuser,
                'is_staff': is_staff,
            },
        )
        changed_fields = []
        desired = {
            'first_name': first_name,
            'last_name': last_name,
            'is_active': True,
            'is_superuser': is_superuser,
            'is_staff': is_staff,
        }
        for field, value in desired.items():
            if getattr(user, field) != value:
                setattr(user, field, value)
                changed_fields.append(field)
        if created or user.has_usable_password():
            user.set_unusable_password()
            changed_fields.append('password')
        if changed_fields:
            user.save(update_fields=list(dict.fromkeys(changed_fields)))

        UserFlag.objects.update_or_create(
            user=user,
            defaults={
                'department': department,
            },
        )
        return user

    def _get_infrastructure_categories(self):
        categories = list(
            InfrastructureCategory.objects.filter(is_active=True).order_by(
                'infrastructure_category_id'
            )
        )
        if categories:
            return categories

        result = []
        for code, name in INFRA_CATEGORY_FALLBACKS:
            category, _ = InfrastructureCategory.objects.get_or_create(
                category_code=code,
                defaults={'category_name': name, 'is_active': True},
            )
            result.append(category)
        return result

    def _get_non_infrastructure_categories(self):
        categories = list(
            NonInfrastructureCategory.objects.order_by(
                'non_infrastructure_category_id'
            )
        )
        if categories:
            return categories

        result = []
        for code, name in NON_INFRA_CATEGORY_FALLBACKS:
            category, _ = NonInfrastructureCategory.objects.get_or_create(
                type_code=code,
                defaults={'type_name': name},
            )
            result.append(category)
        return result

    def _get_implementing_office(self):
        office = ImplementingOffice.objects.filter(
            office_name__iexact='Municipal Engineering Office'
        ).first()
        if office:
            return office
        return ImplementingOffice.objects.create(
            office_name='Municipal Engineering Office',
            is_active=True,
        )

    def _get_contractors(self):
        contractors = []
        for name in CONTRACTOR_NAMES:
            contractor = Contractor.objects.filter(
                contractor_name__iexact=name
            ).first()
            if contractor is None:
                contractor = Contractor.objects.create(
                    contractor_name=name,
                    is_active=True,
                )
            contractors.append(contractor)
        return contractors

    def _get_fund_sources(self):
        sources = []
        for code, name in FUND_SOURCES:
            source = FundSource.objects.filter(
                fund_source_name__iexact=name
            ).first()
            if source is None:
                source = FundSource.objects.filter(
                    fund_source_code__iexact=code
                ).first()
            if source is None:
                source = FundSource.objects.create(
                    fund_source_code=code,
                    fund_source_name=name,
                    is_active=True,
                )
            sources.append(source)
        return sources

    def _address(self, index):
        barangay = BARANGAYS[index % len(BARANGAYS)]
        latitude = Decimal('15.2915000') + Decimal(index % 8) * Decimal('0.0021000')
        longitude = Decimal('121.3386000') + Decimal(index % 7) * Decimal('0.0023000')
        return Address.objects.create(
            street=f'Purok {(index % 6) + 1}',
            barangay=barangay,
            municipality='Gabaldon',
            province='Nueva Ecija',
            country='Philippines',
            postal_code=SEED_POSTAL_MARKER,
            latitude=latitude,
            longitude=longitude,
            is_active=True,
        )

    def _title(self, titles, index):
        base = titles[index % len(titles)]
        batch = index // len(titles)
        return base if batch == 0 else f'{base} - Demo {batch + 1}'

    def _create_infrastructure_project(
        self,
        *,
        index,
        actor,
        categories,
        office,
        contractors,
        fund_sources,
    ):
        project = Project.objects.create(
            project_type='infrastructure',
            created_by_user=actor,
            updated_by_user=actor,
            is_published=False,
            is_visible_to_public=False,
        )
        start_date = date(2026, 1, 15) + timedelta(days=index * 18)
        duration = 120 + (index % 5) * 30
        end_date = start_date + timedelta(days=duration)
        statuses = ['awarded', 'ongoing_bidding', 'completed', 'rebid', 'cancelled']
        status = statuses[index % len(statuses)]
        progress_by_status = {
            'awarded': Decimal('25.00') + Decimal(index % 4) * Decimal('10.00'),
            'ongoing_bidding': Decimal('0.00'),
            'completed': Decimal('100.00'),
            'rebid': Decimal('0.00'),
            'cancelled': Decimal('0.00'),
        }
        progress = progress_by_status[status]

        infrastructure = Infrastructure_Project.objects.create(
            project=project,
            infrastructure_code=f'SEED-INF-{project.pk:06d}',
            infrastructure_title=self._title(INFRA_TITLES, index),
            infrastructure_description=(
                'Municipal infrastructure test record generated for development '
                'and workflow verification. Includes normalized location, '
                'procurement, schedule, and financial information.'
            ),
            category=categories[index % len(categories)],
            address=self._address(index),
            contractor=contractors[index % len(contractors)],
            implementing_office=office,
            procurement_method=(
                Infrastructure_Project.PROCUREMENT_METHOD_CHOICES[
                    index % len(Infrastructure_Project.PROCUREMENT_METHOD_CHOICES)
                ][0]
            ),
            award_status=status,
            planned_start_date=start_date,
            planned_end_date=end_date,
            cost_progress_percentage=progress,
            physical_progress_percentage=progress,
        )

        approved_budget = Decimal('1500000.00') + Decimal(index) * Decimal('375000.00')
        bid_amount = approved_budget * Decimal('0.94')
        actual_expenditure = (
            bid_amount
            if status == 'completed'
            else (bid_amount * progress / Decimal('100.00'))
        )
        Financial.objects.create(
            infrastructure=infrastructure,
            fund_source=fund_sources[index % len(fund_sources)],
            approved_budget=approved_budget,
            bid_amount=bid_amount,
            actual_expenditure=actual_expenditure.quantize(Decimal('0.01')),
            is_visible_to_public=False,
        )

        posting_date = start_date - timedelta(days=60)
        actual_start = start_date if status in {'awarded', 'completed'} else None
        actual_completion = end_date if status == 'completed' else None
        Infrastructure_Schedule.objects.create(
            infrastructure=infrastructure,
            posting_date=posting_date,
            pre_bid_date=posting_date + timedelta(days=14),
            bidding_date=posting_date + timedelta(days=28),
            notice_award_date=posting_date + timedelta(days=42),
            notice_proceed_date=posting_date + timedelta(days=52),
            duration_days=duration,
            contract_expiry_date=end_date,
            actual_start_date=actual_start,
            actual_completion_date=actual_completion,
        )
        return project

    def _create_non_infrastructure_project(self, *, index, actor, categories):
        project = Project.objects.create(
            project_type='non_infrastructure',
            created_by_user=actor,
            updated_by_user=actor,
            is_published=False,
            is_visible_to_public=False,
        )
        statuses = ['planned', 'ongoing', 'completed']
        event_date = date(2026, 8, 25) + timedelta(days=index * 12)
        Non_Infrastructure_Project.objects.create(
            project=project,
            non_infra_name=self._title(NON_INFRA_TITLES, index),
            non_infra_category=categories[index % len(categories)],
            status=statuses[index % len(statuses)],
            proponent=(
                "Mayor's Office" if index % 2 == 0 else 'Municipal Social Services Office'
            ),
            beneficiaries=50 + (index * 25),
            event_date=event_date,
            start_time=time(8 + (index % 2), 0),
            end_time=time(15 + (index % 2), 30),
            venue_name=(
                f'{BARANGAYS[index % len(BARANGAYS)]} Barangay Hall'
            ),
            address=self._address(index + 100),
            description=(
                'Municipal non-infrastructure test record generated for '
                'development and publication workflow verification. The record '
                'contains realistic program scheduling, beneficiary, location, '
                'and category data.'
            ),
        )
        return project

    def _publish_project(self, project, *, employee, admin):
        revision = submit_project_for_review(project, employee)
        revision = review_publication_revision(
            revision,
            admin,
            PublicationStatus.APPROVED,
            notes='Automatically approved by seed_projects for test data.',
        )
        publish_publication_revision(revision, admin)

    def _clear_seed_data(self):
        seed_users = User.objects.filter(username__in=SEED_USERNAMES.values())
        seeded_projects = Project.objects.filter(created_by_user__in=seed_users)
        project_count = seeded_projects.count()
        address_ids = set(
            Address.objects.filter(postal_code=SEED_POSTAL_MARKER).values_list(
                'pk', flat=True
            )
        )

        with transaction.atomic():
            seeded_projects.delete()
            if address_ids:
                Address.objects.filter(pk__in=address_ids).delete()
            seed_users.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f'Removed {project_count} seeded project(s) and their seed users.'
            )
        )
