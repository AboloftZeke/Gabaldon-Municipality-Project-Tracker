from copy import deepcopy

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
        second_infrastructure = deepcopy(self.infrastructure_snapshot())
        second_infrastructure['project'].update({'id': 3})
        second_infrastructure['infrastructure'].update({
            'id': 102,
            'code': 'INF-ROAD-102',
            'title': 'Completed Farm Road',
            'category': {'id': 2, 'code': 'road', 'name': 'Roads'},
            'address': {
                'street': '', 'barangay': 'Bagting',
                'municipality': 'Gabaldon', 'province': 'Nueva Ecija',
            },
            'award_status': 'completed',
            'award_status_label': 'Completed',
            'planned_start_date': '2025-01-15',
            'planned_end_date': '2025-08-30',
            'physical_progress_percentage': '100.00',
        })
        second_infrastructure['financial'].update({
            'contract_price': '5000000.00',
            'actual_expenditure': '4900000.00',
        })
        second_infrastructure['inspection'] = None
        second_infrastructure['images'] = []
        self.create_published_revision(
            'infrastructure', second_infrastructure,
        )

        second_non_infrastructure = deepcopy(self.non_infrastructure_snapshot())
        second_non_infrastructure['project'].update({'id': 4})
        second_non_infrastructure['non_infrastructure'].update({
            'id': 203,
            'code': 'NINF-00203',
            'title': 'Youth Skills Training',
            'category': {
                'id': 3, 'code': 'education', 'name': 'Education',
            },
            'status': 'completed',
            'status_label': 'Completed',
            'proponent': 'Municipal Youth Office',
            'beneficiaries': 100,
            'event_date': '2025-11-10',
            'venue_name': 'Barangay Hall',
            'address': {
                'street': '', 'barangay': 'Bagting',
                'municipality': 'Gabaldon', 'province': 'Nueva Ecija',
            },
        })
        second_non_infrastructure['images'] = []
        self.create_published_revision(
            'non_infrastructure', second_non_infrastructure,
        )
        self.create_unpublished_revision()
        self.create_non_current_published_revision()

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

    def create_non_current_published_revision(self):
        project = Project.objects.create(project_type='infrastructure')
        return ProjectRevision.objects.create(
            project=project, revision_number=1, status='published',
            is_current_public=False,
            snapshot={
                'project': {'id': project.pk, 'type': 'infrastructure'},
                'infrastructure': {
                    'id': 304, 'code': 'INF-OLD-304',
                    'title': 'Superseded Published Project',
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

    def test_summary_pages_enforce_office_head_permissions(self):
        summary_pages = {
            'reports:infrastructure_summary': ('engineer', 'head'),
            'reports:non_infrastructure_summary': ('mayor', 'head'),
        }
        for route, allowed_assignment in summary_pages.items():
            for assignment, user in self.users.items():
                with self.subTest(route=route, assignment=assignment):
                    self.client.force_login(user)
                    response = self.client.get(reverse(route))
                    self.assertEqual(
                        response.status_code,
                        200 if assignment == allowed_assignment else 403,
                    )

    def test_empty_summary_filters_return_all_disclosed_projects_in_scope(self):
        for assignment, route, expected, excluded in [
            (
                ('engineer', 'head'), 'reports:infrastructure_summary',
                ['Barangay Bridge Improvement', 'Completed Farm Road'],
                ['Community Health Day', 'Unpublished Internal Project'],
            ),
            (
                ('mayor', 'head'), 'reports:non_infrastructure_summary',
                ['Community Health Day', 'Youth Skills Training'],
                ['Barangay Bridge Improvement', 'Unpublished Internal Project'],
            ),
        ]:
            with self.subTest(route=route):
                self.client.force_login(self.users[assignment])
                response = self.client.get(reverse(route))
                self.assertEqual(response.context['summary']['total_projects'], 2)
                for title in expected:
                    self.assertContains(response, title)
                for title in excluded:
                    self.assertNotContains(response, title)
                self.assertNotContains(response, 'Superseded Published Project')

    def test_report_dashboards_link_to_the_correct_summary_scope(self):
        for assignment, report_type in [
            (('engineer', 'head'), 'infrastructure'),
            (('mayor', 'head'), 'non_infrastructure'),
        ]:
            with self.subTest(report_type=report_type):
                self.client.force_login(self.users[assignment])
                response = self.client.get(reverse(f'reports:{report_type}'))
                self.assertContains(
                    response,
                    reverse(f'reports:{report_type}_summary'),
                )
                self.assertContains(response, 'Project Summary Report')

    def test_infrastructure_filters_work_individually(self):
        self.client.force_login(self.users['engineer', 'head'])
        route = reverse('reports:infrastructure_summary')
        cases = [
            ({'barangay': 'Calabasa'}, 'Barangay Bridge Improvement'),
            ({'category': 'road'}, 'Completed Farm Road'),
            ({'status': 'completed'}, 'Completed Farm Road'),
            ({'date_from': '2026-01-01'}, 'Barangay Bridge Improvement'),
            ({'date_to': '2025-12-31'}, 'Completed Farm Road'),
        ]
        for filters, expected in cases:
            with self.subTest(filters=filters):
                response = self.client.get(route, filters)
                self.assertEqual(response.context['summary']['total_projects'], 1)
                self.assertContains(response, expected)

    def test_combined_infrastructure_filters_and_aggregates(self):
        self.client.force_login(self.users['engineer', 'head'])
        response = self.client.get(
            reverse('reports:infrastructure_summary'),
            {
                'barangay': 'Calabasa',
                'category': 'bridge',
                'status': 'awarded',
                'date_from': '2026-01-01',
                'date_to': '2026-12-31',
            },
        )
        summary = response.context['summary']
        self.assertEqual(summary['total_projects'], 1)
        self.assertEqual(summary['status_counts'], {'Awarded': 1})
        self.assertEqual(summary['total_contract_value'], 11900000)
        self.assertEqual(summary['average_physical_progress'], 55)
        self.assertContains(response, 'Barangay Bridge Improvement')
        self.assertNotContains(response, 'Completed Farm Road')
        self.assertEqual(response.context['form']['barangay'].value(), 'Calabasa')

    def test_infrastructure_unfiltered_aggregates_are_correct(self):
        self.client.force_login(self.users['engineer', 'head'])
        response = self.client.get(reverse('reports:infrastructure_summary'))
        summary = response.context['summary']
        self.assertEqual(summary['status_counts'], {'Awarded': 1, 'Completed': 1})
        self.assertEqual(summary['total_contract_value'], 16900000)
        self.assertEqual(summary['average_physical_progress'], 77.5)
        self.assertNotContains(response, '4900000.00')

    def test_non_infrastructure_filters_work_individually(self):
        self.client.force_login(self.users['mayor', 'head'])
        route = reverse('reports:non_infrastructure_summary')
        cases = [
            ({'barangay': 'North Poblacion'}, 'Community Health Day'),
            ({'category': 'education'}, 'Youth Skills Training'),
            ({'status': 'completed'}, 'Youth Skills Training'),
            ({'date_from': '2026-01-01'}, 'Community Health Day'),
            ({'date_to': '2025-12-31'}, 'Youth Skills Training'),
        ]
        for filters, expected in cases:
            with self.subTest(filters=filters):
                response = self.client.get(route, filters)
                self.assertEqual(response.context['summary']['total_projects'], 1)
                self.assertContains(response, expected)

    def test_combined_non_infrastructure_filters_and_aggregates(self):
        self.client.force_login(self.users['mayor', 'head'])
        response = self.client.get(
            reverse('reports:non_infrastructure_summary'),
            {
                'barangay': 'North Poblacion',
                'category': 'health',
                'status': 'ongoing',
                'date_from': '2026-01-01',
                'date_to': '2026-12-31',
            },
        )
        summary = response.context['summary']
        self.assertEqual(summary['total_projects'], 1)
        self.assertEqual(summary['status_counts'], {'Ongoing': 1})
        self.assertEqual(summary['category_counts'], {'Health Services': 1})
        self.assertEqual(summary['total_beneficiaries'], 350)
        self.assertContains(response, 'Community Health Day')
        self.assertNotContains(response, 'Youth Skills Training')

    def test_non_infrastructure_unfiltered_aggregates_are_correct(self):
        self.client.force_login(self.users['mayor', 'head'])
        response = self.client.get(reverse(
            'reports:non_infrastructure_summary',
        ))
        summary = response.context['summary']
        self.assertEqual(summary['status_counts'], {'Ongoing': 1, 'Completed': 1})
        self.assertEqual(
            summary['category_counts'],
            {'Health Services': 1, 'Education': 1},
        )
        self.assertEqual(summary['total_beneficiaries'], 450)

    def test_summary_no_result_filter_shows_empty_state(self):
        self.client.force_login(self.users['engineer', 'head'])
        response = self.client.get(
            reverse('reports:infrastructure_summary'),
            {'barangay': 'Calabasa', 'status': 'completed'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['summary']['total_projects'], 0)
        self.assertContains(
            response,
            'No disclosed infrastructure projects match these filters.',
        )

