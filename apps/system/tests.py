import json
from datetime import date, time
from decimal import Decimal

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.contrib.auth.models import User
from .forms import CustomUserCreationForm
from .models import (
    Address,
    Contractor,
    Financial,
    FundSource,
    ImplementingOffice,
    InfrastructureCategory,
    Infrastructure_Schedule,
    Infrastructure_Project,
    NonInfrastructureCategory,
    Non_Infrastructure_Project,
    Project,
    Project_Image,
    Project_Inspection,
    ProjectPublicationRevision,
    UserProfile,
)
from .publication_workflow import (
    PublicationStatus,
    available_publication_transitions,
    can_transition_publication,
    validate_publication_transition,
)
from .publication_snapshots import build_project_publication_snapshot
from .publication_images import retire_project_images


class PublicationWorkflowTests(TestCase):
    def test_workflow_exposes_expected_review_path(self):
        self.assertEqual(
            available_publication_transitions(PublicationStatus.DRAFT),
            frozenset({PublicationStatus.PENDING_REVIEW}),
        )
        self.assertEqual(
            available_publication_transitions(
                PublicationStatus.PENDING_REVIEW,
            ),
            frozenset({
                PublicationStatus.APPROVED,
                PublicationStatus.NEEDS_REVISION,
                PublicationStatus.REJECTED,
            }),
        )
        self.assertTrue(can_transition_publication('approved', 'published'))
        self.assertTrue(can_transition_publication('published', 'archived'))

    def test_workflow_rejects_skipping_review(self):
        self.assertFalse(can_transition_publication('draft', 'published'))

        with self.assertRaisesMessage(
            ValidationError,
            'Publication status cannot change from Draft to Published.',
        ):
            validate_publication_transition('draft', 'published')

    def test_terminal_states_have_no_transitions(self):
        self.assertEqual(
            available_publication_transitions(PublicationStatus.REJECTED),
            frozenset(),
        )
        self.assertEqual(
            available_publication_transitions(PublicationStatus.ARCHIVED),
            frozenset(),
        )

    def test_unknown_states_are_rejected(self):
        self.assertFalse(can_transition_publication('unknown', 'published'))

        with self.assertRaisesMessage(
            ValidationError,
            'Unknown publication workflow status.',
        ):
            validate_publication_transition('draft', 'unknown')


class ProjectPublicationRevisionModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='publication-reviewer',
            password='password123',
        )
        self.project = Project.objects.create(
            project_type='infrastructure',
            created_by_user=self.user,
            updated_by_user=self.user,
        )

    def test_revision_stores_snapshot_and_defaults_to_draft(self):
        revision = ProjectPublicationRevision.objects.create(
            project=self.project,
            revision_number=1,
            snapshot_data={'title': 'Barangay Road Project'},
        )

        self.assertEqual(revision.status, PublicationStatus.DRAFT)
        self.assertEqual(
            revision.snapshot_data,
            {'title': 'Barangay Road Project'},
        )
        self.assertFalse(revision.is_current_public_revision)
        self.assertEqual(
            str(revision),
            f'Project {self.project.pk} publication revision 1',
        )

    def test_revision_number_is_unique_within_project(self):
        ProjectPublicationRevision.objects.create(
            project=self.project,
            revision_number=1,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectPublicationRevision.objects.create(
                project=self.project,
                revision_number=1,
            )

    def test_project_can_have_only_one_current_public_revision(self):
        first_revision = ProjectPublicationRevision.objects.create(
            project=self.project,
            revision_number=1,
            status=PublicationStatus.PUBLISHED,
            is_current_public_revision=True,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectPublicationRevision.objects.create(
                project=self.project,
                revision_number=2,
                status=PublicationStatus.PUBLISHED,
                is_current_public_revision=True,
                supersedes_revision=first_revision,
            )

    def test_current_public_revision_must_be_published(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectPublicationRevision.objects.create(
                project=self.project,
                revision_number=1,
                status=PublicationStatus.DRAFT,
                is_current_public_revision=True,
            )

    def test_revision_can_reference_the_version_it_supersedes(self):
        first_revision = ProjectPublicationRevision.objects.create(
            project=self.project,
            revision_number=1,
        )
        second_revision = ProjectPublicationRevision.objects.create(
            project=self.project,
            revision_number=2,
            supersedes_revision=first_revision,
        )

        self.assertEqual(second_revision.supersedes_revision, first_revision)
        self.assertIn(
            second_revision,
            first_revision.superseded_by_revisions.all(),
        )


class ProjectPublicationSnapshotTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='snapshot-author',
            first_name='Snapshot',
            last_name='Author',
            password='password123',
        )

    def test_builds_complete_json_safe_infrastructure_snapshot(self):
        project = Project.objects.create(
            project_type='infrastructure',
            created_by_user=self.user,
            updated_by_user=self.user,
        )
        category = InfrastructureCategory.objects.create(
            category_code='roads',
            category_name='Roads',
        )
        address = Address.objects.create(
            street='Rizal Street',
            barangay='Bagting',
            municipality='Gabaldon',
            province='Nueva Ecija',
            latitude=Decimal('15.2915000'),
            longitude=Decimal('121.3386000'),
        )
        contractor = Contractor.objects.create(
            contractor_name='Road Builder Inc.',
        )
        office = ImplementingOffice.objects.create(
            office_name='Municipal Engineering Office',
        )
        infrastructure = Infrastructure_Project.objects.create(
            project=project,
            infrastructure_code='INF-001',
            infrastructure_title='Barangay Road Rehabilitation',
            infrastructure_description='Rehabilitation description.',
            category=category,
            address=address,
            contractor=contractor,
            implementing_office=office,
            procurement_method='competitive_bidding',
            award_status='awarded',
            planned_start_date=date(2026, 1, 15),
            planned_end_date=date(2026, 8, 30),
            cost_progress_percentage=Decimal('42.50'),
            physical_progress_percentage=Decimal('55.25'),
        )
        fund_source = FundSource.objects.create(
            fund_source_code='ldf',
            fund_source_name='Local Development Fund',
            fund_percentage=Decimal('20.00'),
        )
        Financial.objects.create(
            infrastructure=infrastructure,
            fund_source=fund_source,
            approved_budget=Decimal('2500000.00'),
            bid_amount=Decimal('2400000.00'),
            actual_expenditure=Decimal('500000.00'),
        )
        Infrastructure_Schedule.objects.create(
            infrastructure=infrastructure,
            posting_date=date(2025, 12, 1),
            actual_start_date=date(2026, 1, 20),
            duration_days=180,
        )
        Project_Inspection.objects.create(
            project=project,
            inspection_date=date(2026, 4, 15),
            inspected_by_user=self.user,
            completion_percentage=Decimal('55.25'),
            findings='Work is on schedule.',
        )
        Project_Image.objects.create(
            project=project,
            image_url='/media/projects/road-cover.jpg',
            is_cover=True,
        )
        Project_Image.objects.create(
            project=project,
            image_url='/media/projects/road-progress.jpg',
        )

        snapshot = build_project_publication_snapshot(project)

        self.assertEqual(snapshot['schema_version'], 1)
        self.assertEqual(
            snapshot['infrastructure']['title'],
            'Barangay Road Rehabilitation',
        )
        self.assertEqual(
            snapshot['infrastructure']['category']['name'],
            'Roads',
        )
        self.assertEqual(
            snapshot['infrastructure']['address']['latitude'],
            '15.2915000',
        )
        self.assertEqual(
            snapshot['financial']['approved_budget'],
            '2500000.00',
        )
        self.assertEqual(snapshot['schedule']['duration_days'], 180)
        self.assertEqual(
            snapshot['inspection']['completion_percentage'],
            '55.25',
        )
        self.assertEqual(
            snapshot['project']['cover_image_url'],
            '/media/projects/road-cover.jpg',
        )
        self.assertEqual(len(snapshot['images']), 2)
        json.dumps(snapshot)

    def test_builds_complete_json_safe_non_infrastructure_snapshot(self):
        project = Project.objects.create(
            project_type='non_infrastructure',
            created_by_user=self.user,
            updated_by_user=self.user,
        )
        category = NonInfrastructureCategory.objects.create(
            type_code='health',
            type_name='Health Program',
        )
        address = Address.objects.create(
            barangay='South Poblacion',
            municipality='Gabaldon',
            province='Nueva Ecija',
        )
        non_infrastructure = Non_Infrastructure_Project.objects.create(
            project=project,
            non_infra_name='Community Health Day',
            non_infra_category=category,
            status='planned',
            description='Free health services.',
            proponent='Municipal Health Office',
            beneficiaries=250,
            event_date=date(2026, 9, 1),
            start_time=time(8, 30),
            end_time=time(16, 0),
            venue_name='Municipal Gymnasium',
            address=address,
        )
        Project_Image.objects.create(
            project=project,
            image_url='/media/projects/health-cover.jpg',
            is_cover=True,
        )

        snapshot = build_project_publication_snapshot(project)

        content = snapshot['non_infrastructure']
        self.assertEqual(content['id'], non_infrastructure.pk)
        self.assertEqual(content['code'], f'NINF-{non_infrastructure.pk:05d}')
        self.assertEqual(content['title'], 'Community Health Day')
        self.assertEqual(content['category']['name'], 'Health Program')
        self.assertEqual(content['status_label'], 'Planned')
        self.assertEqual(content['event_date'], '2026-09-01')
        self.assertEqual(content['start_time'], '08:30:00')
        self.assertEqual(content['beneficiaries'], 250)
        self.assertEqual(
            snapshot['project']['cover_image_url'],
            '/media/projects/health-cover.jpg',
        )
        json.dumps(snapshot)

    def test_rejects_unsupported_project_types(self):
        project = Project.objects.create(project_type='gallery')

        with self.assertRaisesMessage(
            ValueError,
            "Unsupported project type: 'gallery'.",
        ):
            build_project_publication_snapshot(project)


class ProjectPublicationImageRetentionTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(project_type='infrastructure')
        self.infrastructure = Infrastructure_Project.objects.create(
            project=self.project,
            infrastructure_title='Image Retention Project',
        )

    def test_revision_referenced_image_is_retired_not_deleted(self):
        image = Project_Image.objects.create(
            project=self.project,
            image_url='/media/projects/published-cover.jpg',
            is_cover=True,
        )
        ProjectPublicationRevision.objects.create(
            project=self.project,
            revision_number=1,
            snapshot_data={
                'images': [{
                    'id': image.pk,
                    'url': image.image_url,
                    'is_cover': True,
                }],
            },
        )

        result = retire_project_images(self.project, [image.pk])

        self.assertEqual(result, {'retired': 1, 'deleted': 0})
        self.assertFalse(Project_Image.objects.filter(pk=image.pk).exists())
        retained = Project_Image.all_objects.get(pk=image.pk)
        self.assertFalse(retained.is_active)
        self.assertFalse(retained.is_cover)
        self.assertIsNotNone(retained.removed_at)
        self.assertEqual(
            retained.image_url,
            '/media/projects/published-cover.jpg',
        )

    def test_unreferenced_image_metadata_is_deleted(self):
        image = Project_Image.objects.create(
            project=self.project,
            image_url='/media/projects/unused.jpg',
        )

        result = retire_project_images(self.project, [image.pk])

        self.assertEqual(result, {'retired': 0, 'deleted': 1})
        self.assertFalse(
            Project_Image.all_objects.filter(pk=image.pk).exists(),
        )

    def test_new_snapshots_exclude_retired_images(self):
        retained_image = Project_Image.objects.create(
            project=self.project,
            image_url='/media/projects/old-version.jpg',
        )
        active_image = Project_Image.objects.create(
            project=self.project,
            image_url='/media/projects/current-version.jpg',
            is_cover=True,
        )
        ProjectPublicationRevision.objects.create(
            project=self.project,
            revision_number=1,
            snapshot_data={
                'images': [{
                    'id': retained_image.pk,
                    'url': retained_image.image_url,
                }],
            },
        )
        retire_project_images(self.project, [retained_image.pk])

        snapshot = build_project_publication_snapshot(self.project)

        self.assertEqual(
            [image['url'] for image in snapshot['images']],
            ['/media/projects/current-version.jpg'],
        )


class PublicDashboardInfrastructureDataSourceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='infrastructure-dashboard-author',
            password='password123',
        )
        base_project = Project.objects.create(
            project_type='infrastructure',
            created_by_user=self.user,
            updated_by_user=self.user,
        )
        category = InfrastructureCategory.objects.create(
            category_code='road-test',
            category_name='Road Test',
        )
        address = Address.objects.create(
            barangay='Bagting',
            municipality='Gabaldon',
            province='Nueva Ecija',
            latitude='15.2915000',
            longitude='121.3386000',
        )
        contractor = Contractor.objects.create(
            contractor_name='Public Works Contractor',
        )
        office = ImplementingOffice.objects.create(
            office_name='Municipal Engineering Office',
        )
        fund_source = FundSource.objects.create(
            fund_source_code='local-test',
            fund_source_name='Local Development Fund',
        )
        self.infrastructure = Infrastructure_Project.objects.create(
            project=base_project,
            infrastructure_title='Normalized Road Project',
            infrastructure_description='Connected through normalized data.',
            category=category,
            address=address,
            contractor=contractor,
            implementing_office=office,
            procurement_method='competitive_bidding',
            award_status='awarded',
            planned_start_date='2026-01-15',
            planned_end_date='2026-08-30',
            cost_progress_percentage=42,
            physical_progress_percentage=55,
        )
        Financial.objects.create(
            infrastructure=self.infrastructure,
            fund_source=fund_source,
            approved_budget=2500000,
            bid_amount=2400000,
        )
        Infrastructure_Schedule.objects.create(
            infrastructure=self.infrastructure,
            actual_start_date='2026-01-20',
        )
        Project_Image.objects.create(
            project=base_project,
            image_url='/media/projects/infrastructure-cover.jpg',
            is_cover=True,
        )

    def test_public_dashboard_reads_normalized_infrastructure_relations(self):
        response = self.client.get(reverse('public_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['infra_total'], 1)
        self.assertEqual(response.context['total_budget'], 2500000)
        self.assertEqual(response.context['ongoing_projects'], 1)
        self.assertEqual(response.context['completed_projects'], 0)
        self.assertIn(
            ('infra:road-test', 'Road Test'),
            response.context['project_categories'],
        )
        self.assertIn(
            ('bagting', 'Bagting'),
            response.context['location_options'],
        )
        self.assertIn(
            ('bagong_sikat', 'Bagong Sikat'),
            response.context['location_options'],
        )

        row = next(
            row for row in response.context['project_rows']
            if row['category'] == 'infra'
        )
        self.assertEqual(row['record_id'], f'infra-{self.infrastructure.pk}')
        self.assertEqual(row['title'], 'Normalized Road Project')
        self.assertEqual(row['status_key'], 'ongoing')
        self.assertEqual(row['status_label'], 'Awarded')
        self.assertEqual(row['project_category_key'], 'infra:road-test')
        self.assertEqual(row['location_key'], 'bagting')
        self.assertEqual(row['category_label'], 'Road Test')
        self.assertEqual(row['location'], 'Bagting')
        self.assertEqual(row['office'], 'Municipal Engineering Office')
        self.assertEqual(row['contractor'], 'Public Works Contractor')
        self.assertEqual(row['source_of_fund'], 'Local Development Fund')
        self.assertEqual(
            row['cover_image_url'],
            '/media/projects/infrastructure-cover.jpg',
        )
        self.assertEqual(row['budget'], 2500000)
        self.assertTrue(row['has_financial'])
        self.assertEqual(row['abc_amount'], 2500000)
        self.assertEqual(row['contract_price'], 2400000)
        self.assertEqual(row['progress'], 55)
        self.assertTrue(row['has_progress'])
        self.assertEqual(row['cost_progress_percentage'], 42)
        self.assertEqual(row['physical_progress_percentage'], 55)
        self.assertEqual(
            str(row['actual_start_date']),
            '2026-01-20',
        )
        self.assertEqual(
            row['detail_url'],
            reverse(
                'public_infrastructure_project_detail',
                args=[self.infrastructure.pk],
            ),
        )
        self.assertContains(
            response,
            'data-project-modal-trigger',
        )
        self.assertContains(
            response,
            f'data-project-detail-url="{row["detail_url"]}"',
        )
        self.assertContains(
            response,
            'data-project-office="Municipal Engineering Office"',
        )
        self.assertContains(
            response,
            'data-project-contractor="Public Works Contractor"',
        )
        self.assertContains(
            response,
            'data-project-source-of-fund="Local Development Fund"',
        )
        self.assertContains(
            response,
            'data-project-physical-progress-percentage="55.0%"',
        )
        self.assertContains(
            response,
            '/media/projects/infrastructure-cover.jpg',
        )
        self.assertNotContains(response, 'images/infra-icon.png')
        self.assertContains(response, 'P2500000.00')
        self.assertContains(response, '>55%<', html=False)
        self.assertContains(response, 'Municipal Engineering Office')
        self.assertContains(response, 'Public Works Contractor')
        self.assertContains(
            response,
            'label="Infrastructure Categories"',
        )
        self.assertContains(
            response,
            'label="Non-Infrastructure Categories"',
        )
        self.assertContains(
            response,
            'data-project-category-type="infra"',
        )

    def test_public_infrastructure_detail_is_available_without_login(self):
        detail_url = reverse(
            'public_infrastructure_project_detail',
            args=[self.infrastructure.pk],
        )

        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            'Dashboard/infrastructure_detail.html',
        )
        self.assertContains(response, 'Normalized Road Project')
        self.assertContains(
            response,
            f'INF-{self.infrastructure.pk:05d}',
        )
        self.assertContains(response, 'Municipal Engineering Office')
        self.assertContains(response, 'Public Works Contractor')
        self.assertContains(response, 'Local Development Fund')
        self.assertContains(response, '2500000.00')
        self.assertContains(response, '55.0%')
        self.assertContains(response, 'Bagting')
        self.assertContains(
            response,
            '/media/projects/infrastructure-cover.jpg',
        )
        self.assertContains(
            response,
            'css/templates/Dashboard/infrastructure_detail.css',
        )
        self.assertContains(response, 'GIS Location')
        self.assertContains(response, 'id="gabaldon-gis-root"')
        self.assertContains(
            response,
            f'data-focus-project-id="{self.infrastructure.pk}"',
        )
        self.assertContains(
            response,
            'data-focus-project-type="infrastructure"',
        )
        self.assertContains(response, 'data-focus-lat="15.2915"')
        self.assertContains(response, 'data-focus-lng="121.3386"')
        self.assertContains(response, 'Open exact location in Google Maps')
        self.assertNotContains(response, 'Edit Project')
        self.assertNotContains(response, 'Delete Project')

    def test_public_infrastructure_detail_handles_missing_coordinates(self):
        address = self.infrastructure.address
        address.latitude = None
        address.longitude = None
        address.save(update_fields=['latitude', 'longitude'])

        response = self.client.get(
            reverse(
                'public_infrastructure_project_detail',
                args=[self.infrastructure.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Map location unavailable')
        self.assertContains(response, 'Location has not yet been assigned.')
        self.assertNotContains(response, 'id="gabaldon-gis-root"')


class PublicDashboardNonInfrastructureStatusTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='dashboard-author',
            password='password123',
        )

        for name, status in (
            ('Planned Program', 'planned'),
            ('Ongoing Program', 'ongoing'),
            ('Completed Program', 'completed'),
        ):
            project = Project.objects.create(
                project_type='non_infrastructure',
                created_by_user=self.user,
                updated_by_user=self.user,
            )
            noninfra = Non_Infrastructure_Project.objects.create(
                project=project,
                non_infra_name=name,
                status=status,
            )

            if status == 'ongoing':
                Project_Image.objects.create(
                    project=noninfra.project,
                    image_url='/media/projects/ongoing-cover.jpg',
                    is_cover=True,
                )
                Project_Image.objects.create(
                    project=noninfra.project,
                    image_url='/media/projects/ongoing-other.jpg',
                )

    def test_public_dashboard_uses_saved_non_infrastructure_statuses(self):
        response = self.client.get(reverse('public_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['noninfra_total'], 3)
        self.assertEqual(response.context['planned_projects'], 1)
        self.assertEqual(response.context['ongoing_projects'], 1)
        self.assertEqual(response.context['completed_projects'], 1)

        statuses = {
            row['title']: (row['status_key'], row['status_label'])
            for row in response.context['project_rows']
            if row['category'] == 'noninfra'
        }
        self.assertEqual(statuses['Planned Program'], ('planned', 'Planned'))
        self.assertEqual(statuses['Ongoing Program'], ('ongoing', 'Ongoing'))
        self.assertEqual(statuses['Completed Program'], ('completed', 'Completed'))

        ongoing_row = next(
            row
            for row in response.context['project_rows']
            if row['title'] == 'Ongoing Program'
        )
        self.assertEqual(
            ongoing_row['cover_image_url'],
            '/media/projects/ongoing-cover.jpg',
        )
        self.assertContains(response, '/media/projects/ongoing-cover.jpg')

        noninfra_rows = [
            row
            for row in response.context['project_rows']
            if row['category'] == 'noninfra'
        ]
        self.assertTrue(
            all(row['location_key'] == '' for row in noninfra_rows)
        )
        self.assertTrue(
            all(row['location'] == '' for row in noninfra_rows)
        )
        for row in noninfra_rows:
            project_pk = int(row['record_id'].removeprefix('noninfra-'))
            self.assertEqual(
                row['detail_url'],
                reverse(
                    'public_non_infrastructure_project_detail',
                    args=[project_pk],
                ),
            )

        mayor_detail_url = reverse(
            'mayor_projects:non_infrastructure_project_detail',
            args=[Non_Infrastructure_Project.objects.get(status='ongoing').pk],
        )
        self.assertNotContains(response, mayor_detail_url)
        self.assertContains(response, 'data-project-modal-trigger', count=3)

    def test_public_non_infrastructure_detail_is_available_without_login(self):
        project = Non_Infrastructure_Project.objects.get(status='ongoing')
        detail_url = reverse(
            'public_non_infrastructure_project_detail',
            args=[project.pk],
        )

        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            'Dashboard/non_infrastructure_detail.html',
        )
        self.assertContains(response, project.non_infra_name)
        self.assertContains(response, '/media/projects/ongoing-cover.jpg')
        self.assertContains(
            response,
            '/static/css/templates/Dashboard/infrastructure_detail.css',
        )
        self.assertContains(response, '<main class="public-detail">')
        self.assertContains(response, 'class="public-detail__hero"')
        self.assertContains(response, 'class="public-detail__summary"')
        self.assertContains(response, 'class="public-image-grid"')
        self.assertContains(response, 'class="public-image-card"', count=2)
        self.assertContains(response, 'Cover photo')
        self.assertContains(response, '<h2>Schedule and Venue</h2>', html=True)
        self.assertNotContains(
            response,
            '/static/css/templates/non_infrastructure/non_infrastructure_detail.css',
        )
        self.assertNotContains(response, '<h3>Location</h3>', html=True)
        self.assertNotContains(response, 'Edit Project')
        self.assertNotContains(response, 'Delete Project')


class UserDeactivateViewTests(TestCase):
    def test_current_user_deactivation_shows_warning(self):
        user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='password',
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )

        self.client.force_login(user)
        response = self.client.get(reverse('user_deactivate', args=[user.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_deactivate'])
        self.assertEqual(response.context['warning_message'], 'You cannot deactivate your own account.')


class SuperuserProfileTests(TestCase):
    def test_created_superuser_gets_admin_profile(self):
        user = User.objects.create_superuser(
            username='root',
            email='root@example.com',
            password='password123',
        )
        # Runtime no longer creates archive-backed profiles; department is inferred.
        self.assertTrue(user.is_superuser)
        self.assertEqual(user.profile.department, 'admin')


class UserCreationFormTests(TestCase):
    def test_user_creation_form_defaults_to_no_department(self):
        form = CustomUserCreationForm()

        self.assertEqual(form.fields['role'].initial, '')

    def test_user_creation_form_rejects_blank_department(self):
        form = CustomUserCreationForm(
            data={
                'username': 'tempuser2',
                'email': 'tempuser2@example.com',
                'first_name': 'Temp',
                'last_name': 'User',
                'role': '',
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn('role', form.errors)

    def test_user_creation_form_does_not_require_manual_password(self):
        form = CustomUserCreationForm(
            data={
                'username': 'tempuser',
                'email': 'tempuser@example.com',
                'first_name': 'Temp',
                'last_name': 'User',
                'role': 'engineering',
            }
        )

        self.assertTrue(form.is_valid())

        user = form.save(commit=True, temporary_password='TempPass123!')

        self.assertTrue(user.check_password('TempPass123!'))
        self.assertEqual(user.profile.department, 'engineer')

    def test_mayor_user_is_staff_and_keeps_mayor_department(self):
        form = CustomUserCreationForm(
            data={
                'username': 'mayoruser2',
                'email': 'mayoruser2@example.com',
                'first_name': 'Mayor',
                'last_name': 'User',
                'role': 'mayors',
            }
        )

        self.assertTrue(form.is_valid())

        user = form.save(commit=True, temporary_password='TempPass123!')

        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.profile.department, 'mayor')


class UserCreateConfirmViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin2',
            email='admin2@example.com',
            password='password123',
        )

    def test_confirm_creation_preserves_mayor_department(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session['user_create_form_data'] = {
            'username': 'mayoruser',
            'email': 'mayoruser@example.com',
            'first_name': 'Mayor',
            'last_name': 'User',
            'role': 'mayors',
        }
        session.save()

        response = self.client.post(reverse('user_create_confirm'))

        self.assertEqual(response.status_code, 302)
        created_user = User.objects.get(username='mayoruser')
        self.assertEqual(created_user.profile.department, 'mayor')
        self.assertTrue(created_user.profile.must_change_password)

