from copy import deepcopy
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from .models import ProjectPublicationRevision
from .permissions import can_publish_revision
from .publication_service import publish_publication_revision, archive_publication_revision


class HeadPublishTests(TestCase):
    def setUp(self):
        from .test_publication_review_permissions import OfficeReviewPermissionTests
        OfficeReviewPermissionTests.setUp(self)

    def test_publish_matrix_at_view_and_service(self):
        for office, revision in self.revisions.items():
            ProjectPublicationRevision.objects.filter(pk=revision.pk).update(status='approved')
            revision.refresh_from_db()
            for user in [*self.users.values(), self.admin, AnonymousUser()]:
                if user == self.users[office, 'head']:
                    continue
                self.client.logout()
                if user.is_authenticated:
                    self.client.force_login(user)
                self.assertFalse(can_publish_revision(user, revision))
                self.assertEqual(self.client.post(reverse('publication_revision_publish', args=[revision.pk])).status_code, 403)
                with self.assertRaises(PermissionDenied):
                    publish_publication_revision(revision, user)
                revision.refresh_from_db()
                self.assertEqual(revision.status, 'approved')
            head = self.users[office, 'head']
            self.client.force_login(head)
            self.assertContains(self.client.get(reverse('publication_revision_detail', args=[revision.pk])), 'Publish to Public Dashboard')
            snapshot = deepcopy(revision.snapshot_data)
            self.assertEqual(self.client.post(reverse('publication_revision_publish', args=[revision.pk])).status_code, 302)
            revision.refresh_from_db()
            self.assertEqual(revision.status, 'published')
            self.assertEqual(revision.published_by, head)
            self.assertTrue(revision.is_current_public_revision)
            self.assertEqual(revision.snapshot_data, snapshot)
            revision.project.refresh_from_db()
            self.assertTrue(revision.project.is_visible_to_public)

    def test_wrong_status_and_stale_caller_cannot_publish(self):
        revision = self.revisions['engineer']
        head = self.users['engineer', 'head']
        self.client.force_login(head)
        for status in ['draft', 'pending_review', 'needs_revision', 'rejected', 'published', 'archived']:
            ProjectPublicationRevision.objects.filter(pk=revision.pk).update(status=status)
            revision.status = 'approved'
            with self.assertRaises(PermissionDenied):
                publish_publication_revision(revision, head)
            self.assertEqual(self.client.post(reverse('publication_revision_publish', args=[revision.pk])).status_code, 403)

    def test_replacement_archives_previous_and_manual_archive_is_denied(self):
        revision = self.revisions['engineer']
        ProjectPublicationRevision.objects.filter(pk=revision.pk).update(status='approved')
        head = self.users['engineer', 'head']
        first = publish_publication_revision(revision, head)
        second = ProjectPublicationRevision.objects.create(project=first.project, revision_number=2, status='approved', snapshot_data=first.snapshot_data)
        second = publish_publication_revision(second, head)
        first.refresh_from_db()
        self.assertEqual(first.status, 'archived')
        self.assertFalse(first.is_current_public_revision)
        self.assertTrue(second.is_current_public_revision)
        for user in [head, self.admin, self.users['engineer', 'staff']]:
            self.client.force_login(user)
            self.assertEqual(self.client.post(reverse('publication_revision_archive', args=[second.pk])).status_code, 403)
            with self.assertRaises(PermissionDenied):
                archive_publication_revision(second, user)
        self.client.force_login(self.admin)
        detail = self.client.get(reverse('publication_revision_detail', args=[second.pk]))
        self.assertNotContains(detail, 'Publish to Public Dashboard')
        self.assertNotContains(detail, 'Archive and Remove')
        self.assertContains(self.client.get(reverse('publication_lifecycle')), 'Read-only publication history')
