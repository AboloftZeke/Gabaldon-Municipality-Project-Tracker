from django.contrib.auth import get_user_model
from django import forms
from django.test import TestCase

from apps.infrastructure.forms import InfrastructureProjectForm
from apps.system.models import (
    Contractor,
    FundSource,
    ImplementingOffice,
    InfrastructureCategory,
)


class InfrastructureProjectFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='engineer1',
            email='engineer1@example.com',
            password='Testpass123!',
        )
        self.category = InfrastructureCategory.objects.create(
            category_code='roads',
            category_name='Roads',
        )
        self.office = ImplementingOffice.objects.create(office_name='Engineering Office')
        self.contractor = Contractor.objects.create(contractor_name='Sample Contractor')
        self.fund_source = FundSource.objects.create(
            fund_source_code='local',
            fund_source_name='Local Funds',
        )

    def test_form_uses_model_dropdowns_and_fixed_location(self):
        form = InfrastructureProjectForm()

        self.assertIsInstance(form.fields['category'], forms.ModelChoiceField)
        self.assertIsInstance(form.fields['contractor'], forms.ModelChoiceField)
        self.assertIsInstance(form.fields['implementing_office'], forms.ModelChoiceField)
        self.assertIsInstance(form.fields['fund_source'], forms.ModelChoiceField)
        self.assertEqual(form.fields['municipality'].initial, 'Gabaldon')
        self.assertEqual(form.fields['province'].initial, 'Nueva Ecija')
        self.assertIn('competitive_bidding', [value for value, label in form.fields['procurement_method'].choices])
        self.assertIn('awarded', [value for value, label in form.fields['award_status'].choices])

    def test_form_save_persists_normalized_infrastructure_relationships(self):
        form = InfrastructureProjectForm(
            data={
                'title': 'Road Improvement Project',
                'description': 'Paving and drainage works along the main road.',
                'category': str(self.category.infrastructure_category_id),
                'implementing_office': str(self.office.office_id),
                'contractor': str(self.contractor.contractor_id),
                'procurement_method': 'competitive_bidding',
                'award_status': 'awarded',
                'street': 'Main Street',
                'barangay': 'San Jose',
                'municipality': 'Gabaldon',
                'province': 'Nueva Ecija',
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
        )

        self.assertTrue(form.is_valid(), form.errors)
        infra = form.save(user=self.user)

        self.assertEqual(infra.category_id, self.category.infrastructure_category_id)
        self.assertEqual(infra.contractor_id, self.contractor.contractor_id)
        self.assertEqual(infra.implementing_office_id, self.office.office_id)
        self.assertEqual(infra.procurement_method, 'competitive_bidding')
        self.assertEqual(infra.award_status, 'awarded')
        self.assertEqual(infra.financial_records.first().fund_source_id, self.fund_source.fund_source_id)
        self.assertEqual(infra.address.municipality, 'Gabaldon')
        self.assertEqual(infra.address.province, 'Nueva Ecija')
        self.assertEqual(float(infra.address.latitude), 15.1234567)
        self.assertEqual(float(infra.address.longitude), 120.9876543)

        edit_form = InfrastructureProjectForm(instance=infra.project)
        self.assertEqual(float(edit_form.initial['latitude']), 15.1234567)
        self.assertEqual(float(edit_form.initial['longitude']), 120.9876543)
