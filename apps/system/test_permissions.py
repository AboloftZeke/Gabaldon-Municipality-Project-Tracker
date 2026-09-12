from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase
from django.urls import reverse

from .models import Infrastructure_Project, Non_Infrastructure_Project, Project, UserFlag
from .permissions import (
    can_manage_infrastructure, can_manage_non_infrastructure,
    department_for_user, is_engineering_head, is_mayor_head,
)


class ProjectCapabilityTests(TestCase):
    def setUp(self):
        self.accounts = {}
        for department in ['engineer', 'mayor']:
            for role in ['staff', 'head']:
                user = User.objects.create_user(f'{department}-{role}', is_staff=True)
                UserFlag.objects.create(user=user, department=department, role=role)
                self.accounts[department, role] = user
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'password')
        self.infra = Infrastructure_Project.objects.create(
            project=Project.objects.create(project_type='infrastructure', created_by_user=self.admin),
            infrastructure_title='Permission test road',
        )
        self.noninfra = Non_Infrastructure_Project.objects.create(
            project=Project.objects.create(project_type='non_infrastructure', created_by_user=self.admin),
            non_infra_name='Permission test program',
        )

    def urls(self, department):
        if department == 'engineer':
            prefix, name, pk = 'engineering_projects', 'project', self.infra.pk
        else:
            prefix, name, pk = 'mayor_projects', 'non_infrastructure_project', self.noninfra.pk
        return {
            action: reverse(f'{prefix}:{name}_{action}', args=[] if action == 'create' else [pk])
            for action in ['create', 'update', 'delete', 'submit_for_review']
        }

    def test_capability_matrix(self):
        for pair, user in self.accounts.items():
            with self.subTest(pair=pair):
                self.assertEqual(can_manage_infrastructure(user), pair == ('engineer', 'staff'))
                self.assertEqual(can_manage_non_infrastructure(user), pair == ('mayor', 'staff'))
                self.assertEqual(is_engineering_head(user), pair == ('engineer', 'head'))
                self.assertEqual(is_mayor_head(user), pair == ('mayor', 'head'))
        self.assertEqual(department_for_user(self.admin), 'admin')
        self.assertFalse(can_manage_infrastructure(self.admin))
        self.assertFalse(can_manage_non_infrastructure(self.admin))

    def test_heads_and_other_department_cannot_get_or_post_management_routes(self):
        for pair, user in self.accounts.items():
            self.client.force_login(user)
            for department in ['engineer', 'mayor']:
                if pair == (department, 'staff'):
                    continue
                for action, url in self.urls(department).items():
                    with self.subTest(pair=pair, department=department, action=action):
                        self.assertEqual(self.client.get(url).status_code, 403)
                        self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.assertEqual(Project.objects.count(), 2)
        self.assertEqual(self.infra.project.publication_revisions.count(), 0)
        self.assertEqual(self.noninfra.project.publication_revisions.count(), 0)

    def test_staff_reach_forms_and_can_delete_their_office_project(self):
        for department in ['engineer', 'mayor']:
            self.client.force_login(self.accounts[department, 'staff'])
            urls = self.urls(department)
            for action in ['create', 'update', 'delete']:
                self.assertEqual(self.client.get(urls[action]).status_code, 200)
            # Invalid input reaches form validation rather than authorization denial.
            for action in ['create', 'update']:
                self.assertEqual(self.client.post(urls[action], {}).status_code, 200)
            self.assertEqual(self.client.post(urls['delete']).status_code, 302)
        self.assertEqual(Project.objects.count(), 0)

    def test_admin_exceptions_are_unchanged(self):
        self.client.force_login(self.admin)
        for url in self.urls('engineer').values():
            self.assertEqual(self.client.post(url, {}).status_code, 403)
        urls = self.urls('mayor')
        for action in ['create', 'submit_for_review']:
            self.assertEqual(self.client.post(urls[action], {}).status_code, 403)
        self.assertEqual(self.client.get(urls['update']).status_code, 200)
        self.assertEqual(self.client.post(urls['update'], {}).status_code, 200)
        self.assertEqual(self.client.post(urls['delete']).status_code, 302)
        self.assertEqual(self.client.get(reverse('publication_review_queue')).status_code, 200)

    def test_missing_flag_and_compatibility_profile_do_not_grant_management(self):
        user = User.objects.create_user('missing', is_staff=True)
        user.__dict__['_compat_profile'] = {'department': 'engineer'}
        for subject in [None, AnonymousUser(), user]:
            for helper in [can_manage_infrastructure, can_manage_non_infrastructure, is_engineering_head, is_mayor_head]:
                self.assertFalse(helper(subject))
        self.client.force_login(user)
        for department in ['engineer', 'mayor']:
            self.assertEqual(self.client.post(self.urls(department)['create'], {}).status_code, 403)

    def test_invalid_persisted_combinations_fail_closed(self):
        user = self.accounts['engineer', 'staff']
        # Simulate legacy/corrupt data without disabling the database constraint.
        for pair in [('engineer', ''), ('engineer', 'admin'), ('mayor', None), ('admin', 'head'), ('', 'staff'), ('unknown', 'staff')]:
            with self.subTest(pair=pair), patch('apps.system.permissions.UserFlag.objects.filter') as query:
                query.return_value.values_list.return_value.first.return_value = pair
                self.assertIsNone(department_for_user(user))
                for helper in [can_manage_infrastructure, can_manage_non_infrastructure, is_engineering_head, is_mayor_head]:
                    self.assertFalse(helper(user))

    def test_persisted_role_change_overrides_cached_profile_and_flag(self):
        user = self.accounts['engineer', 'staff']
        self.assertEqual(user.flags.role, 'staff')
        self.assertEqual(user.profile.department, 'engineer')
        UserFlag.objects.filter(user=user).update(role='head')
        self.assertFalse(can_manage_infrastructure(user))
        self.assertTrue(is_engineering_head(user))

    def test_inactive_accounts_fail_closed(self):
        user = self.accounts['engineer', 'staff']
        user.is_active = False
        self.assertFalse(can_manage_infrastructure(user))

    def test_heads_remain_without_publication_review_access(self):
        for department in ['engineer', 'mayor']:
            self.client.force_login(self.accounts[department, 'head'])
            self.assertEqual(self.client.get(reverse('publication_review_queue')).status_code, 403)
