from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.infrastructure.forms import InfrastructureProjectForm
from apps.system.models import (
    Contractor,
    FundSource,
    ImplementingOffice,
    InfrastructureCategory,
    Project_Image,
)


class InfrastructureProjectFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='engineer1',
            email='engineer1@example.com',
            password='Testpass123!',
        )
        self.category = InfrastructureCategory.objects.create(
            category_code='roads_test',
            category_name='Roads Test',
        )
        self.office = ImplementingOffice.objects.create(
            office_name='Engineering Office',
        )
        self.contractor = Contractor.objects.create(
            contractor_name='Sample Contractor',
        )
        self.fund_source = FundSource.objects.create(
            fund_source_code='local_test',
            fund_source_name='Local Test Funds',
        )

    def valid_data(self, **overrides):
        data = {
            'title': 'Road Improvement Project',
            'description': 'Paving and drainage works along the main road.',
            'category': str(self.category.infrastructure_category_id),
            'implementing_office': str(self.office.office_id),
            'contractor': str(self.contractor.contractor_id),
            'procurement_method': 'competitive_bidding',
            'award_status': 'awarded',
            'street': 'Main Street',
            'barangay': 'Bagting',
            'latitude': '15.1234567',
            'longitude': '120.9876543',
            'planned_start_date': '2026-01-01',
            'planned_end_date': '2026-12-31',
            'cost_progress_percentage': '25.00',
            'physical_progress_percentage': '40.00',
            'abc_amount': '1500000.00',
            'contract_price': '1400000.00',
            'fund_source': str(self.fund_source.fund_source_id),
            'actual_expenditure': '500000.00',
            'duration_days': '365',
        }
        data.update(overrides)
        return data

    def create_project(self, **overrides):
        form = InfrastructureProjectForm(data=self.valid_data(**overrides))
        self.assertTrue(form.is_valid(), form.errors)
        return form.save(user=self.user)

    def test_form_uses_normalized_dropdowns_and_fixed_location(self):
        form = InfrastructureProjectForm()

        self.assertIsInstance(form.fields['category'], forms.ModelChoiceField)
        self.assertIsInstance(
            form.fields['contractor'],
            forms.ModelChoiceField,
        )
        self.assertIsInstance(
            form.fields['implementing_office'],
            forms.ModelChoiceField,
        )
        self.assertIsInstance(
            form.fields['fund_source'],
            forms.ModelChoiceField,
        )
        self.assertEqual(form.fields['municipality'].initial, 'Gabaldon')
        self.assertEqual(form.fields['province'].initial, 'Nueva Ecija')

    def test_save_persists_normalized_relationships_and_financials(self):
        infra = self.create_project()

        self.assertEqual(
            infra.category_id,
            self.category.infrastructure_category_id,
        )
        self.assertEqual(infra.contractor_id, self.contractor.contractor_id)
        self.assertEqual(
            infra.implementing_office_id,
            self.office.office_id,
        )
        self.assertEqual(infra.address.barangay, 'Bagting')
        self.assertEqual(infra.address.municipality, 'Gabaldon')
        self.assertEqual(float(infra.address.latitude), 15.1234567)

        financial = infra.financial_records.get()
        self.assertEqual(
            financial.fund_source_id,
            self.fund_source.fund_source_id,
        )
        self.assertEqual(
            financial.approved_budget,
            Decimal('1500000.00'),
        )
        self.assertEqual(financial.bid_amount, Decimal('1400000.00'))
        self.assertEqual(
            financial.actual_expenditure,
            Decimal('500000.00'),
        )

    def test_edit_form_preloads_normalized_relationships(self):
        infra = self.create_project()

        form = InfrastructureProjectForm(instance=infra)

        self.assertEqual(form.initial['category'], infra.category_id)
        self.assertEqual(form.initial['contractor'], infra.contractor_id)
        self.assertEqual(
            form.initial['implementing_office'],
            infra.implementing_office_id,
        )
        self.assertEqual(
            form.initial['fund_source'],
            self.fund_source.fund_source_id,
        )

    def test_edit_can_clear_optional_address_schedule_and_financial_values(self):
        infra = self.create_project(
            posting_date='2026-01-02',
            actual_start_date='2026-01-10',
        )

        edit_form = InfrastructureProjectForm(
            data=self.valid_data(
                street='',
                barangay='',
                latitude='',
                longitude='',
                posting_date='',
                actual_start_date='',
                duration_days='',
                abc_amount='',
                contract_price='',
                fund_source='',
                actual_expenditure='',
            ),
            instance=infra,
        )
        self.assertTrue(edit_form.is_valid(), edit_form.errors)
        edit_form.save(user=self.user, instance=infra)

        infra.refresh_from_db()
        infra.address.refresh_from_db()
        financial = infra.financial_records.get()
        schedule = infra.schedules.get()

        self.assertEqual(infra.address.street, '')
        self.assertEqual(infra.address.barangay, '')
        self.assertIsNone(infra.address.latitude)
        self.assertIsNone(infra.address.longitude)
        self.assertIsNone(schedule.posting_date)
        self.assertIsNone(schedule.actual_start_date)
        self.assertIsNone(schedule.duration_days)
        self.assertIsNone(financial.approved_budget)
        self.assertIsNone(financial.bid_amount)
        self.assertIsNone(financial.fund_source)
        self.assertEqual(financial.actual_expenditure, Decimal('0'))

    def test_validation_rejects_invalid_ranges_and_date_order(self):
        form = InfrastructureProjectForm(
            data=self.valid_data(
                physical_progress_percentage='101',
                cost_progress_percentage='-1',
                inspection_completion_percentage='101',
                planned_start_date='2026-02-01',
                planned_end_date='2026-01-01',
                posting_date='2026-03-01',
                bidding_date='2026-02-01',
                actual_start_date='2026-04-01',
                actual_completion_date='2026-03-01',
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn('physical_progress_percentage', form.errors)
        self.assertIn('cost_progress_percentage', form.errors)
        self.assertIn('inspection_completion_percentage', form.errors)
        self.assertIn('planned_end_date', form.errors)
        self.assertIn('bidding_date', form.errors)
        self.assertIn('actual_completion_date', form.errors)

    def test_inspection_details_require_a_date(self):
        form = InfrastructureProjectForm(
            data=self.valid_data(
                inspection_findings='Work is on schedule.',
                inspection_date='',
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn('inspection_date', form.errors)

    def test_edit_updates_latest_inspection_without_creating_duplicate(self):
        infra = self.create_project(
            inspection_date='2026-06-01',
            inspection_completion_percentage='40',
            inspection_findings='Initial findings',
        )
        self.assertEqual(infra.project.inspections.count(), 1)

        edit_form = InfrastructureProjectForm(
            data=self.valid_data(
                inspection_date='2026-06-02',
                inspection_completion_percentage='50',
                inspection_findings='Updated findings',
            ),
            instance=infra,
        )
        self.assertTrue(edit_form.is_valid(), edit_form.errors)
        edit_form.save(user=self.user, instance=infra)

        self.assertEqual(infra.project.inspections.count(), 1)
        inspection = infra.project.inspections.get()
        self.assertEqual(inspection.findings, 'Updated findings')
        self.assertEqual(
            inspection.completion_percentage,
            Decimal('50'),
        )

    def test_image_edit_deletes_selected_image_and_changes_cover(self):
        infra = self.create_project()
        first = Project_Image.objects.create(
            project=infra.project,
            image_url='https://example.com/first.jpg',
            is_cover=True,
        )
        second = Project_Image.objects.create(
            project=infra.project,
            image_url='https://example.com/second.jpg',
        )

        edit_form = InfrastructureProjectForm(
            data=self.valid_data(
                images_to_delete=str(first.pk),
                cover_image_selection=f'existing:{second.pk}',
            ),
            instance=infra,
        )
        self.assertTrue(edit_form.is_valid(), edit_form.errors)
        edit_form.save(user=self.user, instance=infra)

        self.assertFalse(
            infra.project.images.filter(pk=first.pk).exists()
        )
        second.refresh_from_db()
        self.assertTrue(second.is_cover)
        self.assertEqual(infra.project.images.count(), 1)

    def test_other_category_requires_a_custom_name(self):
        other, _ = InfrastructureCategory.objects.get_or_create(
            category_code='other',
            defaults={'category_name': 'Other'},
        )
        form = InfrastructureProjectForm(
            data=self.valid_data(
                category=str(other.infrastructure_category_id),
                other_category='',
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn('other_category', form.errors)
