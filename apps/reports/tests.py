from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.system.models import Project, ProjectRevision, UserRole


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
            UserRole.objects.create(user=user, department=department, role=role)
            self.users[department, role] = user

        self.infrastructure_revision = self.create_published_revision(
            'infrastructure', self.infrastructure_snapshot(),
        )
        self.non_infrastructure_revision = self.create_published_revision(
            'non_infrastructure', self.non_infrastructure_snapshot(),
        )
        self.create_unpublished_revision()

    def infrastructure_snapshot(self):
        return {
            'project': {
                'id': 1, 'type': 'infrastructure',
                'creator': {'display_name': 'Engineering Publisher'},
                'created_at': '2026-01-02T08:00:00',
                'updated_at': '2026-06-15T09:30:00',
                'cover_image_url': '/media/projects/bridge-cover.jpg',
            },
            'infrastructure': {
                'id': 101, 'code': 'INF-BRIDGE-101',
                'title': 'Barangay Bridge Improvement',
                'description': 'Published bridge improvement details.',
                'category': {'id': 1, 'code': 'bridge', 'name': 'Bridges'},
                'address': {
                    'street': 'Rizal Street', 'barangay': 'Calabasa',
                    'municipality': 'Gabaldon', 'province': 'Nueva Ecija',
                },
                'contractor': {'id': 1, 'name': 'Public Works Builder'},
                'implementing_office': {
                    'id': 1, 'name': 'Municipal Engineering Office',
                },
                'procurement_method': 'competitive_bidding',
                'procurement_method_label': 'Competitive Bidding / Public Bidding',
                'award_status': 'awarded', 'award_status_label': 'Awarded',
                'planned_start_date': '2026-02-01',
                'planned_end_date': '2026-10-31',
                'cost_progress_percentage': '48.50',
                'physical_progress_percentage': '55.00',
            },
            'financial': {
                'id': 1, 'approved_budget': '12500000.00',
                'contract_price': '11900000.00',
                'actual_expenditure': '5432100.00',
                'fund_source': {
                    'id': 1, 'code': 'LDF', 'name': 'Local Development Fund',
                },
            },
            'schedule': {
                'id': 1, 'actual_start_date': '2026-02-10',
                'actual_completion_date': None,
            },
            'inspection': {
                'id': 1, 'inspection_date': '2026-06-10',
                'completion_percentage': '55.00',
                'findings': 'Work follows the approved plan.',
                'remarks': 'Continue scheduled monitoring.',
                'inspected_by': {'display_name': 'Engineer Inspector'},
            },
            'images': [{
                'id': 1, 'url': '/media/projects/bridge-cover.jpg',
                'is_cover': True,
            }],
        }

    def non_infrastructure_snapshot(self):
        return {
            'project': {
                'id': 2, 'type': 'non_infrastructure',
                'creator': {'display_name': 'Mayor Office Publisher'},
                'created_at': '2026-03-01T08:00:00',
                'updated_at': '2026-07-01T10:00:00',
            },
            'non_infrastructure': {
                'id': 202, 'code': 'NINF-00202',
                'title': 'Community Health Day',
                'description': 'Published community health services.',
                'category': {
                    'id': 2, 'code': 'health', 'name': 'Health Services',
                },
                'status': 'ongoing', 'status_label': 'Ongoing',
                'proponent': 'Municipal Health Office', 'beneficiaries': 350,
                'event_date': '2026-08-20', 'start_time': '08:00:00',
                'end_time': '15:00:00',
                'venue_name': 'Gabaldon Municipal Gym',
                'address': {
                    'street': 'Municipal Road', 'barangay': 'North Poblacion',
                    'municipality': 'Gabaldon', 'province': 'Nueva Ecija',
                },
            },
            'images': [{
                'id': 2, 'url': '/media/projects/health-day.jpg',
                'is_cover': True,
            }],
        }

    def create_published_revision(self, project_type, snapshot):
        project = Project.objects.create(
            project_type=project_type,
            is_published=True,
            is_visible_to_public=True,
        )
        return ProjectRevision.objects.create(
            project=project, revision_number=1, status='published',
            is_current_public=True, snapshot=snapshot,
        )

    def create_unpublished_revision(self):
        project = Project.objects.create(project_type='infrastructure')
        return ProjectRevision.objects.create(
            project=project, revision_number=1, status='pending_review',
            snapshot={
                'project': {'id': project.pk, 'type': 'infrastructure'},
                'infrastructure': {
                    'id': 303, 'code': 'INF-PRIVATE-303',
                    'title': 'Unpublished Internal Project',
                },
            },
        )

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
            ('admin', 'admin'), ('engineer', 'staff'), ('mayor', 'staff'),
        ]:
            with self.subTest(assignment=assignment):
                self.client.force_login(self.users[assignment])
                self.assertEqual(
                    self.client.get(reverse('reports:dashboard')).status_code,
                    403,
                )

    def test_scoped_report_pages_enforce_office_head_permissions(self):
        report_pages = {
            'infrastructure': ('engineer', 'head'),
            'non_infrastructure': ('mayor', 'head'),
        }
        for report_type, allowed_assignment in report_pages.items():
            for assignment, user in self.users.items():
                with self.subTest(report_type=report_type, assignment=assignment):
                    self.client.force_login(user)
                    response = self.client.get(reverse(f'reports:{report_type}'))
                    self.assertEqual(
                        response.status_code,
                        200 if assignment == allowed_assignment else 403,
                    )

    def test_selection_exposes_only_current_disclosed_office_scope(self):
        for assignment, report_type, included, excluded in [
            (('engineer', 'head'), 'infrastructure',
             'Barangay Bridge Improvement', 'Community Health Day'),
            (('mayor', 'head'), 'non_infrastructure',
             'Community Health Day', 'Barangay Bridge Improvement'),
        ]:
            with self.subTest(report_type=report_type):
                self.client.force_login(self.users[assignment])
                response = self.client.get(reverse(f'reports:{report_type}'))
                self.assertContains(response, included)
                self.assertNotContains(response, excluded)
                self.assertNotContains(response, 'Unpublished Internal Project')

    def test_heads_can_submit_individual_report_requests(self):
        for assignment, report_type, project_id, destination in [
            (('engineer', 'head'), 'infrastructure', 101,
             'reports:infrastructure_project'),
            (('mayor', 'head'), 'non_infrastructure', 202,
             'reports:non_infrastructure_project'),
        ]:
            with self.subTest(report_type=report_type):
                self.client.force_login(self.users[assignment])
                response = self.client.post(
                    reverse(f'reports:{report_type}'),
                    {'project_id': project_id},
                )
                self.assertRedirects(
                    response, reverse(destination, args=[project_id]),
                )

    def test_cross_office_heads_cannot_access_other_report_preview(self):
        for assignment, destination, project_id in [
            (('engineer', 'head'), 'reports:non_infrastructure_project', 202),
            (('mayor', 'head'), 'reports:infrastructure_project', 101),
        ]:
            with self.subTest(assignment=assignment):
                self.client.force_login(self.users[assignment])
                response = self.client.get(reverse(destination, args=[project_id]))
                self.assertEqual(response.status_code, 403)

    def test_staff_and_admin_cannot_access_individual_report_previews(self):
        for assignment in [
            ('admin', 'admin'), ('engineer', 'staff'), ('mayor', 'staff'),
        ]:
            for destination, project_id in [
                ('reports:infrastructure_project', 101),
                ('reports:non_infrastructure_project', 202),
            ]:
                with self.subTest(assignment=assignment, destination=destination):
                    self.client.force_login(self.users[assignment])
                    response = self.client.get(
                        reverse(destination, args=[project_id]),
                    )
                    self.assertEqual(response.status_code, 403)

    def test_invalid_or_undisclosed_project_ids_return_404(self):
        self.client.force_login(self.users['engineer', 'head'])
        for project_id in [999999, 303]:
            with self.subTest(project_id=project_id):
                response = self.client.get(reverse(
                    'reports:infrastructure_project', args=[project_id],
                ))
                self.assertEqual(response.status_code, 404)

    def test_infrastructure_preview_uses_disclosed_snapshot_fields(self):
        self.client.force_login(self.users['engineer', 'head'])
        response = self.client.get(reverse(
            'reports:infrastructure_project', args=[101],
        ))
        self.assertEqual(response.status_code, 200)
        for expected in [
            'Barangay Bridge Improvement', 'Calabasa', 'Bridges',
            'Municipal Engineering Office', 'Awarded', '55.0%',
            'Published bridge improvement details.', 'Local Development Fund',
            '12500000.00', '11900000.00',
            'Competitive Bidding / Public Bidding', 'Public Works Builder',
            'Work follows the approved plan.',
            '/media/projects/bridge-cover.jpg',
        ]:
            self.assertContains(response, expected)
        self.assertNotContains(response, '5432100.00')

    def test_non_infrastructure_preview_uses_disclosed_snapshot_fields(self):
        self.client.force_login(self.users['mayor', 'head'])
        response = self.client.get(reverse(
            'reports:non_infrastructure_project', args=[202],
        ))
        self.assertEqual(response.status_code, 200)
        for expected in [
            'Community Health Day', 'Health Services', 'North Poblacion',
            'Gabaldon Municipal Gym', 'August 20, 2026', '8:00 AM', '3:00 PM',
            'Municipal Health Office', '350',
            'Published community health services.', 'Ongoing',
            '/media/projects/health-day.jpg',
        ]:
            self.assertContains(response, expected)

    def test_optional_snapshot_fields_do_not_crash_preview(self):
        revision = self.create_published_revision(
            'non_infrastructure',
            {
                'project': {'id': 4, 'type': 'non_infrastructure'},
                'non_infrastructure': {
                    'id': 404, 'title': 'Minimal Published Program',
                },
            },
        )
        self.client.force_login(self.users['mayor', 'head'])
        response = self.client.get(reverse(
            'reports:non_infrastructure_project', args=[404],
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['report']['revision'], revision)
        self.assertContains(response, 'Minimal Published Program')
        self.assertContains(response, 'N/A')

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

