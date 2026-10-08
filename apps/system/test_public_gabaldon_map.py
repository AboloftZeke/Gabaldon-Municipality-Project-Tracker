"""Public geographic exploration must remain separate from the registry GIS."""
from django.test import TestCase
from django.urls import reverse


class PublicGabaldonMapTests(TestCase):
    def test_map_is_available_on_dashboard_and_both_registry_views(self):
        for params in ({}, {'type': 'infra'}, {'type': 'noninfra'}):
            with self.subTest(params=params):
                response = self.client.get(reverse('public_dashboard'), params)
                self.assertContains(response, 'Explore Gabaldon')
                self.assertContains(response, 'id="gabaldon-public-map"', count=1)
                self.assertContains(response, '/static/vendor/leaflet/leaflet.css')
                self.assertContains(response, '/static/vendor/leaflet/leaflet.js')
                self.assertContains(response, '/static/js/gis/public_gabaldon_map.js')
                for obsolete in (
                    'GIS Project Map', 'mapped projects', 'gis-visible-count',
                    'project-gis-map', 'gis-empty-state', 'Project status map legend',
                    'gis-legend', 'leaflet.markercluster', 'https://unpkg.com/leaflet',
                ):
                    self.assertNotContains(response, obsolete)

    def test_project_sections_and_registry_controls_remain_available(self):
        dashboard = self.client.get(reverse('public_dashboard'))
        self.assertContains(dashboard, 'Infrastructure Projects')
        self.assertContains(dashboard, 'Non-Infrastructure Projects')
        for project_type in ('infra', 'noninfra'):
            with self.subTest(project_type=project_type):
                response = self.client.get(reverse('public_dashboard'), {'type': project_type})
                for control in ('project-search', 'category-filter', 'location-filter', 'visible-count'):
                    self.assertContains(response, f'id="{control}"')
                self.assertContains(response, 'data-status="ongoing"')
                self.assertContains(response, 'data-dashboard-view="card"')

    def test_shared_project_and_local_layer_endpoints_remain_available(self):
        response = self.client.get(reverse('gis_projects_layer'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['type'], 'FeatureCollection')
        for layer in ('roads', 'bridges', 'waterways', 'facilities'):
            with self.subTest(layer=layer):
                response = self.client.get(reverse('gis_static_layer', args=[layer]))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['type'], 'FeatureCollection')
