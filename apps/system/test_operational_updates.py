from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import (
    Financial,
    NonInfrastructureCategory,
    Non_Infrastructure_Project,
    Project,
    Project_Inspection,
    ProjectPublicationRevision,
    UserFlag,
)
from .progress import expected_progress


class HeadOperationalUpdateTests(TestCase):
    def setUp(self):
        self.users = {}
        for department, role in [
            ('engineer', 'staff'), ('engineer', 'head'),
            ('mayor', 'staff'), ('mayor', 'head'),
        ]:
            user = User.objects.create_user(
                f'{department}-{role}', is_staff=True,
            )
            UserFlag.objects.create(
                user=user, department=department, role=role,
            )
            self.users[department, role] = user
        self.admin = User.objects.create_superuser('admin')

        from apps.infrastructure.tests import InfrastructureProjectFormTests
        fixture = InfrastructureProjectFormTests()
        fixture.setUp()
        self.infrastructure = fixture.create_project()
        self.infrastructure.award_status = 'awarded'
        self.infrastructure.physical_progress_percentage = Decimal('25')
        self.infrastructure.cost_progress_percentage = Decimal('20')
        self.infrastructure.planned_start_date = date.today() - timedelta(days=5)
        self.infrastructure.planned_end_date = date.today() + timedelta(days=5)
        self.infrastructure.save()
        self.inspection = Project_Inspection.objects.create(
            project=self.infrastructure.project,
            inspection_date=date.today(),
            completion_percentage=Decimal('30'),
        )
        Financial.objects.filter(infrastructure=self.infrastructure).update(
            bid_amount=Decimal('1000'), actual_expenditure=Decimal('400'),
        )
        self.public_revision = ProjectPublicationRevision.objects.create(
            project=self.infrastructure.project,
            revision_number=1,
            status='published',
            is_current_public_revision=True,
            snapshot_data={'infrastructure': {'title': 'Published version'}},
        )
        self.staff_payload = fixture.valid_data(
            title='Changed by Engineering Staff',
            award_status='completed',
            physical_progress_percentage='99',
            cost_progress_percentage='98',
            inspection_completion_percentage='97',
        )

        base = Project.objects.create(project_type='non_infrastructure')
        self.non_infrastructure_category = NonInfrastructureCategory.objects.create(
            type_code='operational-test', type_name='Operational Test',
        )
        self.non_infrastructure = Non_Infrastructure_Project.objects.create(
            project=base,
            non_infra_name='Community Program',
            status='planned',
            non_infra_category=self.non_infrastructure_category,
        )

    def infra_url(self):
        return reverse(
            'engineering_projects:project_operations',
            args=[self.infrastructure.pk],
        )

    def test_engineering_head_updates_only_operational_fields(self):
        self.client.force_login(self.users['engineer', 'head'])
        before_title = self.infrastructure.infrastructure_title
        before_expected = expected_progress(
            self.infrastructure.planned_start_date,
            self.infrastructure.planned_end_date,
        )
        response = self.client.post(self.infra_url(), {
            'award_status': 'completed',
            'physical_progress_percentage': '60',
            'cost_progress_percentage': '55',
            'inspection_completion_percentage': '70',
            'infrastructure_title': 'Crafted ordinary-field change',
            'expected_progress_percentage': '1',
        })
        self.assertEqual(response.status_code, 302)
        self.infrastructure.refresh_from_db()
        self.inspection.refresh_from_db()
        self.assertEqual(self.infrastructure.award_status, 'completed')
        self.assertEqual(self.infrastructure.physical_progress_percentage, Decimal('60'))
        self.assertEqual(self.infrastructure.cost_progress_percentage, Decimal('55'))
        self.assertEqual(self.inspection.completion_percentage, Decimal('70'))
        self.assertEqual(self.infrastructure.infrastructure_title, before_title)
        self.assertEqual(
            expected_progress(
                self.infrastructure.planned_start_date,
                self.infrastructure.planned_end_date,
            ),
            before_expected,
        )
        self.assertEqual(self.infrastructure.project.publication_revisions.count(), 2)
        operational_revision = (
            self.infrastructure.project.publication_revisions
            .exclude(pk=self.public_revision.pk)
            .get()
        )
        self.assertEqual(operational_revision.status, 'approved')
        self.assertEqual(
            operational_revision.supersedes_revision,
            self.public_revision,
        )
        self.public_revision.refresh_from_db()
        self.assertEqual(
            self.public_revision.snapshot_data,
            {'infrastructure': {'title': 'Published version'}},
        )
        self.assertTrue(self.public_revision.is_current_public_revision)

    def test_operational_form_shows_derived_values_as_read_only(self):
        self.client.force_login(self.users['engineer', 'head'])
        detail = self.client.get(reverse(
            'engineering_projects:project_detail',
            args=[self.infrastructure.pk],
        ))
        self.assertContains(detail, self.infra_url())
        response = self.client.get(self.infra_url())
        self.assertContains(response, 'Expected Progress:')
        self.assertContains(response, 'Variance:')
        self.assertContains(response, 'Calculated Cost Progress:')
        for field in [
            'expected_progress', 'progress_variance',
            'calculated_cost_progress', 'infrastructure_title',
        ]:
            self.assertNotContains(response, f'name="{field}"')
        self.client.force_login(self.users['engineer', 'staff'])
        detail = self.client.get(reverse(
            'engineering_projects:project_detail',
            args=[self.infrastructure.pk],
        ))
        self.assertNotContains(detail, self.infra_url())

    def test_wrong_roles_are_denied_without_mutation(self):
        before = (
            self.infrastructure.award_status,
            self.infrastructure.physical_progress_percentage,
            self.infrastructure.cost_progress_percentage,
            self.inspection.completion_percentage,
        )
        for user in [
            self.users['mayor', 'head'], self.users['engineer', 'staff'],
            self.admin, None,
        ]:
            self.client.logout()
            if user:
                self.client.force_login(user)
            response = self.client.post(self.infra_url(), {
                'award_status': 'completed',
                'physical_progress_percentage': '100',
                'cost_progress_percentage': '100',
                'inspection_completion_percentage': '100',
            })
            self.assertIn(response.status_code, [302, 403])
            self.infrastructure.refresh_from_db()
            self.inspection.refresh_from_db()
            self.assertEqual(before, (
                self.infrastructure.award_status,
                self.infrastructure.physical_progress_percentage,
                self.infrastructure.cost_progress_percentage,
                self.inspection.completion_percentage,
            ))

    def test_staff_crafted_edit_cannot_change_head_owned_fields(self):
        self.client.force_login(self.users['engineer', 'staff'])
        response = self.client.post(reverse(
            'engineering_projects:project_update',
            args=[self.infrastructure.pk],
        ), self.staff_payload)
        self.assertEqual(response.status_code, 302)
        self.infrastructure.refresh_from_db()
        self.inspection.refresh_from_db()
        self.assertEqual(self.infrastructure.infrastructure_title, 'Changed by Engineering Staff')
        self.assertEqual(self.infrastructure.award_status, 'awarded')
        self.assertEqual(self.infrastructure.physical_progress_percentage, Decimal('25'))
        self.assertEqual(self.infrastructure.cost_progress_percentage, Decimal('20'))
        self.assertEqual(self.inspection.completion_percentage, Decimal('30'))

        self.client.force_login(self.users['mayor', 'staff'])
        response = self.client.post(reverse(
            'mayor_projects:non_infrastructure_project_update',
            args=[self.non_infrastructure.pk],
        ), {
            'non_infra_name': 'Changed by Mayor Staff',
            'description': 'Ordinary details remain editable.',
            'non_infra_category': self.non_infrastructure_category.pk,
            'status': 'completed',
            'proponent': 'Municipal Office',
            'beneficiaries': '20',
            'event_date': '2026-09-01',
            'start_time': '08:00',
            'end_time': '09:00',
            'venue_name': 'Municipal Hall',
            'barangay': 'bagting',
        })
        self.assertEqual(response.status_code, 302)
        self.non_infrastructure.refresh_from_db()
        self.assertEqual(
            self.non_infrastructure.non_infra_name,
            'Changed by Mayor Staff',
        )
        self.assertEqual(self.non_infrastructure.status, 'planned')

    def test_percentages_reject_out_of_range_values(self):
        self.client.force_login(self.users['engineer', 'head'])
        before = self.infrastructure.physical_progress_percentage
        for value in ['-0.01', '100.01']:
            response = self.client.post(self.infra_url(), {
                'award_status': 'awarded',
                'physical_progress_percentage': value,
                'cost_progress_percentage': value,
                'inspection_completion_percentage': value,
            })
            self.assertEqual(response.status_code, 400)
        self.infrastructure.refresh_from_db()
        self.assertEqual(self.infrastructure.physical_progress_percentage, before)

    def test_mayor_head_alone_updates_existing_normalized_status(self):
        url = reverse(
            'mayor_projects:non_infrastructure_project_operations',
            args=[self.non_infrastructure.pk],
        )
        for user in [
            self.users['engineer', 'head'], self.users['mayor', 'staff'],
            self.admin,
        ]:
            self.client.force_login(user)
            self.assertEqual(self.client.post(url, {'status': 'completed'}).status_code, 403)
        self.client.force_login(self.users['mayor', 'head'])
        self.assertEqual(self.client.post(url, {
            'status': 'completed', 'non_infra_name': 'Crafted change',
        }).status_code, 302)
        self.non_infrastructure.refresh_from_db()
        self.assertEqual(self.non_infrastructure.status, 'completed')
        self.assertEqual(self.non_infrastructure.non_infra_name, 'Community Program')
        self.assertEqual(self.non_infrastructure.project.publication_revisions.count(), 0)
