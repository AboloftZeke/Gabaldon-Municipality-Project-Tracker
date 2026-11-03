from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.infrastructure import test_inspections as fixtures
from apps.infrastructure.forms import InfrastructureInspectionForm
from apps.system.models import (
    NonInfrastructureProject,
    Project,
    ProjectInspection,
    UserRole,
)


class ProjectInspectionCompletionTests(TestCase):
    def setUp(self):
        fixtures.InfrastructureInspectionHistoryTests.setUp(self)
        self.infrastructure.status = 'ongoing'
        self.infrastructure.save(update_fields=['status'])
        self.today = timezone.localdate()
        self.detail_url = reverse(
            'engineering_projects:project_detail',
            args=[self.infrastructure.pk],
        )
        self.confirm_url = reverse(
            'engineering_projects:completion_confirmation',
            args=[self.infrastructure.pk],
        )

    def record(self, days_ago, completion, **fields):
        return ProjectInspection.objects.create(
            project=self.infrastructure.project,
            inspection_date=self.today - timedelta(days=days_ago),
            completion_percentage=Decimal(str(completion)),
            **fields,
        )

    def project_completion(self):
        project = Project.objects.get(pk=self.infrastructure.project_id)
        return project.completion_percentage

    def test_create_and_update_overwrite_cumulative_completion_without_adding(self):
        inspection = self.record(3, '20.00')
        self.assertEqual(
            self.project_completion(),
            Decimal('20.00'),
        )

        inspection.completion_percentage = Decimal('45.00')
        inspection.save()
        self.assertEqual(
            self.project_completion(),
            Decimal('45.00'),
        )

        self.record(2, '70.00')
        self.record(1, '60.00')
        self.assertEqual(
            self.project_completion(),
            Decimal('70.00'),
        )

    def test_completion_percentage_is_limited_to_zero_through_100(self):
        for value in ('-0.01', '100.01'):
            with self.subTest(value=value):
                form = InfrastructureInspectionForm(
                    data={
                        'inspection_date': self.today.isoformat(),
                        'completion_percentage': value,
                    },
                    project=self.infrastructure.project,
                )
                self.assertFalse(form.is_valid())
                self.assertIn('completion_percentage', form.errors)
                with self.assertRaises(ValidationError):
                    self.record(1, value)

    def test_historical_edit_delete_and_unrelated_edits_never_lower_completion(self):
        historical = self.record(4, '80.00', findings='Initial')
        self.record(3, '75.00')

        historical.completion_percentage = Decimal('40.00')
        historical.findings = 'Updated historical note'
        historical.save()
        historical.delete()

        self.assertEqual(
            self.project_completion(),
            Decimal('80.00'),
        )

        self.infrastructure.title = 'Updated title'
        self.infrastructure.save()
        self.infrastructure.refresh_from_db()
        base_project = Project.objects.get(pk=self.infrastructure.project_id)
        base_project.completion_percentage = Decimal('20.00')
        base_project.save(update_fields=['completion_percentage'])
        self.assertEqual(
            self.project_completion(),
            Decimal('80.00'),
        )
        self.assertIsNone(self.infrastructure.physical_progress_percentage)

    def test_existing_inspection_history_seeds_project_completion_with_its_maximum(self):
        older = ProjectInspection(
            project=self.infrastructure.project,
            inspection_date=self.today - timedelta(days=3),
            completion_percentage=Decimal('85.00'),
        )
        newer = ProjectInspection(
            project=self.infrastructure.project,
            inspection_date=self.today - timedelta(days=2),
            completion_percentage=Decimal('60.00'),
        )
        ProjectInspection.objects.bulk_create([older, newer])

        older.completion_percentage = Decimal('40.00')
        older.save()

        self.assertEqual(self.project_completion(), Decimal('85.00'))

    def test_reaching_100_shows_head_only_confirmation_and_yes_completes_project(self):
        self.record(1, '100.00')
        self.infrastructure.refresh_from_db()
        self.assertEqual(self.infrastructure.status, 'ongoing')
        self.assertEqual(
            Project.objects.get(
                pk=self.infrastructure.project_id,
            ).completion_confirmation_status,
            Project.CompletionConfirmationStatus.PENDING,
        )
        self.assertIsNone(self.infrastructure.physical_progress_percentage)

        self.client.force_login(self.head)
        detail = self.client.get(self.detail_url)
        self.assertContains(detail, '100% physical completion')
        self.assertContains(detail, 'Yes, mark as Completed')
        self.assertContains(detail, 'No, not yet')

        response = self.client.post(self.confirm_url, {'decision': 'yes'})

        self.assertRedirects(response, self.detail_url)
        self.infrastructure.refresh_from_db()
        self.assertEqual(self.infrastructure.status, 'completed')
        self.assertEqual(
            Project.objects.get(
                pk=self.infrastructure.project_id,
            ).completion_confirmation_status,
            '',
        )
        self.assertNotContains(self.client.get(self.detail_url), 'Confirm Project Completion')

    def test_declining_keeps_100_and_existing_status_without_repeating_prompt(self):
        self.record(1, '100.00')
        self.client.force_login(self.head)

        response = self.client.post(self.confirm_url, {'decision': 'no'})

        self.assertRedirects(response, self.detail_url)
        self.infrastructure.refresh_from_db()
        self.assertEqual(self.infrastructure.status, 'ongoing')
        self.assertEqual(
            self.project_completion(),
            Decimal('100.00'),
        )
        self.assertEqual(
            Project.objects.get(
                pk=self.infrastructure.project_id,
            ).completion_confirmation_status,
            Project.CompletionConfirmationStatus.DECLINED,
        )
        self.record(0, '100.00')
        self.assertNotContains(self.client.get(self.detail_url), 'Confirm Project Completion')

    def test_unauthorized_user_cannot_confirm_completion(self):
        self.record(1, '100.00')
        self.client.force_login(self.staff)

        response = self.client.post(self.confirm_url, {'decision': 'yes'})

        self.assertEqual(response.status_code, 403)
        self.infrastructure.refresh_from_db()
        self.assertEqual(self.infrastructure.status, 'ongoing')

    def test_already_completed_project_does_not_create_confirmation_prompt(self):
        self.infrastructure.status = 'completed'
        self.infrastructure.save(update_fields=['status'])
        self.record(1, '100.00')

        self.client.force_login(self.head)
        response = self.client.get(self.detail_url)

        self.assertNotContains(response, 'Confirm Project Completion')
        self.assertEqual(
            Project.objects.get(
                pk=self.infrastructure.project_id,
            ).completion_confirmation_status,
            '',
        )

    def test_non_infrastructure_inspections_share_completion_and_confirmation_rules(self):
        staff = get_user_model().objects.create_user('noninfra-mayor-staff')
        head = get_user_model().objects.create_user('noninfra-mayor-head')
        UserRole.objects.create(user=staff, department='mayor', role='staff')
        UserRole.objects.create(user=head, department='mayor', role='head')
        base_project = Project.objects.create(project_type='non_infrastructure')
        project = NonInfrastructureProject.objects.create(
            project=base_project,
            title='Community Program',
            status='ongoing',
            implementation_start_date=self.today - timedelta(days=10),
            implementation_end_date=self.today + timedelta(days=10),
        )
        with self.assertRaisesMessage(
            ValidationError,
            'Inspection date cannot be earlier than the project start date.',
        ):
            ProjectInspection.objects.create(
                project=base_project,
                inspection_date=self.today - timedelta(days=11),
                completion_percentage=Decimal('20.00'),
            )
        ProjectInspection.objects.create(
            project=base_project,
            inspection_date=self.today - timedelta(days=2),
            completion_percentage=Decimal('55.00'),
            inspected_by_user=staff,
        )
        ProjectInspection.objects.create(
            project=base_project,
            inspection_date=self.today - timedelta(days=1),
            completion_percentage=Decimal('100.00'),
            inspected_by_user=staff,
        )
        project.refresh_from_db()
        base_project.refresh_from_db()
        self.assertEqual(
            project.project.completion_percentage,
            Decimal('100.00'),
        )
        self.assertEqual(
            base_project.completion_confirmation_status,
            Project.CompletionConfirmationStatus.PENDING,
        )

        detail_url = reverse(
            'mayor_projects:non_infrastructure_project_detail',
            args=[project.pk],
        )
        confirm_url = reverse(
            'mayor_projects:completion_confirmation',
            args=[project.pk],
        )
        self.client.force_login(head)
        self.assertContains(self.client.get(detail_url), '100% physical completion')
        self.assertRedirects(
            self.client.post(confirm_url, {'decision': 'yes'}),
            detail_url,
        )
        project.refresh_from_db()
        self.assertEqual(project.status, 'completed')
