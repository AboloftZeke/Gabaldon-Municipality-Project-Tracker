from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django import forms
from django.test import TestCase
from django.urls import reverse

from apps.infrastructure.forms import InfrastructureOperationalForm
from apps.infrastructure.tests import InfrastructureProjectFormTests
from apps.system.models import (
    InfrastructureSchedule,
    ProjectInspection,
    UserRole,
)


class InfrastructureRestoredFeatureTests(TestCase):
    def setUp(self):
        fixture = InfrastructureProjectFormTests()
        fixture.setUp()
        self.fixture = fixture
        self.user = fixture.user
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        UserRole.objects.update_or_create(
            user=self.user,
            defaults={'department': 'engineer', 'role': 'staff'},
        )
        self.infrastructure = fixture.create_project()
        self.client.force_login(self.user)

    @property
    def detail_url(self):
        return reverse(
            'engineering_projects:project_detail',
            args=[self.infrastructure.pk],
        )

    @property
    def create_url(self):
        return reverse('engineering_projects:project_create')

    def test_create_and_edit_render_hidden_coordinates_and_picker(self):
        self.infrastructure.address.latitude = Decimal('15.4541234')
        self.infrastructure.address.longitude = Decimal('121.3375123')
        self.infrastructure.address.save(update_fields=['latitude', 'longitude'])

        for url in (
            self.create_url,
            reverse(
                'engineering_projects:project_update',
                args=[self.infrastructure.pk],
            ),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="infrastructure-location-map"')
                self.assertContains(response, '/static/vendor/leaflet/leaflet.css')
                self.assertContains(response, '/static/vendor/leaflet/leaflet.js')
                for field in ('latitude', 'longitude'):
                    self.assertIsInstance(
                        response.context['form'].fields[field].widget,
                        forms.HiddenInput,
                    )
                    self.assertContains(response, f'type="hidden" name="{field}"')
                if url != self.create_url:
                    self.assertContains(response, 'value="15.4541234"')
                    self.assertContains(response, 'value="121.3375123"')
                self.assertNotContains(response, '<label for="id_latitude">')
                self.assertNotContains(response, '<label for="id_longitude">')

    def test_create_and_edit_persist_map_selected_coordinates(self):
        response = self.client.post(
            self.create_url,
            self.fixture.valid_data(
                latitude='15.4541234',
                longitude='121.3375123',
            ),
        )
        self.assertEqual(response.status_code, 302)
        created = self.infrastructure.__class__.objects.exclude(
            pk=self.infrastructure.pk,
        ).get()
        self.assertEqual(created.address.latitude, Decimal('15.4541234'))
        self.assertEqual(created.address.longitude, Decimal('121.3375123'))

        address_id = self.infrastructure.address_id
        response = self.client.post(
            reverse(
                'engineering_projects:project_update',
                args=[self.infrastructure.pk],
            ),
            self.fixture.valid_data(
                latitude='15.4522345',
                longitude='121.3387654',
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.infrastructure.refresh_from_db()
        self.assertEqual(self.infrastructure.address_id, address_id)
        self.assertEqual(
            self.infrastructure.address.latitude,
            Decimal('15.4522345'),
        )
        self.assertEqual(
            self.infrastructure.address.longitude,
            Decimal('121.3387654'),
        )

    def test_coordinate_presence_and_range_remain_backend_validated(self):
        for coordinates in (
            {'latitude': '', 'longitude': ''},
            {'latitude': '15.45', 'longitude': ''},
            {'latitude': '91', 'longitude': '121.3'},
            {'latitude': '15.12345678', 'longitude': '121.3'},
        ):
            with self.subTest(coordinates=coordinates):
                response = self.client.post(
                    self.create_url,
                    self.fixture.valid_data(**coordinates),
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(
                    {'latitude', 'longitude'}.intersection(
                        response.context['form'].errors,
                    ),
                )
        self.assertEqual(
            self.infrastructure.__class__.objects.count(),
            1,
        )

    def _operational_form(self, status, current_status):
        self.infrastructure.status = current_status
        return InfrastructureOperationalForm(
            data={
                'status': status,
                'physical_progress_percentage': '50',
                'supporting_inspections': [],
            },
            instance=self.infrastructure,
            require_initial_values=True,
        )

    def test_operational_status_can_advance_but_cannot_reopen_completed_work(self):
        self.assertTrue(
            self._operational_form('on_hold', 'ongoing').is_valid(),
        )
        self.assertTrue(
            self._operational_form('completed', 'on_hold').is_valid(),
        )

        form = self._operational_form('ongoing', 'completed')
        self.assertFalse(form.is_valid())
        self.assertIn('status', form.errors)

    @patch(
        'apps.system.schedule_indicators.timezone.localdate',
        return_value=date(2026, 9, 11),
    )
    def test_internal_schedule_indicator_uses_planned_target_without_mutation(
        self,
        _localdate,
    ):
        self.infrastructure.status = 'on_hold'
        self.infrastructure.planned_start_date = date(2026, 8, 1)
        self.infrastructure.planned_end_date = date(2026, 9, 1)
        self.infrastructure.physical_progress_percentage = Decimal('55')
        self.infrastructure.save()
        InfrastructureSchedule.objects.create(
            infrastructure=self.infrastructure,
            contract_expiry_date=date(2026, 12, 31),
        )

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Past target date — 10 days')
        self.assertEqual(
            response.context['schedule_indicator']['deadline'],
            date(2026, 9, 1),
        )
        self.infrastructure.refresh_from_db()
        self.assertEqual(self.infrastructure.status, 'on_hold')
        self.assertEqual(
            self.infrastructure.physical_progress_percentage,
            Decimal('55'),
        )

    def test_inspection_history_is_paginated_and_preserves_other_query_params(self):
        for index in range(6):
            ProjectInspection.objects.create(
                project=self.infrastructure.project,
                inspection_date=date(2026, 6, 1 + index),
                inspected_by_user=self.user,
                completion_percentage=Decimal(index * 10),
                findings=f'Inspection {index + 1}',
                remarks='Pagination regression test',
            )

        first_page = self.client.get(self.detail_url)
        self.assertEqual(first_page.context['inspection_page'].number, 1)
        self.assertEqual(len(first_page.context['inspection_history']), 5)
        self.assertContains(first_page, 'Showing inspections 1–5 of 6')
        self.assertContains(first_page, 'Next')

        second_page = self.client.get(
            f'{self.detail_url}?inspection_page=2&from_review=1',
        )
        self.assertEqual(second_page.context['inspection_page'].number, 2)
        self.assertEqual(len(second_page.context['inspection_history']), 1)
        self.assertContains(second_page, 'Inspection 1')
        self.assertContains(second_page, 'from_review=1')
