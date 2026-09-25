from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import (
    FinancialRecord,
    InfrastructureProgressUpdate,
    NonInfrastructureCategory,
    NonInfrastructureProject,
    Project,
    ProjectInspection,
    ProjectRevision,
    UserRole,
)
from .progress import expected_progress
from apps.infrastructure.progress_history import record_progress_update


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
            UserRole.objects.create(
                user=user, department=department, role=role,
            )
            self.users[department, role] = user
        self.admin = User.objects.create_superuser('admin')

        from apps.infrastructure.tests import InfrastructureProjectFormTests
        fixture = InfrastructureProjectFormTests()
        fixture.setUp()
        self.infrastructure = fixture.create_project()
        self.infrastructure.status = 'not_yet_started'
        self.infrastructure.physical_progress_percentage = Decimal('25')
        self.infrastructure.cost_progress_percentage = Decimal('20')
        self.infrastructure.planned_start_date = date.today() - timedelta(days=5)
        self.infrastructure.planned_end_date = date.today() + timedelta(days=5)
        self.infrastructure.save()
        self.inspection = ProjectInspection.objects.create(
            project=self.infrastructure.project,
            inspection_date=date.today(),
            completion_percentage=Decimal('30'),
        )
        FinancialRecord.objects.filter(infrastructure=self.infrastructure).update(
            bid_amount=Decimal('1000'), actual_expenditure=Decimal('400'),
        )
        self.public_revision = ProjectRevision.objects.create(
            project=self.infrastructure.project,
            revision_number=1,
            status='published',
            is_current_public=True,
            snapshot={'infrastructure': {'title': 'Published version'}},
        )
        self.staff_payload = fixture.valid_data(
            title='Changed by Engineering Staff',
            status='completed',
            physical_progress_percentage='99',
            cost_progress_percentage='98',
            inspection_completion_percentage='97',
        )

        base = Project.objects.create(project_type='non_infrastructure')
        self.non_infrastructure_category = NonInfrastructureCategory.objects.create(
            type_code='operational-test', type_name='Operational Test',
        )
        self.non_infrastructure = NonInfrastructureProject.objects.create(
            project=base,
            title='Community Program',
            project_type=NonInfrastructureProject.ProjectType.PROGRAM,
            status='planned',
            category=self.non_infrastructure_category,
        )

    def infra_url(self):
        return reverse(
            'engineering_projects:project_operations',
            args=[self.infrastructure.pk],
        )

    def test_engineering_head_updates_only_operational_fields(self):
        self.client.force_login(self.users['engineer', 'head'])
        before_title = self.infrastructure.title
        before_expected = expected_progress(
            self.infrastructure.planned_start_date,
            self.infrastructure.planned_end_date,
        )
        response = self.client.post(self.infra_url(), {
            'status': 'completed',
            'physical_progress_percentage': '60',
            'cost_progress_percentage': '55',
            'inspection_completion_percentage': '70',
            'head_remarks': 'Verified against the latest field report.',
            'title': 'Crafted ordinary-field change',
            'expected_progress_percentage': '1',
        })
        self.assertEqual(response.status_code, 302)
        self.infrastructure.refresh_from_db()
        self.inspection.refresh_from_db()
        self.assertEqual(self.infrastructure.status, 'completed')
        self.assertEqual(self.infrastructure.physical_progress_percentage, Decimal('60'))
        self.assertEqual(self.infrastructure.cost_progress_percentage, Decimal('55'))
        self.assertEqual(self.inspection.completion_percentage, Decimal('70'))
        self.assertEqual(self.infrastructure.title, before_title)
        self.assertEqual(
            expected_progress(
                self.infrastructure.planned_start_date,
                self.infrastructure.planned_end_date,
            ),
            before_expected,
        )
        self.assertEqual(self.infrastructure.project.revisions.count(), 2)
        operational_revision = (
            self.infrastructure.project.revisions
            .exclude(pk=self.public_revision.pk)
            .get()
        )
        self.assertEqual(operational_revision.status, 'approved')
        self.assertEqual(
            operational_revision.previous_revision,
            self.public_revision,
        )
        self.public_revision.refresh_from_db()
        self.assertEqual(
            self.public_revision.snapshot,
            {'infrastructure': {'title': 'Published version'}},
        )
        self.assertTrue(self.public_revision.is_current_public)
        progress_update = InfrastructureProgressUpdate.objects.get()
        self.assertEqual(progress_update.infrastructure, self.infrastructure)
        self.assertEqual(progress_update.previous_official_status, 'not_yet_started')
        self.assertEqual(progress_update.new_official_status, 'completed')
        self.assertEqual(
            progress_update.previous_physical_progress,
            Decimal('25'),
        )
        self.assertEqual(
            progress_update.new_physical_progress,
            Decimal('60'),
        )
        self.assertEqual(
            progress_update.head_remarks,
            'Verified against the latest field report.',
        )
        self.assertEqual(
            progress_update.updated_by,
            self.users['engineer', 'head'],
        )
        self.assertIsNotNone(progress_update.created_at)

    def test_unchanged_status_and_progress_do_not_create_history(self):
        self.client.force_login(self.users['engineer', 'head'])

        response = self.client.post(self.infra_url(), {
            'status': 'not_yet_started',
            'physical_progress_percentage': '25',
            'cost_progress_percentage': '35',
            'inspection_completion_percentage': '45',
            'head_remarks': 'No official change.',
        })

        self.assertEqual(response.status_code, 302)
        self.assertFalse(InfrastructureProgressUpdate.objects.exists())
        self.infrastructure.refresh_from_db()
        self.inspection.refresh_from_db()
        self.assertEqual(
            self.infrastructure.physical_progress_percentage,
            Decimal('25'),
        )
        self.assertEqual(
            self.infrastructure.cost_progress_percentage,
            Decimal('35'),
        )
        self.assertEqual(
            self.inspection.completion_percentage,
            Decimal('45'),
        )

    def test_head_can_link_multiple_project_inspections_without_copying_progress(self):
        earlier_inspection = ProjectInspection.objects.create(
            project=self.infrastructure.project,
            inspection_date=date.today() - timedelta(days=2),
            inspection_type='progress',
            completion_percentage=Decimal('82'),
            inspected_by_user=self.users['engineer', 'staff'],
        )
        self.client.force_login(self.users['engineer', 'head'])

        response = self.client.post(self.infra_url(), {
            'status': 'completed',
            'physical_progress_percentage': '61',
            'cost_progress_percentage': '55',
            'inspection_completion_percentage': '70',
            'head_remarks': 'Supported by two field inspections.',
            'supporting_inspections': [
                str(self.inspection.pk), str(earlier_inspection.pk),
            ],
        })

        self.assertEqual(response.status_code, 302)
        update = InfrastructureProgressUpdate.objects.get()
        self.assertCountEqual(
            update.supporting_inspections.values_list('pk', flat=True),
            [self.inspection.pk, earlier_inspection.pk],
        )
        self.infrastructure.refresh_from_db()
        self.assertEqual(
            self.infrastructure.physical_progress_percentage,
            Decimal('61'),
        )
        self.assertNotEqual(
            self.infrastructure.physical_progress_percentage,
            earlier_inspection.completion_percentage,
        )

    def test_operational_form_rejects_inspection_from_another_project(self):
        other_project = Project.objects.create(project_type='infrastructure')
        other_inspection = ProjectInspection.objects.create(
            project=other_project,
            inspection_date=date.today(),
            inspection_type='special',
            completion_percentage=Decimal('95'),
        )
        self.client.force_login(self.users['engineer', 'head'])

        get_response = self.client.get(self.infra_url())
        self.assertContains(get_response, 'Supporting Inspections')
        self.assertContains(get_response, '30.00% observed')
        self.assertContains(get_response, 'class="inspection-choice-card"')
        self.assertContains(
            get_response,
            'does not automatically set official physical progress',
        )
        available = get_response.context['form'].fields[
            'supporting_inspections'
        ].queryset
        self.assertIn(self.inspection, available)
        self.assertNotIn(other_inspection, available)

        response = self.client.post(self.infra_url(), {
            'status': 'completed',
            'physical_progress_percentage': '61',
            'cost_progress_percentage': '55',
            'inspection_completion_percentage': '70',
            'supporting_inspections': [str(other_inspection.pk)],
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            'Select a valid choice.',
            response.context['form'].errors['supporting_inspections'][0],
        )
        self.assertFalse(InfrastructureProgressUpdate.objects.exists())
        self.infrastructure.refresh_from_db()
        self.assertEqual(self.infrastructure.status, 'not_yet_started')
        self.assertEqual(
            self.infrastructure.physical_progress_percentage,
            Decimal('25'),
        )

        self.infrastructure.status = 'completed'
        with self.assertRaisesMessage(
            ValidationError,
            'Supporting inspections must belong to this Infrastructure project.',
        ):
            record_progress_update(
                self.infrastructure,
                self.users['engineer', 'head'],
                previous_status='not_yet_started',
                previous_physical_progress=Decimal('25'),
                supporting_inspections=[other_inspection],
            )
        self.assertFalse(InfrastructureProgressUpdate.objects.exists())

    def test_progress_history_is_read_only_for_staff_and_head(self):
        older = InfrastructureProgressUpdate.objects.create(
            infrastructure=self.infrastructure,
            previous_official_status='not_yet_started',
            new_official_status='not_yet_started',
            previous_physical_progress=Decimal('10'),
            new_physical_progress=Decimal('25'),
            head_remarks='Earlier decision',
            updated_by=self.users['engineer', 'head'],
        )
        newest = InfrastructureProgressUpdate.objects.create(
            infrastructure=self.infrastructure,
            previous_official_status='not_yet_started',
            new_official_status='completed',
            previous_physical_progress=Decimal('25'),
            new_physical_progress=Decimal('100'),
            head_remarks='Final decision',
            updated_by=self.users['engineer', 'head'],
        )
        newest.supporting_inspections.add(self.inspection)
        detail_url = reverse(
            'engineering_projects:project_detail',
            args=[self.infrastructure.pk],
        )

        for user in [
            self.users['engineer', 'staff'],
            self.users['engineer', 'head'],
        ]:
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(detail_url)
                history = list(response.context['progress_update_history'])
                self.assertEqual(history, [newest, older])
                self.assertContains(response, 'Progress Update History')
                self.assertContains(response, 'Earlier decision')
                self.assertContains(response, 'Final decision')
                self.assertContains(response, 'Supporting Inspections')
                self.assertContains(response, '30.00% observed completion')
                self.assertContains(response, 'class="progress-timeline"')
                self.assertContains(response, 'progress-update-card')
                self.assertContains(response, '25.00%')
                self.assertContains(response, '100.00%')
                self.assertNotContains(response, 'Edit Progress Update')

    def test_operational_form_shows_derived_values_as_read_only(self):
        self.client.force_login(self.users['engineer', 'head'])
        detail = self.client.get(reverse(
            'engineering_projects:project_detail',
            args=[self.infrastructure.pk],
        ))
        self.assertContains(detail, 'Update Status &amp; Progress')
        self.assertContains(detail, self.infra_url())
        self.assertNotContains(detail, 'Edit Project')
        self.assertNotContains(detail, 'Delete Project')
        self.assertContains(detail, 'Expected / Scheduled Progress')
        self.assertContains(detail, 'Actual Physical Progress')
        self.assertContains(detail, 'Variance (Actual vs Scheduled)')
        self.assertContains(detail, 'Entered Cost Progress')
        self.assertContains(detail, 'Calculated Cost Progress')
        self.assertContains(detail, 'Observed Completion')
        self.assertContains(detail, 'Calculated reference', count=3)
        self.assertContains(detail, 'class="information-card-grid"')
        self.assertContains(detail, 'Financial &amp; Funding Information')
        self.assertContains(detail, 'Procurement &amp; Contractor Information')
        self.assertContains(detail, 'Status &amp; Progress')
        response = self.client.get(self.infra_url())
        self.assertContains(response, 'Expected / Scheduled Progress')
        self.assertContains(response, 'Variance')
        self.assertContains(response, 'Calculated Cost Progress')
        self.assertContains(response, 'Read-only')
        for field in [
            'expected_progress', 'progress_variance',
            'calculated_cost_progress', 'title',
        ]:
            self.assertNotContains(response, f'name="{field}"')
        ProjectRevision.objects.filter(
            pk=self.public_revision.pk,
        ).update(review_notes='Retained review note')
        self.client.force_login(self.users['engineer', 'staff'])
        detail = self.client.get(reverse(
            'engineering_projects:project_detail',
            args=[self.infrastructure.pk],
        ))
        self.assertNotContains(detail, self.infra_url())
        self.assertNotContains(detail, 'Update Status &amp; Progress')
        self.assertContains(detail, 'Edit Project')
        self.assertContains(detail, 'Submit Updated Version')
        self.assertContains(detail, 'Office Head notes')
        self.assertNotContains(detail, 'Administrator notes')
        self.assertNotContains(detail, 'Record Decision')
        self.assertNotContains(detail, 'Publish to Public Dashboard')

    def test_wrong_roles_are_denied_without_mutation(self):
        before = (
            self.infrastructure.status,
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
                'status': 'completed',
                'physical_progress_percentage': '100',
                'cost_progress_percentage': '100',
                'inspection_completion_percentage': '100',
            })
            self.assertIn(response.status_code, [302, 403])
            self.infrastructure.refresh_from_db()
            self.inspection.refresh_from_db()
            self.assertEqual(before, (
                self.infrastructure.status,
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
        self.assertEqual(self.infrastructure.title, 'Changed by Engineering Staff')
        self.assertEqual(self.infrastructure.status, 'not_yet_started')
        self.assertEqual(self.infrastructure.physical_progress_percentage, Decimal('25'))
        self.assertEqual(self.infrastructure.cost_progress_percentage, Decimal('20'))
        self.assertEqual(self.inspection.completion_percentage, Decimal('30'))

        self.client.force_login(self.users['mayor', 'staff'])
        response = self.client.post(reverse(
            'mayor_projects:non_infrastructure_project_update',
            args=[self.non_infrastructure.pk],
        ), {
            'title': 'Changed by Mayor Staff',
            'description': 'Ordinary details remain editable.',
            'category': self.non_infrastructure_category.pk,
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
            self.non_infrastructure.title,
            'Changed by Mayor Staff',
        )
        self.assertEqual(self.non_infrastructure.status, 'planned')

    def test_percentages_reject_out_of_range_values(self):
        self.client.force_login(self.users['engineer', 'head'])
        before = self.infrastructure.physical_progress_percentage
        for value in ['-0.01', '100.01']:
            response = self.client.post(self.infra_url(), {
                'status': 'not_yet_started',
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
        detail = self.client.get(reverse(
            'mayor_projects:non_infrastructure_project_detail',
            args=[self.non_infrastructure.pk],
        ))
        self.assertContains(detail, 'Update Project Status')
        self.assertNotContains(detail, 'Edit Project')
        self.assertNotContains(detail, 'Delete Project')
        self.assertContains(detail, 'class="information-card-grid"')
        self.assertContains(detail, 'Project Information')
        self.assertContains(detail, 'Location &amp; Venue')
        self.assertContains(detail, 'Service &amp; Beneficiary Information')
        self.assertContains(detail, 'Status &amp; Operational Information')
        self.assertEqual(self.client.post(url, {
            'status': 'completed', 'title': 'Crafted change',
        }).status_code, 302)
        self.non_infrastructure.refresh_from_db()
        self.assertEqual(self.non_infrastructure.status, 'completed')
        self.assertEqual(self.non_infrastructure.title, 'Community Program')
        self.assertEqual(self.non_infrastructure.project.revisions.count(), 0)
        self.client.force_login(self.users['mayor', 'staff'])
        detail = self.client.get(reverse(
            'mayor_projects:non_infrastructure_project_detail',
            args=[self.non_infrastructure.pk],
        ))
        self.assertNotContains(detail, 'Update Project Status')
        self.assertContains(detail, 'Edit Project')
        self.assertContains(detail, 'Delete Project')
        self.assertContains(detail, 'Submit for Public Review')
        self.assertNotContains(detail, 'Record Decision')
        self.assertNotContains(detail, 'Publish to Public Dashboard')
