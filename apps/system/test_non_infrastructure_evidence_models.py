"""Phase 1 data relationships for Mayor's Office update evidence."""

from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings

from .models import (
    NonInfrastructureEvidence,
    NonInfrastructureProgressUpdate,
    NonInfrastructureProject,
    Project,
)


class NonInfrastructureEvidenceModelTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        storage_settings = override_settings(MEDIA_ROOT=self.media_directory.name)
        storage_settings.enable()
        self.addCleanup(storage_settings.disable)

        self.submitter = get_user_model().objects.create_user('mayor-staff')
        self.reviewer = get_user_model().objects.create_user('mayor-head')
        base = Project.objects.create(project_type='non_infrastructure')
        self.project = NonInfrastructureProject.objects.create(
            project=base,
            title='Community program',
            project_type=NonInfrastructureProject.ProjectType.PROGRAM,
            status='planned',
        )

    def make_update(self, **overrides):
        fields = {
            'non_infrastructure': self.project,
            'previous_status': 'planned',
            'proposed_status': 'ongoing',
            'remarks': 'Program has started',
            'submitted_by': self.submitter,
        }
        fields.update(overrides)
        return NonInfrastructureProgressUpdate.objects.create(**fields)

    def make_evidence(self, update, name='proof.jpg'):
        return NonInfrastructureEvidence.objects.create(
            progress_update=update,
            evidence_file=SimpleUploadedFile(name, b'example proof', content_type='image/jpeg'),
            description='Project activity',
            uploaded_by=self.submitter,
        )

    def test_creating_update_does_not_change_official_project_status(self):
        update = self.make_update()
        self.assertEqual(update.non_infrastructure, self.project)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, 'planned')
        self.assertEqual(update.review_status, NonInfrastructureProgressUpdate.ReviewStatus.DRAFT)

    def test_one_project_has_multiple_updates(self):
        self.make_update()
        self.make_update(proposed_status='completed')
        self.assertEqual(self.project.progress_updates.count(), 2)

    def test_one_update_has_multiple_evidence_files_in_storage(self):
        update = self.make_update()
        first = self.make_evidence(update)
        second = self.make_evidence(update, name='second.pdf')
        self.assertEqual(update.evidence.count(), 2)
        for evidence in (first, second):
            self.assertTrue(evidence.evidence_file.storage.exists(evidence.evidence_file.name))
            self.assertTrue(evidence.evidence_file.name.startswith('non_infrastructure/evidence/'))

    def test_evidence_records_its_uploader(self):
        evidence = self.make_evidence(self.make_update())
        self.assertEqual(evidence.uploaded_by, self.submitter)
        self.assertIsNotNone(evidence.uploaded_at)
        self.assertIsNotNone(evidence.created_at)

    def test_review_status_choices_and_proposed_status_validation(self):
        expected = {'draft', 'pending_review', 'returned', 'approved'}
        self.assertEqual(set(NonInfrastructureProgressUpdate.ReviewStatus.values), expected)
        for status in expected:
            update = self.make_update(review_status=status)
            update.full_clean()
        invalid = self.make_update(review_status='published')
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_evidence_protects_its_update_from_deletion(self):
        update = self.make_update()
        evidence = self.make_evidence(update)
        with self.assertRaises(ProtectedError):
            update.delete()
        self.assertTrue(NonInfrastructureProgressUpdate.objects.filter(pk=update.pk).exists())
        self.assertTrue(NonInfrastructureEvidence.objects.filter(pk=evidence.pk).exists())

    def test_project_with_update_cannot_be_deleted_accidentally(self):
        update = self.make_update()
        with self.assertRaises(ProtectedError):
            self.project.project.delete()
        self.assertTrue(NonInfrastructureProgressUpdate.objects.filter(pk=update.pk).exists())

    def test_deactivating_user_does_not_remove_history(self):
        update = self.make_update(reviewed_by=self.reviewer)
        evidence = self.make_evidence(update)
        self.submitter.is_active = False
        self.submitter.save(update_fields=['is_active'])
        update.refresh_from_db()
        evidence.refresh_from_db()
        self.assertEqual(update.submitted_by, self.submitter)
        self.assertEqual(evidence.uploaded_by, self.submitter)

    def test_deleting_users_keeps_updates_and_evidence(self):
        update = self.make_update(reviewed_by=self.reviewer)
        evidence = self.make_evidence(update)
        self.submitter.delete()
        self.reviewer.delete()
        update.refresh_from_db()
        evidence.refresh_from_db()
        self.assertIsNone(update.submitted_by)
        self.assertIsNone(update.reviewed_by)
        self.assertIsNone(evidence.uploaded_by)
