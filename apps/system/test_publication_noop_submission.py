from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import NonInfrastructureCategory, NonInfrastructureProject, Project, ProjectRevision, UserRole
from .publication_snapshots import build_project_publication_snapshot
from .publication_workflow import PublicationStatus


class NonInfrastructureNoOpSubmissionTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('mayor-staff', password='test-password')
        UserRole.objects.create(user=self.staff, department='mayor', role='staff')
        category = NonInfrastructureCategory.objects.create(
            type_code='noop-test',
            type_name='No-op Test Category',
        )
        self.base = Project.objects.create(
            project_type='non_infrastructure',
            created_by_user=self.staff,
        )
        self.project = NonInfrastructureProject.objects.create(
            project=self.base,
            title='Published Program',
            description='Published description',
            category=category,
            project_type=NonInfrastructureProject.ProjectType.PROGRAM,
            proponent='Mayor Office',
            beneficiaries=10,
        )
        self.published = ProjectRevision.objects.create(
            project=self.base,
            revision_number=1,
            status=PublicationStatus.PUBLISHED,
            snapshot=build_project_publication_snapshot(self.base),
            is_current_public=True,
        )
        self.submit_url = reverse(
            'mayor_projects:non_infrastructure_project_submit_for_review',
            args=[self.project.pk],
        )
        self.client.force_login(self.staff)

    def test_unchanged_published_project_is_rejected_without_new_revision(self):
        response = self.client.post(self.submit_url, follow=True)

        self.assertContains(
            response,
            'No changes have been made since the current published version.',
        )
        self.assertEqual(self.base.revisions.count(), 1)
        self.published.refresh_from_db()
        self.assertEqual(self.published.status, PublicationStatus.PUBLISHED)
        self.assertTrue(self.published.is_current_public)

    def test_changed_project_can_still_be_submitted(self):
        self.project.title = 'Updated Published Program'
        self.project.save(update_fields=['title', 'updated_at'])

        response = self.client.post(self.submit_url)

        self.assertEqual(response.status_code, 302)
        revision = self.base.revisions.exclude(pk=self.published.pk).get()
        self.assertEqual(revision.status, PublicationStatus.PENDING_REVIEW)
        self.assertEqual(revision.snapshot['non_infrastructure']['title'], 'Updated Published Program')
        self.assertEqual(revision.previous_revision_id, self.published.pk)

    def test_initial_publication_without_current_baseline_is_unaffected(self):
        self.published.delete()

        response = self.client.post(self.submit_url)

        self.assertEqual(response.status_code, 302)
        revision = self.base.revisions.get()
        self.assertEqual(revision.status, PublicationStatus.PENDING_REVIEW)
        self.assertEqual(revision.previous_revision_id, None)
