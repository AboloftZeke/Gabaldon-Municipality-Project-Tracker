from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from .models import (
    NonInfrastructureCategory,
    Non_Infrastructure_Project,
    Project,
    Project_Inspection,
    ProjectPublicationRevision,
    UserFlag,
)
from .publication_service import create_head_operational_revision
from .publication_snapshots import build_project_publication_snapshot
from .publication_workflow import PublicationStatus


class HeadOperationalRevisionTests(TestCase):
    def setUp(self):
        self.users = {}
        for department, role in [
            ('engineer', 'staff'), ('engineer', 'head'),
            ('mayor', 'staff'), ('mayor', 'head'),
        ]:
            user = User.objects.create_user(
                username=f'{department}-{role}',
                is_staff=True,
            )
            UserFlag.objects.create(
                user=user,
                department=department,
                role=role,
            )
            self.users[department, role] = user
        self.admin = User.objects.create_superuser('admin')

        from apps.infrastructure.tests import InfrastructureProjectFormTests

        fixture = InfrastructureProjectFormTests()
        fixture.setUp()
        self.infrastructure = fixture.create_project()
        self.infrastructure.award_status = 'awarded'
        self.infrastructure.physical_progress_percentage = Decimal('25')
        self.infrastructure.cost_progress_percentage = Decimal('20')
        self.infrastructure.planned_start_date = date.today() - timedelta(days=5)
        self.infrastructure.planned_end_date = date.today() + timedelta(days=5)
        self.infrastructure.save()
        self.inspection = Project_Inspection.objects.create(
            project=self.infrastructure.project,
            inspection_date=date.today(),
            completion_percentage=Decimal('30'),
        )
        self.infrastructure_public = self._publish_current(
            self.infrastructure.project,
        )

        self.category = NonInfrastructureCategory.objects.create(
            type_code='head-revision',
            type_name='Head Revision',
        )
        base = Project.objects.create(
            project_type='non_infrastructure',
            created_by_user=self.users['mayor', 'staff'],
        )
        self.non_infrastructure = Non_Infrastructure_Project.objects.create(
            project=base,
            non_infra_name='Community Program',
            description='Published description',
            status='planned',
            non_infra_category=self.category,
        )
        self.non_infrastructure_public = self._publish_current(base)

    def _publish_current(self, project):
        return ProjectPublicationRevision.objects.create(
            project=project,
            revision_number=1,
            status=PublicationStatus.PUBLISHED,
            is_current_public_revision=True,
            snapshot_data=build_project_publication_snapshot(project),
        )

    def test_infrastructure_update_creates_approved_snapshot_without_republishing(self):
        previous_snapshot = deepcopy(self.infrastructure_public.snapshot_data)
        self.client.force_login(self.users['engineer', 'head'])
        response = self.client.post(reverse(
            'engineering_projects:project_operations',
            args=[self.infrastructure.pk],
        ), {
            'award_status': 'completed',
            'physical_progress_percentage': '60',
            'cost_progress_percentage': '55',
            'inspection_completion_percentage': '70',
        })
        self.assertEqual(response.status_code, 302)

        revision = self.infrastructure.project.publication_revisions.get(
            status=PublicationStatus.APPROVED,
        )
        self.assertEqual(revision.revision_number, 2)
        self.assertEqual(revision.supersedes_revision, self.infrastructure_public)
        self.assertEqual(revision.submitted_by, self.users['engineer', 'head'])
        self.assertEqual(revision.reviewed_by, self.users['engineer', 'head'])
        self.assertFalse(revision.is_current_public_revision)
        self.assertIsNone(revision.published_at)
        self.assertEqual(
            revision.snapshot_data['infrastructure']['award_status'],
            'completed',
        )
        self.assertEqual(
            revision.snapshot_data['infrastructure']['physical_progress_percentage'],
            '60.00',
        )
        self.assertEqual(
            revision.snapshot_data['infrastructure']['cost_progress_percentage'],
            '55.00',
        )
        self.assertEqual(
            revision.snapshot_data['inspection']['completion_percentage'],
            '70.00',
        )

        self.infrastructure_public.refresh_from_db()
        self.assertEqual(self.infrastructure_public.status, PublicationStatus.PUBLISHED)
        self.assertTrue(self.infrastructure_public.is_current_public_revision)
        self.assertEqual(self.infrastructure_public.snapshot_data, previous_snapshot)
        public_response = self.client.get(reverse(
            'public_infrastructure_project_detail',
            args=[self.infrastructure.pk],
        ))
        self.assertEqual(public_response.status_code, 200)
        public_project = public_response.context['public_project']
        self.assertEqual(public_project['award_status'], 'awarded')
        self.assertEqual(public_project['physical_progress_percentage'], Decimal('25.00'))

        preview = self.client.get(reverse(
            'publication_revision_detail',
            args=[revision.pk],
        ))
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.context['comparison']['baseline'], self.infrastructure_public)
        changed = {
            (section['label'], field['path'])
            for section in preview.context['comparison']['sections']
            for field in section['fields']
            if field['changed']
        }
        self.assertIn(('Project Information', 'award_status'), changed)
        self.assertIn(
            ('Project Information', 'physical_progress_percentage'),
            changed,
        )
        self.assertIn(
            ('Project Information', 'cost_progress_percentage'),
            changed,
        )
        self.assertIn(('Latest Inspection', 'completion_percentage'), changed)
        self.assertContains(preview, 'Replaces public revision')
        self.assertContains(preview, 'Publish Update to Public Dashboard')

        publish_response = self.client.post(reverse(
            'publication_revision_publish',
            args=[revision.pk],
        ))
        self.assertEqual(publish_response.status_code, 302)
        revision.refresh_from_db()
        self.infrastructure_public.refresh_from_db()
        self.assertEqual(revision.status, PublicationStatus.PUBLISHED)
        self.assertTrue(revision.is_current_public_revision)
        self.assertEqual(
            self.infrastructure_public.status,
            PublicationStatus.ARCHIVED,
        )
        self.assertFalse(self.infrastructure_public.is_current_public_revision)
        public_response = self.client.get(reverse(
            'public_infrastructure_project_detail',
            args=[self.infrastructure.pk],
        ))
        public_project = public_response.context['public_project']
        self.assertEqual(public_project['award_status'], 'completed')
        self.assertEqual(public_project['physical_progress_percentage'], Decimal('60.00'))
        self.assertEqual(public_project['cost_progress_percentage'], Decimal('55.00'))
        self.assertEqual(
            public_project['inspection']['completion_percentage'],
            Decimal('70.00'),
        )

    def test_non_infrastructure_update_creates_approved_snapshot_without_republishing(self):
        previous_snapshot = deepcopy(self.non_infrastructure_public.snapshot_data)
        self.client.force_login(self.users['mayor', 'head'])
        response = self.client.post(reverse(
            'mayor_projects:non_infrastructure_project_operations',
            args=[self.non_infrastructure.pk],
        ), {'status': 'completed'})
        self.assertEqual(response.status_code, 302)

        revision = self.non_infrastructure.project.publication_revisions.get(
            status=PublicationStatus.APPROVED,
        )
        self.assertEqual(revision.supersedes_revision, self.non_infrastructure_public)
        self.assertEqual(
            revision.snapshot_data['non_infrastructure']['status'],
            'completed',
        )
        self.assertFalse(revision.is_current_public_revision)
        self.non_infrastructure_public.refresh_from_db()
        self.assertTrue(self.non_infrastructure_public.is_current_public_revision)
        self.assertEqual(self.non_infrastructure_public.snapshot_data, previous_snapshot)
        public_response = self.client.get(reverse(
            'public_non_infrastructure_project_detail',
            args=[self.non_infrastructure.pk],
        ))
        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(public_response.context['public_project']['status'], 'planned')

        preview = self.client.get(reverse(
            'publication_revision_detail',
            args=[revision.pk],
        ))
        self.assertEqual(preview.context['comparison']['baseline'], self.non_infrastructure_public)
        changed = {
            (section['label'], field['path'])
            for section in preview.context['comparison']['sections']
            for field in section['fields']
            if field['changed']
        }
        self.assertIn(('Program Information', 'status'), changed)
        self.assertContains(preview, 'Publish Update to Public Dashboard')
        self.assertEqual(self.client.post(reverse(
            'publication_revision_publish',
            args=[revision.pk],
        )).status_code, 302)
        revision.refresh_from_db()
        self.non_infrastructure_public.refresh_from_db()
        self.assertTrue(revision.is_current_public_revision)
        self.assertEqual(
            self.non_infrastructure_public.status,
            PublicationStatus.ARCHIVED,
        )
        public_response = self.client.get(reverse(
            'public_non_infrastructure_project_detail',
            args=[self.non_infrastructure.pk],
        ))
        self.assertEqual(
            public_response.context['public_project']['status'],
            'completed',
        )

    def test_never_published_update_changes_working_data_without_revision(self):
        project = Project.objects.create(project_type='non_infrastructure')
        unpublished = Non_Infrastructure_Project.objects.create(
            project=project,
            non_infra_name='Unpublished Program',
            status='planned',
            non_infra_category=self.category,
        )
        self.client.force_login(self.users['mayor', 'head'])
        response = self.client.post(reverse(
            'mayor_projects:non_infrastructure_project_operations',
            args=[unpublished.pk],
        ), {'status': 'ongoing'})
        self.assertEqual(response.status_code, 302)
        unpublished.refresh_from_db()
        self.assertEqual(unpublished.status, 'ongoing')
        self.assertFalse(project.publication_revisions.exists())

    def test_service_rejects_wrong_roles_without_creating_a_revision(self):
        original_count = self.infrastructure.project.publication_revisions.count()
        for actor in [
            self.users['engineer', 'staff'],
            self.users['mayor', 'head'],
            self.admin,
        ]:
            with self.subTest(actor=actor.username):
                with self.assertRaises(PermissionDenied):
                    create_head_operational_revision(
                        self.infrastructure.project,
                        actor,
                    )
                self.assertEqual(
                    self.infrastructure.project.publication_revisions.count(),
                    original_count,
                )

    def test_active_staff_revision_blocks_update_and_rolls_back_working_data(self):
        pending = ProjectPublicationRevision.objects.create(
            project=self.infrastructure.project,
            revision_number=2,
            status=PublicationStatus.PENDING_REVIEW,
            snapshot_data=build_project_publication_snapshot(
                self.infrastructure.project,
            ),
            submitted_by=self.users['engineer', 'staff'],
        )
        before_snapshot = deepcopy(pending.snapshot_data)
        self.client.force_login(self.users['engineer', 'head'])
        response = self.client.post(reverse(
            'engineering_projects:project_operations',
            args=[self.infrastructure.pk],
        ), {
            'award_status': 'completed',
            'physical_progress_percentage': '80',
            'cost_progress_percentage': '75',
            'inspection_completion_percentage': '90',
        })
        self.assertEqual(response.status_code, 409)
        self.infrastructure.refresh_from_db()
        self.inspection.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(self.infrastructure.award_status, 'awarded')
        self.assertEqual(self.infrastructure.physical_progress_percentage, Decimal('25'))
        self.assertEqual(self.infrastructure.cost_progress_percentage, Decimal('20'))
        self.assertEqual(self.inspection.completion_percentage, Decimal('30'))
        self.assertEqual(pending.snapshot_data, before_snapshot)
        self.assertEqual(self.infrastructure.project.publication_revisions.count(), 2)
