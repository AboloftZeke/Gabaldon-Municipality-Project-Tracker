"""Direct URL access and account-state regression checks for Phase 10."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .forms import CustomUserChangeForm, CustomUserCreationForm
from .models import (
    InfrastructureProject, NonInfrastructureProgressUpdate,
    NonInfrastructureProject, Project, ProjectRevision, UserRole,
)
from .publication_snapshots import build_project_publication_snapshot


class InternalRouteAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'password')
        self.engineer_staff = self.account('engineer-staff', 'engineer', 'staff')
        self.engineer_head = self.account('engineer-head', 'engineer', 'head')
        self.mayor_staff = self.account('mayor-staff', 'mayor', 'staff')
        self.mayor_head = self.account('mayor-head', 'mayor', 'head')
        self.public = User.objects.create_user('resident', password='password')

        infra_base = Project.objects.create(project_type='infrastructure')
        self.infra = InfrastructureProject.objects.create(
            project=infra_base, title='Engineering project',
        )
        mayor_base = Project.objects.create(project_type='non_infrastructure')
        self.mayor = NonInfrastructureProject.objects.create(
            project=mayor_base, title='Mayor program',
            project_type=NonInfrastructureProject.ProjectType.PROGRAM,
        )
        self.revision = ProjectRevision.objects.create(
            project=infra_base, revision_number=1, status='pending_review',
            snapshot=build_project_publication_snapshot(infra_base),
        )
        self.update = NonInfrastructureProgressUpdate.objects.create(
            non_infrastructure=self.mayor,
            submitted_by=self.mayor_staff,
            previous_status='planned', proposed_status='ongoing',
            review_status=NonInfrastructureProgressUpdate.ReviewStatus.PENDING_REVIEW,
        )

    def account(self, username, department, role):
        user = User.objects.create_user(username, password='password', is_staff=True)
        UserRole.objects.create(user=user, department=department, role=role)
        return user

    def route(self, name, *args):
        return reverse(name, args=args)

    def protected_routes(self):
        infra, mayor, revision, update = (
            self.infra.pk, self.mayor.pk, self.revision.pk, self.update.pk,
        )
        return {
            'admin_dashboard': self.route('admin_dashboard'),
            'engineering_staff_dashboard': self.route('engineering_dashboard'),
            'engineering_head_dashboard': self.route('engineering_head_dashboard'),
            'mayor_staff_dashboard': self.route('mayor_dashboard'),
            'mayor_head_dashboard': self.route('mayor_head_dashboard'),
            'engineering_list': self.route('engineering_projects:project_list'),
            'engineering_detail': self.route('engineering_projects:project_detail', infra),
            'engineering_create': self.route('engineering_projects:project_create'),
            'engineering_edit': self.route('engineering_projects:project_update', infra),
            'engineering_delete': self.route('engineering_projects:project_delete', infra),
            'engineering_operations': self.route('engineering_projects:project_operations', infra),
            'engineering_inspection': self.route('engineering_projects:inspection_create', infra),
            'engineering_submit': self.route('engineering_projects:project_submit_for_review', infra),
            'mayor_list': self.route('mayor_projects:non_infrastructure_project_list'),
            'mayor_detail': self.route('mayor_projects:non_infrastructure_project_detail', mayor),
            'mayor_create': self.route('mayor_projects:non_infrastructure_project_create'),
            'mayor_edit': self.route('mayor_projects:non_infrastructure_project_update', mayor),
            'mayor_delete': self.route('mayor_projects:non_infrastructure_project_delete', mayor),
            'mayor_operations': self.route('mayor_projects:non_infrastructure_project_operations', mayor),
            'mayor_submit': self.route('mayor_projects:non_infrastructure_project_submit_for_review', mayor),
            'progress_create': self.route('mayor_projects:non_infrastructure_progress_update_create', mayor),
            'progress_detail': self.route('mayor_projects:non_infrastructure_progress_update_detail', mayor, update),
            'progress_submit': self.route('mayor_projects:non_infrastructure_progress_update_submit', mayor, update),
            'progress_queue': self.route('mayor_projects:non_infrastructure_progress_review_queue'),
            'progress_review': self.route('mayor_projects:non_infrastructure_progress_review_detail', update),
            'progress_approve': self.route('mayor_projects:non_infrastructure_progress_approve', update),
            'progress_return': self.route('mayor_projects:non_infrastructure_progress_return', update),
            'progress_apply': self.route('mayor_projects:non_infrastructure_progress_apply', update),
            'revision_queue': self.route('publication_review_queue'),
            'revision_detail': self.route('publication_revision_detail', revision),
            'revision_review': self.route('publication_revision_review', revision),
            'revision_publish': self.route('publication_revision_publish', revision),
            'revision_archive': self.route('publication_revision_archive', revision),
            'publication_lifecycle': self.route('publication_lifecycle'),
            'reports': self.route('reports:dashboard'),
            'infrastructure_report': self.route('reports:infrastructure'),
            'mayor_report': self.route('reports:non_infrastructure'),
            'report_generate': self.route('reports:infrastructure_summary_generate'),
            'report_file': self.route('reports:generated_report_view', 1),
            'user_list': self.route('user_list'),
            'user_create': self.route('user_create'),
            'user_create_confirm': self.route('user_create_confirm'),
            'user_edit': self.route('user_edit', self.engineer_staff.pk),
            'user_edit_confirm': self.route('user_edit_confirm', self.engineer_staff.pk),
            'user_activate': self.route('user_activate', self.engineer_staff.pk),
            'user_deactivate': self.route('user_deactivate', self.engineer_staff.pk),
            'user_resend_setup': self.route('user_resend_account_setup', self.engineer_staff.pk),
            'password_change': self.route('password_change'),
            'django_password_change': '/auth/password_change/',
            'django_password_change_done': '/auth/password_change/done/',
        }

    def test_logged_out_get_and_post_redirect_to_login_for_internal_routes(self):
        for label, url in self.protected_routes().items():
            for method in ('get', 'post'):
                with self.subTest(route=label, method=method):
                    response = getattr(self.client, method)(url)
                    self.assertRedirects(
                        response, f"{reverse('login')}?next={url}",
                        fetch_redirect_response=False,
                    )

    def test_dashboard_roles_and_same_office_head_redirect(self):
        routes = self.protected_routes()
        allowed = {
            # Existing admin exception permits reading both office dashboards.
            self.admin: {'admin_dashboard', 'engineering_staff_dashboard', 'mayor_staff_dashboard'},
            self.engineer_staff: {'engineering_staff_dashboard'},
            self.engineer_head: {'engineering_staff_dashboard', 'engineering_head_dashboard'},
            self.mayor_staff: {'mayor_staff_dashboard'},
            self.mayor_head: {'mayor_staff_dashboard', 'mayor_head_dashboard'},
            self.public: set(),
        }
        dashboard_keys = [key for key in routes if key.endswith('_dashboard')]
        for actor, permitted in allowed.items():
            self.client.force_login(actor)
            for key in dashboard_keys:
                with self.subTest(actor=actor.username, route=key):
                    response = self.client.get(routes[key])
                    if key in permitted and actor in (self.engineer_head, self.mayor_head) and key.endswith('staff_dashboard'):
                        target = ('engineering_head_dashboard' if actor == self.engineer_head else 'mayor_head_dashboard')
                        self.assertRedirects(response, routes[target])
                    else:
                        self.assertEqual(response.status_code, 200 if key in permitted else 403)

    def test_cross_office_and_head_staff_action_boundaries(self):
        routes = self.protected_routes()
        denied = {
            self.mayor_staff: ('engineering_list', 'engineering_detail', 'engineering_create', 'engineering_operations', 'revision_queue', 'progress_review'),
            self.engineer_staff: ('mayor_list', 'mayor_detail', 'mayor_create', 'mayor_operations', 'progress_create', 'progress_review', 'revision_review'),
            self.mayor_head: ('engineering_operations', 'engineering_inspection', 'engineering_submit', 'progress_create', 'progress_submit'),
            self.engineer_head: ('mayor_operations', 'mayor_create', 'mayor_submit', 'progress_approve', 'progress_apply', 'engineering_create'),
            self.admin: ('progress_create', 'progress_approve', 'progress_apply', 'engineering_operations', 'mayor_operations', 'revision_review'),
            self.public: ('user_create', 'revision_publish', 'report_generate', 'progress_review'),
        }
        for actor, keys in denied.items():
            self.client.force_login(actor)
            for key in keys:
                url = routes[key]
                for method in ('get', 'post'):
                    with self.subTest(actor=actor.username, route=key, method=method):
                        self.assertEqual(getattr(self.client, method)(url).status_code, 403)

    def test_valid_roles_reach_their_own_protected_pages(self):
        routes = self.protected_routes()
        cases = (
            (self.admin, 'admin_dashboard'), (self.admin, 'user_create'),
            (self.admin, 'publication_lifecycle'),
            (self.engineer_staff, 'engineering_list'),
            (self.engineer_staff, 'engineering_create'),
            (self.engineer_head, 'engineering_head_dashboard'),
            (self.engineer_head, 'revision_queue'),
            (self.engineer_head, 'infrastructure_report'),
            (self.mayor_staff, 'mayor_staff_dashboard'),
            (self.mayor_staff, 'progress_create'),
            (self.mayor_head, 'mayor_head_dashboard'),
            (self.mayor_head, 'progress_queue'),
            (self.mayor_head, 'progress_review'),
            (self.mayor_head, 'mayor_report'),
        )
        for actor, key in cases:
            with self.subTest(actor=actor.username, route=key):
                self.client.force_login(actor)
                self.assertEqual(self.client.get(routes[key]).status_code, 200)

    def test_wrong_role_cannot_probe_missing_report_or_revision(self):
        for user in (self.engineer_staff, self.mayor_staff, self.public):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.route('reports:generated_report_view', 99999)).status_code, 403)
                self.assertEqual(self.client.get(self.route('publication_revision_detail', 99999)).status_code, 403)


class UserCreationStatusTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'password')
        self.client.force_login(self.admin)

    def test_creation_form_has_no_status_section_or_status_field(self):
        response = self.client.get(reverse('user_create'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('is_active', response.context['form'].fields)
        self.assertNotContains(response, 'Account Status')
        self.assertNotContains(response, 'name="is_active"')

    def test_account_creation_ignores_posted_status_and_preserves_role_and_setup(self):
        response = self.client.post(reverse('user_create'), {
            'username': 'new-mayor', 'email': 'new-mayor@example.com',
            'first_name': 'Mayor', 'last_name': 'Staff',
            'role': 'mayors', 'is_active': '',
        })
        self.assertRedirects(response, reverse('user_create_confirm'))
        self.assertNotIn('is_active', self.client.session['user_create_form_data'])
        response = self.client.post(reverse('user_create_confirm'))
        self.assertRedirects(response, reverse('user_list'))
        created = User.objects.get(username='new-mayor')
        self.assertTrue(created.is_active)
        self.assertTrue(created.is_staff)
        self.assertFalse(created.has_usable_password())
        self.assertEqual((created.role_assignment.department, created.role_assignment.role), ('mayor', 'staff'))

    def test_edit_preserves_active_state_and_has_no_blank_status_section(self):
        user = User.objects.create_user('existing', is_active=False, is_staff=True)
        UserRole.objects.create(user=user, department='engineer', role='staff')
        response = self.client.get(reverse('user_edit', args=[user.pk]))
        self.assertNotContains(response, 'Account Status')
        self.assertContains(response, 'name="is_active"', html=False)
        form = CustomUserChangeForm({
            'username': 'existing', 'email': 'existing@example.com',
            'first_name': 'Test', 'last_name': 'User',
            'role': 'engineering', 'is_active': 'on',
        }, instance=user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data['is_active'])
        form.save()
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertNotIn('is_active', CustomUserCreationForm().fields)

    def test_edit_confirmation_ignores_tampered_activation_state(self):
        user = User.objects.create_user('active-user', email='active@example.com', is_staff=True)
        UserRole.objects.create(user=user, department='engineer', role='staff')
        response = self.client.post(reverse('user_edit', args=[user.pk]), {
            'username': user.username, 'email': user.email,
            'first_name': 'Active', 'last_name': 'User',
            'role': 'engineering', 'is_active': '',
        })
        self.assertRedirects(response, reverse('user_edit_confirm', args=[user.pk]))
        self.assertTrue(self.client.session[f'user_edit_form_data_{user.pk}']['new_data']['is_active'])
        self.assertRedirects(self.client.post(reverse('user_edit_confirm', args=[user.pk])), reverse('user_list'))
        user.refresh_from_db()
        self.assertTrue(user.is_active)
