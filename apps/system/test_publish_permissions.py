from copy import deepcopy
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from .models import ProjectRevision
from .permissions import can_publish_revision
from .publication_service import (
    OPERATIONAL_CONFIRMATION_KEY,
    archive_publication_revision,
    publish_publication_revision,
)


class HeadPublishTests(TestCase):
    def setUp(self):
        from .test_publication_review_permissions import OfficeReviewPermissionTests
        OfficeReviewPermissionTests.setUp(self)

    def make_first_publication_ready(self, revision, head):
        snapshot = deepcopy(revision.snapshot)
        project_type = revision.project.project_type
        if project_type == 'infrastructure':
            snapshot.setdefault('infrastructure', {}).update({
                'award_status': 'planned',
                'physical_progress_percentage': '0.00',
            })
        else:
            snapshot.setdefault('non_infrastructure', {})['status'] = 'planned'
        snapshot[OPERATIONAL_CONFIRMATION_KEY] = {
            'project_type': project_type,
            'confirmed_by_user_id': head.pk,
        }
        revision.snapshot = snapshot
        revision.save(update_fields=['snapshot'])

    def test_publish_matrix_at_view_and_service(self):
        for office, revision in self.revisions.items():
            ProjectRevision.objects.filter(pk=revision.pk).update(status='approved')
            revision.refresh_from_db()
            for user in [*self.users.values(), self.admin, AnonymousUser()]:
                if user == self.users[office, 'head']:
                    continue
                self.client.logout()
                if user.is_authenticated:
                    self.client.force_login(user)
                self.assertFalse(can_publish_revision(user, revision))
                response = self.client.post(reverse(
                    'publication_revision_publish',
                    args=[revision.pk],
                ))
                self.assertEqual(
                    response.status_code,
                    403 if user.is_authenticated else 302,
                )
                if not user.is_authenticated:
                    self.assertIn(reverse('login'), response.url)
                with self.assertRaises(PermissionDenied):
                    publish_publication_revision(revision, user)
                revision.refresh_from_db()
                self.assertEqual(revision.status, 'approved')
            head = self.users[office, 'head']
            self.make_first_publication_ready(revision, head)
            self.client.force_login(head)
            self.assertContains(self.client.get(reverse('publication_revision_detail', args=[revision.pk])), 'Publish to Public Dashboard')
            snapshot = deepcopy(revision.snapshot)
            self.assertEqual(self.client.post(reverse('publication_revision_publish', args=[revision.pk])).status_code, 302)
            revision.refresh_from_db()
            self.assertEqual(revision.status, 'published')
            self.assertEqual(revision.published_by, head)
            self.assertTrue(revision.is_current_public)
            self.assertEqual(revision.snapshot, snapshot)
            revision.project.refresh_from_db()
            self.assertTrue(revision.project.is_visible_to_public)

    def test_wrong_status_and_stale_caller_cannot_publish(self):
        revision = self.revisions['engineer']
        head = self.users['engineer', 'head']
        self.client.force_login(head)
        for status in ['draft', 'pending_review', 'needs_revision', 'rejected', 'published', 'archived']:
            ProjectRevision.objects.filter(pk=revision.pk).update(status=status)
            revision.status = 'approved'
            with self.assertRaises(PermissionDenied):
                publish_publication_revision(revision, head)
            self.assertEqual(self.client.post(reverse('publication_revision_publish', args=[revision.pk])).status_code, 403)

    def test_replacement_archives_previous_and_manual_archive_is_denied(self):
        revision = self.revisions['engineer']
        ProjectRevision.objects.filter(pk=revision.pk).update(status='approved')
        head = self.users['engineer', 'head']
        revision.refresh_from_db()
        self.make_first_publication_ready(revision, head)
        first = publish_publication_revision(revision, head)
        second = ProjectRevision.objects.create(
            project=first.project,
            revision_number=2,
            status='approved',
            snapshot=first.snapshot,
            previous_revision=first,
        )
        second = publish_publication_revision(second, head)
        first.refresh_from_db()
        self.assertEqual(first.status, 'archived')
        self.assertFalse(first.is_current_public)
        self.assertTrue(second.is_current_public)
        for user in [head, self.admin, self.users['engineer', 'staff']]:
            self.client.force_login(user)
            self.assertEqual(self.client.post(reverse('publication_revision_archive', args=[second.pk])).status_code, 403)
            with self.assertRaises(PermissionDenied):
                archive_publication_revision(second, user)
        self.client.force_login(self.admin)
        detail = self.client.get(reverse('publication_revision_detail', args=[second.pk]))
        self.assertNotContains(detail, 'Publish to Public Dashboard')
        self.assertNotContains(detail, 'Publish Update to Public Dashboard')
        self.assertNotContains(detail, 'Archive and Remove')
        self.assertContains(self.client.get(reverse('publication_lifecycle')), 'Read-only publication history')

    def test_stale_replacement_is_rejected_without_changing_public_history(self):
        stale = self.revisions['engineer']
        ProjectRevision.objects.filter(pk=stale.pk).update(
            status='approved',
        )
        current = ProjectRevision.objects.create(
            project=stale.project,
            revision_number=2,
            status='published',
            snapshot=stale.snapshot,
            is_current_public=True,
        )
        stale.refresh_from_db()
        head = self.users['engineer', 'head']

        with self.assertRaises(ValidationError):
            publish_publication_revision(stale, head)
        stale.refresh_from_db()
        current.refresh_from_db()
        self.assertEqual(stale.status, 'approved')
        self.assertEqual(current.status, 'published')
        self.assertTrue(current.is_current_public)

        self.client.force_login(head)
        detail = self.client.get(reverse(
            'publication_revision_detail',
            args=[stale.pk],
        ))
        self.assertFalse(detail.context['can_publish'])
        self.assertNotContains(detail, 'Publish Update to Public Dashboard')
        response = self.client.post(reverse(
            'publication_revision_publish',
            args=[stale.pk],
        ))
        self.assertEqual(response.status_code, 302)
        stale.refresh_from_db()
        current.refresh_from_db()
        self.assertEqual(stale.status, 'approved')
        self.assertEqual(current.status, 'published')
        self.assertTrue(current.is_current_public)
