from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.non_infrastructure.forms import NonInfrastructureProjectForm
from apps.system.models import (
    NonInfrastructureCategory,
    Non_Infrastructure_Project,
    Project,
    Project_Image,
)


class NonInfrastructureProjectFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='project-admin',
            email='admin@example.com',
            password='testpass123',
        )
        self.category = NonInfrastructureCategory.objects.create(
            type_code='health-care',
            type_name='Health Care',
            description='Health care services',
        )

    def test_form_saves_normalized_non_infrastructure_project(self):
        form = NonInfrastructureProjectForm(
            data={
                'non_infra_name': 'Community Health Fair',
                'description': 'Free medical and health education event.',
                'non_infra_category': str(self.category.non_infrastructure_category_id),
                'event_date': '2026-08-20',
                'start_time': '08:00',
                'end_time': '12:00',
                'venue_name': 'Municipal Plaza',
                'street': 'Rizal Street',
                'barangay': 'Mabini',
                'municipality': 'Gabaldon',
                'province': 'Nueva Ecija',
                'latitude': '15.3000000',
                'longitude': '121.3500000',
                'project_images': 'https://example.com/one.jpg\nhttps://example.com/two.jpg',
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        project = form.save(user=self.user)

        self.assertEqual(project.non_infra_name, 'Community Health Fair')
        self.assertEqual(project.non_infra_category, self.category)
        self.assertEqual(project.address.barangay, 'Mabini')
        self.assertEqual(project.venue_name, 'Municipal Plaza')
        self.assertEqual(project.project.created_by_user, self.user)
        self.assertEqual(
            list(project.project.images.order_by('project_image_id').values_list('image_url', flat=True)),
            ['https://example.com/one.jpg', 'https://example.com/two.jpg'],
        )

    def test_form_updates_existing_project_and_images(self):
        proj = Project.objects.create(project_type='non_infrastructure', created_by_user=self.user, updated_by_user=self.user)
        existing = Non_Infrastructure_Project.objects.create(
            project=proj,
            non_infra_name='Old Program',
            description='Old description',
            non_infra_category=self.category,
            event_date='2026-01-10',
            venue_name='Old Venue',
        )
        Project_Image.objects.create(project=proj, image_url='https://example.com/old.jpg')

        form = NonInfrastructureProjectForm(
            instance=existing,
            data={
                'non_infra_name': 'Updated Community Fair',
                'description': 'Updated description.',
                'non_infra_category': str(self.category.non_infrastructure_category_id),
                'event_date': '2026-09-15',
                'start_time': '09:00',
                'end_time': '13:00',
                'venue_name': 'New Event Grounds',
                'street': 'Main Avenue',
                'barangay': 'San Francisco',
                'municipality': 'Gabaldon',
                'province': 'Nueva Ecija',
                'project_images': 'https://example.com/new-one.jpg\nhttps://example.com/new-two.jpg',
            },
        )

        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save(user=self.user, instance=existing)

        self.assertEqual(updated.non_infra_name, 'Updated Community Fair')
        self.assertEqual(updated.event_date.isoformat(), '2026-09-15')
        self.assertEqual(updated.venue_name, 'New Event Grounds')
        self.assertEqual(
            list(updated.project.images.order_by('project_image_id').values_list('image_url', flat=True)),
            ['https://example.com/new-one.jpg', 'https://example.com/new-two.jpg'],
        )
