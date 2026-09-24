from copy import deepcopy
import tempfile

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.non_infrastructure.progress_application import apply_approved_progress_update
from apps.system.models import (
    NonInfrastructureEvidence,
    NonInfrastructureProgressUpdate,
    NonInfrastructureProject,
    Project,
    ProjectRevision,
    UserRole,
)
from apps.system.publication_snapshots import build_project_publication_snapshot
from apps.system.publication_workflow import PublicationStatus


class ApplyApprovedProgressUpdateTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        media_override = override_settings(MEDIA_ROOT=directory.name)
        media_override.enable()
        self.addCleanup(media_override.disable)

        self.staff = self.make_user('mayor-staff', 'mayor', 'staff')
        self.head = self.make_user('mayor-head', 'mayor', 'head')
        self.base = Project.objects.create(
            project_type='non_infrastructure',
            created_by_user=self.staff,
            is_published=True,
            is_visible_to_public=True,
        )
        self.project = NonInfrastructureProject.objects.create(
            project=self.base, title='Community Program', status='planned',
            project_type=NonInfrastructureProject.ProjectType.PROGRAM,
        )
        self.public_revision = ProjectRevision.objects.create(
            project=self.base,
            revision_number=1,
            status=PublicationStatus.PUBLISHED,
            snapshot=build_project_publication_snapshot(self.base),
            is_current_public=True,
        )
        self.update = self.make_update()
        self.apply_url = reverse(
            'mayor_projects:non_infrastructure_progress_apply', args=[self.update.pk],
        )
        self.head_detail_url = reverse(
            'mayor_projects:non_infrastructure_progress_review_detail',
            args=[self.update.pk],
        )
        self.public_detail_url = reverse(
            'public_non_infrastructure_project_detail', args=[self.project.pk],
        )
        self.client.force_login(self.head)

    def make_user(self, name, department, role):
        user = get_user_model().objects.create_user(username=name, password='testpass123')
        UserRole.objects.create(user=user, department=department, role=role)
        return user

    def make_update(self, status='approved', *, with_evidence=True):
        update = NonInfrastructureProgressUpdate.objects.create(
            non_infrastructure=self.project,
            previous_status='planned',
            proposed_status='ongoing',
            remarks='Activity has started.',
            submitted_by=self.staff,
            submitted_at=timezone.now(),
            review_status=status,
            reviewed_by=self.head if status == 'approved' else None,
            reviewed_at=timezone.now() if status == 'approved' else None,
        )
        if with_evidence:
            NonInfrastructureEvidence.objects.create(
                progress_update=update,
                evidence_file=SimpleUploadedFile(
                    'support.pdf', b'%PDF-1.4\nproof', content_type='application/pdf',
                ),
                description='Attendance sheet',
                uploaded_by=self.staff,
            )
        return update

    def assert_not_applied(self, update=None):
        update = update or self.update
        update.refresh_from_db()
        self.project.refresh_from_db()
        self.public_revision.refresh_from_db()
        self.assertIsNone(update.applied_at)
        self.assertIsNone(update.publication_revision_id)
        self.assertEqual(self.project.status, 'planned')
        self.assertEqual(self.public_revision.snapshot['non_infrastructure']['status'], 'planned')

    def test_apply_creates_one_linked_revision_without_changing_public_snapshot(self):
        baseline = deepcopy(self.public_revision.snapshot)
        self.assertContains(self.client.get(self.head_detail_url), 'Apply Approved Update')
        response = self.client.post(self.apply_url)
        self.update.refresh_from_db()
        revision = self.update.publication_revision
        self.assertRedirects(response, reverse('publication_revision_detail', args=[revision.pk]))
        self.project.refresh_from_db()
        self.public_revision.refresh_from_db()
        self.assertEqual(self.update.review_status, 'approved')
        self.assertEqual(self.update.applied_by, self.head)
        self.assertIsNotNone(self.update.applied_at)
        self.assertEqual(self.update.evidence.count(), 1)
        self.assertEqual(revision.source_non_infrastructure_progress_update, self.update)
        self.assertEqual(self.project.status, 'ongoing')
        self.assertEqual(revision.status, PublicationStatus.APPROVED)
        self.assertEqual(revision.previous_revision, self.public_revision)
        self.assertEqual(revision.snapshot['non_infrastructure']['status'], 'ongoing')
        self.assertEqual(revision.snapshot['non_infrastructure']['status_label'], 'Ongoing')
        self.assertNotIn('progress_update', revision.snapshot)
        self.assertNotIn('evidence', revision.snapshot)
        self.assertEqual(self.public_revision.snapshot, baseline)
        self.assertTrue(self.public_revision.is_current_public)
        self.assertFalse(revision.is_current_public)
        self.assertEqual(self.client.get(self.public_detail_url).context['public_project']['status'], 'planned')
        self.assertNotContains(self.client.get(self.head_detail_url), 'Apply Approved Update')
        self.assertContains(self.client.get(self.head_detail_url), 'View Publication Revision')

        self.assertEqual(self.client.post(
            reverse('publication_revision_publish', args=[revision.pk]),
        ).status_code, 302)
        self.assertEqual(self.client.get(self.public_detail_url).context['public_project']['status'], 'ongoing')
        self.assertNotContains(self.client.get(self.public_detail_url), 'support.pdf')

    def test_second_application_is_rejected_even_after_publication(self):
        apply_approved_progress_update(self.update.pk, self.head)
        self.update.refresh_from_db()
        self.project.refresh_from_db()
        revision_id = self.update.publication_revision_id
        response = self.client.post(self.apply_url, follow=True)
        self.assertContains(response, 'already been applied')
        self.update.refresh_from_db()
        self.assertEqual(self.update.publication_revision_id, revision_id)
        self.assertEqual(self.base.revisions.count(), 2)
        self.assertEqual(self.project.status, 'ongoing')

    def test_unapproved_states_cannot_be_applied(self):
        for status in ('draft', 'pending_review', 'returned'):
            with self.subTest(status=status):
                self.update.review_status = status
                self.update.save(update_fields=['review_status'])
                response = self.client.post(self.apply_url, follow=True)
                self.assertContains(response, 'Only Approved progress updates can be applied')
                self.assert_not_applied()

    def test_stale_or_invalid_status_is_rejected_without_revision(self):
        for before, proposed in (
            ('completed', 'ongoing'),
            ('invalid', 'ongoing'),
            ('planned', 'planned'),
            ('planned', 'invalid'),
        ):
            with self.subTest(before=before, proposed=proposed):
                self.project.status = before
                self.project.save(update_fields=['status'])
                self.update.proposed_status = proposed
                self.update.save(update_fields=['proposed_status'])
                response = self.client.post(self.apply_url, follow=True)
                self.assertEqual(response.status_code, 200)
                self.update.refresh_from_db()
                self.project.refresh_from_db()
                self.assertIsNone(self.update.applied_at)
                self.assertIsNone(self.update.publication_revision_id)
                self.assertEqual(self.project.status, before)
                self.assertEqual(self.base.revisions.count(), 1)

    def test_existing_active_revision_rolls_back_working_status(self):
        ProjectRevision.objects.create(
            project=self.base,
            revision_number=2,
            status=PublicationStatus.APPROVED,
            snapshot=deepcopy(self.public_revision.snapshot),
            previous_revision=self.public_revision,
        )
        response = self.client.post(self.apply_url, follow=True)
        self.assertContains(response, 'active unpublished revision')
        self.assert_not_applied()
        self.assertEqual(self.base.revisions.count(), 2)

    def test_unpublished_project_does_not_apply_without_revision(self):
        self.public_revision.delete()
        response = self.client.post(self.apply_url, follow=True)
        self.assertContains(response, 'Publish this project first')
        self.update.refresh_from_db()
        self.project.refresh_from_db()
        self.assertIsNone(self.update.applied_at)
        self.assertEqual(self.project.status, 'planned')
        self.assertFalse(self.base.revisions.exists())

    def test_missing_evidence_is_rejected(self):
        empty = self.make_update(with_evidence=False)
        with self.assertRaisesMessage(ValidationError, 'Supporting evidence is required'):
            apply_approved_progress_update(empty.pk, self.head)
        self.assert_not_applied(empty)
        self.assertEqual(self.base.revisions.count(), 1)

    def test_other_roles_cannot_apply(self):
        users = [
            self.staff,
            self.make_user('engineer-head', 'engineer', 'head'),
            self.make_user('other-staff', 'engineer', 'staff'),
            get_user_model().objects.create_user(username='resident'),
            get_user_model().objects.create_superuser(
                username='admin', email='admin@example.com', password='testpass123',
            ),
        ]
        for user in users:
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.post(self.apply_url).status_code, 403)
                with self.assertRaises(PermissionDenied):
                    apply_approved_progress_update(self.update.pk, user)
        self.client.logout()
        self.assertEqual(self.client.post(self.apply_url).status_code, 403)
        self.assert_not_applied()

    def test_get_cannot_apply_and_post_requires_csrf(self):
        self.assertEqual(self.client.get(self.apply_url).status_code, 405)
        protected_client = Client(enforce_csrf_checks=True)
        protected_client.force_login(self.head)
        self.assertEqual(protected_client.post(self.apply_url).status_code, 403)
        self.assertEqual(protected_client.get(self.head_detail_url).status_code, 200)
        token = protected_client.cookies['csrftoken'].value
        self.assertEqual(protected_client.post(
            self.apply_url, HTTP_X_CSRFTOKEN=token,
        ).status_code, 302)

    def test_missing_update_returns_404(self):
        url = reverse('mayor_projects:non_infrastructure_progress_apply', args=[999999])
        self.assertEqual(self.client.post(url).status_code, 404)
