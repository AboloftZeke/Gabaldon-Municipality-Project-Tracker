from datetime import date, datetime, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Address,
    InfrastructureProject,
    InfrastructureProgressUpdate,
    InfrastructureSchedule,
    NonInfrastructureProgressUpdate,
    NonInfrastructureProject,
    Project,
    ProjectInspection,
    ProjectRevision,
    UserRole,
)


class ProjectDashboardAnalyticsTests(TestCase):
    def setUp(self):
        self.users = {}
        for office, role, dashboard in (
            ('engineer', 'staff', 'engineering_dashboard'),
            ('engineer', 'head', 'engineering_head_dashboard'),
            ('mayor', 'staff', 'mayor_dashboard'),
            ('mayor', 'head', 'mayor_head_dashboard'),
        ):
            user = User.objects.create_user(
                f'analytics-{office}-{role}',
                password='Testpass123!',
                is_staff=True,
            )
            UserRole.objects.create(
                user=user,
                department=office,
                role=role,
            )
            self.users[dashboard] = user

    def make_infrastructure(
        self,
        title,
        *,
        status='ongoing',
        end_date=None,
        barangay='bagting',
    ):
        project = Project.objects.create(project_type='infrastructure')
        address = Address.objects.create(barangay=barangay)
        details = InfrastructureProject.objects.create(
            project=project,
            title=title,
            status=status,
            planned_end_date=end_date,
            address=address,
        )
        return project, details

    def make_non_infrastructure(
        self,
        title,
        *,
        status='ongoing',
        end_date=None,
        barangay='bagting',
    ):
        project = Project.objects.create(project_type='non_infrastructure')
        address = Address.objects.create(barangay=barangay)
        details = NonInfrastructureProject.objects.create(
            project=project,
            title=title,
            status=status,
            implementation_end_date=end_date,
            address=address,
        )
        return project, details

    @staticmethod
    def published_revision(project, revision_number, status, published_at):
        return ProjectRevision.objects.create(
            project=project,
            revision_number=revision_number,
            status=status,
            published_at=published_at,
            snapshot={},
        )

    def test_all_four_role_dashboards_render_all_four_charts(self):
        for dashboard, user in self.users.items():
            with self.subTest(dashboard=dashboard):
                self.client.force_login(user)
                response = self.client.get(reverse(dashboard))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Projects Published by Month')
                self.assertContains(response, 'Projects by Status')
                self.assertContains(response, 'Completed Projects Over Time')
                self.assertContains(response, 'Projects by Barangay')
                self.assertContains(response, 'project-analytics-data')
                self.assertEqual(
                    len(response.context['project_analytics']['barangays']),
                    16,
                )

    def test_empty_dashboard_has_zeroed_status_and_barangay_series(self):
        self.client.force_login(self.users['engineering_dashboard'])
        response = self.client.get(reverse('engineering_dashboard'))
        analytics = response.context['project_analytics']

        self.assertEqual(analytics['published_by_month'], {
            'labels': [],
            'values': [],
        })
        self.assertEqual(analytics['completed_by_month'], {
            'labels': [],
            'values': [],
        })
        self.assertEqual(analytics['published_without_dates'], 0)
        self.assertEqual(
            [row['value'] for row in analytics['status']],
            [0, 0, 0, 0],
        )
        self.assertEqual(
            [row['value'] for row in analytics['barangays']],
            [0] * 16,
        )

    def test_publication_chart_counts_each_project_at_first_publication(self):
        first_date = timezone.make_aware(datetime(2024, 5, 6, 9))
        later_date = timezone.make_aware(datetime(2025, 1, 7, 9))
        second_project_date = timezone.make_aware(datetime(2025, 5, 12, 9))
        infrastructure, _ = self.make_infrastructure('Published road')
        self.published_revision(
            infrastructure, 1, 'archived', first_date,
        )
        self.published_revision(
            infrastructure, 2, 'published', later_date,
        )
        another_infrastructure, _ = self.make_infrastructure('Published bridge')
        self.published_revision(
            another_infrastructure, 1, 'published', second_project_date,
        )
        undated_project, _ = self.make_infrastructure(
            'Publication date not recorded',
        )
        self.published_revision(
            undated_project, 1, 'published', None,
        )
        non_infrastructure, _ = self.make_non_infrastructure(
            'Mayor program',
        )
        self.published_revision(
            non_infrastructure, 1, 'published', later_date,
        )

        self.client.force_login(self.users['engineering_dashboard'])
        response = self.client.get(reverse('engineering_dashboard'))
        chart = response.context['project_analytics']['published_by_month']
        counts = dict(zip(chart['labels'], chart['values']))
        self.assertEqual(counts['May 2024'], 1)
        self.assertEqual(counts['Jan 2025'], 0)
        self.assertEqual(counts['May 2025'], 1)
        self.assertEqual(
            response.context['project_analytics']['published_without_dates'],
            1,
        )
        self.assertContains(
            response,
            '1 published project has no publication date and is not plotted.',
        )

        self.client.force_login(self.users['mayor_dashboard'])
        response = self.client.get(reverse('mayor_dashboard'))
        mayor_chart = response.context['project_analytics']['published_by_month']
        mayor_counts = dict(zip(mayor_chart['labels'], mayor_chart['values']))
        self.assertEqual(mayor_counts['Jan 2025'], 1)
        self.assertNotIn('May 2024', mayor_counts)

    def test_status_and_barangay_counts_use_recorded_office_project_data(self):
        today = timezone.localdate()
        self.make_infrastructure(
            'Current road',
            status='ongoing',
            end_date=today + timedelta(days=1),
            barangay='bagting',
        )
        self.make_infrastructure(
            'Late road',
            status='ongoing',
            end_date=today - timedelta(days=1),
            barangay='Calabasa',
        )
        self.make_infrastructure(
            'Paused road',
            status='on_hold',
            end_date=today - timedelta(days=3),
            barangay='Unknown',
        )
        self.make_infrastructure(
            'Finished road',
            status='completed',
            end_date=today - timedelta(days=5),
            barangay='North Poblacion',
        )
        self.make_non_infrastructure(
            'Mayor completed program', status='completed',
        )
        self.make_non_infrastructure(
            'Mayor planned program', status='planned',
        )

        self.client.force_login(self.users['engineering_dashboard'])
        response = self.client.get(reverse('engineering_dashboard'))
        analytics = response.context['project_analytics']
        self.assertEqual(
            {row['key']: row['value'] for row in analytics['status']},
            {
                'ongoing': 2,
                'on_hold': 1,
                'completed': 1,
                'unspecified': 0,
            },
        )
        barangay_counts = {
            row['key']: row['value'] for row in analytics['barangays']
        }
        self.assertEqual(barangay_counts['bagting'], 1)
        self.assertEqual(barangay_counts['calabasa'], 1)
        self.assertEqual(barangay_counts['bitulok'], 1)
        self.assertEqual(len(barangay_counts), 16)
        self.assertEqual(
            sum(value == 0 for value in barangay_counts.values()),
            13,
        )

        self.client.force_login(self.users['mayor_dashboard'])
        mayor_response = self.client.get(reverse('mayor_dashboard'))
        mayor_statuses = {
            row['key']: row['value']
            for row in mayor_response.context['project_analytics']['status']
        }
        self.assertEqual(
            mayor_statuses,
            {
                'planned': 1,
                'ongoing': 0,
                'completed': 1,
                'unspecified': 0,
            },
        )
        self.assertEqual(mayor_response.context['planned_projects'], 1)
        self.assertEqual(mayor_response.context['ongoing_projects'], 0)
        self.assertEqual(mayor_response.context['completed_projects'], 1)
        self.assertEqual(mayor_response.context['total_projects'], 2)
        self.assertEqual(
            sum((
                mayor_response.context['planned_projects'],
                mayor_response.context['ongoing_projects'],
                mayor_response.context['completed_projects'],
            )),
            mayor_response.context['total_projects'],
        )
        self.assertContains(mayor_response, '<h3>Ongoing</h3>', html=True)
        self.assertNotContains(mayor_response, 'In Progress')

    def test_status_chart_keeps_projects_with_unset_status_visible(self):
        self.make_infrastructure('Unclassified legacy project', status=None)

        self.client.force_login(self.users['engineering_dashboard'])
        response = self.client.get(reverse('engineering_dashboard'))
        analytics = response.context['project_analytics']

        self.assertEqual(
            {row['key']: row['value'] for row in analytics['status']},
            {
                'ongoing': 0,
                'on_hold': 0,
                'completed': 0,
                'unspecified': 1,
            },
        )
        self.assertEqual(analytics['status_project_count'], 1)

    def test_completion_charts_use_recorded_completion_events_only(self):
        completion_day = date(2025, 8, 14)
        _, completed_infrastructure = self.make_infrastructure(
            'Dated completed road', status='completed',
        )
        InfrastructureSchedule.objects.create(
            infrastructure=completed_infrastructure,
            actual_completion_date=completion_day,
        )
        self.make_infrastructure('Undated completed road', status='completed')

        _, completed_program = self.make_non_infrastructure(
            'Dated completed program', status='completed',
        )
        NonInfrastructureProgressUpdate.objects.create(
            non_infrastructure=completed_program,
            proposed_status='completed',
            review_status=NonInfrastructureProgressUpdate.ReviewStatus.APPROVED,
            applied_at=timezone.make_aware(
                datetime(2025, 9, 2, 10),
            ),
        )
        self.make_non_infrastructure(
            'Undated completed program', status='completed',
        )

        self.client.force_login(self.users['engineering_dashboard'])
        engineering = self.client.get(reverse('engineering_dashboard'))
        chart = engineering.context['project_analytics']
        self.assertEqual(
            dict(zip(
                chart['completed_by_month']['labels'],
                chart['completed_by_month']['values'],
            )),
            {'Aug 2025': 1},
        )
        self.assertEqual(chart['completed_without_dates'], 1)
        self.assertContains(
            engineering,
            '1 completed project has no reliable completion date and is not plotted.',
        )

        self.client.force_login(self.users['mayor_dashboard'])
        mayor = self.client.get(reverse('mayor_dashboard'))
        chart = mayor.context['project_analytics']
        self.assertEqual(
            dict(zip(
                chart['completed_by_month']['labels'],
                chart['completed_by_month']['values'],
            )),
            {'Sep 2025': 1},
        )
        self.assertEqual(chart['completed_without_dates'], 1)

    def test_completion_charts_fall_back_to_recorded_status_and_final_inspection_dates(self):
        inspection_day = date(2025, 11, 3)
        _, completed_infrastructure = self.make_infrastructure(
            'Completed by recorded status', status='completed',
        )
        status_update = InfrastructureProgressUpdate.objects.create(
            infrastructure=completed_infrastructure,
            new_official_status='completed',
            new_physical_progress=100,
        )
        InfrastructureProgressUpdate.objects.filter(
            pk=status_update.pk,
        ).update(created_at=timezone.make_aware(
            datetime(2025, 10, 12, 9),
        ))
        _, inspected_infrastructure = self.make_infrastructure(
            'Completed by final inspection', status='completed',
        )
        ProjectInspection.objects.create(
            project=inspected_infrastructure.project,
            inspection_date=inspection_day,
            completion_percentage=100,
        )

        self.client.force_login(self.users['engineering_dashboard'])
        response = self.client.get(reverse('engineering_dashboard'))
        chart = response.context['project_analytics']

        self.assertEqual(
            dict(zip(
                chart['completed_by_month']['labels'],
                chart['completed_by_month']['values'],
            )),
            {'Oct 2025': 1, 'Nov 2025': 1},
        )
        self.assertEqual(chart['completed_without_dates'], 0)

        _, completed_program = self.make_non_infrastructure(
            'Completed program by final inspection',
            status='completed',
        )
        ProjectInspection.objects.create(
            project=completed_program.project,
            inspection_date=inspection_day,
            completion_percentage=100,
        )
        self.client.force_login(self.users['mayor_dashboard'])
        response = self.client.get(reverse('mayor_dashboard'))
        chart = response.context['project_analytics']
        self.assertEqual(
            dict(zip(
                chart['completed_by_month']['labels'],
                chart['completed_by_month']['values'],
            )),
            {'Nov 2025': 1},
        )
        self.assertEqual(chart['completed_without_dates'], 0)

    def test_dashboard_access_remains_scoped_by_office(self):
        self.client.force_login(self.users['mayor_dashboard'])
        response = self.client.get(reverse('engineering_dashboard'))
        self.assertEqual(response.status_code, 403)
        self.client.force_login(
            self.users['engineering_head_dashboard'],
        )
        response = self.client.get(reverse('mayor_head_dashboard'))
        self.assertEqual(response.status_code, 403)
