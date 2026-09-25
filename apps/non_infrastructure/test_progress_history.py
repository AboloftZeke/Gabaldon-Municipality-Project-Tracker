"""Publication history for approved, applied Mayor progress updates."""

from copy import deepcopy
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.non_infrastructure.progress_application import apply_approved_progress_update
from apps.system.models import (
    NonInfrastructureEvidence, NonInfrastructureProgressUpdate,
    NonInfrastructureProject, Project, ProjectRevision, UserRole,
)
from apps.system.publication_service import (
    create_head_operational_revision, publish_publication_revision,
)
from apps.system.publication_snapshots import build_project_publication_snapshot
from apps.system.publication_workflow import PublicationStatus


class MayorPublicationHistoryTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        media_override = override_settings(MEDIA_ROOT=directory.name)
        media_override.enable()
        self.addCleanup(media_override.disable)

        self.staff = self.user('mayor-staff', 'mayor', 'staff')
        self.head = self.user('mayor-head', 'mayor', 'head')
        self.engineer = self.user('engineering-head', 'engineer', 'head')
        self.base = Project.objects.create(
            project_type='non_infrastructure', created_by_user=self.staff,
            is_published=True, is_visible_to_public=True,
        )
        self.project = NonInfrastructureProject.objects.create(
            project=self.base, title='Community training', status='planned',
            project_type=NonInfrastructureProject.ProjectType.PROGRAM,
        )
        self.public = ProjectRevision.objects.create(
            project=self.base, revision_number=1,
            status=PublicationStatus.PUBLISHED,
            snapshot=build_project_publication_snapshot(self.base),
            is_current_public=True,
        )
        self.public_url = reverse(
            'public_non_infrastructure_project_detail', args=[self.project.pk],
        )

    def user(self, name, department, role):
        user = get_user_model().objects.create_user(username=name, password='testpass123')
        UserRole.objects.create(user=user, department=department, role=role)
        return user

    def progress_update(self, *, previous='planned', proposed='ongoing',
                        status=NonInfrastructureProgressUpdate.ReviewStatus.APPROVED,
                        files=('attendance.pdf', 'photo.jpg')):
        update = NonInfrastructureProgressUpdate.objects.create(
            non_infrastructure=self.project, previous_status=previous,
            proposed_status=proposed, remarks=f'{previous} to {proposed} report',
            submitted_by=self.staff, submitted_at=timezone.now(),
            review_status=status,
            reviewed_by=self.head if status == 'approved' else None,
            reviewed_at=timezone.now() if status == 'approved' else None,
            review_notes='Reviewed supporting records.' if status == 'approved' else '',
        )
        for name in files:
            NonInfrastructureEvidence.objects.create(
                progress_update=update,
                evidence_file=SimpleUploadedFile(name, b'proof', content_type='application/pdf'),
                description=f'Proof: {name}', uploaded_by=self.staff,
            )
        return update

    def test_applied_update_freezes_full_audit_and_evidence_in_revision(self):
        update = self.progress_update()
        source_files = list(update.evidence.order_by('evidence_id'))
        applied = apply_approved_progress_update(update.pk, self.head)
        revision = applied.publication_revision
        frozen = revision.snapshot['non_infrastructure_progress_update']
        self.assertEqual(revision.source_non_infrastructure_progress_update, applied)
        self.assertEqual(frozen['id'], update.pk)
        self.assertEqual(frozen['previous_status'], 'planned')
        self.assertEqual(frozen['proposed_status'], 'ongoing')
        self.assertEqual(frozen['remarks'], update.remarks)
        self.assertEqual(frozen['review_status'], 'approved')
        self.assertEqual(frozen['review_notes'], update.review_notes)
        self.assertEqual(frozen['submitted_by']['id'], self.staff.pk)
        self.assertEqual(frozen['reviewed_by']['id'], self.head.pk)
        self.assertEqual(frozen['applied_by']['id'], self.head.pk)
        self.assertEqual(frozen['submitted_at'], update.submitted_at.isoformat())
        self.assertEqual(frozen['reviewed_at'], update.reviewed_at.isoformat())
        self.assertEqual(frozen['applied_at'], applied.applied_at.isoformat())
        self.assertEqual(
            [(item['id'], item['file_path'], item['description']) for item in frozen['evidence']],
            [(item.pk, item.evidence_file.name, item.description) for item in source_files],
        )
        self.assertTrue(all(item['uploaded_by']['id'] == self.staff.pk for item in frozen['evidence']))
        self.assertTrue(all(item['uploaded_at'] for item in frozen['evidence']))
        self.assertEqual(update.evidence.count(), 2)
        self.assertNotIn('non_infrastructure_progress_update', self.public.snapshot)

    def test_authorized_revision_history_shows_frozen_values_and_files(self):
        update = self.progress_update()
        revision = apply_approved_progress_update(update.pk, self.head).publication_revision
        self.client.force_login(self.head)
        detail = reverse('publication_revision_detail', args=[revision.pk])
        response = self.client.get(detail)
        self.assertContains(response, f'Revision {revision.revision_number}')
        self.assertContains(response, 'Status')
        self.assertContains(response, 'Planned')
        self.assertContains(response, 'Ongoing')
        self.assertContains(response, 'Approved')
        self.assertNotContains(response, 'Reviewed supporting records.')
        self.assertNotContains(response, 'attendance.pdf')
        self.assertNotContains(response, 'photo.jpg')
        self.client.force_login(self.engineer)
        self.assertEqual(self.client.get(detail).status_code, 403)

    def test_unpublished_evidence_is_not_on_public_detail_or_public_data(self):
        update = self.progress_update()
        revision = apply_approved_progress_update(update.pk, self.head).publication_revision
        self.assertEqual(self.client.get(self.public_url).context['public_project']['status'], 'planned')
        self.assertNotContains(self.client.get(self.public_url), 'attendance.pdf')
        self.assertNotContains(self.client.get(self.public_url), 'Reviewed supporting records.')
        publish_publication_revision(revision, self.head)
        response = self.client.get(self.public_url)
        self.assertEqual(response.context['public_project']['status'], 'ongoing')
        self.assertContains(response, 'attendance.pdf')
        self.assertNotContains(response, 'Reviewed supporting records.')
        self.assertNotIn('non_infrastructure_progress_update', response.context['public_project'])
        from apps.reports.services import get_non_infrastructure_project_report_data
        report = get_non_infrastructure_project_report_data(self.project.pk)
        self.assertEqual(report['status'], 'ongoing')
        self.assertNotIn('non_infrastructure_progress_update', report)

    def test_second_publication_keeps_first_update_and_evidence_separate(self):
        first = self.progress_update()
        first_revision = apply_approved_progress_update(first.pk, self.head).publication_revision
        first_snapshot = deepcopy(first_revision.snapshot)
        publish_publication_revision(first_revision, self.head)

        second = self.progress_update(previous='ongoing', proposed='completed', files=('finish.pdf',))
        second_revision = apply_approved_progress_update(second.pk, self.head).publication_revision
        self.assertEqual(second_revision.revision_number, 3)
        self.assertEqual(second_revision.previous_revision, first_revision)
        self.assertEqual(second_revision.snapshot['non_infrastructure_progress_update']['id'], second.pk)
        self.assertEqual(
            [item['id'] for item in second_revision.snapshot['non_infrastructure_progress_update']['evidence']],
            list(second.evidence.values_list('pk', flat=True)),
        )
        self.assertNotIn('attendance.pdf', str(second_revision.snapshot['non_infrastructure_progress_update']))
        first.refresh_from_db()
        first_revision.refresh_from_db()
        self.assertEqual(first_revision.snapshot, first_snapshot)
        self.assertEqual(first.publication_revision_id, first_revision.pk)
        self.assertEqual(first.evidence.count(), 2)
        self.assertEqual(second.evidence.count(), 1)
        self.assertEqual(self.client.get(self.public_url).context['public_project']['status'], 'ongoing')
        publish_publication_revision(second_revision, self.head)
        first_revision.refresh_from_db()
        self.assertEqual(first_revision.status, PublicationStatus.ARCHIVED)
        self.assertEqual(first_revision.snapshot, first_snapshot)
        self.assertEqual(self.client.get(self.public_url).context['public_project']['status'], 'completed')
        self.client.force_login(self.head)
        history = self.client.get(reverse('publication_review_queue') + '?status=archived')
        self.assertContains(history, f'Revision {first_revision.revision_number}')
        self.assertNotContains(
            self.client.get(reverse('publication_revision_detail', args=[first_revision.pk])),
            'attendance.pdf',
        )

    def test_evidence_description_edits_do_not_rewrite_published_history(self):
        update = self.progress_update(files=('proof.pdf',))
        revision = apply_approved_progress_update(update.pk, self.head).publication_revision
        publish_publication_revision(revision, self.head)
        frozen = deepcopy(revision.snapshot['non_infrastructure_progress_update'])
        item = update.evidence.get()
        item.description = 'Later edited description'
        item.save(update_fields=['description'])
        revision.refresh_from_db()
        self.assertEqual(revision.snapshot['non_infrastructure_progress_update'], frozen)
        self.client.force_login(self.head)
        detail = self.client.get(reverse('publication_revision_detail', args=[revision.pk]))
        self.assertNotContains(detail, 'Proof: proof.pdf')
        self.assertNotContains(detail, 'Later edited description')

    def test_direct_head_update_does_not_inherit_previous_evidence_history(self):
        first = self.progress_update()
        first_revision = apply_approved_progress_update(first.pk, self.head).publication_revision
        publish_publication_revision(first_revision, self.head)
        self.project.status = 'completed'
        self.project.save(update_fields=['status'])
        direct_revision = create_head_operational_revision(self.base, self.head)
        self.assertEqual(direct_revision.snapshot['non_infrastructure']['status'], 'completed')
        self.assertNotIn('non_infrastructure_progress_update', direct_revision.snapshot)
        first_revision.refresh_from_db()
        self.assertEqual(first_revision.snapshot['non_infrastructure_progress_update']['id'], first.pk)

    def test_pending_and_returned_updates_never_enter_publication_history(self):
        private_ids = []
        for status in ('pending_review', 'returned'):
            with self.subTest(status=status):
                update = self.progress_update(status=status)
                self.assertIsNone(update.publication_revision_id)
                private_ids.append(update.pk)
        self.assertEqual(self.base.revisions.count(), 1)
        self.assertNotIn('non_infrastructure_progress_update', self.public.snapshot)
        approved = self.progress_update()
        revision = apply_approved_progress_update(approved.pk, self.head).publication_revision
        publish_publication_revision(revision, self.head)
        frozen = revision.snapshot['non_infrastructure_progress_update']
        self.assertEqual(frozen['id'], approved.pk)
        self.assertTrue(all(other_id != frozen['id'] for other_id in private_ids))
        self.assertEqual(len(frozen['evidence']), approved.evidence.count())

    def test_deleted_submitter_does_not_erase_snapshot_or_evidence(self):
        update = self.progress_update()
        revision = apply_approved_progress_update(update.pk, self.head).publication_revision
        expected = deepcopy(revision.snapshot['non_infrastructure_progress_update'])
        self.staff.delete()
        update.refresh_from_db()
        revision.refresh_from_db()
        self.assertIsNone(update.submitted_by)
        self.assertEqual(update.evidence.count(), 2)
        self.assertEqual(revision.snapshot['non_infrastructure_progress_update'], expected)

    def test_infrastructure_progress_snapshot_format_is_unchanged(self):
        from apps.system.models import InfrastructureProject, InfrastructureProgressUpdate
        from apps.system.publication_snapshots import build_progress_update_snapshot

        infra = InfrastructureProject.objects.create(
            project=Project.objects.create(project_type='infrastructure'), title='Bridge',
        )
        update = InfrastructureProgressUpdate.objects.create(
            infrastructure=infra, new_official_status='ongoing',
            updated_by=self.engineer, head_remarks='Work started',
        )
        snapshot = build_progress_update_snapshot(update)
        self.assertEqual(snapshot['official_status'], 'ongoing')
        self.assertEqual(snapshot['head_remarks'], 'Work started')
        self.assertEqual(snapshot['supporting_inspections'], [])
