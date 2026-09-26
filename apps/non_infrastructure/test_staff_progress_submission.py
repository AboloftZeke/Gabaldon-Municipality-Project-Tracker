import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.system.models import (
    NonInfrastructureEvidence,
    NonInfrastructureProgressUpdate,
    NonInfrastructureProject,
    Project,
    UserRole,
)


class MayorStaffProgressSubmissionTests(TestCase):
    def setUp(self):
        media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(media_directory.cleanup)
        media_override = override_settings(MEDIA_ROOT=media_directory.name)
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
        self.create_url = reverse(
            'mayor_projects:non_infrastructure_progress_update_create',
            args=[self.project.pk],
        )
        self.client.force_login(self.staff)
        self.update = self.make_draft()
        self.detail_url = self.detail_url_for(self.update)
        self.submit_url = reverse(
            'mayor_projects:non_infrastructure_progress_update_submit',
            args=[self.project.pk, self.update.pk],
        )

    def make_user(self, username, department, role):
        user = get_user_model().objects.create_user(username=username, password='testpass123')
        UserRole.objects.create(user=user, department=department, role=role)
        return user

    def make_draft(self, *, evidence=True):
        update = NonInfrastructureProgressUpdate.objects.create(
            non_infrastructure=self.project,
            previous_status='planned',
            proposed_status='ongoing',
            remarks='The program has started.',
            submitted_by=self.staff,
        )
        if evidence:
            NonInfrastructureEvidence.objects.create(
                progress_update=update,
                evidence_file=SimpleUploadedFile(
                    'report.pdf', b'%PDF-1.4\nproof', content_type='application/pdf',
                ),
                description='Activity report',
                uploaded_by=self.staff,
            )
        return update

    def detail_url_for(self, update):
        return reverse(
            'mayor_projects:non_infrastructure_progress_update_detail',
            args=[self.project.pk, update.pk],
        )

    def test_internal_form_and_draft_show_evidence_actions(self):
        form = self.client.get(self.create_url)
        self.assertContains(form, 'id="mayor-selected-files"')
        self.assertContains(form, 'id="id_proposed_status"')
        self.assertContains(form, 'id="id_remarks"')
        self.assertContains(form, 'id="id_evidence_files"')
        self.assertContains(form, 'id="id_evidence_description"')
        self.assertContains(form, 'Save Draft')
        detail = self.client.get(self.detail_url)
        self.assertContains(detail, 'Submit for Review')
        self.assertContains(detail, 'PDF document')
        self.assertContains(detail, 'Open file')
        self.assertContains(detail, 'Download file')

    def test_internal_evidence_image_has_preview_and_return_note_is_visible(self):
        NonInfrastructureEvidence.objects.create(
            progress_update=self.update,
            evidence_file=SimpleUploadedFile('activity.png', b'image', content_type='image/png'),
            description='Activity photo', uploaded_by=self.staff,
        )
        self.update.review_status = 'returned'
        self.update.review_notes = 'Add the attendance sheet.'
        self.update.save(update_fields=['review_status', 'review_notes'])
        detail = self.client.get(self.detail_url)
        self.assertContains(detail, 'Evidence preview: Activity photo')
        self.assertContains(detail, 'Add the attendance sheet.')
        self.assertNotContains(detail, 'Submit for Review')

    def test_staff_can_find_and_review_saved_draft_with_evidence(self):
        project_page = self.client.get(reverse(
            'mayor_projects:non_infrastructure_project_detail',
            args=[self.project.pk],
        ))
        self.assertContains(project_page, self.detail_url)
        detail = self.client.get(self.detail_url)
        self.assertContains(detail, 'Review status: Draft')
        self.assertContains(detail, 'Previous status:')
        self.assertContains(detail, 'Current official status:')
        self.assertContains(detail, 'Proposed status:')
        self.assertContains(detail, 'The program has started.')
        self.assertContains(detail, 'report.pdf')
        self.assertContains(detail, 'Activity report')
        self.assertContains(detail, 'Not submitted')
        self.assertContains(detail, 'Submit for Review')
        self.assertContains(detail, 'name="csrfmiddlewaretoken"')

    def test_submit_draft_sets_pending_and_timestamp_without_publishing(self):
        evidence_id = self.update.evidence.get().pk
        response = self.client.post(self.submit_url)
        self.assertRedirects(response, self.detail_url)
        self.update.refresh_from_db()
        self.project.refresh_from_db()
        self.assertEqual(
            self.update.review_status,
            NonInfrastructureProgressUpdate.ReviewStatus.PENDING_REVIEW,
        )
        self.assertIsNotNone(self.update.submitted_at)
        self.assertEqual(self.update.submitted_by, self.staff)
        self.assertEqual(self.update.evidence.get().pk, evidence_id)
        self.assertEqual(self.project.status, 'planned')
        self.assertFalse(self.project.project.revisions.exists())
        detail = self.client.get(self.detail_url)
        self.assertContains(detail, 'Review status: Pending Review')
        self.assertContains(detail, 'Waiting for Mayor Head review')
        self.assertNotContains(detail, 'Submit for Review')
        self.assertNotContains(detail, 'Not submitted')

    def test_get_cannot_submit(self):
        self.assertEqual(self.client.get(self.submit_url).status_code, 405)
        self.update.refresh_from_db()
        self.assertEqual(self.update.review_status, 'draft')
        self.assertIsNone(self.update.submitted_at)

    def test_submit_requires_csrf_token(self):
        protected_client = Client(enforce_csrf_checks=True)
        protected_client.force_login(self.staff)
        self.assertEqual(protected_client.post(self.submit_url).status_code, 403)
        self.assertEqual(protected_client.get(self.detail_url).status_code, 200)
        token = protected_client.cookies['csrftoken'].value
        self.assertEqual(protected_client.post(
            self.submit_url, HTTP_X_CSRFTOKEN=token,
        ).status_code, 302)

    def test_draft_without_evidence_cannot_submit(self):
        empty = self.make_draft(evidence=False)
        url = reverse(
            'mayor_projects:non_infrastructure_progress_update_submit',
            args=[self.project.pk, empty.pk],
        )
        response = self.client.post(url, follow=True)
        self.assertContains(response, 'Add supporting evidence before submitting')
        empty.refresh_from_db()
        self.assertEqual(empty.review_status, 'draft')
        self.assertIsNone(empty.submitted_at)

    def test_invalid_saved_draft_cannot_submit(self):
        for fields in ({'proposed_status': 'invalid'}, {'remarks': '  '}):
            with self.subTest(fields=fields):
                for name, value in fields.items():
                    setattr(self.update, name, value)
                self.update.save(update_fields=list(fields))
                response = self.client.post(self.submit_url, follow=True)
                self.assertContains(response, 'Add a valid proposed status and remarks')
                self.update.refresh_from_db()
                self.assertEqual(self.update.review_status, 'draft')
                self.assertIsNone(self.update.submitted_at)
                self.update.proposed_status = 'ongoing'
                self.update.remarks = 'The program has started.'
                self.update.save(update_fields=['proposed_status', 'remarks'])

    def test_pending_returned_or_approved_update_cannot_be_submitted(self):
        for status in ('pending_review', 'returned', 'approved'):
            with self.subTest(status=status):
                self.update.review_status = status
                self.update.submitted_at = None
                self.update.save(update_fields=['review_status', 'submitted_at'])
                response = self.client.post(self.submit_url, follow=True)
                self.assertContains(response, 'Only Draft updates can be submitted')
                self.update.refresh_from_db()
                self.assertEqual(self.update.review_status, status)
                self.assertIsNone(self.update.submitted_at)

    def test_only_owner_with_mayor_staff_role_can_view_and_submit(self):
        other_staff = self.make_user('other-mayor-staff', 'mayor', 'staff')
        for user, forbidden_status in (
            (other_staff, 404),
            (self.make_user('mayor-head', 'mayor', 'head'), 403),
            (self.make_user('engineer-staff', 'engineer', 'staff'), 403),
            (get_user_model().objects.create_user(username='resident'), 403),
            (get_user_model().objects.create_superuser(
                username='admin', email='admin@example.com', password='testpass123',
            ), 403),
        ):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.detail_url).status_code, forbidden_status)
                self.assertEqual(self.client.post(self.submit_url).status_code, forbidden_status)
        self.client.logout()
        self.assertRedirects(
            self.client.post(self.submit_url),
            f"{reverse('login')}?next={self.submit_url}",
            fetch_redirect_response=False,
        )
        self.update.refresh_from_db()
        self.assertEqual(self.update.review_status, 'draft')

    def test_draft_form_cannot_set_review_status_or_submission_date(self):
        self.client.force_login(self.staff)
        response = self.client.post(self.create_url, {
            'proposed_status': 'completed',
            'remarks': 'Completed activity report.',
            'evidence_files': SimpleUploadedFile(
                'proof.pdf', b'%PDF-1.4\nproof', content_type='application/pdf',
            ),
            'review_status': 'approved',
            'submitted_at': '2026-01-01T12:00:00Z',
            'submitted_by': '0',
        })
        self.assertEqual(response.status_code, 302)
        draft = NonInfrastructureProgressUpdate.objects.exclude(pk=self.update.pk).get()
        self.assertEqual(draft.review_status, 'draft')
        self.assertIsNone(draft.submitted_at)
        self.assertEqual(draft.submitted_by, self.staff)

    def test_update_cannot_be_submitted_under_another_project(self):
        another_project = NonInfrastructureProject.objects.create(
            project=Project.objects.create(project_type='non_infrastructure'),
            title='Other Program',
        )
        url = reverse(
            'mayor_projects:non_infrastructure_progress_update_submit',
            args=[another_project.pk, self.update.pk],
        )
        self.assertEqual(self.client.post(url).status_code, 404)
        self.update.refresh_from_db()
        self.assertEqual(self.update.review_status, 'draft')
