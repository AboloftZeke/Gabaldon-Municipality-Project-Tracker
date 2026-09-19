from .permissions import department_for_user as _department_for_user
import json
import re
from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from .forms import CustomUserCreationForm
from .account_setup import AccountSetupDeliveryError
from .models import (
    Address,
    Contractor,
    FinancialRecord,
    FundSource,
    ImplementingOffice,
    InfrastructureCategory,
    InfrastructureSchedule,
    InfrastructureProject,
    LoginOTPChallenge,
    NonInfrastructureCategory,
    NonInfrastructureProject,
    Project,
    ProjectImage,
    ProjectInspection,
    ProjectRevision,
    UserRole,
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
    create_head_operational_revision,
    create_publication_draft,
    publish_publication_revision,
    review_publication_revision,
    submit_project_for_review,
    submit_publication_revision,
)


def publish_current_snapshot(project):
    # Reload so model date/time fields assigned as test strings are normalized.
    project = Project.objects.get(pk=project.pk)
    return ProjectRevision.objects.create(
        project=project,
        revision_number=1,
        status=PublicationStatus.PUBLISHED,
        snapshot=build_project_publication_snapshot(project),
        source_updated_at=project.updated_at,
        is_current_public=True,
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


class ProjectRevisionModelTests(TestCase):
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
        revision = ProjectRevision.objects.create(
            project=self.project,
            revision_number=1,
            snapshot={'title': 'Barangay Road Project'},
        )

        self.assertEqual(revision.status, PublicationStatus.DRAFT)
        self.assertEqual(
            revision.snapshot,
            {'title': 'Barangay Road Project'},
        )
        self.assertFalse(revision.is_current_public)
        self.assertEqual(
            str(revision),
            f'Project {self.project.pk} publication revision 1',
        )

    def test_revision_number_is_unique_within_project(self):
        ProjectRevision.objects.create(
            project=self.project,
            revision_number=1,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectRevision.objects.create(
                project=self.project,
                revision_number=1,
            )

    def test_project_can_have_only_one_current_public_revision(self):
        first_revision = ProjectRevision.objects.create(
            project=self.project,
            revision_number=1,
            status=PublicationStatus.PUBLISHED,
            is_current_public=True,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectRevision.objects.create(
                project=self.project,
                revision_number=2,
                status=PublicationStatus.PUBLISHED,
                is_current_public=True,
                previous_revision=first_revision,
            )

    def test_current_public_revision_must_be_published(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectRevision.objects.create(
                project=self.project,
                revision_number=1,
                status=PublicationStatus.DRAFT,
                is_current_public=True,
            )

    def test_revision_can_reference_the_version_it_supersedes(self):
        first_revision = ProjectRevision.objects.create(
            project=self.project,
            revision_number=1,
        )
        second_revision = ProjectRevision.objects.create(
            project=self.project,
            revision_number=2,
            previous_revision=first_revision,
        )

        self.assertEqual(second_revision.previous_revision, first_revision)
        self.assertIn(
            second_revision,
            first_revision.superseded_by_revisions.all(),
        )


class PublicationServiceTests(TestCase):
    def setUp(self):
        self.head = User.objects.create_user(username='review-head', is_staff=True)
        UserRole.objects.create(user=self.head, department='engineer', role='head')
        self.employee = User.objects.create_user(
            username='publication-employee',
            password='password123',
        )
        UserRole.objects.create(user=self.employee, department='engineer', role='staff')
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
        self.infrastructure = InfrastructureProject.objects.create(
            project=self.project,
            title='Working Project Title',
            award_status='pre_construction',
        )

    def _approve_and_publish(self, revision):
        submitted = submit_publication_revision(revision, self.employee)
        if not self.project.revisions.filter(
            status__in=[
                PublicationStatus.PUBLISHED,
                PublicationStatus.ARCHIVED,
            ],
        ).exists():
            self._confirm_initial_operations()
        approved = review_publication_revision(
            submitted,
            self.head,
            PublicationStatus.APPROVED,
        )
        return publish_publication_revision(approved, self.head)

    def _confirm_initial_operations(self):
        self.infrastructure.physical_progress_percentage = Decimal('0')
        self.infrastructure.save(update_fields=[
            'physical_progress_percentage',
        ])
        create_head_operational_revision(self.project, self.head)

    def test_full_workflow_publishes_submitted_snapshot(self):
        draft = create_publication_draft(self.project, self.employee)
        self.infrastructure.title = 'Submitted Project Title'
        self.infrastructure.save(update_fields=['title'])

        submitted = submit_publication_revision(draft, self.employee)
        self._confirm_initial_operations()
        approved = review_publication_revision(
            submitted,
            self.head,
            PublicationStatus.APPROVED,
        )
        published = publish_publication_revision(approved, self.head)

        self.assertEqual(published.status, PublicationStatus.PUBLISHED)
        self.assertTrue(published.is_current_public)
        self.assertEqual(published.published_by, self.head)
        self.assertEqual(
            published.snapshot['infrastructure']['title'],
            'Submitted Project Title',
        )
        self.project.refresh_from_db()
        self.assertTrue(self.project.is_published)
        self.assertTrue(self.project.is_visible_to_public)

    def test_new_publication_atomically_archives_previous_revision(self):
        first = self._approve_and_publish(
            create_publication_draft(self.project, self.employee),
        )
        self.infrastructure.title = 'Approved Revision Two'
        self.infrastructure.save(update_fields=['title'])
        second_draft = create_publication_draft(self.project, self.employee)

        self.assertEqual(second_draft.revision_number, 2)
        self.assertEqual(second_draft.previous_revision, first)
        second = self._approve_and_publish(second_draft)

        first.refresh_from_db()
        self.assertEqual(first.status, PublicationStatus.ARCHIVED)
        self.assertFalse(first.is_current_public)
        self.assertTrue(second.is_current_public)
        self.assertEqual(
            ProjectRevision.objects.filter(
                project=self.project,
                is_current_public=True,
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
                self.head,
                PublicationStatus.NEEDS_REVISION,
            )

        returned = review_publication_revision(
            submitted,
            self.head,
            PublicationStatus.NEEDS_REVISION,
            notes='Clarify the public project title.',
        )
        self.infrastructure.title = 'Corrected Public Title'
        self.infrastructure.save(update_fields=['title'])
        resubmitted = submit_publication_revision(returned, self.employee)

        self.assertEqual(resubmitted.status, PublicationStatus.PENDING_REVIEW)
        self.assertEqual(resubmitted.review_notes, '')
        self.assertEqual(
            resubmitted.snapshot['infrastructure']['title'],
            'Corrected Public Title',
        )

    def test_active_revision_prevents_duplicate_drafts(self):
        create_publication_draft(self.project, self.employee)

        with self.assertRaisesMessage(
            ValidationError,
            'already has an active publication revision',
        ):
            create_publication_draft(self.project, self.employee)

    def test_manual_archiving_current_revision_is_denied(self):
        from django.core.exceptions import PermissionDenied
        published = self._approve_and_publish(create_publication_draft(self.project, self.employee))
        with self.assertRaises(PermissionDenied):
            archive_publication_revision(published, self.admin)
        published.refresh_from_db()
        self.assertTrue(published.is_current_public)



class EmployeePublicationWorkflowViewTests(TestCase):
    def setUp(self):
        self.head = User.objects.create_user(username='review-head', is_staff=True)
        UserRole.objects.create(user=self.head, department='engineer', role='head')
        self.engineer = User.objects.create_user(
            username='workflow-engineer',
            password='password123',
            is_staff=True,
        )
        UserRole.objects.create(user=self.engineer, department='engineer')
        self.mayor_user = User.objects.create_user(
            username='workflow-mayor',
            password='password123',
            is_staff=True,
        )
        UserRole.objects.create(user=self.mayor_user, department='mayor')
        self.admin = User.objects.create_superuser(
            username='workflow-admin',
            email='workflow-admin@example.com',
            password='password123',
        )

        infra_base = Project.objects.create(
            project_type='infrastructure',
            created_by_user=self.engineer,
        )
        self.infrastructure = InfrastructureProject.objects.create(
            project=infra_base,
            title='Employee Submission Road',
            award_status='pre_construction',
        )
        noninfra_base = Project.objects.create(
            project_type='non_infrastructure',
            created_by_user=self.mayor_user,
        )
        self.non_infrastructure = NonInfrastructureProject.objects.create(
            project=noninfra_base,
            title='Employee Submission Program',
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
        revision = ProjectRevision.objects.get(
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
            self.head,
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
        revision = ProjectRevision.objects.get(
            project=self.non_infrastructure.project,
        )
        self.assertEqual(revision.status, PublicationStatus.PENDING_REVIEW)
        self.assertEqual(
            revision.snapshot['non_infrastructure']['title'],
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


class OfficeHeadPublicationReviewViewTests(TestCase):
    def setUp(self):
        self.head = User.objects.create_user(username='review-head', is_staff=True)
        UserRole.objects.create(user=self.head, department='engineer', role='head')
        self.employee = User.objects.create_user(
            username='review-queue-employee',
            password='password123',
            is_staff=True,
        )
        UserRole.objects.create(user=self.employee, department='engineer')
        self.admin = User.objects.create_superuser(
            username='review-queue-admin',
            email='review-queue-admin@example.com',
            password='password123',
        )
        project = Project.objects.create(
            project_type='infrastructure',
            created_by_user=self.employee,
        )
        self.infrastructure = InfrastructureProject.objects.create(
            project=project,
            title='Submitted Admin Preview Project',
            description='Snapshot reviewed by the administrator.',
            award_status='pre_construction',
        )
        ProjectImage.objects.create(
            project=project,
            image_url='/media/projects/admin-review-cover.jpg',
            is_cover=True,
        )
        self.revision = submit_project_for_review(project, self.employee)

    def test_head_queue_and_detail_show_submitted_snapshot(self):
        self.infrastructure.title = 'Later Working Copy Edit'
        self.infrastructure.save(update_fields=['title'])
        self.client.force_login(self.head)

        queue = self.client.get(reverse('publication_review_queue'))
        self.client.force_login(self.admin)
        dashboard = self.client.get(reverse('admin_dashboard'))
        self.client.force_login(self.head)
        detail = self.client.get(reverse(
            'publication_revision_detail',
            args=[self.revision.pk],
        ))

        self.assertContains(queue, 'Submitted Admin Preview Project')
        self.assertContains(queue, 'Pending Review')
        self.assertContains(dashboard, 'Publication Lifecycle')
        self.assertEqual(
            dashboard.context['approved_revisions'],
            0,
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
            '/static/css/templates/core/publication_review.css?v=20260912-1',
        )
        self.assertContains(
            detail,
            '/static/css/components/publication_workflow.css?v=20260821-1',
        )

    def test_head_can_open_working_project_without_management_access(self):
        self.client.force_login(self.head)
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
        self.assertNotContains(working, 'Edit Project')
        self.assertNotContains(working, 'Delete Project')
        self.assertEqual(self.client.post(reverse('engineering_projects:project_update', args=[self.infrastructure.pk]), {}).status_code, 403)
        self.assertEqual(project_list.status_code, 200)
        self.assertRedirects(dashboard, reverse('engineering_head_dashboard'))

    def test_staff_cannot_access_review_actions(self):
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
        self.client.force_login(self.head)
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

    def test_head_approves_and_publishes_without_manual_archival(self):
        self.client.force_login(self.head)
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

        operational_response = self.client.post(
            reverse(
                'engineering_projects:project_operations',
                args=[self.infrastructure.pk],
            ),
            {
                'award_status': 'pre_construction',
                'physical_progress_percentage': '0',
                'cost_progress_percentage': '',
                'from_review': str(self.revision.pk),
            },
        )
        self.assertRedirects(
            operational_response,
            reverse(
                'publication_revision_detail',
                args=[self.revision.pk],
            ),
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
        self.client.force_login(self.head)
        self.assertEqual(self.client.get(publish_url).status_code, 405)

        self.client.post(publish_url)
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.status, PublicationStatus.PUBLISHED)
        self.assertTrue(self.revision.is_current_public)
        public = self.client.get(reverse('public_dashboard'))
        self.assertContains(public, 'Submitted Admin Preview Project')

        self.assertEqual(self.client.post(archive_url).status_code, 403)
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.status, PublicationStatus.PUBLISHED)
        self.assertTrue(self.revision.is_current_public)
        public = self.client.get(reverse('public_dashboard'))
        self.assertContains(public, 'Submitted Admin Preview Project')


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
        UserRole.objects.create(user=self.engineer, department='engineer')
        self.mayor = User.objects.create_user(
            username='dashboard-access-mayor',
            password='password123',
            is_staff=True,
        )
        UserRole.objects.create(user=self.mayor, department='mayor')

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
        infrastructure = InfrastructureProject.objects.create(
            project=project,
            infrastructure_code='INF-001',
            title='Barangay Road Rehabilitation',
            description='Rehabilitation description.',
            category=category,
            address=address,
            contractor=contractor,
            implementing_office=office,
            procurement_method='competitive_bidding',
            award_status='pre_construction',
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
        FinancialRecord.objects.create(
            infrastructure=infrastructure,
            fund_source=fund_source,
            approved_budget=Decimal('2500000.00'),
            bid_amount=Decimal('2400000.00'),
            actual_expenditure=Decimal('500000.00'),
        )
        InfrastructureSchedule.objects.create(
            infrastructure=infrastructure,
            posting_date=date(2025, 12, 1),
            actual_start_date=date(2026, 1, 20),
            duration_days=180,
        )
        ProjectInspection.objects.create(
            project=project,
            inspection_date=date(2026, 4, 15),
            inspected_by_user=self.user,
            completion_percentage=Decimal('55.25'),
            findings='Work is on schedule.',
        )
        ProjectImage.objects.create(
            project=project,
            image_url='/media/projects/road-cover.jpg',
            is_cover=True,
        )
        ProjectImage.objects.create(
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
        non_infrastructure = NonInfrastructureProject.objects.create(
            project=project,
            title='Community Health Day',
            category=category,
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
        ProjectImage.objects.create(
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
        self.infrastructure = InfrastructureProject.objects.create(
            project=self.project,
            title='Image Retention Project',
        )

    def test_revision_referenced_image_is_retired_not_deleted(self):
        image = ProjectImage.objects.create(
            project=self.project,
            image_url='/media/projects/published-cover.jpg',
            is_cover=True,
        )
        ProjectRevision.objects.create(
            project=self.project,
            revision_number=1,
            snapshot={
                'images': [{
                    'id': image.pk,
                    'url': image.image_url,
                    'is_cover': True,
                }],
            },
        )

        result = retire_project_images(self.project, [image.pk])

        self.assertEqual(result, {'retired': 1, 'deleted': 0})
        self.assertFalse(ProjectImage.objects.filter(pk=image.pk).exists())
        retained = ProjectImage.all_objects.get(pk=image.pk)
        self.assertFalse(retained.is_active)
        self.assertFalse(retained.is_cover)
        self.assertIsNotNone(retained.removed_at)
        self.assertEqual(
            retained.image_url,
            '/media/projects/published-cover.jpg',
        )

    def test_unreferenced_image_metadata_is_deleted(self):
        image = ProjectImage.objects.create(
            project=self.project,
            image_url='/media/projects/unused.jpg',
        )

        result = retire_project_images(self.project, [image.pk])

        self.assertEqual(result, {'retired': 0, 'deleted': 1})
        self.assertFalse(
            ProjectImage.all_objects.filter(pk=image.pk).exists(),
        )

    def test_new_snapshots_exclude_retired_images(self):
        retained_image = ProjectImage.objects.create(
            project=self.project,
            image_url='/media/projects/old-version.jpg',
        )
        active_image = ProjectImage.objects.create(
            project=self.project,
            image_url='/media/projects/current-version.jpg',
            is_cover=True,
        )
        ProjectRevision.objects.create(
            project=self.project,
            revision_number=1,
            snapshot={
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
        self.infrastructure = InfrastructureProject.objects.create(
            project=base_project,
            title='Normalized Road Project',
            description='Connected through normalized data.',
            category=category,
            address=address,
            contractor=contractor,
            implementing_office=office,
            procurement_method='competitive_bidding',
            award_status='pre_construction',
            planned_start_date='2026-01-15',
            planned_end_date='2026-08-30',
            cost_progress_percentage=42,
            physical_progress_percentage=55,
        )
        FinancialRecord.objects.create(
            infrastructure=self.infrastructure,
            fund_source=fund_source,
            approved_budget=2500000,
            bid_amount=2400000,
        )
        InfrastructureSchedule.objects.create(
            infrastructure=self.infrastructure,
            actual_start_date='2026-01-20',
        )
        ProjectInspection.objects.create(
            project=base_project,
            inspection_date='2026-04-15',
            inspected_by_user=self.user,
            completion_percentage=55.25,
            findings='Work is on schedule.',
            remarks='Continue regular monitoring.',
        )
        ProjectImage.objects.create(
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
        registry_response = self.client.get(
            reverse('public_dashboard'),
            {'type': 'infra'},
        )
        self.assertContains(
            registry_response,
            'label="Infrastructure Categories"',
        )
        self.assertNotContains(
            registry_response,
            'label="Non-Infrastructure Categories"',
        )
        self.assertContains(
            registry_response,
            'data-project-category-type="infra"',
        )

    def test_view_all_registries_are_isolated_by_project_type(self):
        noninfra_project = Project.objects.create(
            project_type='non_infrastructure',
            created_by_user=self.user,
            updated_by_user=self.user,
        )
        noninfra_category = NonInfrastructureCategory.objects.create(
            type_code='community-test',
            type_name='Community Test',
        )
        NonInfrastructureProject.objects.create(
            project=noninfra_project,
            title='Published Community Program',
            category=noninfra_category,
            status='planned',
        )
        publish_current_snapshot(noninfra_project)

        infrastructure = self.client.get(
            reverse('public_dashboard'),
            {'type': 'infra'},
        )
        noninfrastructure = self.client.get(
            reverse('public_dashboard'),
            {'type': 'noninfra'},
        )

        self.assertEqual(
            {row['category'] for row in infrastructure.context['project_rows']},
            {'infra'},
        )
        self.assertContains(infrastructure, 'data-project-type="infra"')
        self.assertContains(infrastructure, 'label="Infrastructure Categories"')
        self.assertNotContains(infrastructure, 'label="Non-Infrastructure Categories"')
        self.assertNotContains(infrastructure, 'class="tab-buttons"')
        self.assertNotContains(infrastructure, 'Published Community Program')

        self.assertEqual(
            {row['category'] for row in noninfrastructure.context['project_rows']},
            {'noninfra'},
        )
        self.assertContains(noninfrastructure, 'data-project-type="noninfra"')
        self.assertContains(noninfrastructure, 'label="Non-Infrastructure Categories"')
        self.assertNotContains(noninfrastructure, 'label="Infrastructure Categories"')
        self.assertNotContains(noninfrastructure, 'class="tab-buttons"')
        self.assertNotContains(noninfrastructure, 'Normalized Road Project')

        for response in (infrastructure, noninfrastructure):
            self.assertContains(response, 'data-dashboard-view="detail"')
            self.assertContains(response, 'data-dashboard-view="card"')
            self.assertContains(response, 'id="project-search"')
            self.assertContains(response, 'id="location-filter"')
            self.assertContains(response, 'class="status-buttons"')

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
        self.assertContains(response, '<span>Category</span>', html=False)
        self.assertContains(response, '<strong>Road Test</strong>', html=False)
        self.assertContains(response, 'Inspection Details')
        self.assertContains(response, 'April 15, 2026')
        self.assertContains(response, '55.3%')
        self.assertContains(response, 'Work is on schedule.')
        self.assertContains(response, 'Continue regular monitoring.')
        self.assertContains(response, 'infrastructure-dashboard-author')
        self.assertEqual(
            response.context['public_project']['inspection'][
                'inspection_date'
            ],
            date(2026, 4, 15),
        )
        self.assertEqual(
            response.context['public_project']['inspection'][
                'completion_percentage'
            ],
            Decimal('55.25'),
        )
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

    def test_public_infrastructure_detail_hides_missing_inspection(self):
        snapshot = self.public_revision.snapshot
        snapshot['inspection'] = None
        self.public_revision.snapshot = snapshot
        self.public_revision.save(update_fields=['snapshot'])

        response = self.client.get(reverse(
            'public_infrastructure_project_detail',
            args=[self.infrastructure.pk],
        ))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Inspection Details')

    def test_public_infrastructure_detail_handles_missing_coordinates(self):
        snapshot = self.public_revision.snapshot
        snapshot['infrastructure']['address']['latitude'] = None
        snapshot['infrastructure']['address']['longitude'] = None
        self.public_revision.snapshot = snapshot
        self.public_revision.save(update_fields=['snapshot'])

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
        self.infrastructure.title = 'Unapproved Edited Title'
        self.infrastructure.physical_progress_percentage = 99
        self.infrastructure.save(update_fields=[
            'title',
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
        unpublished = InfrastructureProject.objects.create(
            project=project,
            title='Internal Draft Project',
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
            noninfra = NonInfrastructureProject.objects.create(
                project=project,
                title=name,
                status=status,
            )

            if status == 'ongoing':
                ProjectImage.objects.create(
                    project=noninfra.project,
                    image_url='/media/projects/ongoing-cover.jpg',
                    is_cover=True,
                )
                ProjectImage.objects.create(
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
            args=[NonInfrastructureProject.objects.get(status='ongoing').pk],
        )
        self.assertNotContains(response, mayor_detail_url)
        self.assertContains(response, 'data-project-modal-trigger', count=3)

    def test_public_non_infrastructure_detail_is_available_without_login(self):
        project = NonInfrastructureProject.objects.get(status='ongoing')
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
        self.assertContains(response, project.title)
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
        self.assertEqual(_department_for_user(user), 'admin')


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

        user = form.save(commit=True)

        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.role_assignment.department, 'engineer')

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

        user = form.save(commit=True)

        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.role_assignment.department, 'mayor')


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
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
        self.assertEqual(created_user.role_assignment.department, 'mayor')
        self.assertFalse(created_user.has_usable_password())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [created_user.email])
        self.assertIn('/account-setup/', mail.outbox[0].body)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    LOGIN_OTP_ENABLED=True,
    LOGIN_OTP_TIMEOUT=300,
    LOGIN_OTP_MAX_ATTEMPTS=5,
    LOGIN_OTP_RESEND_COOLDOWN=60,
    LOGIN_OTP_RATE_LIMIT=5,
    LOGIN_OTP_RATE_WINDOW=900,
)
class AccountSetupFlowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='setup-admin',
            email='setup-admin@example.com',
            password='AdminPass!2026',
        )
        self.client.force_login(self.admin)

    def _create_pending_user(self, username='new-employee'):
        session = self.client.session
        session['user_create_form_data'] = {
            'username': username,
            'email': f'{username}@example.com',
            'first_name': 'New',
            'last_name': 'Employee',
            'role': 'engineering',
        }
        session.save()
        response = self.client.post(
            reverse('user_create_confirm'),
            follow=True,
        )
        return User.objects.get(username=username), response

    def _setup_path(self, email_index=-1):
        match = re.search(
            r'http://testserver(?P<path>/account-setup/[^\s]+)',
            mail.outbox[email_index].body,
        )
        self.assertIsNotNone(match)
        return match.group('path')

    def _complete_setup(self, password='EmployeeSecurePass!2026'):
        initial_path = self._setup_path()
        redirect_response = self.client.get(initial_path)
        self.assertRedirects(
            redirect_response,
            redirect_response.url,
            fetch_redirect_response=False,
        )
        response = self.client.post(
            redirect_response.url,
            {
                'new_password1': password,
                'new_password2': password,
            },
            follow=True,
        )
        return initial_path, response

    def test_admin_creation_sends_setup_email_without_password(self):
        user, response = self._create_pending_user()

        self.assertRedirects(response, reverse('user_list'))
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.role_assignment.department, 'engineer')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        self.assertIn('Set up your Municipality Project Tracker account', mail.outbox[0].subject)
        self.assertNotContains(response, 'Temporary password')
        self.assertContains(response, 'Setup Pending')
        self.assertContains(response, 'Resend Setup')

    def test_setup_email_failure_rolls_back_account_creation(self):
        session = self.client.session
        session['user_create_form_data'] = {
            'username': 'delivery-failure',
            'email': 'delivery-failure@example.com',
            'first_name': 'Delivery',
            'last_name': 'Failure',
            'role': 'engineering',
        }
        session.save()

        with patch(
            'apps.system.views.send_account_setup_email',
            side_effect=AccountSetupDeliveryError,
        ):
            response = self.client.post(
                reverse('user_create_confirm'),
                follow=True,
            )

        self.assertFalse(User.objects.filter(username='delivery-failure').exists())
        self.assertContains(response, 'setup email could not be sent')
        self.assertIn('user_create_form_data', self.client.session)

    def test_pending_account_cannot_login_before_setup(self):
        user, _ = self._create_pending_user()
        self.client.logout()
        mail.outbox.clear()

        response = self.client.post(
            reverse('login'),
            {'username': user.username, 'password': 'AnyPassword!2026'},
        )

        self.assertContains(response, 'Invalid credentials')
        self.assertEqual(len(mail.outbox), 0)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_setup_validators_reject_weak_password(self):
        user, _ = self._create_pending_user()
        initial_path = self._setup_path()
        redirect_response = self.client.get(initial_path)

        response = self.client.post(
            redirect_response.url,
            {'new_password1': 'password', 'new_password2': 'password'},
        )

        self.assertContains(response, 'This password is too common.')
        user.refresh_from_db()
        self.assertFalse(user.has_usable_password())

    def test_valid_setup_is_one_time_then_login_requires_otp(self):
        user, _ = self._create_pending_user()
        initial_path, response = self._complete_setup()

        self.assertRedirects(response, reverse('account_setup_complete'))
        user.refresh_from_db()
        self.assertTrue(user.check_password('EmployeeSecurePass!2026'))
        reused = self.client.get(initial_path, follow=True)
        self.assertContains(reused, 'Invalid or Expired Setup Link')

        self.client.logout()
        mail.outbox.clear()
        login_response = self.client.post(
            reverse('login'),
            {
                'username': user.username,
                'password': 'EmployeeSecurePass!2026',
            },
        )
        self.assertRedirects(
            login_response,
            reverse('login_otp_verify'),
            fetch_redirect_response=False,
        )
        self.assertNotIn('_auth_user_id', self.client.session)
        otp_match = re.search(r'\b(\d{6})\b', mail.outbox[-1].body)
        self.assertIsNotNone(otp_match)
        otp_response = self.client.post(
            reverse('login_otp_verify'),
            {'code': otp_match.group(1)},
        )
        self.assertRedirects(
            otp_response,
            reverse('engineering_dashboard'),
            fetch_redirect_response=False,
        )
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_invalid_and_expired_setup_links_are_rejected(self):
        _, _ = self._create_pending_user()
        setup_path = self._setup_path()
        invalid_path = setup_path.rsplit('/', 2)[0] + '/invalid-token/'

        invalid_response = self.client.get(invalid_path)
        self.assertContains(invalid_response, 'Invalid or Expired Setup Link')

        with override_settings(PASSWORD_RESET_TIMEOUT=-1):
            expired_response = self.client.get(setup_path)
        self.assertContains(expired_response, 'Invalid or Expired Setup Link')

    def test_resend_invalidates_previous_setup_link(self):
        user, _ = self._create_pending_user()
        original_path = self._setup_path()

        response = self.client.post(
            reverse('user_resend_account_setup', args=[user.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('user_list'))
        self.assertEqual(len(mail.outbox), 2)
        replacement_path = self._setup_path(email_index=1)
        self.assertContains(
            self.client.get(original_path),
            'Invalid or Expired Setup Link',
        )
        replacement_response = self.client.get(replacement_path)
        self.assertRedirects(
            replacement_response,
            replacement_response.url,
            fetch_redirect_response=False,
        )


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class PublicPasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='reset-user',
            email='reset-user@example.com',
            password='OriginalPass!2026',
            is_staff=True,
        )

        UserRole.objects.create(user=self.user, department='engineer', role='staff')

    def _request_reset(self, email=None):
        return self.client.post(
            reverse('password_reset'),
            {'email': email or self.user.email},
            follow=True,
        )

    def _reset_path_from_email(self):
        match = re.search(
            r'http://testserver(?P<path>/reset-password/[^\s]+)',
            mail.outbox[0].body,
        )
        self.assertIsNotNone(match)
        return match.group('path')

    def test_login_links_to_forgot_password_form(self):
        response = self.client.get(reverse('login'))

        self.assertContains(response, reverse('password_reset'))
        self.assertContains(response, 'Forgot Password?')

    def test_request_uses_generic_confirmation_for_known_email(self):
        response = self._request_reset()

        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertContains(
            response,
            'If an account exists for this email address, password reset '
            'instructions have been sent.',
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn('reset-password/', mail.outbox[0].body)

    def test_request_uses_same_confirmation_for_unknown_email(self):
        response = self._request_reset('unknown@example.com')

        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertContains(
            response,
            'If an account exists for this email address, password reset '
            'instructions have been sent.',
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_password_validators_reject_weak_new_password(self):
        self._request_reset()
        initial_path = self._reset_path_from_email()
        redirect_response = self.client.get(initial_path)
        self.assertRedirects(
            redirect_response,
            redirect_response.url,
            fetch_redirect_response=False,
        )

        response = self.client.post(
            redirect_response.url,
            {
                'new_password1': 'password',
                'new_password2': 'password',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This password is too common.')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OriginalPass!2026'))
        self.assertFalse(hasattr(self.user, 'password_changes'))

    def test_reset_changes_password_invalidates_link_and_allows_login(self):
        self._request_reset()
        initial_path = self._reset_path_from_email()
        redirect_response = self.client.get(initial_path)

        response = self.client.post(
            redirect_response.url,
            {
                'new_password1': 'UpdatedSecurePass!2026',
                'new_password2': 'UpdatedSecurePass!2026',
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('password_reset_complete'))
        self.assertContains(response, 'Password Successfully Changed')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('UpdatedSecurePass!2026'))
        self.assertFalse(self.user.check_password('OriginalPass!2026'))

        reused_link = self.client.get(initial_path, follow=True)
        self.assertContains(reused_link, 'Invalid or Expired Link')
        self.assertFalse(hasattr(self.user, 'password_changes'))

        login_response = self.client.post(reverse('login'), {
            'username': self.user.username,
            'password': 'UpdatedSecurePass!2026',
        })
        self.assertRedirects(
            login_response,
            reverse('login_otp_verify'),
            fetch_redirect_response=False,
        )
        self.assertNotIn('_auth_user_id', self.client.session)

        otp_match = re.search(r'\b(\d{6})\b', mail.outbox[-1].body)
        self.assertIsNotNone(otp_match)
        otp_response = self.client.post(
            reverse('login_otp_verify'),
            {'code': otp_match.group(1)},
        )
        self.assertRedirects(
            otp_response,
            reverse('engineering_dashboard'),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            int(self.client.session['_auth_user_id']),
            self.user.pk,
        )

    def test_admin_password_history_and_reset_routes_are_removed(self):
        admin = User.objects.create_superuser(
            username='admin-user',
            email='admin@example.com',
            password='AdminPass!2026',
        )
        self.client.force_login(admin)

        for path in (
            '/password-history/',
            f'/users/{self.user.pk}/password-history/',
            f'/users/{self.user.pk}/reset-password/',
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

        response = self.client.get(reverse('user_list'))
        self.assertNotContains(response, 'History')
        self.assertNotContains(response, 'Reset Password')


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    LOGIN_OTP_ENABLED=True,
    LOGIN_OTP_TIMEOUT=300,
    LOGIN_OTP_MAX_ATTEMPTS=5,
    LOGIN_OTP_RESEND_COOLDOWN=60,
    LOGIN_OTP_RATE_LIMIT=5,
    LOGIN_OTP_RATE_WINDOW=900,
)
class LoginOTPTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='otp-user',
            email='otp-user@example.com',
            password='ValidLoginPass!2026',
            is_staff=True,
        )
        UserRole.objects.update_or_create(
            user=self.user,
            defaults={'department': 'engineer'},
        )

    def _start_login(self):
        return self.client.post(reverse('login'), {
            'username': self.user.username,
            'password': 'ValidLoginPass!2026',
        })

    def _emailed_code(self, index=-1):
        match = re.search(r'\b(\d{6})\b', mail.outbox[index].body)
        self.assertIsNotNone(match)
        return match.group(1)

    @override_settings(LOGIN_OTP_ENABLED=False)
    def test_disabled_otp_logs_in_without_email_and_clears_pending_challenge(self):
        self.user.email = ''
        self.user.save(update_fields=['email'])
        session = self.client.session
        session['pending_login_otp_challenge'] = 'stale-challenge'
        session.save()

        response = self._start_login()

        self.assertRedirects(response, reverse('engineering_dashboard'),
                             fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)
        self.assertNotIn('pending_login_otp_challenge', self.client.session)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(LoginOTPChallenge.objects.exists())

    @override_settings(LOGIN_OTP_ENABLED=False)
    def test_disabled_otp_still_rejects_invalid_or_unauthorized_accounts(self):
        for changes in ({'password': 'wrong'}, {'is_active': False}, {'is_staff': False}):
            with self.subTest(changes=changes):
                self.user.set_password('ValidLoginPass!2026')
                self.user.is_active = True
                self.user.is_staff = True
                for key, value in changes.items():
                    if key == 'password':
                        self.user.set_password(value)
                    else:
                        setattr(self.user, key, value)
                self.user.save()
                response = self._start_login()
                self.assertEqual(response.status_code, 200)
                self.assertNotIn('_auth_user_id', self.client.session)
                self.assertEqual(len(mail.outbox), 0)
                self.assertFalse(LoginOTPChallenge.objects.exists())

    def test_valid_credentials_send_hashed_otp_without_authenticating(self):
        response = self._start_login()

        self.assertRedirects(
            response,
            reverse('login_otp_verify'),
            fetch_redirect_response=False,
        )
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(len(mail.outbox), 1)
        code = self._emailed_code()
        challenge = LoginOTPChallenge.objects.get()
        self.assertNotEqual(challenge.code_hash, code)
        self.assertNotIn(code, challenge.code_hash)
        self.assertEqual(challenge.attempts_remaining, 5)

    def test_correct_code_is_one_time_and_starts_authenticated_session(self):
        self._start_login()
        code = self._emailed_code()

        response = self.client.post(
            reverse('login_otp_verify'),
            {'code': code},
        )

        self.assertRedirects(
            response,
            reverse('engineering_dashboard'),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            int(self.client.session['_auth_user_id']),
            self.user.pk,
        )
        challenge = LoginOTPChallenge.objects.get()
        self.assertIsNotNone(challenge.consumed_at)
        self.client.logout()
        reused = self.client.post(
            reverse('login_otp_verify'),
            {'code': code},
        )
        self.assertContains(reused, 'Invalid or expired verification code.')

    def test_five_invalid_attempts_lock_the_challenge(self):
        self._start_login()

        for _ in range(5):
            response = self.client.post(
                reverse('login_otp_verify'),
                {'code': '000000'},
            )
            self.assertContains(
                response,
                'Invalid or expired verification code.',
            )

        challenge = LoginOTPChallenge.objects.get()
        self.assertEqual(challenge.attempts_remaining, 0)
        self.assertIsNotNone(challenge.consumed_at)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_expired_challenge_cannot_authenticate(self):
        self._start_login()
        code = self._emailed_code()
        LoginOTPChallenge.objects.update(
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        response = self.client.post(
            reverse('login_otp_verify'),
            {'code': code},
        )

        self.assertContains(response, 'Invalid or expired verification code.')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_resend_cooldown_does_not_generate_another_code(self):
        self._start_login()

        response = self.client.post(
            reverse('login_otp_resend'),
            follow=True,
        )

        self.assertContains(response, 'Please wait before requesting another code.')
        self.assertEqual(LoginOTPChallenge.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(LOGIN_OTP_RESEND_COOLDOWN=0)
    def test_resend_invalidates_previous_code(self):
        self._start_login()
        first_code = self._emailed_code()
        first_challenge = LoginOTPChallenge.objects.get()

        response = self.client.post(reverse('login_otp_resend'))

        self.assertRedirects(
            response,
            reverse('login_otp_verify'),
            fetch_redirect_response=False,
        )
        first_challenge.refresh_from_db()
        self.assertIsNotNone(first_challenge.consumed_at)
        self.assertEqual(LoginOTPChallenge.objects.count(), 2)
        self.assertNotEqual(first_code, self._emailed_code())

    @override_settings(
        LOGIN_OTP_RESEND_COOLDOWN=0,
        LOGIN_OTP_RATE_LIMIT=2,
    )
    def test_generation_rate_limit_blocks_excess_resends(self):
        self._start_login()
        self.client.post(reverse('login_otp_resend'))

        response = self.client.post(
            reverse('login_otp_resend'),
            follow=True,
        )

        self.assertContains(
            response,
            'Too many verification codes requested. Please try again later.',
        )
        self.assertEqual(LoginOTPChallenge.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 2)
