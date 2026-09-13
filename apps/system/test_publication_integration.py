from copy import deepcopy

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Infrastructure_Project, Non_Infrastructure_Project, NonInfrastructureCategory, UserFlag


class OfficePublicationIntegrationTests(TestCase):
    def test_both_offices_publish_and_replace_only_approved_snapshots(self):
        from apps.infrastructure.tests import InfrastructureProjectFormTests
        fixture = InfrastructureProjectFormTests()
        fixture.setUp()
        category = NonInfrastructureCategory.objects.create(type_code='integration', type_name='Integration')
        publisher = User.objects.create_superuser('publisher', 'publisher@example.com', 'password')
        for office, model, prefix, title_key, payload, public_route in [
            ('engineer', Infrastructure_Project, 'engineering_projects:project', 'title', fixture.valid_data(), 'public_infrastructure_project_detail'),
            ('mayor', Non_Infrastructure_Project, 'mayor_projects:non_infrastructure_project', 'non_infra_name', {
                'non_infra_name': 'Community event', 'description': 'Integration program',
                'non_infra_category': category.pk, 'status': 'planned', 'proponent': 'Mayor Office',
                'beneficiaries': '10', 'event_date': '2026-09-01', 'start_time': '08:00',
                'end_time': '09:00', 'venue_name': 'Plaza', 'barangay': 'bagting',
            }, 'public_non_infrastructure_project_detail'),
        ]:
            staff = User.objects.create_user(office + '-staff', is_staff=True)
            head = User.objects.create_user(office + '-head', is_staff=True)
            UserFlag.objects.create(user=staff, department=office, role='staff')
            UserFlag.objects.create(user=head, department=office, role='head')
            self.client.force_login(staff)
            self.assertEqual(self.client.post(reverse(prefix + '_create'), payload).status_code, 302)
            record = model.objects.order_by('-pk').first()
            previous = None
            for version in [1, 2]:
                title = f'{office} approved version {version}'
                payload[title_key] = title
                self.client.force_login(staff)
                self.assertEqual(self.client.post(reverse(prefix + '_update', args=[record.pk]), payload).status_code, 302)
                if previous:
                    self.client.logout()
                    public = self.client.get(reverse(public_route, args=[record.pk]))
                    self.assertNotContains(public, title)
                    self.assertContains(public, f'{office} approved version 1')
                    self.client.force_login(staff)
                submit_url = reverse(prefix + '_submit_for_review', args=[record.pk])
                self.assertEqual(self.client.post(submit_url).status_code, 302)
                revision = record.project.publication_revisions.order_by('-revision_number').first()
                working = self.client.get(reverse(prefix + '_detail', args=[record.pk]))
                self.assertContains(working, 'office Head review')
                self.assertNotContains(working, 'administrator review')
                self.client.force_login(head)
                queue = self.client.get(reverse('publication_review_queue'))
                self.assertContains(queue, title)
                detail_url = reverse('publication_revision_detail', args=[revision.pk])
                self.assertEqual(self.client.get(detail_url).context['comparison']['is_initial'], previous is None)
                # Both return paths require notes, and Staff can subsequently resubmit.
                for decision in ['needs_revision', 'rejected']:
                    review_url = reverse('publication_revision_review', args=[revision.pk])
                    self.client.post(review_url, {'decision': decision})
                    revision.refresh_from_db()
                    self.assertEqual(revision.status, 'pending_review')
                    self.assertEqual(self.client.post(review_url, {'decision': decision, 'notes': 'Correct the submission.'}).status_code, 302)
                    self.client.force_login(staff)
                    self.assertEqual(self.client.post(submit_url).status_code, 302)
                    revision = record.project.publication_revisions.order_by('-revision_number').first()
                    self.client.force_login(head)
                snapshot = deepcopy(revision.snapshot_data)
                self.client.post(reverse('publication_revision_review', args=[revision.pk]), {'decision': 'approved'})
                self.client.force_login(publisher)
                self.assertContains(self.client.get(reverse('publication_lifecycle')), reverse('publication_revision_detail', args=[revision.pk]))
                self.client.force_login(head)
                self.assertEqual(self.client.post(reverse('publication_revision_publish', args=[revision.pk])).status_code, 302)
                revision.refresh_from_db()
                self.assertEqual(revision.snapshot_data, snapshot)
                self.assertTrue(revision.is_current_public_revision)
                self.client.logout()
                self.assertContains(self.client.get(reverse(public_route, args=[record.pk])), title)
                map_response = self.client.get(reverse('gis_projects_layer'))
                self.assertEqual(map_response.status_code, 200)
                self.assertEqual(map_response.json()['type'], 'FeatureCollection')
                self.assertEqual(self.client.get(reverse('gis_project_photos', args=[record.project_id])).status_code, 200)
                if previous:
                    previous.refresh_from_db()
                    self.assertEqual(previous.status, 'archived')
                    self.assertFalse(previous.is_current_public_revision)
                previous = revision
