from datetime import date
from decimal import Decimal

from django.test import TestCase

from .models import Infrastructure_Project, Project
from .progress import (
    derived_cost_progress,
    expected_progress,
    progress_variance,
)


class DerivedProgressTests(TestCase):
    def test_expected_progress_before_start(self):
        self.assertEqual(
            expected_progress(
                date(2026, 2, 1),
                date(2026, 2, 11),
                as_of=date(2026, 1, 31),
            ),
            Decimal('0.00'),
        )

    def test_expected_progress_during_schedule(self):
        self.assertEqual(
            expected_progress(
                date(2026, 2, 1),
                date(2026, 2, 11),
                as_of=date(2026, 2, 6),
            ),
            Decimal('50.00'),
        )

    def test_expected_progress_after_end(self):
        self.assertEqual(
            expected_progress(
                date(2026, 2, 1),
                date(2026, 2, 11),
                as_of=date(2026, 2, 15),
            ),
            Decimal('100.00'),
        )

    def test_valid_revised_end_is_active_schedule_end(self):
        self.assertEqual(
            expected_progress(
                date(2026, 2, 1),
                date(2026, 2, 11),
                revised_end_date=date(2026, 2, 21),
                as_of=date(2026, 2, 11),
            ),
            Decimal('50.00'),
        )
        self.assertEqual(
            expected_progress(
                date(2026, 2, 1),
                date(2026, 2, 11),
                revised_end_date=date(2026, 2, 5),
                as_of=date(2026, 2, 6),
            ),
            Decimal('50.00'),
        )

    def test_variance_is_actual_minus_expected(self):
        self.assertEqual(
            progress_variance(Decimal('42.50'), Decimal('35.25')),
            Decimal('7.25'),
        )

    def test_calculations_do_not_mutate_actual_value(self):
        project = Project.objects.create(project_type='infrastructure')
        infrastructure = Infrastructure_Project.objects.create(
            project=project,
            infrastructure_title='Stored progress test',
            planned_start_date=date(2026, 2, 1),
            planned_end_date=date(2026, 2, 11),
            physical_progress_percentage=Decimal('42.50'),
            cost_progress_percentage=Decimal('27.25'),
        )
        actual = infrastructure.physical_progress_percentage
        expected = expected_progress(
            infrastructure.planned_start_date,
            infrastructure.planned_end_date,
            as_of=date(2026, 2, 6),
        )
        progress_variance(actual, expected)
        derived_cost_progress(Decimal('250.00'), Decimal('1000.00'))
        infrastructure.refresh_from_db()
        self.assertEqual(
            infrastructure.physical_progress_percentage,
            Decimal('42.50'),
        )
        self.assertEqual(
            infrastructure.cost_progress_percentage,
            Decimal('27.25'),
        )

    def test_cost_progress_uses_expenditure_over_contract_price(self):
        self.assertEqual(
            derived_cost_progress(Decimal('250.00'), Decimal('1000.00')),
            Decimal('25.00'),
        )
        self.assertIsNone(derived_cost_progress(Decimal('10.00'), Decimal('0')))
