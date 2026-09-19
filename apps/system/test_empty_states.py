from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import (
    InfrastructureProject,
    NonInfrastructureProject,
    Project,
    ProjectRevision,
    UserRole,
)


class SharedEmptyStateTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            'empty-admin', 'empty-admin@example.com', 'password123',
        )
        self.engineer = User.objects.create_user(
            'empty-engineer', password='password123', is_staff=True,
        )
        UserRole.objects.create(
            user=self.engineer, department='engineer', role='staff',
        )
        self.engineering_head = User.objects.create_user(
            'empty-engineering-head', password='password123', is_staff=True,
        )
        UserRole.objects.create(
            user=self.engineering_head, department='engineer', role='head',
        )
        self.mayor = User.objects.create_user(
            'empty-mayor', password='password123', is_staff=True,
        )
        UserRole.objects.create(
            user=self.mayor, department='mayor', role='staff',
        )

    def test_project_lists_explain_a_truly_empty_collection(self):
        for user, route, heading, create_route in [
            (
                self.engineer,
                'engineering_projects:project_list',
                'No infrastructure projects yet',
                'engineering_projects:project_create',
            ),
            (
                self.mayor,
                'mayor_projects:non_infrastructure_project_list',
                'No non-infrastructure projects yet',
                'mayor_projects:non_infrastructure_project_create',
            ),
        ]:
            self.client.force_login(user)
            response = self.client.get(reverse(route))
            with self.subTest(route=route):
                self.assertContains(response, 'ui-empty-state')
                self.assertContains(response, heading)
                self.assertContains(response, reverse(create_route))
                self.assertNotContains(
                    response, 'No results match your current filters.',
                )

    def test_project_lists_offer_clear_filters_when_records_exist(self):
        infrastructure_base = Project.objects.create(
            project_type='infrastructure',
        )
        InfrastructureProject.objects.create(
            project=infrastructure_base, title='Existing Bridge Project',
        )
        non_infrastructure_base = Project.objects.create(
            project_type='non_infrastructure',
        )
        NonInfrastructureProject.objects.create(
            project=non_infrastructure_base, title='Existing Health Program',
        )

        for user, route in [
            (self.engineer, 'engineering_projects:project_list'),
            (self.mayor, 'mayor_projects:non_infrastructure_project_list'),
        ]:
            self.client.force_login(user)
            response = self.client.get(reverse(route), {'location': 'Nowhere'})
            with self.subTest(route=route):
                self.assertContains(
                    response, 'No results match your current filters.',
                )
                self.assertContains(response, 'Clear Filters')
                self.assertNotContains(response, 'Create Project')

    def test_user_management_filter_empty_state_resets_search(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse('user_list'), {'search': 'no-such-account'},
        )

        self.assertContains(response, 'No matching user accounts')
        self.assertContains(response, 'No results match your current filters.')
        self.assertContains(response, 'Reset Search')
        self.assertContains(response, f'href="{reverse("user_list")}"')

    def test_publication_queue_uses_positive_and_filter_empty_states(self):
        self.client.force_login(self.engineering_head)
        response = self.client.get(reverse('publication_review_queue'))
        self.assertContains(response, "You're all caught up.")
        self.assertContains(
            response,
            'There are currently no submissions waiting for review.',
        )

        project = Project.objects.create(project_type='infrastructure')
        ProjectRevision.objects.create(
            project=project, revision_number=1, status='approved',
        )
        response = self.client.get(
            reverse('publication_review_queue'), {'status': 'rejected'},
        )
        self.assertContains(response, 'No results match your current filters.')
        self.assertContains(response, 'Clear Filters')

    def test_reports_history_empty_state_offers_generation_action(self):
        self.client.force_login(self.engineering_head)
        response = self.client.get(reverse('reports:infrastructure'))

        self.assertContains(response, 'No generated reports yet')
        self.assertContains(response, 'Generate Report')
        self.assertContains(response, 'href="#report-options-heading"')

    def test_head_dashboard_says_when_no_action_is_required(self):
        self.client.force_login(self.engineering_head)
        response = self.client.get(reverse('engineering_head_dashboard'))

        self.assertContains(response, "You're all caught up.")
        self.assertContains(
            response,
            'There are currently no submissions or publication updates requiring attention.',
        )

