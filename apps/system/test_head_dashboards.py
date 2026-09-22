import re

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Project, ProjectRevision, UserRole
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
            UserRole.objects.create(user=user, department=department, role=role)
            self.users[department, role] = (user, destination)
        self.revisions = {}
        for office, kind in [('engineer', 'infrastructure'), ('mayor', 'non_infrastructure')]:
            project = Project.objects.create(project_type=kind)
            self.revisions[office] = ProjectRevision.objects.create(
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
                        self.assertEqual(list(response.context['recent_revisions']), [])
                        self.assertEqual(
                            [card['count'] for card in response.context['status_cards']],
                            [0, 1, 0, 0],
                        )
                        self.assertContains(response, reverse('publication_review_queue') + '?status=pending_review')
                        self.assertContains(response, reverse('password_change'))
                        self.assertNotContains(response, 'project_create')
                        self.assertNotContains(response, 'Edit Project')
                        self.assertContains(response, 'Needs Your Attention')
                        self.assertContains(
                            response,
                            'Complete Operational Information',
                        )
                        self.assertContains(response, 'Published Projects')
                        self.assertContains(response, 'Recent Activity')
                        own_list = reverse(
                            'engineering_projects:project_list'
                            if office == 'engineer'
                            else 'mayor_projects:non_infrastructure_project_list'
                        )
                        other_list = reverse(
                            'mayor_projects:non_infrastructure_project_list'
                            if office == 'engineer'
                            else 'engineering_projects:project_list'
                        )
                        self.assertContains(response, own_list)
                        self.assertNotContains(response, other_list)
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

    def test_sidebar_navigation_is_scoped_to_each_role(self):
        expectations = {
            ('engineer', 'staff'): {
                'groups': ['Overview', 'Projects', 'Account'],
                'project': 'Infrastructure Projects',
                'excluded': ['Non-Infrastructure Projects', 'Publication Review', 'Reports', 'User Management'],
            },
            ('engineer', 'head'): {
                'groups': ['Overview', 'Projects', 'Review & Publication', 'Reports', 'Account'],
                'project': 'Infrastructure Projects',
                'excluded': ['Non-Infrastructure Projects', 'User Management'],
            },
            ('mayor', 'staff'): {
                'groups': ['Overview', 'Projects', 'Account'],
                'project': 'Non-Infrastructure Projects',
                'excluded': ['Infrastructure Projects', 'Publication Review', 'Reports', 'User Management'],
            },
            ('mayor', 'head'): {
                'groups': ['Overview', 'Projects', 'Review & Publication', 'Reports', 'Account'],
                'project': 'Non-Infrastructure Projects',
                'excluded': ['Infrastructure Projects', 'User Management'],
            },
            ('admin', 'admin'): {
                'groups': ['Overview', 'Administration', 'Account'],
                'project': None,
                'excluded': [
                    'Infrastructure Projects', 'Non-Infrastructure Projects',
                    'Publication Review', 'Publication Lifecycle', 'Reports',
                ],
            },
        }
        for assignment, expected in expectations.items():
            user, destination = self.users[assignment]
            self.client.force_login(user)
            response = self.client.get(reverse(destination))
            navigation = response.context['account_navigation']
            labels = [
                item['label']
                for group in navigation['groups']
                for item in group['items']
            ]
            with self.subTest(assignment=assignment):
                self.assertEqual(
                    [group['label'] for group in navigation['groups']],
                    expected['groups'],
                )
                if expected['project']:
                    self.assertIn(expected['project'], labels)
                for excluded in expected['excluded']:
                    self.assertNotIn(excluded, labels)
                self.assertNotIn('Create Project', labels)
                self.assertNotIn('Create User', labels)
                self.assertContains(response, 'aria-label="Account navigation"')
                self.assertContains(response, 'aria-current="page"')

    def test_sidebar_marks_project_and_administration_destinations_active(self):
        engineer, _ = self.users['engineer', 'staff']
        self.client.force_login(engineer)
        response = self.client.get(reverse('engineering_projects:project_list'))
        projects = next(
            group for group in response.context['account_navigation']['groups']
            if group['label'] == 'Projects'
        )
        self.assertTrue(projects['items'][0]['active'])
        self.assertContains(
            response,
            'class="ui-sidebar__link active" aria-current="page"',
        )

        admin, _ = self.users['admin', 'admin']
        self.client.force_login(admin)
        response = self.client.get(reverse('user_list'))
        administration = next(
            group for group in response.context['account_navigation']['groups']
            if group['label'] == 'Administration'
        )
        self.assertTrue(administration['items'][0]['active'])

    def test_admin_user_management_pages_use_shared_sidebar_layout(self):
        admin, _ = self.users['admin', 'admin']
        editable_user, _ = self.users['engineer', 'staff']
        self.client.force_login(admin)

        for url, content_class in [
            (reverse('user_list'), 'user-management-content'),
            (reverse('user_create'), 'user-management-form-content'),
            (reverse('user_edit', kwargs={'pk': editable_user.pk}), 'user-management-form-content'),
        ]:
            response = self.client.get(url)
            navigation = response.context['account_navigation']
            labels = [
                item['label']
                for group in navigation['groups']
                for item in group['items']
            ]
            with self.subTest(url=url):
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    [group['label'] for group in navigation['groups']],
                    ['Overview', 'Administration', 'Account'],
                )
                self.assertEqual(
                    labels,
                    ['Dashboard', 'User Management', 'Profile & Password', 'Logout'],
                )
                self.assertContains(response, 'aria-label="Account navigation"')
                self.assertContains(response, content_class)
                self.assertNotContains(response, '>Publication Lifecycle<')

    def test_confirm_and_password_pages_render_inside_shared_sidebar_content(self):
        admin, _ = self.users['admin', 'admin']
        active_user, _ = self.users['engineer', 'staff']
        inactive_user, _ = self.users['mayor', 'staff']
        inactive_user.is_active = False
        inactive_user.save(update_fields=['is_active'])
        self.client.force_login(admin)

        for url, heading in [
            (reverse('user_deactivate', kwargs={'pk': active_user.pk}), 'Deactivate User'),
            (reverse('user_activate', kwargs={'pk': inactive_user.pk}), 'Activate User'),
        ]:
            response = self.client.get(url)
            with self.subTest(url=url):
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="ui-sidebar-layout"')
                self.assertContains(response, 'user-confirmation-content')
                self.assertContains(response, heading)
                header_markup = response.content.decode().split('</header>', 1)[0]
                self.assertNotIn(reverse('user_list'), header_markup)
                self.assertNotIn(reverse('logout'), header_markup)

        response = self.client.get(reverse('password_change'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<main class="ui-sidebar-layout">')
        self.assertContains(response, 'class="ui-sidebar-content"')
        self.assertContains(response, 'class="password-change-content"')
        self.assertContains(response, 'Change Your Password')

    def test_staff_dashboards_render_with_shared_sidebar_content(self):
        for assignment, route, content_class in [
            (('engineer', 'staff'), 'engineering_dashboard', 'role-dashboard-content'),
            (('mayor', 'staff'), 'mayor_dashboard', 'role-dashboard-content'),
            (('engineer', 'staff'), 'engineering_projects:project_dashboard', 'project-dashboard-content'),
            (('mayor', 'staff'), 'mayor_projects:non_infrastructure_project_dashboard', 'project-dashboard-content'),
        ]:
            user, _ = self.users[assignment]
            self.client.force_login(user)
            response = self.client.get(reverse(route))
            with self.subTest(route=route):
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'ui-sidebar-layout')
                self.assertContains(response, content_class)
                self.assertEqual(response.content.decode().count('<main'), 1)

        for assignment, route in [
            (('engineer', 'staff'), 'engineering_dashboard'),
            (('mayor', 'staff'), 'mayor_dashboard'),
        ]:
            user, _ = self.users[assignment]
            self.client.force_login(user)
            response = self.client.get(reverse(route))
            header_markup = response.content.decode().split('</header>', 1)[0]
            self.assertNotIn(reverse('logout'), header_markup)

    def test_user_management_department_filters_and_search_work_together(self):
        admin, _ = self.users['admin', 'admin']
        self.client.force_login(admin)
        expected = {
            '': {user.pk for user, _ in self.users.values()},
            'engineer': {
                self.users['engineer', 'staff'][0].pk,
                self.users['engineer', 'head'][0].pk,
            },
            'mayor': {
                self.users['mayor', 'staff'][0].pk,
                self.users['mayor', 'head'][0].pk,
            },
            'admin': {admin.pk},
        }

        for department, expected_ids in expected.items():
            response = self.client.get(
                reverse('user_list'),
                {'department': department} if department else {},
            )
            with self.subTest(department=department or 'all'):
                self.assertEqual(
                    {user.pk for user in response.context['users']},
                    expected_ids,
                )
                self.assertEqual(response.context['current_department'], department)
                self.assertContains(response, 'aria-label="Filter users by department"')
                selected_label = {
                    '': 'All Users',
                    'engineer': 'Engineering',
                    'mayor': "Mayor's Office",
                    'admin': 'Admin',
                }[department]
                self.assertContains(
                    response,
                    f'aria-current="page">{selected_label}</a>',
                )

        response = self.client.get(
            reverse('user_list'),
            {'search': 'head', 'department': 'engineer'},
        )
        self.assertEqual(
            [user.pk for user in response.context['users']],
            [self.users['engineer', 'head'][0].pk],
        )
        self.assertContains(
            response,
            '<input type="hidden" name="department" value="engineer">',
            html=True,
        )
        self.assertContains(response, 'search=head&amp;department=mayor')

    def test_user_management_pagination_preserves_search_and_department(self):
        admin, _ = self.users['admin', 'admin']
        self.client.force_login(admin)
        for index in range(11):
            user = User.objects.create_user(f'filter-engineer-{index:02d}')
            UserRole.objects.create(user=user, department='engineer', role='staff')

        response = self.client.get(
            reverse('user_list'),
            {'search': 'filter-engineer', 'department': 'engineer'},
        )

        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['users']), 10)
        self.assertContains(
            response,
            'search=filter-engineer&amp;department=engineer&amp;page=2',
        )

    def test_admin_lifecycle_navigation_excludes_review_queue(self):
        admin, _ = self.users['admin', 'admin']
        self.client.force_login(admin)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertContains(response, 'class="ui-sidebar-layout admin-dashboard-layout"')
        self.assertContains(response, 'class="dashboard-content admin-dashboard-content"')
        self.assertContains(response, 'class="welcome-section ui-card ui-card--padded"')
        self.assertContains(response, 'class="dashboard-stats"')
        self.assertContains(response, 'class="action-grid"')
        header_markup = response.content.decode().split('</header>', 1)[0]
        self.assertNotIn(reverse('user_list'), header_markup)
        self.assertNotIn(reverse('publication_lifecycle'), header_markup)
        self.assertNotIn(reverse('logout'), header_markup)
        self.assertContains(response, reverse('publication_lifecycle'))
        self.assertNotContains(response, reverse('publication_review_queue'))
        response = self.client.get(reverse('publication_lifecycle'))
        self.assertEqual(set(response.context['revisions']), set(self.revisions.values()))
        revision = self.revisions['engineer']
        ProjectRevision.objects.filter(pk=revision.pk).update(status='pending_review')
        response = self.client.get(reverse('publication_lifecycle'))
        self.assertNotIn(revision.pk, [item.pk for item in response.context['revisions']])
        for (department, role), (user, _) in self.users.items():
            if role != 'admin':
                self.client.force_login(user)
                self.assertEqual(self.client.get(reverse('publication_lifecycle')).status_code, 403)

    def test_head_dashboard_surfaces_only_its_operational_replacements(self):
        operational = {}
        for office, project_type in [
            ('engineer', 'infrastructure'),
            ('mayor', 'non_infrastructure'),
        ]:
            project = Project.objects.create(project_type=project_type)
            current = ProjectRevision.objects.create(
                project=project,
                revision_number=1,
                status='published',
                is_current_public=True,
                snapshot={'project': {'type': project_type}},
            )
            head = self.users[office, 'head'][0]
            operational[office] = ProjectRevision.objects.create(
                project=project,
                revision_number=2,
                status='approved',
                previous_revision=current,
                submitted_by=head,
                reviewed_by=head,
                reviewed_at=timezone.now(),
                snapshot={
                    'project': {'type': project_type},
                    project_type: {
                        'id': 20,
                        'title': f'{office} operational update',
                    },
                },
            )

        for office, destination in [
            ('engineer', 'engineering_head_dashboard'),
            ('mayor', 'mayor_head_dashboard'),
        ]:
            self.client.force_login(self.users[office, 'head'][0])
            response = self.client.get(reverse(destination))
            self.assertEqual(
                list(response.context['operational_revisions']),
                [operational[office]],
            )
            self.assertEqual(response.context['operational_revision_count'], 1)
            self.assertContains(
                response,
                f'{office} operational update',
            )
            self.assertContains(response, 'Preview &amp; Publish Update')
            self.assertContains(
                response,
                'Operational Updates Waiting to Publish',
            )
            other = 'mayor' if office == 'engineer' else 'engineer'
            self.assertNotContains(
                response,
                f'{other} operational update',
            )

    def test_complete_initial_revision_is_ready_to_publish(self):
        revision = self.revisions['engineer']
        revision.snapshot = {
            'project': {'type': 'infrastructure'},
            'infrastructure': {
                'id': 1,
                'title': 'Ready Infrastructure Project',
                'status': 'not_yet_started',
                'status_label': 'Not Yet Started',
                'physical_progress_percentage': '0.00',
            },
            '_head_operational_confirmation': {
                'project_type': 'infrastructure',
                'confirmed_by_user_id': self.users['engineer', 'head'][0].pk,
            },
        }
        revision.save(update_fields=['snapshot'])
        self.client.force_login(self.users['engineer', 'head'][0])

        response = self.client.get(reverse('engineering_head_dashboard'))

        self.assertEqual(response.context['needs_operational_items'], [])
        self.assertEqual(
            len(response.context['ready_to_publish_items']),
            1,
        )
        self.assertContains(response, 'Ready Infrastructure Project')
        self.assertContains(response, 'Preview &amp; Publish')
        self.assertNotContains(response, 'Complete Operational Information')

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
