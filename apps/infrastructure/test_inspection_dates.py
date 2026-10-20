from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.infrastructure import test_inspections as fixtures
from apps.system.models import Project, ProjectInspection


class InspectionDateTests(TestCase):
    create_url = fixtures.InfrastructureInspectionHistoryTests.create_url
    detail_url = fixtures.InfrastructureInspectionHistoryTests.detail_url

    def setUp(self):
        fixtures.InfrastructureInspectionHistoryTests.setUp(self)
        self.client.force_login(self.staff)
        self.today = timezone.localdate()

    def post(self, days_ago, url=None):
        return self.client.post(url or self.create_url, {
            'inspection_date': (self.today - timedelta(days=days_ago)).isoformat(),
            'completion_percentage': '25', 'findings': 'Retained field observations',
            'remarks': 'Retained remarks',
        })

    def add(self, days_ago):
        return ProjectInspection.objects.create(
            project=self.infrastructure.project,
            inspection_date=self.today - timedelta(days=days_ago),
            completion_percentage=10, inspected_by_user=self.staff,
        )

    def edit_url(self, record):
        return reverse('engineering_projects:inspection_update', args=[self.infrastructure.pk, record.pk])

    def test_antedated_first_inspection_and_today_are_allowed(self):
        self.assertEqual(self.post(20).status_code, 302)
        self.assertEqual(self.post(0).status_code, 302)
        self.assertEqual(self.infrastructure.project.inspections.count(), 2)

    def test_future_date_rejected_with_values_and_field_error_retained(self):
        response = self.post(-1)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Inspection date cannot be in the future.', status_code=400)
        self.assertEqual(response.context['form']['findings'].value(), 'Retained field observations')
        self.assertIn('inspection_date', response.context['form'].errors)
        self.assertFalse(self.infrastructure.project.inspections.exists())

    def test_later_succeeding_inspection_is_accepted(self):
        self.add(20)
        self.assertEqual(self.post(19).status_code, 302)

    def test_earlier_succeeding_inspection_is_rejected(self):
        self.add(20)
        response = self.post(21)
        self.assertEqual(response.status_code, 400)
        self.assertIn('later than the previous inspection date', response.context['form'].errors['inspection_date'][0])
        self.assertEqual(self.infrastructure.project.inspections.count(), 1)

    def test_duplicate_date_rejected_even_for_nonlatest_record(self):
        self.add(20)
        self.add(10)
        response = self.post(20)
        self.assertEqual(response.status_code, 400)
        self.assertIn('already exists', response.context['form'].errors['inspection_date'][0])

    def test_edit_unchanged_date_does_not_compare_against_itself(self):
        first = self.add(20)
        self.add(10)
        self.assertEqual(self.post(20, self.edit_url(first)).status_code, 302)
        first.refresh_from_db()
        self.assertEqual(first.remarks, 'Retained remarks')

    def test_edit_can_move_between_neighbours_but_not_past_them(self):
        self.add(30)
        middle = self.add(20)
        self.add(10)
        url = self.edit_url(middle)
        for days in (31, 30, 10, 9, -1):
            with self.subTest(days=days):
                self.assertEqual(self.post(days, url).status_code, 400)
        middle.refresh_from_db()
        self.assertEqual(middle.inspection_date, self.today - timedelta(days=20))
        self.assertEqual(self.post(15, url).status_code, 302)

    def test_latest_edit_still_follows_previous(self):
        self.add(20)
        latest = self.add(10)
        self.assertEqual(self.post(21, self.edit_url(latest)).status_code, 400)
        self.assertEqual(self.post(0, self.edit_url(latest)).status_code, 302)

    def test_other_project_dates_do_not_restrict_this_project(self):
        other = Project.objects.create(project_type='infrastructure', created_by_user=self.staff)
        ProjectInspection.objects.create(project=other, inspection_date=self.today, completion_percentage=10)
        self.assertEqual(self.post(0).status_code, 302)

    def test_form_date_picker_has_local_today_maximum(self):
        response = self.client.get(self.create_url)
        self.assertEqual(response.context['form'].fields['inspection_date'].widget.attrs['max'], self.today.isoformat())
