"""Project-wide Mayor progress history without changing publication rules."""

import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.system.models import (
    NonInfrastructureEvidence, NonInfrastructureProgressUpdate,
    NonInfrastructureProject, Project, ProjectRevision, UserRole,
)
from apps.system.publication_workflow import PublicationStatus


class InternalProgressHistoryTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        storage_settings = override_settings(MEDIA_ROOT=media.name)
        storage_settings.enable()
        self.addCleanup(storage_settings.disable)
        self.staff = self.user('staff-one', 'mayor', 'staff')
        self.other_staff = self.user('staff-two', 'mayor', 'staff')
        self.head = self.user('mayor-head', 'mayor', 'head')
        self.engineer = self.user('engineer', 'engineer', 'head')
        self.admin = get_user_model().objects.create_superuser('sys-admin')
        self.resident = get_user_model().objects.create_user('resident')
        self.base = Project.objects.create(project_type='non_infrastructure')
        self.project = NonInfrastructureProject.objects.create(
            project=self.base, title='Community Training', status='planned',
        )
        self.other_project = NonInfrastructureProject.objects.create(
            project=Project.objects.create(project_type='non_infrastructure'),
            title='Other municipality project', status='planned',
        )
        self.url = reverse(
            'mayor_projects:non_infrastructure_project_detail', args=[self.project.pk],
        )

    def user(self, username, department, role):
        user = get_user_model().objects.create_user(username, password='validpassword')
        UserRole.objects.create(user=user, department=department, role=role)
        return user

    def update(self, *, by=None, project=None, status='draft', previous='planned',
               proposed='ongoing', evidence=(), **fields):
        update = NonInfrastructureProgressUpdate.objects.create(
            non_infrastructure=project or self.project,
            submitted_by=by or self.staff,
            previous_status=previous,
            proposed_status=proposed,
            remarks=f'{previous} to {proposed} public-safe remarks',
            review_status=status,
            **fields,
        )
        for filename in evidence:
            NonInfrastructureEvidence.objects.create(
                progress_update=update,
                uploaded_by=by or self.staff,
                evidence_file=SimpleUploadedFile(filename, b'proof', content_type=(
                    'application/pdf' if filename.endswith('.pdf') else 'image/png'
                )),
                description=f'Proof for {filename}',
            )
        return update

    def test_empty_history_is_visible_to_staff_head_and_admin(self):
        for actor in (self.staff, self.head, self.admin):
            with self.subTest(actor=actor.username):
                self.client.force_login(actor)
                page = self.client.get(self.url)
                self.assertContains(page, 'Progress Update History')
                self.assertContains(page, 'No progress updates yet')
                self.assertEqual(list(page.context['progress_update_history']), [])

    def test_newest_first_including_other_staff_but_not_other_projects(self):
        first = self.update(evidence=('older.pdf',))
        second = self.update(by=self.other_staff, evidence=('newer.png',))
        self.update(project=self.other_project, evidence=('unrelated.pdf',))
        # Equal creation times must sort by progress_update_id.
        created = timezone.now() - timedelta(days=1)
        NonInfrastructureProgressUpdate.objects.filter(pk__in=[first.pk, second.pk]).update(created_at=created)
        self.client.force_login(self.staff)
        page = self.client.get(self.url)
        history = page.context['progress_update_history']
        self.assertEqual([item.pk for item in history], [second.pk, first.pk])
        self.assertContains(page, self.other_staff.username)
        self.assertContains(page, 'Planned')
        self.assertContains(page, 'Ongoing')
        self.assertContains(page, 'My Progress Updates')
        self.assertEqual([item.pk for item in page.context['staff_progress_updates']], [first.pk])
        self.assertNotContains(page, 'unrelated.pdf')
        self.assertEqual([item['name'] for item in history[0].history_evidence], ['newer.png'])
        self.assertEqual([item['name'] for item in history[1].history_evidence], ['older.pdf'])
        self.assertContains(page, 'data-image-viewer-trigger')
        self.assertContains(page, 'data-image-viewer-image')
        self.assertContains(page, 'js/components/image_viewer.js')
        self.assertContains(page, 'View Evidence')
        self.assertContains(page, f'href="{history[1].history_evidence[0]["url"]}"')

    def test_draft_pending_and_approved_unapplied_are_distinct(self):
        self.update(status='draft')
        self.update(by=self.other_staff, status='pending_review', submitted_at=timezone.now())
        self.update(status='approved', reviewed_by=self.head, reviewed_at=timezone.now())
        self.client.force_login(self.head)
        page = self.client.get(self.url)
        self.assertContains(page, 'mayor-status--draft')
        self.assertContains(page, 'mayor-status--pending_review')
        self.assertContains(page, 'mayor-status--approved')
        self.assertNotContains(page, 'Applied · Awaiting Publication')

    def test_review_and_publication_states_show_correct_people_and_dates(self):
        now = timezone.now()
        returned = self.update(
            status='returned', review_notes='Correct the supporting record.',
            submitted_at=now, reviewed_at=now, reviewed_by=self.head,
        )
        approved = self.update(status='approved', reviewed_at=now, reviewed_by=self.head)
        revision = ProjectRevision.objects.create(
            project=self.base, revision_number=1,
            status=PublicationStatus.APPROVED,
        )
        applied = self.update(
            by=self.other_staff, status='approved', applied_at=now,
            applied_by=self.head, reviewed_at=now, reviewed_by=self.head,
            publication_revision=revision,
        )
        self.client.force_login(self.head)
        page = self.client.get(self.url)
        for term in ('Returned', 'Approved', 'Applied · Awaiting Publication',
                     'Revision 1 · Approved', 'Submitted by', 'Reviewed by',
                     'Applied by', 'Correct the supporting record.'):
            self.assertContains(page, term)
        self.assertContains(page, reverse('publication_revision_detail', args=[revision.pk]))
        self.assertContains(page, reverse(
            'mayor_projects:non_infrastructure_progress_review_detail', args=[applied.pk],
        ))
        revision.status = PublicationStatus.PUBLISHED
        revision.published_at = now
        revision.published_by = self.head
        revision.save(update_fields=['status', 'published_at', 'published_by'])
        published = self.client.get(self.url)
        self.assertContains(published, 'Revision 1 · Published')
        self.assertContains(published, 'Published by')
        self.assertContains(published, self.head.username)
        self.assertContains(published, now.strftime('%Y'))
        revision.status = PublicationStatus.ARCHIVED
        revision.save(update_fields=['status'])
        self.assertContains(self.client.get(self.url), 'Previously published')
        self.assertEqual(returned.review_status, 'returned')
        self.assertIsNone(approved.applied_at)

    def test_notes_visible_to_head_and_owner_only(self):
        self.update(by=self.other_staff, status='returned',
                    review_notes='Internal correction reason', reviewed_by=self.head)
        for actor, should_see in (
            (self.head, True), (self.other_staff, True),
            (self.staff, False), (self.admin, False),
        ):
            with self.subTest(actor=actor.username):
                self.client.force_login(actor)
                page = self.client.get(self.url)
                self.assertEqual('Internal correction reason' in page.content.decode(), should_see)

    def test_missing_and_unsafe_files_keep_metadata_without_bad_links(self):
        update = self.update(evidence=('present.png', 'missing.pdf'))
        missing = update.evidence.get(evidence_file__endswith='missing.pdf')
        missing.evidence_file.storage.delete(missing.evidence_file.name)
        unsafe = NonInfrastructureEvidence.objects.create(
            progress_update=update,
            evidence_file='../private.pdf',
            description='Historical record without a safe file path',
        )
        self.client.force_login(self.head)
        page = self.client.get(self.url)
        self.assertContains(page, 'File unavailable', count=2)
        self.assertContains(page, 'Historical record without a safe file path')
        self.assertNotContains(page, 'private.pdf')
        self.assertNotContains(page, unsafe.evidence_file.name)
        self.assertContains(page, 'Enlarge evidence image present.png')
        self.assertEqual(sum(bool(x['url']) for x in page.context['progress_update_history'][0].history_evidence), 1)

    def test_internal_permissions_and_public_snapshot_boundary(self):
        update = self.update(by=self.other_staff, status='pending_review',
                             review_notes='Head-only note', evidence=('pending.pdf',))
        for actor in (self.engineer, self.resident):
            self.client.force_login(actor)
            self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.logout()
        self.assertRedirects(
            self.client.get(self.url),
            f"{reverse('login')}?next={self.url}",
            fetch_redirect_response=False,
        )
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(reverse(
            'mayor_projects:non_infrastructure_progress_approve', args=[update.pk],
        )).status_code, 403)
        self.client.force_login(self.head)
        self.assertEqual(self.client.post(reverse(
            'mayor_projects:non_infrastructure_progress_update_submit',
            args=[self.project.pk, update.pk],
        )).status_code, 403)
        self.assertFalse(self.base.revisions.filter(status='published').exists())

    def test_history_queries_remain_bounded_with_multiple_updates(self):
        self.client.force_login(self.head)
        self.update(evidence=('one.pdf',))
        with CaptureQueriesContext(connection) as one:
            self.client.get(self.url)
        for index in range(5):
            self.update(by=self.other_staff, evidence=(f'proof{index}.pdf',))
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.url)
        self.assertLessEqual(len(many), len(one) + 2)
