from copy import deepcopy

from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from .models import Project, ProjectPublicationRevision, UserFlag
from .permissions import can_review_infrastructure, can_review_non_infrastructure
from .publication_service import review_publication_revision


class OfficeReviewPermissionTests(TestCase):
    def setUp(self):
        self.users = {}
        self.revisions = {}
        for office, project_type in [('engineer', 'infrastructure'), ('mayor', 'non_infrastructure')]:
            for role in ['staff', 'head']:
                user = User.objects.create_user(f'{office}-{role}', is_staff=True)
                UserFlag.objects.create(user=user, department=office, role=role)
                self.users[office, role] = user
            staff = self.users[office, 'staff']
            project = Project.objects.create(project_type=project_type, created_by_user=staff)
            self.revisions[office] = ProjectPublicationRevision.objects.create(
                project=project, revision_number=1, status='pending_review', submitted_by=staff,
                snapshot_data={
                    'project': {'type': project_type, 'creator': {'id': staff.pk}},
                    project_type: {'id': 1, 'title': f'{office} submission'},
                },
            )
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'password')

    def test_heads_can_make_all_three_decisions_through_views(self):
        for office, revision in self.revisions.items():
            head = self.users[office, 'head']
            self.client.force_login(head)
            self.assertEqual(can_review_infrastructure(head), office == 'engineer')
            self.assertEqual(can_review_non_infrastructure(head), office == 'mayor')
            detail = self.client.get(reverse(
                'publication_revision_detail',
                args=[revision.pk],
            ))
            self.assertContains(detail, 'Record Decision')
            self.assertNotContains(detail, 'Publish to Public Dashboard')
            snapshot = deepcopy(revision.snapshot_data)
            for decision in ['approved', 'rejected', 'needs_revision']:
                with self.subTest(office=office, decision=decision):
                    ProjectPublicationRevision.objects.filter(pk=revision.pk).update(status='pending_review')
                    response = self.client.post(reverse('publication_revision_review', args=[revision.pk]), {
                        'decision': decision, 'notes': 'Office review notes',
                    })
                    self.assertEqual(response.status_code, 302)
                    revision.refresh_from_db()
                    self.assertEqual(revision.status, decision)
                    self.assertEqual(revision.reviewed_by, head)
                    self.assertEqual(revision.review_notes, 'Office review notes')
                    self.assertEqual(revision.snapshot_data, snapshot)
                    self.assertFalse(revision.is_current_public_revision)
                    if decision == 'approved':
                        detail = self.client.get(reverse(
                            'publication_revision_detail',
                            args=[revision.pk],
                        ))
                        self.assertContains(
                            detail,
                            'Publish to Public Dashboard',
                        )
                        self.assertNotContains(
                            detail,
                            'Publish Update to Public Dashboard',
                        )

    def test_queue_rows_and_counts_are_scoped_for_each_status(self):
        other = self.revisions['mayor']
        ProjectPublicationRevision.objects.create(project=other.project, revision_number=2, status='approved')
        for office in ['engineer', 'mayor']:
            self.client.force_login(self.users[office, 'head'])
            response = self.client.get(reverse('publication_review_queue'))
            self.assertEqual(list(response.context['revisions']), [self.revisions[office]])
            self.assertEqual(response.context['pending_count'], 1)
            self.assertEqual(response.context['approved_count'], int(office == 'mayor'))
            response = self.client.get(reverse('publication_review_queue'), {'status': 'approved'})
            self.assertEqual(len(response.context['revisions']), int(office == 'mayor'))

    def test_wrong_office_staff_admin_and_anonymous_denied_at_view_and_service(self):
        for office, revision in self.revisions.items():
            other = 'mayor' if office == 'engineer' else 'engineer'
            for user in [self.users[other, 'head'], self.users[office, 'staff'], self.users[other, 'staff'], self.admin, AnonymousUser()]:
                with self.subTest(office=office, user=str(user)):
                    self.client.logout()
                    if user.is_authenticated:
                        self.client.force_login(user)
                    self.assertEqual(self.client.get(reverse('publication_revision_detail', args=[revision.pk])).status_code, 403)
                    for decision in ['approved', 'rejected', 'needs_revision']:
                        self.assertEqual(self.client.post(reverse('publication_revision_review', args=[revision.pk]), {
                            'decision': decision, 'notes': 'Not authorized',
                        }).status_code, 403)
                        with self.assertRaises(PermissionDenied):
                            review_publication_revision(revision, user, decision, 'Not authorized')
                    revision.refresh_from_db()
                    self.assertEqual(revision.status, 'pending_review')
            self.client.force_login(self.admin)
            self.assertEqual(self.client.get(reverse('publication_review_queue')).status_code, 403)

    def test_self_review_after_promotion_is_denied_and_not_offered(self):
        for office, revision in self.revisions.items():
            submitter = self.users[office, 'staff']
            UserFlag.objects.filter(user=submitter).update(role='head')
            self.client.force_login(submitter)
            detail = self.client.get(reverse('publication_revision_detail', args=[revision.pk]))
            self.assertEqual(detail.status_code, 200)
            self.assertFalse(detail.context['can_review'])
            self.assertEqual(self.client.post(reverse('publication_revision_review', args=[revision.pk]), {
                'decision': 'approved',
            }).status_code, 403)
            with self.assertRaises(PermissionDenied):
                review_publication_revision(revision, submitter, 'approved')

    def test_service_uses_persisted_submitter_not_callers_stale_revision(self):
        revision = self.revisions['engineer']
        head = self.users['engineer', 'head']
        ProjectPublicationRevision.objects.filter(pk=revision.pk).update(submitted_by=head)
        with self.assertRaises(PermissionDenied):
            review_publication_revision(revision, head, 'approved')

    def test_creator_cannot_review_even_when_someone_else_submits(self):
        revision = self.revisions['engineer']
        creator = self.users['engineer', 'staff']
        head = self.users['engineer', 'head']
        UserFlag.objects.filter(user=creator).update(role='head')
        ProjectPublicationRevision.objects.filter(pk=revision.pk).update(submitted_by=head)
        with self.assertRaises(PermissionDenied):
            review_publication_revision(revision, creator, 'approved')

    def test_missing_flags_and_inactive_heads_cannot_review(self):
        missing = User.objects.create_user('missing-flags', is_staff=True)
        missing.__dict__['_compat_profile'] = {'department': 'engineer', 'role': 'head'}
        inactive = self.users['engineer', 'head']
        inactive.is_active = False
        for user in [missing, inactive]:
            self.assertFalse(can_review_infrastructure(user))
            self.assertFalse(can_review_non_infrastructure(user))
            with self.assertRaises(PermissionDenied):
                review_publication_revision(self.revisions['engineer'], user, 'approved')

    def test_snapshot_creator_attribution_survives_changed_live_creator(self):
        revision = self.revisions['engineer']
        creator = self.users['engineer', 'staff']
        replacement = self.users['engineer', 'head']
        UserFlag.objects.filter(user=creator).update(role='head')
        Project.objects.filter(pk=revision.project_id).update(created_by_user=replacement)
        ProjectPublicationRevision.objects.filter(pk=revision.pk).update(submitted_by=replacement)
        with self.assertRaises(PermissionDenied):
            review_publication_revision(revision, creator, 'approved')

    def test_heads_can_publish_but_admin_detail_is_read_only(self):
        revision = review_publication_revision(self.revisions['engineer'], self.users['engineer', 'head'], 'approved')
        self.client.force_login(self.users['engineer', 'head'])
        detail = self.client.get(reverse('publication_revision_detail', args=[revision.pk]))
        self.assertTrue(detail.context['can_publish'])
        for action in ['archive']:
            self.assertEqual(self.client.post(reverse(f'publication_revision_{action}', args=[revision.pk])).status_code, 403)
        self.client.force_login(self.admin)
        detail = self.client.get(reverse('publication_revision_detail', args=[revision.pk]))
        self.assertFalse(detail.context['can_publish'])
        self.assertFalse(detail.context['can_review'])
        self.assertEqual(self.client.post(reverse('publication_revision_review', args=[revision.pk]), {'decision': 'approved'}).status_code, 403)

    def test_seed_publish_uses_head_approval_and_publication(self):
        from .management.commands.seed_projects import Command
        from .models import Infrastructure_Project

        project = Project.objects.create(project_type='infrastructure', created_by_user=self.users['engineer', 'staff'])
        Infrastructure_Project.objects.create(project=project, infrastructure_title='Seed verification')
        Command()._publish_project(project, employee=self.users['engineer', 'staff'], admin=self.admin)
        revision = project.publication_revisions.get()
        self.assertEqual(revision.status, 'published')
        self.assertEqual(revision.reviewed_by.flags.role, 'head')
        self.assertEqual(revision.published_by, revision.reviewed_by)
