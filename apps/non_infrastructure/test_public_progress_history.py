"""Public Mayor evidence must be sourced from published snapshots only."""

import tempfile

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.non_infrastructure.progress_application import apply_approved_progress_update
from apps.system.models import (
    NonInfrastructureEvidence, NonInfrastructureProgressUpdate,
    NonInfrastructureProject, Project, ProjectRevision, UserRole,
)
from apps.system.publication_service import publish_publication_revision
from apps.system.publication_snapshots import build_project_publication_snapshot
from apps.system.publication_workflow import PublicationStatus


class PublicMayorHistoryTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        media = override_settings(MEDIA_ROOT=directory.name)
        media.enable()
        self.addCleanup(media.disable)
        user = get_user_model()
        self.staff = user.objects.create_user(username='staff-history', password='testpass123')
        self.head = user.objects.create_user(username='head-history', password='testpass123')
        UserRole.objects.create(user=self.staff, department='mayor', role='staff')
        UserRole.objects.create(user=self.head, department='mayor', role='head')
        self.base = Project.objects.create(
            project_type='non_infrastructure', created_by_user=self.staff,
        )
        self.project = NonInfrastructureProject.objects.create(
            project=self.base, title='Skills training', status='planned',
            project_type=NonInfrastructureProject.ProjectType.PROGRAM,
        )
        self.initial = ProjectRevision.objects.create(
            project=self.base, revision_number=1, status=PublicationStatus.PUBLISHED,
            snapshot=build_project_publication_snapshot(self.base),
            is_current_public=True, published_at=timezone.now(),
        )
        self.url = reverse('public_non_infrastructure_project_detail', args=[self.project.pk])

    def create_update(self, status='approved', previous='planned', proposed='ongoing',
                      filename='attendance.pdf'):
        update = NonInfrastructureProgressUpdate.objects.create(
            non_infrastructure=self.project, previous_status=previous,
            proposed_status=proposed, remarks=f'Public activity: {filename}',
            submitted_by=self.staff, submitted_at=timezone.now(),
            reviewed_by=self.head if status == 'approved' else None,
            reviewed_at=timezone.now() if status == 'approved' else None,
            review_status=status, review_notes='CONFIDENTIAL HEAD NOTE',
        )
        file = NonInfrastructureEvidence.objects.create(
            progress_update=update,
            evidence_file=SimpleUploadedFile(filename, b'proof', content_type='application/pdf'),
            description=f'Proof for {filename}', uploaded_by=self.staff,
        )
        return update, file

    def test_published_evidence_and_status_use_frozen_snapshot_without_internal_fields(self):
        update, evidence = self.create_update()
        revision = apply_approved_progress_update(update.pk, self.head).publication_revision
        before = self.client.get(self.url)
        self.assertContains(before, 'Planned')
        self.assertNotContains(before, 'attendance.pdf')
        self.assertNotContains(before, 'Public activity: attendance.pdf')
        publish_publication_revision(revision, self.head)
        response = self.client.get(self.url)
        self.assertEqual(response.context['public_project']['status'], 'ongoing')
        self.assertContains(response, 'Project Updates and Supporting Evidence')
        self.assertContains(response, 'Planned → Ongoing')
        self.assertContains(response, 'Public activity: attendance.pdf')
        self.assertContains(response, 'Proof for attendance.pdf')
        self.assertContains(response, default_storage.url(evidence.evidence_file.name))
        self.assertNotContains(response, 'CONFIDENTIAL HEAD NOTE')
        self.assertNotContains(response, 'Approve</button>')
        self.assertNotContains(response, 'Return for Correction')

    def test_private_states_and_applied_unpublished_revision_are_not_public(self):
        for state in ('draft', 'pending_review', 'returned', 'approved'):
            self.create_update(status=state, filename=f'private-{state}.pdf')
        applied, _ = self.create_update(filename='waiting.pdf')
        revision = apply_approved_progress_update(applied.pk, self.head).publication_revision
        response = self.client.get(self.url)
        self.assertEqual(response.context['public_project']['status'], 'planned')
        self.assertEqual(response.context['published_update_history'], [])
        for name in ('draft', 'pending_review', 'returned', 'approved', 'waiting'):
            self.assertNotContains(response, f'private-{name}.pdf')
        self.assertNotContains(response, 'waiting.pdf')
        publish_publication_revision(revision, self.head)
        self.assertContains(self.client.get(self.url), 'waiting.pdf')
        self.assertNotContains(self.client.get(self.url), 'private-approved.pdf')

    def test_two_published_updates_keep_separate_evidence_and_old_metadata(self):
        first, first_file = self.create_update()
        first_revision = apply_approved_progress_update(first.pk, self.head).publication_revision
        publish_publication_revision(first_revision, self.head)
        second, second_file = self.create_update(
            previous='ongoing', proposed='completed', filename='finish.jpg',
        )
        second_revision = apply_approved_progress_update(second.pk, self.head).publication_revision
        before = self.client.get(self.url)
        self.assertContains(before, 'attendance.pdf')
        self.assertNotContains(before, 'finish.jpg')
        publish_publication_revision(second_revision, self.head)
        first_file.description = 'Changed after publication'
        first_file.save(update_fields=['description'])
        response = self.client.get(self.url)
        history = response.context['published_update_history']
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]['new_status'], 'Completed')
        self.assertEqual(history[0]['evidence'][0]['filename'], 'finish.jpg')
        self.assertTrue(history[0]['evidence'][0]['is_image'])
        self.assertEqual(history[1]['new_status'], 'Ongoing')
        self.assertEqual(history[1]['evidence'][0]['filename'], 'attendance.pdf')
        self.assertEqual(history[1]['evidence'][0]['description'], 'Proof for attendance.pdf')
        self.assertNotContains(response, 'Changed after publication')
        self.assertContains(response, default_storage.url(second_file.evidence_file.name))
        self.assertEqual(response.context['public_project']['status'], 'completed')

    def test_missing_file_keeps_description_but_has_no_link(self):
        update, evidence = self.create_update()
        revision = apply_approved_progress_update(update.pk, self.head).publication_revision
        publish_publication_revision(revision, self.head)
        path = evidence.evidence_file.name
        default_storage.delete(path)
        response = self.client.get(self.url)
        self.assertContains(response, 'Proof for attendance.pdf')
        self.assertContains(response, 'File unavailable')
        self.assertNotContains(response, default_storage.url(path))
        self.assertEqual(response.context['published_update_history'][0]['evidence'][0]['url'], '')

    def test_revision_without_published_date_is_excluded_from_history(self):
        update, _ = self.create_update()
        revision = apply_approved_progress_update(update.pk, self.head).publication_revision
        ProjectRevision.objects.filter(pk=revision.pk).update(status=PublicationStatus.ARCHIVED)
        response = self.client.get(self.url)
        self.assertEqual(response.context['published_update_history'], [])
        self.assertNotContains(response, 'attendance.pdf')

    def test_history_does_not_link_to_paths_outside_evidence_storage(self):
        update, _ = self.create_update()
        revision = apply_approved_progress_update(update.pk, self.head).publication_revision
        frozen = revision.snapshot
        frozen['non_infrastructure_progress_update']['evidence'][0]['file_path'] = '../secret.pdf'
        revision.snapshot = frozen
        revision.save(update_fields=['snapshot'])
        publish_publication_revision(revision, self.head)
        response = self.client.get(self.url)
        self.assertContains(response, 'Proof for attendance.pdf')
        self.assertContains(response, 'File unavailable')
        self.assertNotContains(response, '../secret.pdf')
