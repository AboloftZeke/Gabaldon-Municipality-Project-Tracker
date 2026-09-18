from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.system.models import UserRole


class ReportAccessTests(TestCase):
    def setUp(self):
        self.users = {}
        for department, role in [
            ('admin', 'admin'),
            ('engineer', 'staff'),
            ('engineer', 'head'),
            ('mayor', 'staff'),
            ('mayor', 'head'),
        ]:
            user = User.objects.create_user(
                username=f'{department}-{role}',
                password='ValidReportPass!2026',
                is_staff=True,
                is_superuser=role == 'admin',
            )
            UserRole.objects.create(
                user=user,
                department=department,
                role=role,
            )
            self.users[department, role] = user

    def test_report_entry_routes_each_head_to_its_office_scope(self):
        for assignment, destination in [
            (('engineer', 'head'), 'reports:infrastructure'),
            (('mayor', 'head'), 'reports:non_infrastructure'),
        ]:
            with self.subTest(assignment=assignment):
                self.client.force_login(self.users[assignment])
                self.assertRedirects(
                    self.client.get(reverse('reports:dashboard')),
                    reverse(destination),
                )

    def test_report_entry_rejects_non_head_accounts(self):
        for assignment in [
            ('admin', 'admin'),
            ('engineer', 'staff'),
            ('mayor', 'staff'),
        ]:
            with self.subTest(assignment=assignment):
                self.client.force_login(self.users[assignment])
                response = self.client.get(reverse('reports:dashboard'))
                self.assertEqual(response.status_code, 403)

    def test_scoped_report_pages_enforce_office_head_permissions(self):
        report_pages = {
            'infrastructure': ('engineer', 'head'),
            'non_infrastructure': ('mayor', 'head'),
        }
        for report_type, allowed_assignment in report_pages.items():
            url = reverse(f'reports:{report_type}')
            for assignment, user in self.users.items():
                with self.subTest(
                    report_type=report_type,
                    assignment=assignment,
                ):
                    self.client.force_login(user)
                    response = self.client.get(url)
                    self.assertEqual(
                        response.status_code,
                        200 if assignment == allowed_assignment else 403,
                    )

    def test_report_page_shows_only_the_heads_report_scope(self):
        for assignment, report_type, label in [
            (('engineer', 'head'), 'infrastructure', 'Infrastructure'),
            (('mayor', 'head'), 'non_infrastructure', 'Non-Infrastructure'),
        ]:
            with self.subTest(report_type=report_type):
                self.client.force_login(self.users[assignment])
                response = self.client.get(reverse(f'reports:{report_type}'))

                self.assertEqual(response.context['report_type'], report_type)
                self.assertEqual(response.context['report_type_label'], label)
                self.assertContains(
                    response,
                    f'data-report-scope="{report_type}"',
                )
                self.assertContains(response, 'Individual Project Report')
                self.assertContains(response, 'Project Summary Report')
                self.assertContains(response, 'Coming in Phase 2')
                self.assertContains(response, 'Coming in Phase 3')

    def test_head_dashboards_include_reports_navigation(self):
        for assignment, dashboard in [
            (('engineer', 'head'), 'engineering_head_dashboard'),
            (('mayor', 'head'), 'mayor_head_dashboard'),
        ]:
            with self.subTest(assignment=assignment):
                self.client.force_login(self.users[assignment])
                response = self.client.get(reverse(dashboard))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, reverse('reports:dashboard'))
                self.assertContains(response, 'Reports')
