import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    NonInfrastructureEvidence,
    NonInfrastructureProgressUpdate,
    NonInfrastructureProject,
    Project,
    ProjectRevision,
    UserRole,
)
from .publication_workflow import PublicationStatus


class MayorStaffActionRequiredTests(TestCase):
    def setUp(self):
        media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(media_directory.cleanup)
        media_override = override_settings(MEDIA_ROOT=media_directory.name)
        media_override.enable()
        self.addCleanup(media_override.disable)

        self.staff = self.make_user('mayor-staff', 'mayor', 'staff')
        self.other_staff = self.make_user('other-mayor-staff', 'mayor', 'staff')
        self.mayor_head = self.make_user('mayor-head', 'mayor', 'head')
        self.project = self.make_project('Community Wellness Program', self.staff)
        self.dashboard_url = reverse('mayor_dashboard')
        self.client.force_login(self.staff)

    def make_user(self, username, department, role):
        user = User.objects.create_user(
            username=username,
            password='test-password',
            is_staff=True,
        )
        UserRole.objects.create(user=user, department=department, role=role)
        return user

    def make_project(self, title, creator):
        base = Project.objects.create(
            project_type='non_infrastructure',
            created_by_user=creator,
        )
        return NonInfrastructureProject.objects.create(
            project=base,
            title=title,
            project_type=NonInfrastructureProject.ProjectType.PROGRAM,
        )

    def make_progress_update(self, *, submitted_by=None, review_status=None):
        update = NonInfrastructureProgressUpdate.objects.create(
            non_infrastructure=self.project,
            previous_status='planned',
            proposed_status='ongoing',
            remarks='The program has started.',
            submitted_by=submitted_by or self.staff,
            submitted_at=timezone.now(),
            review_status=(
                review_status
                or NonInfrastructureProgressUpdate.ReviewStatus.RETURNED
            ),
            reviewed_by=self.mayor_head,
            reviewed_at=timezone.now(),
            review_notes='Please include the attendance sheet.',
        )
        NonInfrastructureEvidence.objects.create(
            progress_update=update,
            evidence_file=SimpleUploadedFile(
                'support.pdf',
                b'%PDF-1.4 evidence',
                content_type='application/pdf',
            ),
            uploaded_by=update.submitted_by,
        )
        return update

    def test_returned_update_shows_project_reason_date_and_edit_action(self):
        update = self.make_progress_update()

        response = self.client.get(self.dashboard_url)

        self.assertContains(response, 'Action Required')
        self.assertContains(response, 'Returned Progress Update')
        self.assertContains(response, self.project.title)
        self.assertContains(response, 'Please include the attendance sheet.')
        self.assertContains(response, 'Returned:')
        edit_url = reverse(
            'mayor_projects:non_infrastructure_progress_update_edit',
            args=[self.project.pk, update.pk],
        )
        self.assertContains(response, 'Edit &amp; Resubmit')
        self.assertContains(response, f'href="{edit_url}"')

    def test_dashboard_action_reaches_existing_owner_only_edit_route(self):
        update = self.make_progress_update()
        edit_url = reverse(
            'mayor_projects:non_infrastructure_progress_update_edit',
            args=[self.project.pk, update.pk],
        )

        response = self.client.get(self.dashboard_url)

        self.assertContains(response, f'href="{edit_url}"')
        self.assertEqual(self.client.get(edit_url).status_code, 200)

    def test_another_staff_members_returned_update_is_not_shown(self):
        update = self.make_progress_update(submitted_by=self.other_staff)

        response = self.client.get(self.dashboard_url)

        self.assertNotContains(response, 'Action Required')
        self.assertNotContains(response, update.review_notes)
        edit_url = reverse(
            'mayor_projects:non_infrastructure_progress_update_edit',
            args=[self.project.pk, update.pk],
        )
        self.assertEqual(self.client.get(edit_url).status_code, 404)

    def test_pending_and_approved_progress_updates_are_not_returned_actions(self):
        update = self.make_progress_update()
        for status in (
            NonInfrastructureProgressUpdate.ReviewStatus.PENDING_REVIEW,
            NonInfrastructureProgressUpdate.ReviewStatus.APPROVED,
        ):
            with self.subTest(status=status):
                update.review_status = status
                update.save(update_fields=['review_status'])

                response = self.client.get(self.dashboard_url)

                self.assertNotContains(response, 'Action Required')
                self.assertNotContains(response, update.review_notes)

    def test_resubmitted_update_disappears_from_action_required(self):
        update = self.make_progress_update()
        edit_url = reverse(
            'mayor_projects:non_infrastructure_progress_update_edit',
            args=[self.project.pk, update.pk],
        )
        self.assertContains(self.client.get(self.dashboard_url), 'Action Required')

        response = self.client.post(edit_url, {
            'proposed_status': 'completed',
            'remarks': 'The program has now been completed.',
        })

        self.assertEqual(response.status_code, 302)
        update.refresh_from_db()
        self.assertEqual(
            update.review_status,
            NonInfrastructureProgressUpdate.ReviewStatus.PENDING_REVIEW,
        )
        self.assertNotContains(self.client.get(self.dashboard_url), 'Action Required')

    def test_needs_revision_publication_shows_existing_edit_and_resubmit_access(self):
        revision = ProjectRevision.objects.create(
            project=self.project.project,
            revision_number=1,
            status=PublicationStatus.NEEDS_REVISION,
            reviewed_at=timezone.now(),
            review_notes='Correct the program beneficiary information.',
        )

        response = self.client.get(self.dashboard_url)

        self.assertContains(response, 'Project Needs Revision')
        self.assertContains(response, self.project.title)
        self.assertContains(
            response,
            'Correct the program beneficiary information.',
        )
        self.assertContains(response, 'Edit Project')
        self.assertContains(response, 'Review &amp; Resubmit')
        self.assertContains(
            response,
            reverse(
                'mayor_projects:non_infrastructure_project_update',
                args=[self.project.pk],
            ),
        )
        self.assertContains(
            response,
            reverse(
                'mayor_projects:non_infrastructure_project_detail',
                args=[self.project.pk],
            ),
        )
        self.assertEqual(revision.status, PublicationStatus.NEEDS_REVISION)

    def test_older_needs_revision_is_hidden_when_a_newer_revision_is_active(self):
        ProjectRevision.objects.create(
            project=self.project.project,
            revision_number=1,
            status=PublicationStatus.NEEDS_REVISION,
            review_notes='This older return is no longer active.',
        )
        ProjectRevision.objects.create(
            project=self.project.project,
            revision_number=2,
            status=PublicationStatus.PENDING_REVIEW,
        )

        response = self.client.get(self.dashboard_url)

        self.assertNotContains(response, 'Project Needs Revision')
        self.assertNotContains(response, 'This older return is no longer active.')

    def test_project_revision_not_managed_by_current_office_is_not_exposed(self):
        engineering_staff = self.make_user(
            'engineering-staff',
            'engineer',
            'staff',
        )
        ProjectRevision.objects.create(
            project=self.project.project,
            revision_number=1,
            status=PublicationStatus.NEEDS_REVISION,
            review_notes='This must remain outside the engineering dashboard.',
        )
        self.client.force_login(engineering_staff)

        response = self.client.get(reverse('engineering_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Action Required')
        self.assertNotContains(
            response,
            'This must remain outside the engineering dashboard.',
        )
