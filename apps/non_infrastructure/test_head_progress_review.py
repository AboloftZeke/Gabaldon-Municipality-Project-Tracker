import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.system.models import (
    NonInfrastructureEvidence,
    NonInfrastructureProgressUpdate,
    NonInfrastructureProject,
    Project,
    UserRole,
)


class MayorHeadProgressReviewTests(TestCase):
    def setUp(self):
        media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(media_directory.cleanup)
        media_override = override_settings(MEDIA_ROOT=media_directory.name)
        media_override.enable()
        self.addCleanup(media_override.disable)

        self.staff = self.make_user('mayor-staff', 'mayor', 'staff')
        self.head = self.make_user('mayor-head', 'mayor', 'head')
        self.project = NonInfrastructureProject.objects.create(
            project=Project.objects.create(
                project_type='non_infrastructure',
                created_by_user=self.staff,
            ),
            title='Community Health Program',
            status='planned',
        )
        self.pending = self.make_update('pending_review')
        self.draft = self.make_update('draft')
        self.detail_url = self.detail_url_for(self.pending)
        self.queue_url = reverse('mayor_projects:non_infrastructure_progress_review_queue')
        self.approve_url = reverse(
            'mayor_projects:non_infrastructure_progress_approve',
            args=[self.pending.pk],
        )
        self.return_url = reverse(
            'mayor_projects:non_infrastructure_progress_return',
            args=[self.pending.pk],
        )
        self.client.force_login(self.head)

    def make_user(self, username, department, role):
        user = get_user_model().objects.create_user(username=username, password='testpass123')
        UserRole.objects.create(user=user, department=department, role=role)
        return user

    def make_update(self, review_status, *, with_evidence=True):
        update = NonInfrastructureProgressUpdate.objects.create(
            non_infrastructure=self.project,
            previous_status='planned',
            proposed_status='ongoing',
            remarks='Community outreach has started.',
            submitted_by=self.staff,
            submitted_at=timezone.now() if review_status != 'draft' else None,
            review_status=review_status,
        )
        if with_evidence:
            NonInfrastructureEvidence.objects.create(
                progress_update=update,
                evidence_file=SimpleUploadedFile(
                    'proof.pdf', b'%PDF-1.4\nevidence', content_type='application/pdf',
                ),
                description='Attendance record',
                uploaded_by=self.staff,
            )
        return update

    def detail_url_for(self, update):
        return reverse(
            'mayor_projects:non_infrastructure_progress_review_detail',
            args=[update.pk],
        )

    def assert_official_state_unchanged(self):
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, 'planned')
        self.assertFalse(self.project.project.revisions.exists())

    def test_head_dashboard_and_queue_show_only_pending_updates(self):
        dashboard = self.client.get(reverse('mayor_head_dashboard'))
        self.assertContains(dashboard, 'Non-Infrastructure Progress Updates')
        self.assertContains(dashboard, self.detail_url)
        self.assertContains(dashboard, 'Community Health Program')
        self.assertContains(dashboard, 'Proposed status: Ongoing')
        self.assertContains(dashboard, 'mayor-staff')
        self.assertContains(dashboard, self.queue_url)
        self.assertEqual([item.pk for item in dashboard.context['pending_progress_updates']], [self.pending.pk])

        queue = self.client.get(self.queue_url)
        self.assertEqual(queue.status_code, 200)
        self.assertEqual([item.pk for item in queue.context['progress_updates']], [self.pending.pk])
        self.assertContains(queue, 'Pending Review')
        self.assertNotContains(queue, self.detail_url_for(self.draft))

    def test_dashboard_preview_links_to_full_pending_queue(self):
        for _ in range(7):
            self.make_update('pending_review')
        dashboard = self.client.get(reverse('mayor_head_dashboard'))
        self.assertEqual(dashboard.context['pending_progress_update_count'], 8)
        self.assertEqual(len(dashboard.context['pending_progress_updates']), 6)
        queue = self.client.get(self.queue_url)
        self.assertEqual(queue.context['paginator'].count, 8)

    def test_review_detail_shows_all_information_and_evidence(self):
        response = self.client.get(self.detail_url)
        self.assertContains(response, 'id="head-update-heading"')
        self.assertContains(response, 'id="head-evidence-heading"')
        self.assertContains(response, 'id="head-decision-heading"')
        self.assertContains(response, 'PDF document')
        self.assertContains(response, 'download')
        self.assertContains(response, 'Community Health Program')
        self.assertContains(response, 'Current official status:')
        self.assertContains(response, 'Previous status at draft creation:')
        self.assertContains(response, 'Proposed status:')
        self.assertContains(response, 'Community outreach has started.')
        self.assertContains(response, 'proof.pdf')
        self.assertContains(response, 'Attendance record')
        self.assertContains(response, 'mayor-staff')
        self.assertContains(response, 'Submitted date:')
        self.assertContains(response, 'Review status: Pending Review')
        self.assertContains(response, 'Approve')
        self.assertContains(response, 'Return for Correction')
        self.assertContains(response, 'name="csrfmiddlewaretoken"', count=2)

    def test_approve_records_reviewer_and_time_without_publishing(self):
        evidence_id = self.pending.evidence.get().pk
        response = self.client.post(self.approve_url, {
            'review_status': 'returned', 'reviewed_by': self.staff.pk,
            'review_notes': 'Forged note',
        })
        self.assertRedirects(response, self.detail_url)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.review_status, 'approved')
        self.assertEqual(self.pending.reviewed_by, self.head)
        self.assertIsNotNone(self.pending.reviewed_at)
        self.assertEqual(self.pending.review_notes, '')
        self.assertEqual(self.pending.evidence.get().pk, evidence_id)
        self.assert_official_state_unchanged()
        self.assertNotContains(self.client.get(self.detail_url), 'Return for Correction')
        self.assertNotContains(self.client.get(self.queue_url), self.detail_url)

    def test_return_requires_reason_and_stores_trimmed_note(self):
        for reason in ('', '   '):
            with self.subTest(reason=reason):
                response = self.client.post(self.return_url, {'review_notes': reason})
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, 'Explain what needs correction', status_code=400)
                self.pending.refresh_from_db()
                self.assertEqual(self.pending.review_status, 'pending_review')
                self.assertIsNone(self.pending.reviewed_at)

        response = self.client.post(self.return_url, {
            'review_notes': '  Attach the signed attendance record.  ',
            'review_status': 'approved', 'reviewed_by': self.staff.pk,
        })
        self.assertRedirects(response, self.detail_url)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.review_status, 'returned')
        self.assertEqual(self.pending.review_notes, 'Attach the signed attendance record.')
        self.assertEqual(self.pending.reviewed_by, self.head)
        self.assertIsNotNone(self.pending.reviewed_at)
        self.assertEqual(self.pending.evidence.count(), 1)
        self.assert_official_state_unchanged()
        self.assertContains(self.client.get(self.detail_url), self.pending.review_notes)
        staff_detail = reverse(
            'mayor_projects:non_infrastructure_progress_update_detail',
            args=[self.project.pk, self.pending.pk],
        )
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(staff_detail), self.pending.review_notes)

    def test_draft_and_completed_review_decisions_are_rejected(self):
        for update, decision_url_name, data in (
            (self.draft, 'non_infrastructure_progress_approve', {}),
            (self.draft, 'non_infrastructure_progress_return', {'review_notes': 'Fix'}),
        ):
            with self.subTest(status='draft', decision=decision_url_name):
                url = reverse('mayor_projects:' + decision_url_name, args=[update.pk])
                response = self.client.post(url, data, follow=True)
                self.assertContains(response, 'Only Pending Review updates can be reviewed')
                update.refresh_from_db()
                self.assertEqual(update.review_status, 'draft')
                self.assertIsNone(update.reviewed_at)

        for state in ('approved', 'returned'):
            with self.subTest(state=state):
                self.pending.review_status = state
                self.pending.save(update_fields=['review_status'])
                for url, data in (
                    (self.approve_url, {}), (self.return_url, {'review_notes': 'Fix'}),
                ):
                    response = self.client.post(url, data, follow=True)
                    self.assertContains(response, 'Only Pending Review updates can be reviewed')
                    self.pending.refresh_from_db()
                    self.assertEqual(self.pending.review_status, state)
                    self.assertIsNone(self.pending.reviewed_at)

    def test_get_does_not_review(self):
        for url in (self.approve_url, self.return_url):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.review_status, 'pending_review')

    def test_review_actions_require_csrf(self):
        protected_client = Client(enforce_csrf_checks=True)
        protected_client.force_login(self.head)
        self.assertEqual(protected_client.post(self.approve_url).status_code, 403)
        self.assertEqual(protected_client.get(self.detail_url).status_code, 200)
        token = protected_client.cookies['csrftoken'].value
        self.assertEqual(protected_client.post(
            self.approve_url, HTTP_X_CSRFTOKEN=token,
        ).status_code, 302)

    def test_other_roles_cannot_view_queue_or_review(self):
        users = [
            self.staff,
            self.make_user('engineer-head', 'engineer', 'head'),
            self.make_user('engineer-staff', 'engineer', 'staff'),
            get_user_model().objects.create_user(username='resident'),
            get_user_model().objects.create_superuser(
                username='admin', email='admin@example.com', password='testpass123',
            ),
        ]
        for user in users:
            with self.subTest(user=user.username):
                self.client.force_login(user)
                for url in (self.queue_url, self.detail_url):
                    self.assertEqual(self.client.get(url).status_code, 403)
                for url in (self.approve_url, self.return_url):
                    self.assertEqual(self.client.post(url, {'review_notes': 'Fix'}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.approve_url).status_code, 403)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.review_status, 'pending_review')

    def test_approval_without_evidence_is_rejected(self):
        empty = self.make_update('pending_review', with_evidence=False)
        url = reverse('mayor_projects:non_infrastructure_progress_approve', args=[empty.pk])
        response = self.client.post(url, follow=True)
        self.assertContains(response, 'needs supporting evidence before approval')
        empty.refresh_from_db()
        self.assertEqual(empty.review_status, 'pending_review')
        self.assertIsNone(empty.reviewed_at)
