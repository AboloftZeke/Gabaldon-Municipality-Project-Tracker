"""Exercise Mayor evidence from the staff form through public publication."""

from copy import deepcopy
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.system.models import (
    NonInfrastructureProgressUpdate, NonInfrastructureProject, Project,
    ProjectRevision, UserRole,
)
from apps.system.publication_snapshots import build_project_publication_snapshot
from apps.system.publication_workflow import PublicationStatus


class MayorEvidenceLifecycleTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        media = override_settings(MEDIA_ROOT=directory.name)
        media.enable()
        self.addCleanup(media.disable)

        self.staff = self.user('mayor-staff', 'mayor', 'staff')
        self.head = self.user('mayor-head', 'mayor', 'head')
        self.engineer = self.user('engineering-head', 'engineer', 'head')
        self.admin = get_user_model().objects.create_superuser(
            username='admin', email='admin@example.com', password='testpass123',
        )
        self.base = Project.objects.create(
            project_type='non_infrastructure', created_by_user=self.staff,
            is_published=True, is_visible_to_public=True,
        )
        self.project = NonInfrastructureProject.objects.create(
            project=self.base, title='Community skills program',
            project_type=NonInfrastructureProject.ProjectType.PROGRAM,
            status='planned',
        )
        self.original = ProjectRevision.objects.create(
            project=self.base, revision_number=1,
            status=PublicationStatus.PUBLISHED, is_current_public=True,
            snapshot=build_project_publication_snapshot(self.base),
            published_at=timezone.now(),
        )
        self.create_url = reverse(
            'mayor_projects:non_infrastructure_progress_update_create',
            args=[self.project.pk],
        )
        self.public_url = reverse(
            'public_non_infrastructure_project_detail', args=[self.project.pk],
        )

    def user(self, name, department, role):
        user = get_user_model().objects.create_user(
            username=name, password='testpass123',
        )
        UserRole.objects.create(user=user, department=department, role=role)
        return user

    def create_draft(self, proposed='ongoing', description='Staff activity proof',
                     names=('attendance.pdf',)):
        self.client.force_login(self.staff)
        files = [SimpleUploadedFile(
            name, b'%PDF-1.4\nexample' if name.endswith('.pdf') else b'image',
            content_type={
                '.pdf': 'application/pdf', '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg', '.png': 'image/png',
                '.webp': 'image/webp',
            }[name[name.rfind('.'):]],
        ) for name in names]
        response = self.client.post(self.create_url, {
            'proposed_status': proposed,
            'remarks': f'Activities for {proposed} are documented.',
            'evidence_description': description,
            'evidence_files': files,
        })
        self.assertEqual(response.status_code, 302)
        return NonInfrastructureProgressUpdate.objects.latest('pk')

    def staff_url(self, update):
        return reverse('mayor_projects:non_infrastructure_progress_update_detail',
                       args=[self.project.pk, update.pk])

    def action(self, name, update):
        return reverse(f'mayor_projects:non_infrastructure_progress_{name}',
                       args=[update.pk])

    def submit(self, update):
        self.client.force_login(self.staff)
        url = reverse('mayor_projects:non_infrastructure_progress_update_submit',
                      args=[self.project.pk, update.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 302)
        update.refresh_from_db()
        self.assertEqual(update.review_status, 'pending_review')
        self.assertIsNotNone(update.submitted_at)

    def approve_and_apply(self, update):
        self.client.force_login(self.head)
        self.assertContains(self.client.get(reverse(
            'mayor_projects:non_infrastructure_progress_review_queue',
        )), self.action('approve', update).removesuffix('approve/'))
        detail = reverse('mayor_projects:non_infrastructure_progress_review_detail',
                         args=[update.pk])
        self.assertContains(self.client.get(detail), update.evidence.first().description)
        response = self.client.post(self.action('approve', update))
        update.refresh_from_db()
        self.assertEqual(update.review_status, 'approved')
        self.assertEqual(update.reviewed_by, self.head)
        self.assertIsNotNone(update.reviewed_at)
        self.assertRedirects(
            response,
            reverse('publication_revision_detail', args=[update.publication_revision_id]),
        )
        update.refresh_from_db()
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, update.proposed_status)
        self.assertEqual(update.publication_revision.project_id, self.base.pk)
        self.assertEqual(update.publication_revision.status, PublicationStatus.APPROVED)
        return update.publication_revision

    def publish(self, revision):
        self.client.force_login(self.head)
        self.assertEqual(self.client.post(reverse(
            'publication_revision_publish', args=[revision.pk],
        )).status_code, 302)
        revision.refresh_from_db()
        self.assertEqual(revision.status, PublicationStatus.PUBLISHED)

    def test_complete_staff_to_public_workflow_with_multiple_file_types(self):
        long_name = 'project-activity-' + 'e' * 95 + '.webp'
        update = self.create_draft(names=(
            'attendance.pdf', 'start.jpg', 'activity.jpeg', 'photo.png', long_name,
        ))
        self.assertEqual(update.review_status, 'draft')
        self.assertEqual(update.evidence.count(), 5)
        self.assertTrue(all(item.uploaded_by == self.staff for item in update.evidence.all()))
        self.assertContains(self.client.get(self.staff_url(update)), 'Submit for Review')
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, 'planned')
        self.assertEqual(self.client.get(self.public_url).context['public_project']['status'], 'planned')
        self.assertNotContains(self.client.get(self.public_url), 'Staff activity proof')

        self.submit(update)
        self.assertNotContains(self.client.get(self.staff_url(update)), 'Submit for Review')
        self.client.force_login(self.head)
        review = self.client.get(reverse(
            'mayor_projects:non_infrastructure_progress_review_detail',
            args=[update.pk],
        ))
        self.assertContains(review, 'Current official status:')
        self.assertContains(review, 'Proposed status:')
        self.assertContains(review, 'Planned')
        self.assertContains(review, 'Ongoing')
        self.assertContains(review, update.remarks)
        self.assertContains(review, 'Staff activity proof')
        for name in ('attendance.pdf', 'start.jpg', 'activity.jpeg', 'photo.png', long_name):
            self.assertContains(review, name)
        self.assertContains(review, 'Approve and Prepare Publication')
        self.assertContains(review, 'Return for Correction')
        revision = self.approve_and_apply(update)
        self.assertEqual(revision.source_non_infrastructure_progress_update, update)
        frozen = revision.snapshot['non_infrastructure_progress_update']
        self.assertEqual((frozen['previous_status'], frozen['proposed_status']),
                         ('planned', 'ongoing'))
        self.assertEqual(frozen['remarks'], update.remarks)
        self.assertEqual(frozen['submitted_by']['id'], self.staff.pk)
        self.assertEqual(frozen['reviewed_by']['id'], self.head.pk)
        self.assertEqual(len(frozen['evidence']), 5)
        self.assertEqual({item['id'] for item in frozen['evidence']},
                         set(update.evidence.values_list('pk', flat=True)))
        self.assertEqual(self.client.get(self.public_url).context['public_project']['status'], 'planned')
        self.assertNotContains(self.client.get(self.public_url), 'attendance.pdf')

        self.publish(revision)
        self.client.logout()
        public = self.client.get(self.public_url)
        self.assertEqual(public.context['public_project']['status'], 'ongoing')
        self.assertContains(public, 'Planned → Ongoing')
        self.assertContains(public, 'Staff activity proof')
        self.assertContains(public, 'Published:')
        for name in ('attendance.pdf', 'start.jpg', 'activity.jpeg', 'photo.png', long_name):
            self.assertContains(public, name)
        self.assertContains(public, 'class="public-updates__preview"', count=4)
        self.assertContains(public, 'class="public-updates__file-type">Document</span>')
        self.assertNotContains(public, 'Review Decision')

    def test_publication_review_identifies_applied_update_as_publication_source(self):
        update = self.create_draft(names=('attachment.pdf',))
        self.submit(update)
        revision = self.approve_and_apply(update)
        response = self.client.get(reverse('publication_revision_detail', args=[revision.pk]))

        self.assertContains(response, 'Publish Update to Public Dashboard')
        self.assertNotContains(response, 'Approve and Prepare Publication')
        self.assertNotContains(response, 'Evidence for this update')

    def test_returned_update_stays_internal_and_requires_reason(self):
        update = self.create_draft(names=('private.pdf',))
        self.submit(update)
        self.client.force_login(self.head)
        url = self.action('return', update)
        self.assertEqual(self.client.post(url, {}).status_code, 400)
        self.assertEqual(self.client.post(url, {'review_notes': 'Add a signed record.'}).status_code, 302)
        update.refresh_from_db()
        self.assertEqual(update.review_status, 'returned')
        self.assertEqual(update.review_notes, 'Add a signed record.')
        self.assertEqual(update.reviewed_by, self.head)
        self.assertIsNone(update.publication_revision_id)
        self.assertContains(self.client.get(reverse(
            'mayor_projects:non_infrastructure_progress_review_detail', args=[update.pk],
        )), 'Add a signed record.')
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(self.staff_url(update)), 'Add a signed record.')
        self.assertNotContains(self.client.get(self.staff_url(update)), 'Submit for Review')
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, 'planned')
        self.client.logout()
        self.assertNotContains(self.client.get(self.public_url), 'private.pdf')
        self.assertNotContains(self.client.get(self.public_url), 'Add a signed record.')

    def test_applied_revision_is_private_until_published_and_notes_stay_private(self):
        update = self.create_draft(names=('unpublished.png',))
        self.submit(update)
        revision = self.approve_and_apply(update)
        update.review_notes = 'INTERNAL ONLY'
        update.save(update_fields=['review_notes'])
        self.assertEqual(self.client.get(self.public_url).context['public_project']['status'], 'planned')
        self.assertNotContains(self.client.get(self.public_url), 'unpublished.png')
        self.assertEqual(revision.snapshot['non_infrastructure_progress_update']['review_notes'], '')
        self.publish(revision)
        self.client.logout()
        self.assertContains(self.client.get(self.public_url), 'unpublished.png')
        self.assertNotContains(self.client.get(self.public_url), 'INTERNAL ONLY')

    def test_two_publications_preserve_each_revision_and_its_evidence(self):
        first = self.create_draft(names=('first.pdf',))
        self.submit(first)
        first_revision = self.approve_and_apply(first)
        self.publish(first_revision)
        first_snapshot = deepcopy(first_revision.snapshot)

        second = self.create_draft(proposed='completed', names=('second.png',))
        self.submit(second)
        second_revision = self.approve_and_apply(second)
        self.assertEqual(self.client.get(self.public_url).context['public_project']['status'], 'ongoing')
        self.assertNotContains(self.client.get(self.public_url), 'second.png')
        self.publish(second_revision)
        first_revision.refresh_from_db()
        self.assertEqual(first_revision.status, PublicationStatus.ARCHIVED)
        self.assertEqual(first_revision.snapshot, first_snapshot)
        self.assertNotEqual(first.pk, second.pk)
        self.assertNotEqual(first_revision.pk, second_revision.pk)
        self.assertEqual(first.publication_revision_id, first_revision.pk)
        self.assertEqual(second.publication_revision_id, second_revision.pk)
        self.client.logout()
        public = self.client.get(self.public_url)
        self.assertEqual(public.context['public_project']['status'], 'completed')
        self.assertContains(public, 'Ongoing → Completed')
        self.assertContains(public, 'Planned → Ongoing')
        self.assertContains(public, 'first.pdf')
        self.assertContains(public, 'second.png')
        self.assertEqual(len(public.context['published_update_history']), 2)

    def test_roles_cannot_cross_staff_or_head_actions(self):
        update = self.create_draft()
        self.submit(update)
        review_url = reverse('mayor_projects:non_infrastructure_progress_review_detail',
                             args=[update.pk])
        for actor in (self.staff, self.engineer, self.admin):
            with self.subTest(actor=actor.username):
                self.client.force_login(actor)
                self.assertEqual(self.client.get(review_url).status_code, 403)
                for action in ('approve', 'return', 'apply'):
                    self.assertEqual(self.client.post(self.action(action, update)).status_code, 403)
        self.client.force_login(self.head)
        self.assertEqual(self.client.get(self.create_url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(review_url).status_code, 403)
        self.assertEqual(self.client.get(self.public_url).status_code, 200)

    def test_revision_failure_rolls_back_and_retry_applies_only_once(self):
        update = self.create_draft()
        self.submit(update)
        self.client.force_login(self.head)
        with patch('apps.non_infrastructure.progress_application.create_head_operational_revision',
                   return_value=None):
            self.assertContains(self.client.post(self.action('approve', update), follow=True),
                                'could not be created')
        update.refresh_from_db()
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, 'planned')
        self.assertIsNone(update.applied_at)
        self.assertIsNone(update.applied_by)
        self.assertIsNone(update.publication_revision_id)
        self.assertEqual(self.base.revisions.count(), 1)
        self.assertEqual(self.client.post(self.action('apply', update)).status_code, 302)
        self.assertContains(self.client.post(self.action('apply', update), follow=True),
                            'already been applied')
        self.assertEqual(self.base.revisions.count(), 2)

    def test_stale_official_status_blocks_application_without_partial_state(self):
        update = self.create_draft()
        self.submit(update)
        self.client.force_login(self.head)
        self.project.status = 'completed'
        self.project.save(update_fields=['status'])
        self.assertContains(self.client.post(self.action('approve', update), follow=True),
                    'official status changed')
        self.project.status = 'completed'
        self.project.save(update_fields=['status'])
        update.refresh_from_db()
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, 'completed')
        self.assertIsNone(update.applied_at)
        self.assertIsNone(update.publication_revision_id)
        self.assertEqual(self.base.revisions.count(), 1)
