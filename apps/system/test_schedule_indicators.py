from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.infrastructure import test_inspections as inspection_tests
from apps.system import tests as system_tests
from apps.system.models import InfrastructureSchedule, Project, ProjectRevision
from apps.system.publication_snapshots import build_project_publication_snapshot
from apps.system.schedule_indicators import infrastructure_schedule_indicator


class ScheduleIndicatorTests(SimpleTestCase):
    today = date(2026, 9, 11)

    def indicator(self, status='ongoing', deadline=date(2026, 9, 1), **kwargs):
        return infrastructure_schedule_indicator(status, deadline, as_of=self.today, **kwargs)

    def test_future_and_today_are_within_period(self):
        for deadline in (date(2026, 9, 11), date(2026, 9, 12)):
            with self.subTest(deadline=deadline):
                result = self.indicator(deadline=deadline)
                self.assertEqual(result['label'], 'Within scheduled period')
                self.assertEqual(result['days_past_target'], 0)
                self.assertEqual(result['deadline'], deadline)

    def test_past_target_and_on_hold_have_exact_day_count(self):
        for status in ('ongoing', 'on_hold', 'not_yet_started'):
            with self.subTest(status=status):
                result = self.indicator(status=status)
                self.assertEqual(result['label'], 'Past target date — 10 days')
                self.assertEqual(result['days_past_target'], 10)

    def test_completed_does_not_claim_late_completion(self):
        for deadline in (date(2026, 9, 1), None, 'invalid'):
            with self.subTest(deadline=deadline):
                result = self.indicator(status='completed', deadline=deadline)
                self.assertEqual(result['label'], 'Completed')
                self.assertEqual(result['days_past_target'], 0)

    def test_missing_and_invalid_dates(self):
        for deadline in (None, '', 'invalid', '2026-02-30', 123, datetime(2026, 9, 1)):
            with self.subTest(deadline=deadline):
                result = self.indicator(deadline=deadline)
                self.assertEqual(result['label'], 'Schedule not available')
                self.assertIsNone(result['deadline'])
        for start in ('invalid', date(2026, 9, 2)):
            self.assertEqual(self.indicator(planned_start_date=start)['label'], 'Schedule not available')

    def test_iso_dates_and_missing_start_are_supported(self):
        self.assertEqual(self.indicator(deadline='2026-09-01')['days_past_target'], 10)
        self.assertEqual(self.indicator(planned_start_date='2026-08-01')['days_past_target'], 10)

    @patch('apps.system.schedule_indicators.timezone.localdate', return_value=date(2026, 9, 11))
    def test_default_reference_is_django_localdate(self, localdate):
        self.assertEqual(infrastructure_schedule_indicator('ongoing', date(2026, 9, 1))['days_past_target'], 10)
        localdate.assert_called_once_with()


@patch('apps.system.schedule_indicators.timezone.localdate', return_value=date(2026, 9, 11))
class InternalScheduleIndicatorTests(TestCase):
    detail_url = inspection_tests.InfrastructureInspectionHistoryTests.detail_url

    def setUp(self):
        inspection_tests.InfrastructureInspectionHistoryTests.setUp(self)
        self.infrastructure.status = 'on_hold'
        self.infrastructure.planned_start_date = date(2026, 8, 1)
        self.infrastructure.planned_end_date = date(2026, 9, 1)
        self.infrastructure.physical_progress_percentage = Decimal('100')
        self.infrastructure.save()
        InfrastructureSchedule.objects.create(
            infrastructure=self.infrastructure, contract_expiry_date=date(2026, 12, 31),
        )
        self.client.force_login(self.staff)

    def test_authorized_internal_data_ignores_contract_expiry_and_preserves_status_progress(self, _):
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Past target date — 10 days')
        self.assertContains(response, 'On Hold')
        self.assertContains(response, 'Planned target:')
        self.assertContains(response, '<time datetime="2026-09-01">September 1, 2026</time>', html=True)
        self.assertNotContains(response, 'Based on the latest published update.')
        self.infrastructure.refresh_from_db()
        self.assertEqual(self.infrastructure.status, 'on_hold')
        self.assertEqual(self.infrastructure.physical_progress_percentage, Decimal('100'))
        # Existing expected-progress calculations still use the contract date.
        from apps.system.progress import active_schedule_end
        self.assertEqual(active_schedule_end(
            self.infrastructure.planned_start_date, self.infrastructure.planned_end_date,
            date(2026, 12, 31),
        ), date(2026, 12, 31))

    def test_internal_access_still_requires_authorization(self, _):
        self.client.logout()
        self.assertEqual(self.client.get(self.detail_url).status_code, 302)
        self.client.force_login(self.mayor_head)
        self.assertEqual(self.client.get(self.detail_url).status_code, 403)


@patch('apps.system.schedule_indicators.timezone.localdate', return_value=date(2026, 9, 11))
class PublicScheduleIndicatorTests(TestCase):
    def setUp(self):
        system_tests.PublicDashboardInfrastructureDataSourceTests.setUp(self)
        self.url = reverse('public_infrastructure_project_detail', args=[self.infrastructure.pk])

    def test_only_published_dates_status_and_progress_are_visible(self, _):
        original = deepcopy(self.public_revision.snapshot)
        self.infrastructure.status = 'completed'
        self.infrastructure.planned_end_date = date(2027, 1, 1)
        self.infrastructure.physical_progress_percentage = 100
        self.infrastructure.save()
        self.infrastructure.schedules.update(contract_expiry_date=date(2027, 12, 31))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Past target date — 12 days')
        self.assertContains(response, 'Based on the latest published update.')
        self.assertContains(response, '<time datetime="2026-08-30">August 30, 2026</time>', html=True)
        self.assertEqual(response.context['public_project']['status'], 'ongoing')
        self.assertEqual(response.context['public_project']['physical_progress_percentage'], Decimal('55'))
        self.public_revision.refresh_from_db()
        self.assertEqual(self.public_revision.snapshot, original)

    def publish_next(self):
        self.public_revision.is_current_public = False
        self.public_revision.save(update_fields=['is_current_public'])
        return ProjectRevision.objects.create(
            project=self.infrastructure.project, revision_number=2, status='published',
            is_current_public=True,
            snapshot=build_project_publication_snapshot(
                Project.objects.get(pk=self.infrastructure.project_id),
            ),
            source_updated_at=self.infrastructure.project.updated_at,
        )

    def test_new_published_target_becomes_source_without_rewriting_history(self, _):
        original = deepcopy(self.public_revision.snapshot)
        self.infrastructure.planned_end_date = date(2026, 12, 1)
        self.infrastructure.save()
        newest = self.publish_next()
        snapshot = deepcopy(newest.snapshot)
        response = self.client.get(self.url)
        self.assertContains(response, 'Within scheduled period')
        self.assertContains(response, '<time datetime="2026-12-01">December 1, 2026</time>', html=True)
        self.public_revision.refresh_from_db()
        newest.refresh_from_db()
        self.assertEqual(self.public_revision.snapshot, original)
        self.assertEqual(newest.snapshot, snapshot)

    def test_new_published_completed_status_removes_current_warning(self, _):
        self.infrastructure.status = 'completed'
        self.infrastructure.save()
        self.publish_next()
        response = self.client.get(self.url)
        self.assertEqual(response.context['schedule_indicator']['label'], 'Completed')
        self.assertNotContains(response, 'Past target date')

    def test_published_contract_date_is_not_an_approved_extension(self, _):
        snapshot = deepcopy(self.public_revision.snapshot)
        snapshot['schedule']['contract_expiry_date'] = '2027-12-31'
        self.public_revision.snapshot = snapshot
        self.public_revision.save(update_fields=['snapshot'])
        response = self.client.get(self.url)
        self.assertContains(response, 'Past target date — 12 days')

    def test_invalid_published_target_does_not_fall_back_to_live_data(self, _):
        snapshot = deepcopy(self.public_revision.snapshot)
        snapshot['infrastructure']['planned_end_date'] = 'invalid'
        self.public_revision.snapshot = snapshot
        self.public_revision.save(update_fields=['snapshot'])
        response = self.client.get(self.url)
        self.assertContains(response, 'Schedule not available')
        self.assertIsNone(response.context['schedule_indicator']['deadline'])

    def test_day_count_advances_without_snapshot_mutation(self, localdate):
        original = deepcopy(self.public_revision.snapshot)
        self.assertContains(self.client.get(self.url), 'Past target date — 12 days')
        localdate.return_value = date(2026, 9, 12)
        self.assertContains(self.client.get(self.url), 'Past target date — 13 days')
        self.public_revision.refresh_from_db()
        self.assertEqual(self.public_revision.snapshot, original)
