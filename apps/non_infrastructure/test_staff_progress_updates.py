import os
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.system.models import (
    NonInfrastructureEvidence,
    NonInfrastructureProgressUpdate,
    NonInfrastructureProject,
    Project,
    UserRole,
)


class MayorStaffProgressUpdateTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        media_override.enable()
        self.addCleanup(media_override.disable)

        self.staff = self.make_user('mayor-staff', 'mayor', 'staff')
        base = Project.objects.create(
            project_type='non_infrastructure',
            created_by_user=self.staff,
            updated_by_user=self.staff,
        )
        self.project = NonInfrastructureProject.objects.create(
            project=base, title='Community Program', status='planned',
        )
        self.url = reverse(
            'mayor_projects:non_infrastructure_progress_update_create',
            args=[self.project.pk],
        )

    def make_user(self, name, department, role):
        user = get_user_model().objects.create_user(username=name, password='testpass123')
        UserRole.objects.create(user=user, department=department, role=role)
        return user

    def upload(self, name='proof.pdf'):
        return SimpleUploadedFile(name, b'%PDF-1.4\nexample proof', content_type='application/pdf')

    def form_data(self, **overrides):
        return {
            'proposed_status': 'ongoing',
            'remarks': 'The program has started.',
            'evidence_description': 'Attendance and activity records',
            'evidence_files': self.upload(),
            **overrides,
        }

    def test_mayor_staff_can_open_form_from_project_detail(self):
        self.client.force_login(self.staff)
        detail = self.client.get(reverse(
            'mayor_projects:non_infrastructure_project_detail',
            args=[self.project.pk],
        ))
        self.assertContains(detail, self.url)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Community Program')
        self.assertContains(response, 'Current official status: Planned')
        self.assertContains(response, 'Save Draft')
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_other_roles_cannot_read_or_post(self):
        for department, role in (
            ('mayor', 'head'), ('engineer', 'staff'), ('engineer', 'head'),
        ):
            with self.subTest(department=department, role=role):
                user = self.make_user(f'{department}-{role}', department, role)
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.assertEqual(self.client.post(self.url, self.form_data()).status_code, 403)
        admin = get_user_model().objects.create_superuser(
            username='admin', password='testpass123', email='admin@example.com',
        )
        self.client.force_login(admin)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.form_data()).status_code, 403)
        public_user = get_user_model().objects.create_user(
            username='resident', password='testpass123',
        )
        self.client.force_login(public_user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.form_data()).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(NonInfrastructureProgressUpdate.objects.count(), 0)

    def test_one_evidence_file_saves_draft_and_leaves_official_status_unchanged(self):
        self.client.force_login(self.staff)
        response = self.client.post(self.url, self.form_data())
        self.assertRedirects(response, reverse(
            'mayor_projects:non_infrastructure_project_detail',
            args=[self.project.pk],
        ))
        update = NonInfrastructureProgressUpdate.objects.get()
        evidence = update.evidence.get()
        self.assertEqual(update.non_infrastructure, self.project)
        self.assertEqual(update.previous_status, 'planned')
        self.assertEqual(update.proposed_status, 'ongoing')
        self.assertEqual(update.remarks, 'The program has started.')
        self.assertEqual(update.submitted_by, self.staff)
        self.assertEqual(update.review_status, NonInfrastructureProgressUpdate.ReviewStatus.DRAFT)
        self.assertIsNone(update.submitted_at)
        self.assertEqual(evidence.uploaded_by, self.staff)
        self.assertEqual(evidence.description, 'Attendance and activity records')
        self.assertTrue(evidence.evidence_file.name.startswith('non_infrastructure/evidence/'))
        self.assertTrue(evidence.evidence_file.storage.exists(evidence.evidence_file.name))
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, 'planned')
        self.assertFalse(self.project.project.revisions.exists())

    def test_multiple_evidence_files_are_linked_to_one_update(self):
        self.client.force_login(self.staff)
        data = self.form_data(evidence_files=[self.upload('first.pdf'), self.upload('second.pdf')])
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        update = NonInfrastructureProgressUpdate.objects.get()
        self.assertEqual(update.evidence.count(), 2)
        self.assertEqual(
            list(update.evidence.values_list('uploaded_by_id', flat=True)),
            [self.staff.pk, self.staff.pk],
        )

    def test_previous_status_is_read_when_draft_is_saved(self):
        self.client.force_login(self.staff)
        self.client.get(self.url)
        self.project.status = 'ongoing'
        self.project.save(update_fields=['status'])
        response = self.client.post(self.url, self.form_data(proposed_status='completed'))
        self.assertEqual(response.status_code, 302)
        update = NonInfrastructureProgressUpdate.objects.get()
        self.assertEqual(update.previous_status, 'ongoing')
        self.assertEqual(update.proposed_status, 'completed')
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, 'ongoing')

    def test_invalid_status_remarks_or_evidence_do_not_create_records(self):
        self.client.force_login(self.staff)
        for invalid, field in (
            ({'proposed_status': 'published'}, 'proposed_status'),
            ({'remarks': '  '}, 'remarks'),
            ({'evidence_files': []}, 'evidence_files'),
            ({'evidence_files': SimpleUploadedFile(
                'script.exe', b'executable', content_type='application/octet-stream',
            )}, 'evidence_files'),
            ({'evidence_files': SimpleUploadedFile(
                'too-large.pdf', b'X' * (10 * 1024 * 1024 + 1),
                content_type='application/pdf',
            )}, 'evidence_files'),
        ):
            with self.subTest(field=field, data=invalid):
                response = self.client.post(self.url, self.form_data(**invalid))
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context['form'].errors)
        self.assertEqual(NonInfrastructureProgressUpdate.objects.count(), 0)
        self.assertEqual(NonInfrastructureEvidence.objects.count(), 0)

    def test_file_storage_failure_rolls_back_update_and_removes_earlier_file(self):
        self.client.force_login(self.staff)
        original_save = NonInfrastructureEvidence.save
        calls = 0

        def fail_second_save(evidence, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('Storage is unavailable')
            return original_save(evidence, *args, **kwargs)

        with patch.object(NonInfrastructureEvidence, 'save', fail_second_save):
            response = self.client.post(self.url, self.form_data(
                evidence_files=[self.upload('first.pdf'), self.upload('second.pdf')],
            ))
        self.assertEqual(response.status_code, 200)
        self.assertIn('evidence_files', response.context['form'].errors)
        self.assertEqual(NonInfrastructureProgressUpdate.objects.count(), 0)
        self.assertEqual(NonInfrastructureEvidence.objects.count(), 0)
        self.assertFalse(any(files for _, _, files in os.walk(self.media_directory.name)))
