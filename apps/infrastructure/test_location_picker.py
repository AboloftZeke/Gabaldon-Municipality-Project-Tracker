from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.infrastructure.forms import InfrastructureProjectForm
from apps.infrastructure import tests as infrastructure_tests
from apps.system.models import Address, InfrastructureProject, UserRole
from apps.system.publication_service import (
    confirm_head_operational_information, publish_publication_revision,
    review_publication_revision, submit_project_for_review,
)


class InfrastructureLocationPickerTests(TestCase):
    # Share the existing complete form fixture without duplicating its tests.
    valid_data = infrastructure_tests.InfrastructureProjectFormTests.valid_data
    create_project = infrastructure_tests.InfrastructureProjectFormTests.create_project

    def setUp(self):
        infrastructure_tests.InfrastructureProjectFormTests.setUp(self)
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        UserRole.objects.update_or_create(
            user=self.user, defaults={'department': 'engineer', 'role': 'staff'},
        )
        self.client.force_login(self.user)
        self.create_url = reverse('engineering_projects:project_create')

    def test_create_post_saves_map_selected_coordinates(self):
        response = self.client.post(self.create_url, self.valid_data(
            latitude='15.4541234', longitude='121.3375123',
        ))
        self.assertEqual(response.status_code, 302)
        address = InfrastructureProject.objects.get().address
        self.assertEqual(address.latitude, Decimal('15.4541234'))
        self.assertEqual(address.longitude, Decimal('121.3375123'))

    def test_edit_post_moves_location_without_creating_another_address(self):
        project = self.create_project(latitude='15.4541234', longitude='121.3375123')
        address_id = project.address_id
        response = self.client.post(reverse('engineering_projects:project_update', args=[project.pk]), self.valid_data(
            latitude='15.4522345', longitude='121.3387654',
        ))
        self.assertEqual(response.status_code, 302)
        project.refresh_from_db()
        self.assertEqual(project.address_id, address_id)
        self.assertEqual(Address.objects.count(), 1)
        self.assertEqual(project.address.latitude, Decimal('15.4522345'))
        self.assertEqual(project.address.longitude, Decimal('121.3387654'))

    def test_create_and_edit_expose_only_hidden_coordinate_fields(self):
        project = self.create_project(latitude='15.4541234', longitude='121.3375123')
        for url in (self.create_url, reverse('engineering_projects:project_update', args=[project.pk])):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, 'id="infrastructure-location-map"')
                self.assertContains(response, '/static/vendor/leaflet/leaflet.css')
                self.assertContains(response, '/static/vendor/leaflet/leaflet.js')
                self.assertContains(response, 'data-selected-latitude')
                for name in ('latitude', 'longitude'):
                    self.assertContains(response, f'type="hidden" name="{name}"')
                    self.assertIsInstance(response.context['form'].fields[name].widget, forms.HiddenInput)
                    self.assertNotContains(response, f'<label for="id_{name}">')
        self.assertContains(response, 'value="15.4541234"')
        self.assertContains(response, 'value="121.3375123"')

    def test_missing_and_partial_coordinates_are_rejected_before_save(self):
        for latitude, longitude in (('', ''), ('15.45', ''), ('', '121.33')):
            with self.subTest(latitude=latitude, longitude=longitude):
                response = self.client.post(self.create_url, self.valid_data(latitude=latitude, longitude=longitude))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Select the exact project location on the map.')
        self.assertEqual(InfrastructureProject.objects.count(), 0)
        self.assertEqual(Address.objects.count(), 0)

    def test_backend_rejects_tampered_nonfinite_nonnumeric_and_out_of_range_coordinates(self):
        for field, invalid in (
            ('latitude', 'not-a-number'), ('longitude', 'not-a-number'),
            ('latitude', 'NaN'), ('longitude', 'Infinity'),
            ('latitude', '90.0000001'), ('latitude', '-90.0000001'),
            ('longitude', '180.0000001'), ('longitude', '-180.0000001'),
            ('latitude', '15.12345678'),
        ):
            with self.subTest(field=field, invalid=invalid):
                response = self.client.post(self.create_url, self.valid_data(**{field: invalid}))
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context['form'].errors)
        self.assertEqual(InfrastructureProject.objects.count(), 0)

    def test_invalid_edit_does_not_change_saved_location(self):
        project = self.create_project()
        old = (project.address.latitude, project.address.longitude)
        response = self.client.post(reverse('engineering_projects:project_update', args=[project.pk]), self.valid_data(latitude='91'))
        self.assertEqual(response.status_code, 200)
        project.address.refresh_from_db()
        self.assertEqual((project.address.latitude, project.address.longitude), old)

    def test_existing_record_without_coordinates_opens_with_empty_hidden_values(self):
        project = self.create_project()
        project.address.latitude = project.address.longitude = None
        project.address.save(update_fields=['latitude', 'longitude'])
        response = self.client.get(reverse('engineering_projects:project_update', args=[project.pk]))
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertIsNone(form['latitude'].value())
        self.assertIsNone(form['longitude'].value())

    def test_bound_coordinates_survive_other_validation_errors(self):
        response = self.client.post(self.create_url, self.valid_data(
            title='', latitude='15.4541234', longitude='121.3375123',
        ))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="15.4541234"')
        self.assertContains(response, 'value="121.3375123"')

    def test_selected_point_survives_staff_review_publish_and_shared_gis(self):
        project = self.create_project(latitude='15.4541234', longitude='121.3375123')
        head = get_user_model().objects.create_user(username='location-head', is_staff=True)
        UserRole.objects.create(user=head, department='engineer', role='head')
        revision = submit_project_for_review(project.project, self.user)
        revision = review_publication_revision(revision, head, 'approved')
        # Staff creation leaves official operational values for the Head.
        project.status = 'not_yet_started'
        project.physical_progress_percentage = Decimal('0')
        project.save(update_fields=['status', 'physical_progress_percentage'])
        revision = confirm_head_operational_information(revision, head)
        publish_publication_revision(revision, head)
        response = self.client.get(reverse('gis_projects_layer'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['features'][0]['geometry']['coordinates'], [121.3375123, 15.4541234])
        internal = self.client.get(reverse('engineering_projects:project_detail', args=[project.pk]))
        self.assertEqual(internal.status_code, 200)
        self.assertContains(internal, '15.4541234')
        self.client.logout()
        public = self.client.get(reverse('public_infrastructure_project_detail', args=[project.pk]))
        self.assertContains(public, 'data-focus-lat="15.4541234"')
        self.assertContains(public, 'data-focus-lng="121.3375123"')
        self.assertEqual(self.client.get(reverse('gis_project_photos', args=[project.project_id])).status_code, 200)
