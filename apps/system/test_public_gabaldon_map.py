from django.test import TestCase
from django.urls import reverse


class PublicGabaldonDashboardTests(TestCase):
    def test_dashboard_restores_geographic_map_and_status_snapshot(self):
        for params in ({}, {'type': 'infra'}, {'type': 'noninfra'}):
            with self.subTest(params=params):
                response = self.client.get(
                    reverse('public_dashboard'),
                    params,
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Explore Gabaldon')
                self.assertContains(
                    response,
                    'id="gabaldon-public-map"',
                    count=1,
                )
                self.assertContains(
                    response,
                    '/static/js/gis/public_gabaldon_map.js',
                )
                self.assertContains(response, 'Infrastructure')
                self.assertContains(response, 'Non-Infrastructure')
                self.assertEqual(
                    [
                        item['label']
                        for item in response.context[
                            'infrastructure_status_summaries'
                        ]
                    ],
                    ['Ongoing', 'On Hold', 'Completed'],
                )
                self.assertEqual(
                    [
                        item['label']
                        for item in response.context[
                            'noninfrastructure_status_summaries'
                        ]
                    ],
                    ['Planned', 'Ongoing', 'Completed'],
                )
                self.assertNotContains(response, 'Not Yet Started')
                self.assertNotContains(response, 'GIS Project Map')
                self.assertNotContains(response, 'project-gis-map')
