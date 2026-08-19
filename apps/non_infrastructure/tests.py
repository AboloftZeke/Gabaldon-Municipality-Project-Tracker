from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.non_infrastructure.forms import NonInfrastructureProjectForm
from apps.system.models import (
    Address,
    NonInfrastructureCategory,
    NonInfrastructureProject as SystemNonInfrastructureProject,
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
                'status': 'planned',
                'description': 'Free medical and health education event.',
                'non_infra_category': str(self.category.non_infrastructure_category_id),
                'proponent': 'Municipal Health Office',
                'beneficiaries': '250',
                'event_date': '2026-08-20',
                'start_time': '08:00',
                'end_time': '12:00',
                'venue_name': 'Municipal Plaza',
                'street': 'Rizal Street',
                'barangay': 'bagting',
                'cover_image_selection': 'new:1',
            },
            files={
                'project_images': [
                    SimpleUploadedFile('one.jpg', b'content-one', content_type='image/jpeg'),
                    SimpleUploadedFile('two.jpg', b'content-two', content_type='image/jpeg'),
                ]
            },
        )

        self.assertTrue(form.is_valid(), form.errors)
        project = form.save(user=self.user)

        self.assertEqual(project.non_infra_name, 'Community Health Fair')
        self.assertEqual(project.non_infra_category, self.category)
        self.assertEqual(project.proponent, 'Municipal Health Office')
        self.assertEqual(project.beneficiaries, 250)
        self.assertEqual(project.address.barangay, 'bagting')
        self.assertEqual(project.address.municipality, 'Gabaldon')
        self.assertEqual(project.address.province, 'Nueva Ecija')
        self.assertEqual(project.venue_name, 'Municipal Plaza')
        self.assertEqual(project.project.created_by_user, self.user)
        saved_urls = list(project.project.images.order_by('project_image_id').values_list('image_url', flat=True))
        self.assertEqual(len(saved_urls), 2)
        self.assertTrue(all(url.startswith('/media/') for url in saved_urls))
        self.assertEqual(
            project.project.images.get(is_cover=True).image_url,
            saved_urls[1],
        )

    def test_form_rejects_end_time_before_start_time(self):
        form = NonInfrastructureProjectForm(data={
            'non_infra_name': 'Community Program',
            'status': 'planned',
            'description': 'Program description.',
            'non_infra_category': str(self.category.non_infrastructure_category_id),
            'proponent': 'Mayor Office',
            'beneficiaries': '100',
            'event_date': '2026-08-20',
            'start_time': '13:00',
            'end_time': '12:00',
            'venue_name': 'Municipal Hall',
            'barangay': 'bagting',
        })

        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors['end_time'],
            ['End time must be later than the start time.'],
        )

    def test_form_rejects_end_time_equal_to_start_time(self):
        form = NonInfrastructureProjectForm(data={
            'non_infra_name': 'Community Program',
            'status': 'planned',
            'description': 'Program description.',
            'non_infra_category': str(self.category.non_infrastructure_category_id),
            'proponent': 'Mayor Office',
            'beneficiaries': '100',
            'event_date': '2026-08-20',
            'start_time': '13:00',
            'end_time': '13:00',
            'venue_name': 'Municipal Hall',
            'barangay': 'bagting',
        })

        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors['end_time'],
            ['End time must be later than the start time.'],
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
        old_image = Project_Image.objects.create(
            project=proj,
            image_url='https://example.com/old.jpg',
            is_cover=True,
        )

        form = NonInfrastructureProjectForm(
            instance=existing,
            data={
                'non_infra_name': 'Updated Community Fair',
                'status': 'planned',
                'description': 'Updated description.',
                'non_infra_category': str(self.category.non_infrastructure_category_id),
                'proponent': 'Barangay Nutrition Council',
                'beneficiaries': '180',
                'event_date': '2026-09-15',
                'start_time': '09:00',
                'end_time': '13:00',
                'venue_name': 'New Event Grounds',
                'street': 'Main Avenue',
                'barangay': 'bagting',
                'cover_image_selection': f'existing:{old_image.pk}',
            },
            files={
                'project_images': [
                    SimpleUploadedFile('new-one.jpg', b'content-one', content_type='image/jpeg'),
                    SimpleUploadedFile('new-two.jpg', b'content-two', content_type='image/jpeg'),
                ]
            },
        )

        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save(user=self.user, instance=existing)

        self.assertEqual(updated.non_infra_name, 'Updated Community Fair')
        self.assertEqual(updated.proponent, 'Barangay Nutrition Council')
        self.assertEqual(updated.beneficiaries, 180)
        self.assertEqual(updated.event_date.isoformat(), '2026-09-15')
        self.assertEqual(updated.venue_name, 'New Event Grounds')
        self.assertEqual(updated.address.barangay, 'bagting')
        self.assertEqual(updated.project.images.count(), 3)
        self.assertEqual(
            updated.project.images.get(is_cover=True),
            old_image,
        )

    def test_form_seeds_missing_categories_when_database_is_empty(self):
        NonInfrastructureCategory.objects.all().delete()

        form = NonInfrastructureProjectForm()

        self.assertTrue(form.fields['non_infra_category'].queryset.exists())
        self.assertIn('Social Services', list(form.fields['non_infra_category'].queryset.values_list('type_name', flat=True)))

    def test_compatibility_model_maps_redesigned_fields_for_ui(self):
        project = Project.objects.create(project_type='non_infrastructure', created_by_user=self.user, updated_by_user=self.user)
        address = Address.objects.create(barangay='Bagting', municipality='Gabaldon', province='Nueva Ecija')
        normalized = Non_Infrastructure_Project.objects.create(
            project=project,
            non_infra_name='Community Health Fair',
            non_infra_category=self.category,
            description='Health fair description',
            address=address,
        )
        Project_Image.objects.create(
            project=project,
            image_url='https://example.com/one.jpg',
            is_cover=True,
        )
        Project_Image.objects.create(project=project, image_url='https://example.com/two.jpg')

        compat = SystemNonInfrastructureProject.objects.filter(non_infra_id=normalized.non_infra_id).first()

        self.assertIsNotNone(compat)
        self.assertEqual(compat.title, 'Community Health Fair')
        self.assertEqual(compat.location, 'Bagting')
        self.assertEqual(compat.category, 'Health Care')
        self.assertEqual(compat.get_category_display(), 'Health Care')
        self.assertEqual(len(compat.images), 2)
        self.assertEqual(compat.cover_image_url, 'https://example.com/one.jpg')
