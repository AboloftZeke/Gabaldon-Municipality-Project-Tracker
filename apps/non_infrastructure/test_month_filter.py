from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.system.models import (
    Address, NonInfrastructureCategory, NonInfrastructureProject, Project,
    UserRole,
)


class NonInfrastructureMonthFilterTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('mayor-month', is_staff=True)
        UserRole.objects.create(user=self.user, department='mayor', role='staff')
        self.client.force_login(self.user)
        self.url = reverse('mayor_projects:non_infrastructure_project_list')
        self.bagting = Address.objects.create(barangay='Bagting')
        self.other_location = Address.objects.create(barangay='Calabasa')
        self.health = NonInfrastructureCategory.objects.create(
            type_code='month-health', type_name='Health',
        )
        self.education = NonInfrastructureCategory.objects.create(
            type_code='month-education', type_name='Education',
        )

        self.make('January Event Only', event_date='2025-01-10')
        self.make('Another January Event Only', event_date='2026-01-20')
        self.make('September Event Only', event_date='2026-09-20')
        self.make('January Program',
                  implementation_start_date='2026-01-05')
        self.make('Other Barangay Program',
                  implementation_start_date='2026-09-05', address=self.other_location)
        self.make('Education Program',
                  implementation_start_date='2026-09-07', category=self.education)
        self.make('Implementation Ends March',
                  implementation_start_date='2025-12-10',
                  implementation_end_date='2026-03-08',
                  expected_delivery_date='2026-03-08')
        self.make('Event April, Implementation May',
                  event_date='2026-04-10', implementation_start_date='2026-05-10')
        self.make('Implementation Start May',
                  implementation_start_date='2026-05-10')
        self.make('No Schedule')

    def make(self, title, **fields):
        base = Project.objects.create(project_type='non_infrastructure')
        return NonInfrastructureProject.objects.create(
            project=base, title=title,
            address=fields.pop('address', self.bagting),
            category=fields.pop('category', self.health),
            **fields,
        )

    def titles(self, params=None):
        response = self.client.get(self.url, params or {})
        self.assertEqual(response.status_code, 200)
        return response, {item.title for item in response.context['projects']}

    def test_all_months_and_empty_month_preserve_existing_list(self):
        for month in (None, ''):
            with self.subTest(month=month):
                response, names = self.titles({} if month is None else {'month': month})
                self.assertEqual(response.context['page_obj'].paginator.count, 10)
                self.assertIn('No Schedule', names)
                self.assertContains(response, 'All Months')

    def test_month_matches_implementation_start_or_end_dates(self):
        response, names = self.titles({'month': '1'})
        self.assertEqual(names, {'January Program'})
        self.assertEqual(response.context['selected_month'], '1')

    def test_september_combines_with_location_and_category(self):
        response, names = self.titles({
            'month': '9', 'location': 'Bagting',
            'category': str(self.education.pk),
        })
        self.assertEqual(names, {'Education Program'})
        self.assertContains(response, 'value="9" selected')
        _, names = self.titles({'month': '9', 'location': 'Calabasa'})
        self.assertEqual(names, {'Other Barangay Program'})

    def test_month_ignores_non_implementation_dates_and_uses_end_date(self):
        march, march_names = self.titles({'month': '3'})
        self.assertEqual(march_names, {'Implementation Ends March'})
        self.assertNotIn('Implementation Ends March', self.titles({'month': '1'})[1])
        april, april_names = self.titles({'month': '4'})
        self.assertEqual(april_names, set())
        self.assertEqual(self.titles({'month': '5'})[1], {
            'Event April, Implementation May', 'Implementation Start May',
        })
        self.assertNotIn('January Event Only', march_names)
        self.assertNotIn('No Schedule', self.titles({'month': '9'})[1])

    def test_invalid_month_is_ignored_safely(self):
        for value in ('13', '-1', 'abc', '1 OR 1=1'):
            with self.subTest(value=value):
                response, _ = self.titles({'month': value})
                self.assertEqual(response.context['page_obj'].paginator.count, 10)
                self.assertEqual(response.context['selected_month'], '')

    def test_pagination_keeps_all_active_filters(self):
        for index in range(10):
            self.make(
                f'Additional January {index}',
                implementation_start_date='2026-01-17',
            )
        params = {
            'month': '1', 'location': 'Bagting',
            'category': str(self.health.pk),
        }
        first, _ = self.titles(params)
        self.assertEqual(first.context['page_obj'].paginator.count, 11)
        self.assertEqual(len(first.context['projects']), 10)
        self.assertContains(first, 'page=2')
        for key, value in params.items():
            self.assertContains(first, f'{key}={value}')
        second, names = self.titles({**params, 'page': '2'})
        self.assertEqual(len(names), 1)
        self.assertEqual(second.context['selected_month'], '1')
        self.assertContains(second, 'page=1')
