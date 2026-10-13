from datetime import date, datetime
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.system import tests as system_tests
from apps.system.schedule_indicators import infrastructure_schedule_indicator


class InfrastructureScheduleIndicatorTests(SimpleTestCase):
    today = date(2026, 9, 11)

    def indicator(self, status='ongoing', deadline=date(2026, 9, 1), **kwargs):
        return infrastructure_schedule_indicator(
            status,
            deadline,
            as_of=self.today,
            **kwargs,
        )

    def test_future_and_current_targets_are_within_period(self):
        for deadline in (date(2026, 9, 11), date(2026, 9, 12)):
            with self.subTest(deadline=deadline):
                result = self.indicator(deadline=deadline)
                self.assertEqual(result['kind'], 'within-period')
                self.assertEqual(result['days_past_target'], 0)

    def test_overdue_on_hold_projects_use_the_planned_target(self):
        result = self.indicator(status='on_hold')
        self.assertEqual(result['kind'], 'past-target')
        self.assertEqual(result['days_past_target'], 10)
        self.assertEqual(result['label'], 'Past target date — 10 days')

    def test_completed_status_never_reports_late_completion(self):
        for deadline in (date(2026, 9, 1), None, 'invalid'):
            with self.subTest(deadline=deadline):
                result = self.indicator(status='completed', deadline=deadline)
                self.assertEqual(result['kind'], 'completed')
                self.assertEqual(result['label'], 'Completed')
                self.assertEqual(result['days_past_target'], 0)

    def test_invalid_or_inconsistent_dates_are_unavailable(self):
        for deadline in (None, '', 'invalid', '2026-02-30', 123, datetime(2026, 9, 1)):
            with self.subTest(deadline=deadline):
                self.assertEqual(
                    self.indicator(deadline=deadline)['kind'],
                    'unavailable',
                )
        self.assertEqual(
            self.indicator(
                planned_start_date=date(2026, 9, 2),
            )['kind'],
            'unavailable',
        )

    @patch(
        'apps.system.schedule_indicators.timezone.localdate',
        return_value=date(2026, 9, 11),
    )
    def test_default_reference_uses_django_localdate(self, localdate):
        result = infrastructure_schedule_indicator(
            'ongoing',
            date(2026, 9, 1),
        )
        self.assertEqual(result['days_past_target'], 10)
        localdate.assert_called_once_with()


class PublicScheduleIndicatorTests(TestCase):
    def setUp(self):
        system_tests.PublicDashboardInfrastructureDataSourceTests.setUp(self)
        self.url = reverse(
            'public_infrastructure_project_detail',
            args=[self.infrastructure.pk],
        )

    @patch(
        'apps.system.schedule_indicators.timezone.localdate',
        return_value=date(2026, 9, 11),
    )
    def test_public_indicator_uses_only_the_current_published_revision(
        self,
        _localdate,
    ):
        snapshot = self.public_revision.snapshot.copy()
        self.infrastructure.status = 'completed'
        self.infrastructure.planned_end_date = date(2027, 1, 1)
        self.infrastructure.save(update_fields=['status', 'planned_end_date'])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['schedule_indicator']['deadline'],
            date(2026, 8, 30),
        )
        self.assertEqual(
            response.context['schedule_indicator']['days_past_target'],
            12,
        )
        self.assertContains(response, 'Based on the latest published update.')
        self.public_revision.refresh_from_db()
        self.assertEqual(self.public_revision.snapshot, snapshot)
