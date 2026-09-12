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
        self.assertEqual(self.client.get(reverse('publication_review_queue')).status_code, 403)

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

    def test_heads_can_access_their_publication_review_queue(self):
        for department in ['engineer', 'mayor']:
            self.client.force_login(self.accounts[department, 'head'])
            self.assertEqual(self.client.get(reverse('publication_review_queue')).status_code, 200)

    def test_denied_payloads_leave_all_project_data_unchanged(self):
        from django.apps import apps
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import Project_Image

        image = Project_Image.objects.create(project=self.infra.project, image_url='/media/original.jpg', is_cover=True)
        # Include normalized fields, images, inspections, financials and revisions.
        models = [model for model in apps.get_app_config('system').get_models()
                  if model._meta.managed and model not in [UserFlag]]
        def snapshot():
            return {model._meta.label: list(model.objects.order_by(model._meta.pk.name).values()) for model in models}

        for pair, user in self.accounts.items():
            self.client.force_login(user)
            before = snapshot()
            for department in ['engineer', 'mayor']:
                if pair == (department, 'staff'):
                    continue
                for action, url in self.urls(department).items():
                    with self.subTest(pair=pair, office=department, action=action):
                        response = self.client.post(url, {
                            'title': 'Unauthorized change', 'non_infra_name': 'Unauthorized change',
                            'status': 'completed', 'physical_progress_percentage': '100',
                            'images_to_delete': str(image.pk), 'cover_image_selection': 'new:0',
                            'project_images': SimpleUploadedFile('denied.jpg', b'image', content_type='image/jpeg'),
                        })
                        self.assertEqual(response.status_code, 403)
                        self.assertEqual(snapshot(), before)

    def test_heads_read_details_without_management_controls(self):
        for office, route, record in [
            ('engineer', 'engineering_projects:project_detail', self.infra),
            ('mayor', 'mayor_projects:non_infrastructure_project_detail', self.noninfra),
        ]:
            self.client.force_login(self.accounts[office, 'head'])
            response = self.client.get(reverse(route, args=[record.pk]))
            self.assertEqual(response.status_code, 200)
            for action, url in self.urls(office).items():
                self.assertNotContains(response, url)

    def test_internal_submission_services_reject_heads_and_cross_office(self):
        from django.core.exceptions import PermissionDenied
        from .models import ProjectPublicationRevision
        from .publication_service import create_publication_draft, submit_publication_revision, submit_project_for_review

        for office, project in [('engineer', self.infra.project), ('mayor', self.noninfra.project)]:
            staff = self.accounts[office, 'staff']
            draft = create_publication_draft(project, staff)
            before = list(ProjectPublicationRevision.objects.values())
            for pair, actor in self.accounts.items():
                if pair == (office, 'staff'):
                    continue
                for call in [
                    lambda: create_publication_draft(project, actor),
                    lambda: submit_publication_revision(draft, actor),
                    lambda: submit_project_for_review(project, actor),
                ]:
                    with self.subTest(office=office, actor=pair), self.assertRaises(PermissionDenied):
                        call()
                    self.assertEqual(list(ProjectPublicationRevision.objects.values()), before)
            self.client.force_login(staff)
            self.assertEqual(self.client.post(self.urls(office)['submit_for_review']).status_code, 302)
            draft.refresh_from_db()
            self.assertEqual(draft.status, 'pending_review')
            self.assertEqual(draft.submitted_by, staff)

    def test_django_permissions_do_not_bypass_project_admin_boundary(self):
        from django.contrib import admin
        from django.contrib.auth.models import Permission
        from django.test import RequestFactory
        from .admin import ProjectDataAdmin

        for user in self.accounts.values():
            user.user_permissions.set(Permission.objects.filter(content_type__app_label='system'))
            self.client.force_login(user)
            self.assertEqual(self.client.post(reverse('admin:system_project_add'), {'project_type': 'infrastructure'}).status_code, 403)
            self.assertEqual(self.client.post(reverse('admin:system_project_change', args=[self.infra.project_id]), {'project_type': 'non_infrastructure'}).status_code, 403)
            self.assertEqual(self.client.post(reverse('admin:system_project_delete', args=[self.infra.project_id]), {'post': 'yes'}).status_code, 403)
            self.assertEqual(self.client.post(reverse('admin:system_project_changelist'), {
                'action': 'delete_selected', '_selected_action': self.infra.project_id, 'post': 'yes',
            }).status_code, 403)
            self.assertTrue(Project.objects.filter(pk=self.infra.project_id).exists())
            request = RequestFactory().get('/admin/')
            request.user = user
            for model_admin in admin.site._registry.values():
                if isinstance(model_admin, ProjectDataAdmin):
                    for method in ['has_add_permission', 'has_change_permission', 'has_delete_permission']:
                        self.assertFalse(getattr(model_admin, method)(request))
                    request.user = self.admin
                    self.assertTrue(model_admin.has_change_permission(request))
                    request.user = user

    def test_staff_can_create_and_update_through_real_forms(self):
        from apps.infrastructure.tests import InfrastructureProjectFormTests
        from .models import NonInfrastructureCategory

        # Reuse the established infrastructure valid-payload fixture.
        fixture = InfrastructureProjectFormTests()
        fixture.setUp()
        infra_data = fixture.valid_data()
        category = NonInfrastructureCategory.objects.create(type_code='phase7', type_name='Phase 7')
        noninfra_data = {
            'non_infra_name': 'Staff program', 'description': 'Community event',
            'non_infra_category': category.pk, 'status': 'planned',
            'proponent': 'Mayor Office', 'beneficiaries': '10', 'event_date': '2026-09-01',
            'start_time': '08:00', 'end_time': '09:00', 'venue_name': 'Plaza', 'barangay': 'bagting',
        }
        for office, data, model, title_field in [
            ('engineer', infra_data, Infrastructure_Project, 'infrastructure_title'),
            ('mayor', noninfra_data, Non_Infrastructure_Project, 'non_infra_name'),
        ]:
            self.client.force_login(self.accounts[office, 'staff'])
            response = self.client.post(self.urls(office)['create'], data)
            self.assertEqual(response.status_code, 302, getattr(response, 'context', None))
            record = model.objects.order_by('-pk').first()
            self.assertEqual(record.project.created_by_user, self.accounts[office, 'staff'])
            payload_title = 'title' if office == 'engineer' else 'non_infra_name'
            data[payload_title] = 'Updated by Staff'
            prefix = 'engineering_projects:project' if office == 'engineer' else 'mayor_projects:non_infrastructure_project'
            response = self.client.post(reverse(prefix + '_update', args=[record.pk]), data)
            self.assertEqual(response.status_code, 302)
            record.refresh_from_db()
            self.assertEqual(getattr(record, title_field), 'Updated by Staff')

    def test_submission_uses_database_type_and_role_and_keeps_admin_exception(self):
        from django.core.exceptions import PermissionDenied
        from .publication_service import create_publication_draft, submit_project_for_review
        staff = self.accounts['engineer', 'staff']
        project = self.infra.project
        project.project_type = 'non_infrastructure'  # Caller-supplied stale object.
        with self.assertRaises(PermissionDenied):
            create_publication_draft(project, self.accounts['mayor', 'staff'])
        self.assertEqual(staff.flags.role, 'staff')
        UserFlag.objects.filter(user=staff).update(role='head')
        with self.assertRaises(PermissionDenied):
            submit_project_for_review(project, staff)
        revision = submit_project_for_review(project, self.admin)
        self.assertEqual(revision.status, 'pending_review')
