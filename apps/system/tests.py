import json
import importlib
from datetime import date, time
from decimal import Decimal

from django.apps import apps as django_apps
from django.test import TestCase
from django.core.exceptions import PermissionDenied, ValidationError
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
    UserFlag,
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
from .publication_service import (
    archive_publication_revision,
    create_publication_draft,
    publish_publication_revision,
    review_publication_revision,
    submit_project_for_review,
    submit_publication_revision,
)


def publish_current_snapshot(project):
    # Reload so model date/time fields assigned as test strings are normalized.
    project = Project.objects.get(pk=project.pk)
    return ProjectPublicationRevision.objects.create(
        project=project,
        revision_number=1,
        status=PublicationStatus.PUBLISHED,
        snapshot_data=build_project_publication_snapshot(project),
        source_updated_at=project.updated_at,
        is_current_public_revision=True,
    )


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


class PublicationServiceTests(TestCase):
    def setUp(self):
        self.employee = User.objects.create_user(
            username='publication-employee',
            password='password123',
        )
        self.admin = User.objects.create_superuser(
            username='publication-admin',
            email='admin@example.com',
            password='password123',
        )
        self.project = Project.objects.create(
            project_type='infrastructure',
            created_by_user=self.employee,
            updated_by_user=self.employee,
        )
        self.infrastructure = Infrastructure_Project.objects.create(
            project=self.project,
            infrastructure_title='Working Project Title',
            award_status='awarded',
        )

    def _approve_and_publish(self, revision):
        submitted = submit_publication_revision(revision, self.employee)
        approved = review_publication_revision(
            submitted,
            self.admin,
            PublicationStatus.APPROVED,
        )
        return publish_publication_revision(approved, self.admin)

    def test_full_workflow_publishes_submitted_snapshot(self):
        draft = create_publication_draft(self.project, self.employee)
        self.infrastructure.infrastructure_title = 'Submitted Project Title'
        self.infrastructure.save(update_fields=['infrastructure_title'])

        submitted = submit_publication_revision(draft, self.employee)
        approved = review_publication_revision(
            submitted,
            self.admin,
            PublicationStatus.APPROVED,
        )
        published = publish_publication_revision(approved, self.admin)

        self.assertEqual(published.status, PublicationStatus.PUBLISHED)
        self.assertTrue(published.is_current_public_revision)
        self.assertEqual(published.published_by, self.admin)
        self.assertEqual(
            published.snapshot_data['infrastructure']['title'],
            'Submitted Project Title',
        )
        self.project.refresh_from_db()
        self.assertTrue(self.project.is_published)
        self.assertTrue(self.project.is_visible_to_public)

    def test_new_publication_atomically_archives_previous_revision(self):
        first = self._approve_and_publish(
            create_publication_draft(self.project, self.employee),
        )
        self.infrastructure.infrastructure_title = 'Approved Revision Two'
        self.infrastructure.save(update_fields=['infrastructure_title'])
        second_draft = create_publication_draft(self.project, self.employee)

        self.assertEqual(second_draft.revision_number, 2)
        self.assertEqual(second_draft.supersedes_revision, first)
        second = self._approve_and_publish(second_draft)

        first.refresh_from_db()
        self.assertEqual(first.status, PublicationStatus.ARCHIVED)
        self.assertFalse(first.is_current_public_revision)
        self.assertTrue(second.is_current_public_revision)
        self.assertEqual(
            ProjectPublicationRevision.objects.filter(
                project=self.project,
                is_current_public_revision=True,
            ).count(),
            1,
        )

    def test_returned_revision_requires_notes_and_can_be_resubmitted(self):
        submitted = submit_publication_revision(
            create_publication_draft(self.project, self.employee),
            self.employee,
        )
        with self.assertRaises(PermissionDenied):
            review_publication_revision(
                submitted,
                self.employee,
                PublicationStatus.APPROVED,
            )
        with self.assertRaisesMessage(ValidationError, 'Review notes'):
            review_publication_revision(
                submitted,
                self.admin,
                PublicationStatus.NEEDS_REVISION,
            )

        returned = review_publication_revision(
            submitted,
            self.admin,
            PublicationStatus.NEEDS_REVISION,
            notes='Clarify the public project title.',
        )
        self.infrastructure.infrastructure_title = 'Corrected Public Title'
        self.infrastructure.save(update_fields=['infrastructure_title'])
        resubmitted = submit_publication_revision(returned, self.employee)

        self.assertEqual(resubmitted.status, PublicationStatus.PENDING_REVIEW)
        self.assertEqual(resubmitted.review_notes, '')
        self.assertEqual(
            resubmitted.snapshot_data['infrastructure']['title'],
            'Corrected Public Title',
        )

    def test_active_revision_prevents_duplicate_drafts(self):
        create_publication_draft(self.project, self.employee)

        with self.assertRaisesMessage(
            ValidationError,
            'already has an active publication revision',
        ):
            create_publication_draft(self.project, self.employee)

    def test_archiving_current_revision_removes_project_from_publication(self):
        published = self._approve_and_publish(
            create_publication_draft(self.project, self.employee),
        )

        archived = archive_publication_revision(published, self.admin)

        self.assertEqual(archived.status, PublicationStatus.ARCHIVED)
        self.assertFalse(archived.is_current_public_revision)
        self.project.refresh_from_db()
        self.assertFalse(self.project.is_published)
        self.assertFalse(self.project.is_visible_to_public)


class EmployeePublicationWorkflowViewTests(TestCase):
    def setUp(self):
        self.engineer = User.objects.create_user(
            username='workflow-engineer',
            password='password123',
            is_staff=True,
        )
        UserFlag.objects.create(user=self.engineer, department='engineer')
        self.mayor_user = User.objects.create_user(
            username='workflow-mayor',
            password='password123',
            is_staff=True,
        )
        UserFlag.objects.create(user=self.mayor_user, department='mayor')
        self.admin = User.objects.create_superuser(
            username='workflow-admin',
            email='workflow-admin@example.com',
            password='password123',
        )

        infra_base = Project.objects.create(
            project_type='infrastructure',
            created_by_user=self.engineer,
        )
        self.infrastructure = Infrastructure_Project.objects.create(
            project=infra_base,
            infrastructure_title='Employee Submission Road',
            award_status='awarded',
        )
        noninfra_base = Project.objects.create(
            project_type='non_infrastructure',
            created_by_user=self.mayor_user,
        )
        self.non_infrastructure = Non_Infrastructure_Project.objects.create(
            project=noninfra_base,
            non_infra_name='Employee Submission Program',
            status='planned',
        )

    def test_engineer_submits_and_sees_return_notes(self):
        self.client.force_login(self.engineer)
        detail_url = reverse(
            'engineering_projects:project_detail',
            args=[self.infrastructure.pk],
        )
        submit_url = reverse(
            'engineering_projects:project_submit_for_review',
            args=[self.infrastructure.pk],
        )

        initial = self.client.get(detail_url)
        self.assertContains(initial, 'Not Submitted')
        self.assertContains(initial, 'Submit for Public Review')
        self.assertEqual(self.client.get(submit_url).status_code, 405)

        response = self.client.post(submit_url)
        self.assertRedirects(response, detail_url)
        revision = ProjectPublicationRevision.objects.get(
            project=self.infrastructure.project,
        )
        self.assertEqual(revision.status, PublicationStatus.PENDING_REVIEW)

        pending = self.client.get(detail_url)
        self.assertContains(pending, 'Pending Review')
        self.assertNotContains(pending, 'Submit for Public Review')

        delete_response = self.client.post(reverse(
            'engineering_projects:project_delete',
            args=[self.infrastructure.pk],
        ))
        self.assertRedirects(delete_response, detail_url)
        self.assertTrue(
            Project.objects.filter(pk=self.infrastructure.project_id).exists(),
        )

        returned = review_publication_revision(
            revision,
            self.admin,
            PublicationStatus.NEEDS_REVISION,
            notes='Please clarify the project description.',
        )
        self.assertEqual(returned.status, PublicationStatus.NEEDS_REVISION)
        needs_revision = self.client.get(detail_url)
        self.assertContains(needs_revision, 'Needs Revision')
        self.assertContains(
            needs_revision,
            'Please clarify the project description.',
        )
        self.assertContains(needs_revision, 'Resubmit for Review')

    def test_mayor_user_can_submit_non_infrastructure_project(self):
        self.client.force_login(self.mayor_user)
        detail_url = reverse(
            'mayor_projects:non_infrastructure_project_detail',
            args=[self.non_infrastructure.pk],
        )
        submit_url = reverse(
            'mayor_projects:non_infrastructure_project_submit_for_review',
            args=[self.non_infrastructure.pk],
        )

        initial = self.client.get(detail_url)
        self.assertContains(initial, 'Not Submitted')
        response = self.client.post(submit_url)

        self.assertRedirects(response, detail_url)
        revision = ProjectPublicationRevision.objects.get(
            project=self.non_infrastructure.project,
        )
        self.assertEqual(revision.status, PublicationStatus.PENDING_REVIEW)
        self.assertEqual(
            revision.snapshot_data['non_infrastructure']['title'],
            'Employee Submission Program',
        )
        delete_response = self.client.post(reverse(
            'mayor_projects:non_infrastructure_project_delete',
            args=[self.non_infrastructure.pk],
        ))
        self.assertRedirects(delete_response, detail_url)
        self.assertTrue(Project.objects.filter(
            pk=self.non_infrastructure.project_id,
        ).exists())

    def test_department_submission_endpoints_are_role_protected(self):
        self.client.force_login(self.engineer)
        response = self.client.post(reverse(
            'mayor_projects:non_infrastructure_project_submit_for_review',
            args=[self.non_infrastructure.pk],
        ))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.mayor_user)
        response = self.client.post(reverse(
            'engineering_projects:project_submit_for_review',
            args=[self.infrastructure.pk],
        ))
        self.assertEqual(response.status_code, 403)


class AdminPublicationReviewViewTests(TestCase):
    def setUp(self):
        self.employee = User.objects.create_user(
            username='review-queue-employee',
            password='password123',
            is_staff=True,
        )
        UserFlag.objects.create(user=self.employee, department='engineer')
        self.admin = User.objects.create_superuser(
            username='review-queue-admin',
            email='review-queue-admin@example.com',
            password='password123',
        )
        project = Project.objects.create(
            project_type='infrastructure',
            created_by_user=self.employee,
        )
        self.infrastructure = Infrastructure_Project.objects.create(
            project=project,
            infrastructure_title='Submitted Admin Preview Project',
            infrastructure_description='Snapshot reviewed by the administrator.',
            award_status='awarded',
        )
        Project_Image.objects.create(
            project=project,
            image_url='/media/projects/admin-review-cover.jpg',
            is_cover=True,
        )
        self.revision = submit_project_for_review(project, self.employee)

    def test_admin_queue_and_detail_show_submitted_snapshot(self):
        self.infrastructure.infrastructure_title = 'Later Working Copy Edit'
        self.infrastructure.save(update_fields=['infrastructure_title'])
        self.client.force_login(self.admin)

        queue = self.client.get(reverse('publication_review_queue'))
        dashboard = self.client.get(reverse('admin_dashboard'))
        detail = self.client.get(reverse(
            'publication_revision_detail',
            args=[self.revision.pk],
        ))

        self.assertContains(queue, 'Submitted Admin Preview Project')
        self.assertContains(queue, 'Pending Review')
        self.assertContains(dashboard, 'Review Public Projects')
        self.assertEqual(
            dashboard.context['pending_publication_reviews'],
            1,
        )
        self.assertContains(detail, 'Submitted Admin Preview Project')
        self.assertNotContains(detail, 'Later Working Copy Edit')
        self.assertContains(detail, '/media/projects/admin-review-cover.jpg')
        self.assertContains(detail, 'Record Decision')
        self.assertContains(
            detail,
            '/static/css/templates/base.css?v=20260821-1',
        )
        self.assertContains(
            detail,
            '/static/css/templates/core/publication_review.css?v=20260821-1',
        )
        self.assertContains(
            detail,
            '/static/css/components/publication_workflow.css?v=20260821-1',
        )

    def test_admin_can_return_from_working_project_without_role_403(self):
        self.client.force_login(self.admin)
        review_url = reverse(
            'publication_revision_detail',
            args=[self.revision.pk],
        )
        working_url = reverse(
            'engineering_projects:project_detail',
            args=[self.infrastructure.pk],
        )

        review = self.client.get(review_url)
        working = self.client.get(
            working_url,
            {'from_review': self.revision.pk},
        )
        project_list = self.client.get(reverse(
            'engineering_projects:project_list',
        ))
        dashboard = self.client.get(reverse('engineering_dashboard'))

        self.assertContains(
            review,
            f'{working_url}?from_review={self.revision.pk}',
        )
        self.assertEqual(working.status_code, 200)
        self.assertContains(working, 'Back to Publication Review')
        self.assertContains(working, f'href="{review_url}"')
        self.assertNotContains(working, 'Edit Project')
        self.assertNotContains(working, 'Delete Project')
        self.assertEqual(project_list.status_code, 200)
        self.assertEqual(dashboard.status_code, 200)

    def test_review_workspace_and_actions_are_admin_only(self):
        self.client.force_login(self.employee)

        self.assertEqual(
            self.client.get(reverse('publication_review_queue')).status_code,
            403,
        )
        response = self.client.post(
            reverse('publication_revision_review', args=[self.revision.pk]),
            {'decision': PublicationStatus.APPROVED, 'notes': ''},
        )
        self.assertEqual(response.status_code, 403)
        self.revision.refresh_from_db()
        self.assertEqual(
            self.revision.status,
            PublicationStatus.PENDING_REVIEW,
        )

    def test_return_and_reject_decisions_require_notes(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('publication_revision_review', args=[self.revision.pk]),
            {
                'decision': PublicationStatus.NEEDS_REVISION,
                'notes': '',
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            'Review notes are required for this decision.',
            status_code=400,
        )
        self.revision.refresh_from_db()
        self.assertEqual(
            self.revision.status,
            PublicationStatus.PENDING_REVIEW,
        )

    def test_admin_approves_publishes_and_archives_separately(self):
        self.client.force_login(self.admin)
        review_url = reverse(
            'publication_revision_review',
            args=[self.revision.pk],
        )
        publish_url = reverse(
            'publication_revision_publish',
            args=[self.revision.pk],
        )
        archive_url = reverse(
            'publication_revision_archive',
            args=[self.revision.pk],
        )

        approved_response = self.client.post(review_url, {
            'decision': PublicationStatus.APPROVED,
            'notes': 'Verified for publication.',
        })
        self.assertRedirects(
            approved_response,
            reverse('publication_revision_detail', args=[self.revision.pk]),
        )
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.status, PublicationStatus.APPROVED)
        self.assertEqual(self.client.get(publish_url).status_code, 405)

        self.client.post(publish_url)
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.status, PublicationStatus.PUBLISHED)
        self.assertTrue(self.revision.is_current_public_revision)
        public = self.client.get(reverse('public_dashboard'))
        self.assertContains(public, 'Submitted Admin Preview Project')

        self.client.post(archive_url)
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.status, PublicationStatus.ARCHIVED)
        self.assertFalse(self.revision.is_current_public_revision)
        public = self.client.get(reverse('public_dashboard'))
        self.assertNotContains(public, 'Submitted Admin Preview Project')


class RoleDashboardAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='dashboard-access-admin',
            email='dashboard-access-admin@example.com',
            password='password123',
        )
        self.engineer = User.objects.create_user(
            username='dashboard-access-engineer',
            password='password123',
            is_staff=True,
        )
        UserFlag.objects.create(user=self.engineer, department='engineer')
        self.mayor = User.objects.create_user(
            username='dashboard-access-mayor',
            password='password123',
            is_staff=True,
        )
        UserFlag.objects.create(user=self.mayor, department='mayor')

    def test_superuser_can_follow_working_project_navigation(self):
        self.client.force_login(self.admin)

        self.assertEqual(
            self.client.get(reverse('engineering_dashboard')).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse('mayor_dashboard')).status_code,
            200,
        )

    def test_role_dashboards_still_reject_other_departments(self):
        self.client.force_login(self.engineer)
        self.assertEqual(
            self.client.get(reverse('engineering_dashboard')).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse('mayor_dashboard')).status_code,
            403,
        )

        self.client.force_login(self.mayor)
        self.assertEqual(
            self.client.get(reverse('mayor_dashboard')).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse('engineering_dashboard')).status_code,
            403,
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


class ProjectPublicationBackfillMigrationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.migration = importlib.import_module(
            'apps.system.migrations.0027_backfill_published_revisions',
        )

    def test_backfills_complete_current_revisions_for_existing_projects(self):
        author = User.objects.create_user(
            username='existing-author',
            first_name='Existing',
            last_name='Author',
        )
        infrastructure_project = Project.objects.create(
            project_type='infrastructure',
            created_by_user=author,
        )
        infrastructure = Infrastructure_Project.objects.create(
            project=infrastructure_project,
            infrastructure_title='Existing Road Project',
            procurement_method='competitive_bidding',
            award_status='awarded',
        )
        Financial.objects.create(
            infrastructure=infrastructure,
            approved_budget=Decimal('1000000.00'),
        )
        Project_Image.objects.create(
            project=infrastructure_project,
            image_url='/media/projects/existing-road.jpg',
            is_cover=True,
        )

        non_infrastructure_project = Project.objects.create(
            project_type='non_infrastructure',
            created_by_user=author,
        )
        non_infrastructure = Non_Infrastructure_Project.objects.create(
            project=non_infrastructure_project,
            non_infra_name='Existing Community Program',
            status='ongoing',
        )

        self.migration.backfill_published_revisions(django_apps, None)

        infrastructure_revision = ProjectPublicationRevision.objects.get(
            project=infrastructure_project,
        )
        self.assertEqual(infrastructure_revision.status, 'published')
        self.assertTrue(infrastructure_revision.is_current_public_revision)
        self.assertEqual(
            infrastructure_revision.snapshot_data['infrastructure']['title'],
            'Existing Road Project',
        )
        self.assertEqual(
            infrastructure_revision.snapshot_data['financial'][
                'approved_budget'
            ],
            '1000000.00',
        )
        self.assertEqual(
            infrastructure_revision.snapshot_data['project'][
                'cover_image_url'
            ],
            '/media/projects/existing-road.jpg',
        )

        non_infrastructure_revision = ProjectPublicationRevision.objects.get(
            project=non_infrastructure_project,
        )
        self.assertEqual(
            non_infrastructure_revision.snapshot_data[
                'non_infrastructure'
            ]['status_label'],
            'Ongoing',
        )
        infrastructure_project.refresh_from_db()
        non_infrastructure_project.refresh_from_db()
        self.assertTrue(infrastructure_project.is_published)
        self.assertTrue(infrastructure_project.is_visible_to_public)
        self.assertTrue(non_infrastructure_project.is_published)
        self.assertTrue(non_infrastructure_project.is_visible_to_public)

    def test_is_idempotent_and_preserves_existing_workflow_revisions(self):
        existing_project = Project.objects.create(
            project_type='infrastructure',
        )
        Infrastructure_Project.objects.create(
            project=existing_project,
            infrastructure_title='Already in Workflow',
        )
        existing_revision = ProjectPublicationRevision.objects.create(
            project=existing_project,
            revision_number=1,
            status='draft',
            snapshot_data={'existing': True},
        )
        backfill_project = Project.objects.create(
            project_type='non_infrastructure',
        )
        Non_Infrastructure_Project.objects.create(
            project=backfill_project,
            non_infra_name='Needs Backfill',
        )

        self.migration.backfill_published_revisions(django_apps, None)
        self.migration.backfill_published_revisions(django_apps, None)

        self.assertEqual(
            ProjectPublicationRevision.objects.filter(
                project=existing_project,
            ).count(),
            1,
        )
        existing_revision.refresh_from_db()
        self.assertEqual(existing_revision.snapshot_data, {'existing': True})
        self.assertEqual(
            ProjectPublicationRevision.objects.filter(
                project=backfill_project,
            ).count(),
            1,
        )

    def test_reverse_removes_only_generated_revisions(self):
        backfill_project = Project.objects.create(
            project_type='non_infrastructure',
        )
        Non_Infrastructure_Project.objects.create(
            project=backfill_project,
            non_infra_name='Generated Revision',
        )
        existing_project = Project.objects.create(
            project_type='infrastructure',
        )
        Infrastructure_Project.objects.create(
            project=existing_project,
            infrastructure_title='Manual Revision',
        )
        manual_revision = ProjectPublicationRevision.objects.create(
            project=existing_project,
            revision_number=1,
            status='published',
            snapshot_data={'manual': True},
            is_current_public_revision=True,
        )

        self.migration.backfill_published_revisions(django_apps, None)
        self.migration.remove_backfilled_revisions(django_apps, None)

        self.assertFalse(
            ProjectPublicationRevision.objects.filter(
                project=backfill_project,
            ).exists(),
        )
        self.assertTrue(
            ProjectPublicationRevision.objects.filter(
                pk=manual_revision.pk,
            ).exists(),
        )
        backfill_project.refresh_from_db()
        self.assertFalse(backfill_project.is_published)
        self.assertFalse(backfill_project.is_visible_to_public)


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
        self.public_revision = publish_current_snapshot(base_project)

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
        snapshot = self.public_revision.snapshot_data
        snapshot['infrastructure']['address']['latitude'] = None
        snapshot['infrastructure']['address']['longitude'] = None
        self.public_revision.snapshot_data = snapshot
        self.public_revision.save(update_fields=['snapshot_data'])

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

    def test_public_surfaces_stay_on_snapshot_until_a_new_revision_is_published(self):
        self.infrastructure.infrastructure_title = 'Unapproved Edited Title'
        self.infrastructure.physical_progress_percentage = 99
        self.infrastructure.save(update_fields=[
            'infrastructure_title',
            'physical_progress_percentage',
        ])
        self.infrastructure.project.images.create(
            image_url='/media/projects/unapproved-new-image.jpg',
        )

        dashboard = self.client.get(reverse('public_dashboard'))
        detail = self.client.get(reverse(
            'public_infrastructure_project_detail',
            args=[self.infrastructure.pk],
        ))
        gis = self.client.get(reverse('gis_projects_layer'))
        photos = self.client.get(reverse(
            'gis_project_photos',
            args=[self.infrastructure.project_id],
        ))

        self.assertContains(dashboard, 'Normalized Road Project')
        self.assertNotContains(dashboard, 'Unapproved Edited Title')
        self.assertContains(detail, 'Normalized Road Project')
        self.assertNotContains(detail, 'Unapproved Edited Title')
        self.assertEqual(gis.json()['features'][0]['properties']['name'], 'Normalized Road Project')
        self.assertEqual(gis.json()['features'][0]['properties']['progress'], '55.00')
        self.assertEqual(
            [photo['url'] for photo in photos.json()['photos']],
            ['/media/projects/infrastructure-cover.jpg'],
        )

    def test_unpublished_project_is_absent_and_its_public_detail_is_404(self):
        project = Project.objects.create(project_type='infrastructure')
        unpublished = Infrastructure_Project.objects.create(
            project=project,
            infrastructure_title='Internal Draft Project',
        )

        dashboard = self.client.get(reverse('public_dashboard'))
        detail = self.client.get(reverse(
            'public_infrastructure_project_detail',
            args=[unpublished.pk],
        ))

        self.assertNotContains(dashboard, 'Internal Draft Project')
        self.assertEqual(detail.status_code, 404)


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
            publish_current_snapshot(project)

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

