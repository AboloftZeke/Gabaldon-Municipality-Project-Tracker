import re

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Project, ProjectPublicationRevision, UserFlag
from .navigation import dashboard_name


class HeadDashboardTests(TestCase):
    def setUp(self):
        self.users = {}
        for department, role, destination in [
            ('admin', 'admin', 'admin_dashboard'),
            ('engineer', 'staff', 'engineering_dashboard'),
            ('engineer', 'head', 'engineering_head_dashboard'),
            ('mayor', 'staff', 'mayor_dashboard'),
            ('mayor', 'head', 'mayor_head_dashboard'),
        ]:
            user = User.objects.create_user(
                f'{department}-{role}', email=f'{department}-{role}@example.com',
                password='ValidLoginPass!2026', is_staff=True, is_superuser=role == 'admin',
            )
            UserFlag.objects.create(user=user, department=department, role=role)
            self.users[department, role] = (user, destination)
        self.revisions = {}
        for office, kind in [('engineer', 'infrastructure'), ('mayor', 'non_infrastructure')]:
            project = Project.objects.create(project_type=kind)
            self.revisions[office] = ProjectPublicationRevision.objects.create(
                project=project, revision_number=1, status='approved', reviewed_at=timezone.now(),
            )

    def test_otp_login_destinations_for_all_assignments(self):
        for user, destination in self.users.values():
            with self.subTest(destination=destination):
                self.client.logout()
                response = self.client.post(reverse('login'), {
                    'username': user.username, 'password': 'ValidLoginPass!2026',
                })
                self.assertRedirects(response, reverse('login_otp_verify'))
                self.assertNotIn('_auth_user_id', self.client.session)
                code = re.search(r'\b(\d{6})\b', mail.outbox[-1].body).group(1)
                response = self.client.post(reverse('login_otp_verify'), {'code': code})
                self.assertRedirects(response, reverse(destination))

    def test_head_dashboard_access_matrix_and_scoped_content(self):
        for office, destination in [('engineer', 'engineering_head_dashboard'), ('mayor', 'mayor_head_dashboard')]:
            for assignment, (user, _) in self.users.items():
                self.client.force_login(user)
                response = self.client.get(reverse(destination))
                allowed = assignment == (office, 'head')
                with self.subTest(office=office, assignment=assignment):
                    self.assertEqual(response.status_code, 200 if allowed else 403)
                    if allowed:
                        self.assertEqual(list(response.context['recent_revisions']), [self.revisions[office]])
                        self.assertEqual([card['count'] for card in response.context['status_cards']], [0, 0, 1])
                        self.assertContains(response, reverse('publication_review_queue') + '?status=pending_review')
                        self.assertContains(response, reverse('password_change'))
                        self.assertNotContains(response, 'project_create')
                        self.assertNotContains(response, '/infrastructure/')
                        self.assertNotContains(response, '/non-infrastructure/')
            self.client.logout()
            self.assertEqual(self.client.get(reverse(destination)).status_code, 403)

    def test_staff_navigation_and_head_legacy_dashboard_redirects(self):
        for office, prefix, staff_dashboard in [
            ('engineer', 'engineering_projects:project_create', 'engineering_dashboard'),
            ('mayor', 'mayor_projects:non_infrastructure_project_create', 'mayor_dashboard'),
        ]:
            staff, _ = self.users[office, 'staff']
            self.client.force_login(staff)
            response = self.client.get(reverse(staff_dashboard))
            self.assertContains(response, reverse(prefix))
            head, destination = self.users[office, 'head']
            self.client.force_login(head)
            self.assertRedirects(self.client.get(reverse(staff_dashboard)), reverse(destination))
            for route in ([
                'engineering_projects:project_list', 'engineering_projects:project_dashboard',
            ] if office == 'engineer' else [
                'mayor_projects:non_infrastructure_project_list',
                'mayor_projects:non_infrastructure_project_dashboard',
            ]):
                response = self.client.get(reverse(route))
                self.assertNotContains(response, reverse(prefix))
                self.assertContains(response, reverse(destination))

    def test_admin_lifecycle_navigation_excludes_review_queue(self):
        admin, _ = self.users['admin', 'admin']
        self.client.force_login(admin)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertContains(response, reverse('publication_lifecycle'))
        self.assertNotContains(response, reverse('publication_review_queue'))
        response = self.client.get(reverse('publication_lifecycle'))
        self.assertEqual(set(response.context['revisions']), set(self.revisions.values()))
        revision = self.revisions['engineer']
        ProjectPublicationRevision.objects.filter(pk=revision.pk).update(status='pending_review')
        response = self.client.get(reverse('publication_lifecycle'))
        self.assertNotIn(revision.pk, [item.pk for item in response.context['revisions']])
        for (department, role), (user, _) in self.users.items():
            if role != 'admin':
                self.client.force_login(user)
                self.assertEqual(self.client.get(reverse('publication_lifecycle')).status_code, 403)

    def test_missing_assignment_does_not_use_compatibility_profile(self):
        user = User.objects.create_user('unassigned', is_staff=True)
        self.assertEqual(dashboard_name(user), 'public_dashboard')
        head, _ = self.users['engineer', 'head']
        # A cached compatibility department must not select the login destination.
        head._compat_profile = type('Profile', (), {'department': 'mayor'})()
        self.assertEqual(dashboard_name(head), 'engineering_head_dashboard')

    def test_password_change_preserves_session_and_role_destination(self):
        for user, destination in self.users.values():
            with self.subTest(destination=destination):
                self.client.force_login(user)
                response = self.client.post(reverse('password_change'), {
                    'current_password': 'ValidLoginPass!2026',
                    'new_password': 'UpdatedSecret!7392', 'confirm_password': 'UpdatedSecret!7392',
                })
                self.assertRedirects(response, reverse(destination))
                user.refresh_from_db()
                self.assertTrue(user.check_password('UpdatedSecret!7392'))
                self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
