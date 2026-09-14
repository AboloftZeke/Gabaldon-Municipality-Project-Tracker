from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.system.models import Project_Inspection, UserFlag


class InfrastructureInspectionHistoryTests(TestCase):
    def setUp(self):
        from apps.infrastructure.tests import InfrastructureProjectFormTests

        fixture = InfrastructureProjectFormTests()
        fixture.setUp()
        self.staff = fixture.user
        self.staff.is_staff = True
        self.staff.save(update_fields=['is_staff'])
        UserFlag.objects.create(
            user=self.staff,
            department='engineer',
            role='staff',
        )
        self.infrastructure = fixture.create_project()

        self.head = get_user_model().objects.create_user(
            'engineering-head',
            is_staff=True,
        )
        UserFlag.objects.create(
            user=self.head,
            department='engineer',
            role='head',
        )
        self.mayor_head = get_user_model().objects.create_user(
            'mayor-head',
            is_staff=True,
        )
        UserFlag.objects.create(
            user=self.mayor_head,
            department='mayor',
            role='head',
        )
        self.admin = get_user_model().objects.create_superuser('admin')

    @property
    def create_url(self):
        return reverse(
            'engineering_projects:inspection_create',
            args=[self.infrastructure.pk],
        )

    @property
    def detail_url(self):
        return reverse(
            'engineering_projects:project_detail',
            args=[self.infrastructure.pk],
        )

    def add_inspection(self, inspection_date, completion, findings):
        return self.client.post(self.create_url, {
            'inspection_date': inspection_date,
            'completion_percentage': completion,
            'findings': findings,
            'remarks': f'Remarks for {findings}',
        })

    def test_staff_adds_multiple_inspections_without_overwriting_history(self):
        self.client.force_login(self.staff)

        first_response = self.add_inspection(
            '2026-06-01',
            '35.00',
            'Foundation inspected',
        )
        second_response = self.add_inspection(
            '2026-06-15',
            '48.50',
            'Structural work inspected',
        )

        self.assertRedirects(first_response, self.detail_url)
        self.assertRedirects(second_response, self.detail_url)
        inspections = list(
            self.infrastructure.project.inspections.order_by(
                'inspection_date',
            )
        )
        self.assertEqual(len(inspections), 2)
        self.assertEqual(inspections[0].findings, 'Foundation inspected')
        self.assertEqual(
            inspections[0].completion_percentage,
            Decimal('35.00'),
        )
        self.assertEqual(
            inspections[1].completion_percentage,
            Decimal('48.50'),
        )
        self.assertEqual(inspections[0].inspected_by_user, self.staff)
        self.assertEqual(inspections[1].inspected_by_user, self.staff)
        detail = self.client.get(self.detail_url)
        self.assertContains(detail, 'Add Inspection')
        self.assertContains(detail, 'Edit Inspection', count=2)

    def test_history_is_newest_first_and_visible_to_engineering_head(self):
        Project_Inspection.objects.create(
            project=self.infrastructure.project,
            inspection_date='2026-05-01',
            inspected_by_user=self.staff,
            completion_percentage=Decimal('20.00'),
            findings='Older inspection',
            remarks='Older remarks',
        )
        newest = Project_Inspection.objects.create(
            project=self.infrastructure.project,
            inspection_date='2026-06-01',
            inspected_by_user=self.staff,
            completion_percentage=Decimal('40.00'),
            findings='Newest inspection',
            remarks='Newest remarks',
        )
        self.client.force_login(self.head)

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['inspection_history'])[0], newest)
        self.assertContains(response, 'Inspection History')
        self.assertContains(response, 'engineer1')
        self.assertContains(response, '40.00%')
        self.assertContains(response, 'Newest inspection')
        self.assertContains(response, 'Newest remarks')
        self.assertNotContains(response, 'Add Inspection')
        self.assertNotContains(response, 'Edit Inspection')

    def test_staff_can_edit_one_inspection_without_changing_another(self):
        first = Project_Inspection.objects.create(
            project=self.infrastructure.project,
            inspection_date='2026-05-01',
            inspected_by_user=self.staff,
            completion_percentage=Decimal('20.00'),
            findings='First record',
        )
        second = Project_Inspection.objects.create(
            project=self.infrastructure.project,
            inspection_date='2026-06-01',
            inspected_by_user=self.staff,
            completion_percentage=Decimal('40.00'),
            findings='Second record',
        )
        self.client.force_login(self.staff)
        update_url = reverse(
            'engineering_projects:inspection_update',
            args=[self.infrastructure.pk, second.pk],
        )

        response = self.client.post(update_url, {
            'inspection_date': '2026-06-02',
            'completion_percentage': '45.00',
            'findings': 'Second record updated',
            'remarks': 'Updated remarks',
        })

        self.assertRedirects(response, self.detail_url)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.findings, 'First record')
        self.assertEqual(first.completion_percentage, Decimal('20.00'))
        self.assertEqual(second.findings, 'Second record updated')
        self.assertEqual(second.completion_percentage, Decimal('45.00'))

    def test_non_staff_roles_cannot_add_or_edit_inspections(self):
        inspection = Project_Inspection.objects.create(
            project=self.infrastructure.project,
            inspection_date='2026-06-01',
            inspected_by_user=self.staff,
            completion_percentage=Decimal('40.00'),
        )
        update_url = reverse(
            'engineering_projects:inspection_update',
            args=[self.infrastructure.pk, inspection.pk],
        )
        inspection.refresh_from_db()
        original = (
            inspection.inspection_date,
            inspection.completion_percentage,
        )

        for user in [self.head, self.mayor_head, self.admin]:
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.create_url).status_code, 403)
                self.assertEqual(self.add_inspection(
                    '2026-07-01',
                    '60.00',
                    'Unauthorized inspection',
                ).status_code, 403)
                self.assertEqual(self.client.post(update_url, {
                    'inspection_date': '2026-07-01',
                    'completion_percentage': '60.00',
                    'findings': 'Unauthorized update',
                    'remarks': '',
                }).status_code, 403)

        self.assertEqual(
            self.infrastructure.project.inspections.count(),
            1,
        )
        inspection.refresh_from_db()
        self.assertEqual(
            (inspection.inspection_date, inspection.completion_percentage),
            original,
        )
