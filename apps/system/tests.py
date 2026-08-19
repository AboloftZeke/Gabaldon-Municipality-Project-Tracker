from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from .forms import CustomUserCreationForm
from .models import (
    Address,
    Contractor,
    Financial,
    FundSource,
    ImplementingOffice,
    InfrastructureCategory,
    Infrastructure_Project,
    Non_Infrastructure_Project,
    Project,
    Project_Image,
    UserProfile,
)


class PublicDashboardInfrastructureDataSourceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='infrastructure-dashboard-author',
            password='password123',
        )
        base_project = Project.objects.create(
            project_type='infrastructure',
            created_by_user=self.user,
            updated_by_user=self.user,
        )
        category = InfrastructureCategory.objects.create(
            category_code='road-test',
            category_name='Road Test',
        )
        address = Address.objects.create(
            barangay='Bagting',
            municipality='Gabaldon',
            province='Nueva Ecija',
        )
        contractor = Contractor.objects.create(
            contractor_name='Public Works Contractor',
        )
        office = ImplementingOffice.objects.create(
            office_name='Municipal Engineering Office',
        )
        fund_source = FundSource.objects.create(
            fund_source_code='local-test',
            fund_source_name='Local Development Fund',
        )
        self.infrastructure = Infrastructure_Project.objects.create(
            project=base_project,
            infrastructure_title='Normalized Road Project',
            infrastructure_description='Connected through normalized data.',
            category=category,
            address=address,
            contractor=contractor,
            implementing_office=office,
            procurement_method='competitive_bidding',
            award_status='awarded',
        )
        Financial.objects.create(
            infrastructure=self.infrastructure,
            fund_source=fund_source,
            approved_budget=2500000,
            bid_amount=2400000,
        )

    def test_public_dashboard_reads_normalized_infrastructure_relations(self):
        response = self.client.get(reverse('public_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['infra_total'], 1)
        self.assertEqual(response.context['total_budget'], 2500000)

        row = next(
            row for row in response.context['project_rows']
            if row['category'] == 'infra'
        )
        self.assertEqual(row['record_id'], f'infra-{self.infrastructure.pk}')
        self.assertEqual(row['title'], 'Normalized Road Project')
        self.assertEqual(row['category_label'], 'Road Test')
        self.assertEqual(row['location'], 'Bagting')
        self.assertEqual(row['office'], 'Municipal Engineering Office')
        self.assertEqual(row['contractor'], 'Public Works Contractor')
        self.assertEqual(row['source_of_fund'], 'Local Development Fund')


class PublicDashboardNonInfrastructureStatusTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='dashboard-author',
            password='password123',
        )

        for name, status in (
            ('Planned Program', 'planned'),
            ('Ongoing Program', 'ongoing'),
            ('Completed Program', 'completed'),
        ):
            project = Project.objects.create(
                project_type='non_infrastructure',
                created_by_user=self.user,
                updated_by_user=self.user,
            )
            noninfra = Non_Infrastructure_Project.objects.create(
                project=project,
                non_infra_name=name,
                status=status,
            )

            if status == 'ongoing':
                Project_Image.objects.create(
                    project=noninfra.project,
                    image_url='/media/projects/ongoing-cover.jpg',
                    is_cover=True,
                )
                Project_Image.objects.create(
                    project=noninfra.project,
                    image_url='/media/projects/ongoing-other.jpg',
                )

    def test_public_dashboard_uses_saved_non_infrastructure_statuses(self):
        response = self.client.get(reverse('public_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['noninfra_total'], 3)
        self.assertEqual(response.context['planned_projects'], 1)
        self.assertEqual(response.context['ongoing_projects'], 1)
        self.assertEqual(response.context['completed_projects'], 1)

        statuses = {
            row['title']: (row['status_key'], row['status_label'])
            for row in response.context['project_rows']
            if row['category'] == 'noninfra'
        }
        self.assertEqual(statuses['Planned Program'], ('planned', 'Planned'))
        self.assertEqual(statuses['Ongoing Program'], ('ongoing', 'Ongoing'))
        self.assertEqual(statuses['Completed Program'], ('completed', 'Completed'))

        ongoing_row = next(
            row
            for row in response.context['project_rows']
            if row['title'] == 'Ongoing Program'
        )
        self.assertEqual(
            ongoing_row['cover_image_url'],
            '/media/projects/ongoing-cover.jpg',
        )
        self.assertContains(response, '/media/projects/ongoing-cover.jpg')

        noninfra_rows = [
            row
            for row in response.context['project_rows']
            if row['category'] == 'noninfra'
        ]
        self.assertTrue(
            all(row['location_key'] == '' for row in noninfra_rows)
        )
        self.assertTrue(
            all(row['location'] == '' for row in noninfra_rows)
        )
        for row in noninfra_rows:
            project_pk = int(row['record_id'].removeprefix('noninfra-'))
            self.assertEqual(
                row['detail_url'],
                reverse(
                    'public_non_infrastructure_project_detail',
                    args=[project_pk],
                ),
            )

        mayor_detail_url = reverse(
            'mayor_projects:non_infrastructure_project_detail',
            args=[Non_Infrastructure_Project.objects.get(status='ongoing').pk],
        )
        self.assertNotContains(response, mayor_detail_url)
        self.assertContains(response, 'data-project-modal-trigger', count=3)

    def test_public_non_infrastructure_detail_is_available_without_login(self):
        project = Non_Infrastructure_Project.objects.get(status='ongoing')
        detail_url = reverse(
            'public_non_infrastructure_project_detail',
            args=[project.pk],
        )

        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            'Dashboard/non_infrastructure_detail.html',
        )
        self.assertContains(response, project.non_infra_name)
        self.assertContains(response, '/media/projects/ongoing-cover.jpg')
        self.assertNotContains(response, '<h3>Location</h3>', html=True)
        self.assertNotContains(response, 'Edit Project')
        self.assertNotContains(response, 'Delete Project')


class UserDeactivateViewTests(TestCase):
    def test_current_user_deactivation_shows_warning(self):
        user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='password',
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )

        self.client.force_login(user)
        response = self.client.get(reverse('user_deactivate', args=[user.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_deactivate'])
        self.assertEqual(response.context['warning_message'], 'You cannot deactivate your own account.')


class SuperuserProfileTests(TestCase):
    def test_created_superuser_gets_admin_profile(self):
        user = User.objects.create_superuser(
            username='root',
            email='root@example.com',
            password='password123',
        )
        # Runtime no longer creates archive-backed profiles; department is inferred.
        self.assertTrue(user.is_superuser)
        self.assertEqual(user.profile.department, 'admin')


class UserCreationFormTests(TestCase):
    def test_user_creation_form_defaults_to_no_department(self):
        form = CustomUserCreationForm()

        self.assertEqual(form.fields['role'].initial, '')

    def test_user_creation_form_rejects_blank_department(self):
        form = CustomUserCreationForm(
            data={
                'username': 'tempuser2',
                'email': 'tempuser2@example.com',
                'first_name': 'Temp',
                'last_name': 'User',
                'role': '',
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn('role', form.errors)

    def test_user_creation_form_does_not_require_manual_password(self):
        form = CustomUserCreationForm(
            data={
                'username': 'tempuser',
                'email': 'tempuser@example.com',
                'first_name': 'Temp',
                'last_name': 'User',
                'role': 'engineering',
            }
        )

        self.assertTrue(form.is_valid())

        user = form.save(commit=True, temporary_password='TempPass123!')

        self.assertTrue(user.check_password('TempPass123!'))
        self.assertEqual(user.profile.department, 'engineer')

    def test_mayor_user_is_staff_and_keeps_mayor_department(self):
        form = CustomUserCreationForm(
            data={
                'username': 'mayoruser2',
                'email': 'mayoruser2@example.com',
                'first_name': 'Mayor',
                'last_name': 'User',
                'role': 'mayors',
            }
        )

        self.assertTrue(form.is_valid())

        user = form.save(commit=True, temporary_password='TempPass123!')

        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.profile.department, 'mayor')


class UserCreateConfirmViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin2',
            email='admin2@example.com',
            password='password123',
        )

    def test_confirm_creation_preserves_mayor_department(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session['user_create_form_data'] = {
            'username': 'mayoruser',
            'email': 'mayoruser@example.com',
            'first_name': 'Mayor',
            'last_name': 'User',
            'role': 'mayors',
        }
        session.save()

        response = self.client.post(reverse('user_create_confirm'))

        self.assertEqual(response.status_code, 302)
        created_user = User.objects.get(username='mayoruser')
        self.assertEqual(created_user.profile.department, 'mayor')
        self.assertTrue(created_user.profile.must_change_password)

