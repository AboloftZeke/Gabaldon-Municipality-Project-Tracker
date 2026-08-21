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
            'implementing_office': self.office.office_name,
            'contractor': self.contractor.contractor_name,
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
            'fund_source': self.fund_source.fund_source_name,
            'actual_expenditure': '500000.00',
            'posting_date': '2025-10-01',
            'pre_bid_date': '2025-10-15',
            'bidding_date': '2025-11-01',
            'notice_award_date': '2025-11-15',
            'notice_to_proceed_date': '2025-12-01',
            'duration_days': '365',
        }
        data.update(overrides)
        return data

    def create_project(self, **overrides):
        form = InfrastructureProjectForm(data=self.valid_data(**overrides))
        self.assertTrue(form.is_valid(), form.errors)
        return form.save(user=self.user)

    def test_form_uses_text_inputs_for_normalized_lookups_and_fixed_location(self):
        form = InfrastructureProjectForm()

        self.assertIsInstance(form.fields['category'], forms.ModelChoiceField)
        self.assertIsInstance(form.fields['contractor'], forms.CharField)
        self.assertIsInstance(form.fields['implementing_office'], forms.CharField)
        self.assertIsInstance(form.fields['fund_source'], forms.CharField)
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
        self.assertEqual(form.initial['contractor'], self.contractor.contractor_name)
        self.assertEqual(
            form.initial['implementing_office'],
            self.office.office_name,
        )
        self.assertEqual(
            form.initial['fund_source'],
            self.fund_source.fund_source_name,
        )

    def test_create_trims_and_creates_normalized_text_lookups(self):
        infra = self.create_project(
            contractor='  New Builder Inc.  ',
            implementing_office='  Municipal Engineering Office  ',
            fund_source='  General Fund  ',
        )

        self.assertEqual(infra.contractor.contractor_name, 'New Builder Inc.')
        self.assertEqual(
            infra.implementing_office.office_name,
            'Municipal Engineering Office',
        )
        fund_source = infra.financial_records.get().fund_source
        self.assertEqual(fund_source.fund_source_name, 'General Fund')
        self.assertEqual(fund_source.fund_source_code, 'general-fund')

    def test_repeated_case_insensitive_values_reuse_lookup_rows(self):
        first = self.create_project(
            title='First Project',
            contractor='Reusable Builder',
            implementing_office='Reusable Office',
            fund_source='Reusable Fund',
        )
        second = self.create_project(
            title='Second Project',
            contractor='  reusable builder  ',
            implementing_office='REUSABLE OFFICE',
            fund_source='reusable fund',
        )

        self.assertEqual(first.contractor_id, second.contractor_id)
        self.assertEqual(
            first.implementing_office_id,
            second.implementing_office_id,
        )
        self.assertEqual(
            first.financial_records.get().fund_source_id,
            second.financial_records.get().fund_source_id,
        )
        self.assertEqual(
            Contractor.objects.filter(contractor_name__iexact='Reusable Builder').count(),
            1,
        )

    def test_edit_with_same_values_does_not_create_lookup_duplicates(self):
        infra = self.create_project(
            contractor='Edit Builder',
            implementing_office='Edit Office',
            fund_source='Edit Fund',
        )
        original_ids = (
            infra.contractor_id,
            infra.implementing_office_id,
            infra.financial_records.get().fund_source_id,
        )

        form = InfrastructureProjectForm(
            data=self.valid_data(
                contractor=' edit builder ',
                implementing_office='EDIT OFFICE',
                fund_source='edit fund',
            ),
            instance=infra,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save(user=self.user, instance=infra)
        infra.refresh_from_db()

        self.assertEqual(
            (
                infra.contractor_id,
                infra.implementing_office_id,
                infra.financial_records.get().fund_source_id,
            ),
            original_ids,
        )

    def test_fund_source_code_is_unique_when_slug_is_already_used(self):
        FundSource.objects.create(
            fund_source_code='general-fund',
            fund_source_name='Different Source',
        )

        infra = self.create_project(fund_source='General Fund')

        self.assertEqual(
            infra.financial_records.get().fund_source.fund_source_code,
            'general-fund-2',
        )

    def test_existing_blank_code_fund_source_is_reused_and_repaired(self):
        blank_source = FundSource.objects.create(
            fund_source_code='',
            fund_source_name='Legacy Test Fund',
        )

        infra = self.create_project(fund_source='  legacy test fund  ')

        blank_source.refresh_from_db()
        self.assertEqual(
            infra.financial_records.get().fund_source_id,
            blank_source.fund_source_id,
        )
        self.assertEqual(blank_source.fund_source_code, 'legacy-test-fund')

    def test_edit_can_clear_optional_schedule_and_financial_values(self):
        infra = self.create_project(
            posting_date='2026-01-02',
            pre_bid_date='2026-01-03',
            bidding_date='2026-01-04',
            notice_award_date='2026-01-05',
            notice_to_proceed_date='2026-01-06',
            actual_start_date='2026-01-10',
        )

        edit_form = InfrastructureProjectForm(
            data=self.valid_data(
                actual_start_date='',
                actual_expenditure='',
            ),
            instance=infra,
        )
        self.assertTrue(edit_form.is_valid(), edit_form.errors)
        edit_form.save(user=self.user, instance=infra)

        infra.refresh_from_db()
        financial = infra.financial_records.get()
        schedule = infra.schedules.get()

        self.assertIsNone(schedule.actual_start_date)
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
        self.assertIn('pre_bid_date', form.errors)
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
