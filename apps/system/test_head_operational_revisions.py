from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from .models import (
    InspectionEvidence,
    NonInfrastructureCategory,
    NonInfrastructureProject,
    Project,
    ProjectInspection,
    ProjectRevision,
    UserRole,
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
            UserRole.objects.create(
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
        self.infrastructure.status = 'not_yet_started'
        self.infrastructure.physical_progress_percentage = Decimal('25')
        self.infrastructure.cost_progress_percentage = Decimal('20')
        self.infrastructure.planned_start_date = date.today() - timedelta(days=5)
        self.infrastructure.planned_end_date = date.today() + timedelta(days=5)
        self.infrastructure.save()
        self.inspection = ProjectInspection.objects.create(
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
        self.non_infrastructure = NonInfrastructureProject.objects.create(
            project=base,
            title='Community Program',
            description='Published description',
            status='planned',
            category=self.category,
        )
        self.non_infrastructure_public = self._publish_current(base)

    def _publish_current(self, project):
        return ProjectRevision.objects.create(
            project=project,
            revision_number=1,
            status=PublicationStatus.PUBLISHED,
            is_current_public=True,
            snapshot=build_project_publication_snapshot(project),
        )

    def test_infrastructure_update_creates_approved_snapshot_without_republishing(self):
        previous_snapshot = deepcopy(self.infrastructure_public.snapshot)
        self.client.force_login(self.users['engineer', 'head'])
        response = self.client.post(reverse(
            'engineering_projects:project_operations',
            args=[self.infrastructure.pk],
        ), {
            'status': 'completed',
            'physical_progress_percentage': '60',
            'cost_progress_percentage': '55',
            'inspection_completion_percentage': '70',
        })
        self.assertEqual(response.status_code, 302)

        revision = self.infrastructure.project.revisions.get(
            status=PublicationStatus.APPROVED,
        )
        self.assertRedirects(
            response,
            reverse('publication_revision_detail', args=[revision.pk]),
        )
        self.assertEqual(revision.revision_number, 2)
        self.assertEqual(revision.previous_revision, self.infrastructure_public)
        self.assertEqual(revision.submitted_by, self.users['engineer', 'head'])
        self.assertEqual(revision.reviewed_by, self.users['engineer', 'head'])
        self.assertFalse(revision.is_current_public)
        self.assertIsNone(revision.published_at)
        self.assertEqual(
            revision.snapshot['infrastructure']['status'],
            'completed',
        )
        self.assertEqual(
            revision.snapshot['infrastructure']['physical_progress_percentage'],
            '60.00',
        )
        self.assertEqual(
            revision.snapshot['infrastructure']['cost_progress_percentage'],
            '55.00',
        )
        self.assertEqual(
            revision.snapshot['inspection']['completion_percentage'],
            '70.00',
        )

        self.infrastructure_public.refresh_from_db()
        self.assertEqual(self.infrastructure_public.status, PublicationStatus.PUBLISHED)
        self.assertTrue(self.infrastructure_public.is_current_public)
        self.assertEqual(self.infrastructure_public.snapshot, previous_snapshot)
        public_response = self.client.get(reverse(
            'public_infrastructure_project_detail',
            args=[self.infrastructure.pk],
        ))
        self.assertEqual(public_response.status_code, 200)
        public_project = public_response.context['public_project']
        self.assertEqual(public_project['status'], 'not_yet_started')
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
        self.assertIn(('Project Information', 'status'), changed)
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
        self.assertTrue(revision.is_current_public)
        self.assertEqual(
            self.infrastructure_public.status,
            PublicationStatus.ARCHIVED,
        )
        self.assertFalse(self.infrastructure_public.is_current_public)
        public_response = self.client.get(reverse(
            'public_infrastructure_project_detail',
            args=[self.infrastructure.pk],
        ))
        public_project = public_response.context['public_project']
        self.assertEqual(public_project['status'], 'completed')
        self.assertEqual(public_project['physical_progress_percentage'], Decimal('60.00'))
        self.assertEqual(public_project['cost_progress_percentage'], Decimal('55.00'))
        self.assertEqual(
            public_project['inspection']['completion_percentage'],
            Decimal('70.00'),
        )

    def test_progress_evidence_is_retained_until_explicit_publication(self):
        evidence = InspectionEvidence.objects.create(
            inspection=self.inspection,
            evidence_type='document',
            original_name='field-report.pdf',
            storage_name='inspections/reports/field-report.pdf',
            file_url='/media/inspections/reports/field-report.pdf',
            content_type='application/pdf',
            uploaded_by_user=self.users['engineer', 'staff'],
        )
        self.inspection.inspection_type = 'progress'
        self.inspection.findings = 'Verified structural work on site.'
        self.inspection.remarks = 'Weather delayed the morning inspection.'
        self.inspection.inspected_by_user = self.users['engineer', 'staff']
        self.inspection.save(update_fields=[
            'inspection_type', 'findings', 'remarks', 'inspected_by_user',
        ])
        current_public_snapshot = deepcopy(
            self.infrastructure_public.snapshot,
        )
        self.client.force_login(self.users['engineer', 'head'])

        response = self.client.post(reverse(
            'engineering_projects:project_operations',
            args=[self.infrastructure.pk],
        ), {
            'status': 'completed',
            'physical_progress_percentage': '62',
            'cost_progress_percentage': '55',
            'inspection_completion_percentage': '70',
            'head_remarks': 'Official decision based on the field report.',
            'supporting_inspections': [str(self.inspection.pk)],
        })

        self.assertEqual(response.status_code, 302)
        revision = self.infrastructure.project.revisions.get(
            status=PublicationStatus.APPROVED,
        )
        progress_snapshot = revision.snapshot['progress_update']
        self.assertEqual(progress_snapshot['official_status'], 'completed')
        self.assertEqual(progress_snapshot['official_physical_progress'], '62.00')
        self.assertEqual(
            progress_snapshot['head_remarks'],
            'Official decision based on the field report.',
        )
        inspection_snapshot = progress_snapshot['supporting_inspections'][0]
        self.assertEqual(inspection_snapshot['id'], self.inspection.pk)
        self.assertEqual(inspection_snapshot['inspection_type'], 'progress')
        self.assertEqual(inspection_snapshot['completion_percentage'], '70.00')
        self.assertEqual(
            inspection_snapshot['findings'],
            'Verified structural work on site.',
        )
        self.assertEqual(inspection_snapshot['evidence'][0], {
            'id': evidence.pk,
            'type': 'document',
            'type_label': 'Document',
            'original_name': 'field-report.pdf',
            'url': '/media/inspections/reports/field-report.pdf',
            'content_type': 'application/pdf',
            'uploaded_by': {
                'id': self.users['engineer', 'staff'].pk,
                'username': 'engineer-staff',
                'display_name': 'engineer-staff',
            },
            'created_at': evidence.created_at.isoformat(),
        })

        self.infrastructure_public.refresh_from_db()
        self.assertEqual(
            self.infrastructure_public.snapshot,
            current_public_snapshot,
        )
        self.assertNotIn(
            'progress_update',
            self.infrastructure_public.snapshot,
        )
        public_response = self.client.get(reverse(
            'public_infrastructure_project_detail',
            args=[self.infrastructure.pk],
        ))
        self.assertEqual(
            public_response.context['public_project']['status'],
            'not_yet_started',
        )

        retained_snapshot = deepcopy(revision.snapshot)
        self.inspection.completion_percentage = Decimal('99')
        self.inspection.findings = 'Changed working inspection.'
        self.inspection.save(update_fields=[
            'completion_percentage', 'findings',
        ])
        evidence.original_name = 'renamed-working-report.pdf'
        evidence.file_url = '/media/inspections/reports/renamed.pdf'
        evidence.save(update_fields=['original_name', 'file_url'])
        revision.refresh_from_db()
        self.assertEqual(revision.snapshot, retained_snapshot)

        preview = self.client.get(reverse(
            'publication_revision_detail', args=[revision.pk],
        ))
        self.assertContains(preview, 'class="revision-section progress-evidence-panel"')
        self.assertContains(preview, 'Official Physical Progress')
        self.assertContains(preview, 'Supporting Inspections')
        self.assertContains(preview, 'field-report.pdf')
        self.assertContains(preview, 'Verified structural work on site.')
        self.assertNotContains(preview, 'renamed-working-report.pdf')
        comparison_sections = {
            section['label']
            for section in preview.context['comparison']['sections']
        }
        self.assertIn('Operational Progress Update', comparison_sections)

        publish_response = self.client.post(reverse(
            'publication_revision_publish', args=[revision.pk],
        ))
        self.assertEqual(publish_response.status_code, 302)
        revision.refresh_from_db()
        self.infrastructure_public.refresh_from_db()
        self.assertEqual(revision.status, PublicationStatus.PUBLISHED)
        self.assertTrue(revision.is_current_public)
        self.assertEqual(
            self.infrastructure_public.status,
            PublicationStatus.ARCHIVED,
        )
        self.assertFalse(self.infrastructure_public.is_current_public)
        self.assertEqual(revision.snapshot, retained_snapshot)

    def test_first_publication_revision_receives_head_progress_evidence(self):
        self.infrastructure_public.delete()
        pending = ProjectRevision.objects.create(
            project=self.infrastructure.project,
            revision_number=1,
            status=PublicationStatus.APPROVED,
            snapshot=build_project_publication_snapshot(
                self.infrastructure.project,
            ),
            submitted_by=self.users['engineer', 'staff'],
        )
        evidence = InspectionEvidence.objects.create(
            inspection=self.inspection,
            evidence_type='image',
            original_name='initial-site.jpg',
            storage_name='inspections/photos/initial-site.jpg',
            file_url='/media/inspections/photos/initial-site.jpg',
            content_type='image/jpeg',
            uploaded_by_user=self.users['engineer', 'staff'],
        )
        self.client.force_login(self.users['engineer', 'head'])

        response = self.client.post(reverse(
            'engineering_projects:project_operations',
            args=[self.infrastructure.pk],
        ), {
            'status': 'not_yet_started',
            'physical_progress_percentage': '30',
            'cost_progress_percentage': '20',
            'inspection_completion_percentage': '35',
            'head_remarks': 'Initial publication confirmation.',
            'supporting_inspections': [str(self.inspection.pk)],
            'from_review': str(pending.pk),
        })

        self.assertRedirects(
            response,
            reverse('publication_revision_detail', args=[pending.pk]),
        )
        self.assertEqual(
            self.infrastructure.project.revisions.count(),
            1,
        )
        pending.refresh_from_db()
        progress_snapshot = pending.snapshot['progress_update']
        self.assertEqual(
            progress_snapshot['head_remarks'],
            'Initial publication confirmation.',
        )
        self.assertEqual(
            progress_snapshot['supporting_inspections'][0]['evidence'][0][
                'id'
            ],
            evidence.pk,
        )
        self.assertFalse(pending.is_current_public)

    def test_operational_revision_retains_public_financial_snapshot(self):
        published_snapshot = deepcopy(self.infrastructure_public.snapshot)
        published_snapshot['financial']['contract_price'] = '2350000.00'
        published_snapshot['financial']['actual_expenditure'] = '940000.00'
        self.infrastructure_public.snapshot = published_snapshot
        self.infrastructure_public.save(update_fields=['snapshot'])
        financial = self.infrastructure.financial_records.get()
        financial.bid_amount = Decimal('1000000.00')
        financial.actual_expenditure = Decimal('900000.00')
        financial.save(update_fields=['bid_amount', 'actual_expenditure'])
        self.infrastructure.title = 'Unpublished Staff Title'
        self.infrastructure.save(update_fields=['title'])
        self.client.force_login(self.users['engineer', 'head'])
        operational_url = reverse(
            'engineering_projects:project_operations',
            args=[self.infrastructure.pk],
        )

        form = self.client.get(operational_url)
        self.assertEqual(
            form.context['calculated_cost_progress'],
            Decimal('40.00'),
        )
        self.assertContains(form, '40.00%')

        response = self.client.post(operational_url, {
            'status': 'completed',
            'physical_progress_percentage': '60',
            'cost_progress_percentage': '',
            'inspection_completion_percentage': '70',
        })
        revision = self.infrastructure.project.revisions.get(
            status=PublicationStatus.APPROVED,
        )
        self.assertRedirects(
            response,
            reverse('publication_revision_detail', args=[revision.pk]),
        )
        self.assertEqual(
            revision.snapshot['financial'],
            published_snapshot['financial'],
        )
        self.assertEqual(
            revision.snapshot['infrastructure']['title'],
            published_snapshot['infrastructure']['title'],
        )
        preview = self.client.get(reverse(
            'publication_revision_detail',
            args=[revision.pk],
        ))
        self.assertContains(preview, '40.00%')
        self.assertContains(preview, 'Publish Update to Public Dashboard')
        self.assertFalse(revision.is_current_public)
        self.infrastructure_public.refresh_from_db()
        self.assertTrue(self.infrastructure_public.is_current_public)

        response = self.client.post(reverse(
            'publication_revision_publish',
            args=[revision.pk],
        ))
        self.assertEqual(response.status_code, 302)
        revision.refresh_from_db()
        self.infrastructure_public.refresh_from_db()
        self.assertTrue(revision.is_current_public)
        self.assertEqual(
            revision.snapshot['financial'],
            published_snapshot['financial'],
        )
        self.assertEqual(
            self.infrastructure_public.status,
            PublicationStatus.ARCHIVED,
        )

    def test_non_infrastructure_update_creates_approved_snapshot_without_republishing(self):
        previous_snapshot = deepcopy(self.non_infrastructure_public.snapshot)
        self.client.force_login(self.users['mayor', 'head'])
        response = self.client.post(reverse(
            'mayor_projects:non_infrastructure_project_operations',
            args=[self.non_infrastructure.pk],
        ), {'status': 'completed'})
        self.assertEqual(response.status_code, 302)

        revision = self.non_infrastructure.project.revisions.get(
            status=PublicationStatus.APPROVED,
        )
        self.assertRedirects(
            response,
            reverse('publication_revision_detail', args=[revision.pk]),
        )
        self.assertEqual(revision.previous_revision, self.non_infrastructure_public)
        self.assertEqual(
            revision.snapshot['non_infrastructure']['status'],
            'completed',
        )
        self.assertFalse(revision.is_current_public)
        self.non_infrastructure_public.refresh_from_db()
        self.assertTrue(self.non_infrastructure_public.is_current_public)
        self.assertEqual(self.non_infrastructure_public.snapshot, previous_snapshot)
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
        self.assertTrue(revision.is_current_public)
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
        unpublished = NonInfrastructureProject.objects.create(
            project=project,
            title='Unpublished Program',
            status='planned',
            category=self.category,
        )
        self.client.force_login(self.users['mayor', 'head'])
        response = self.client.post(reverse(
            'mayor_projects:non_infrastructure_project_operations',
            args=[unpublished.pk],
        ), {'status': 'ongoing'})
        self.assertEqual(response.status_code, 302)
        unpublished.refresh_from_db()
        self.assertEqual(unpublished.status, 'ongoing')
        self.assertFalse(project.revisions.exists())

    def test_service_rejects_wrong_roles_without_creating_a_revision(self):
        original_count = self.infrastructure.project.revisions.count()
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
                    self.infrastructure.project.revisions.count(),
                    original_count,
                )

    def test_active_staff_revision_blocks_update_and_rolls_back_working_data(self):
        pending = ProjectRevision.objects.create(
            project=self.infrastructure.project,
            revision_number=2,
            status=PublicationStatus.PENDING_REVIEW,
            snapshot=build_project_publication_snapshot(
                self.infrastructure.project,
            ),
            submitted_by=self.users['engineer', 'staff'],
        )
        before_snapshot = deepcopy(pending.snapshot)
        self.client.force_login(self.users['engineer', 'head'])
        response = self.client.post(reverse(
            'engineering_projects:project_operations',
            args=[self.infrastructure.pk],
        ), {
            'status': 'completed',
            'physical_progress_percentage': '80',
            'cost_progress_percentage': '75',
            'inspection_completion_percentage': '90',
        })
        self.assertEqual(response.status_code, 409)
        self.infrastructure.refresh_from_db()
        self.inspection.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(self.infrastructure.status, 'not_yet_started')
        self.assertEqual(self.infrastructure.physical_progress_percentage, Decimal('25'))
        self.assertEqual(self.infrastructure.cost_progress_percentage, Decimal('20'))
        self.assertEqual(self.inspection.completion_percentage, Decimal('30'))
        self.assertEqual(pending.snapshot, before_snapshot)
        self.assertEqual(self.infrastructure.project.revisions.count(), 2)
        self.assertFalse(self.infrastructure.progress_updates.exists())
