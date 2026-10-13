from django.test import SimpleTestCase

from apps.infrastructure.forms import InfrastructureOperationalForm
from apps.system.models import InfrastructureProject, InfrastructureProgressUpdate


EXPECTED_OFFICIAL_STATUS_CHOICES = [
    ("ongoing", "Ongoing"),
    ("on_hold", "On-Hold"),
    ("completed", "Completed"),
]


class OfficialStatusChoicesTests(SimpleTestCase):
    def test_infrastructure_status_choices_have_the_required_order(self):
        self.assertEqual(
            InfrastructureProject.STATUS_CHOICES,
            EXPECTED_OFFICIAL_STATUS_CHOICES,
        )

    def test_operational_form_and_history_use_official_status_choices(self):
        self.assertEqual(
            list(InfrastructureOperationalForm.base_fields["status"].choices),
            EXPECTED_OFFICIAL_STATUS_CHOICES,
        )
        self.assertEqual(
            list(
                InfrastructureProgressUpdate._meta.get_field(
                    "new_official_status"
                ).choices
            ),
            EXPECTED_OFFICIAL_STATUS_CHOICES,
        )

    def test_obsolete_choices_are_not_available(self):
        values = {value for value, _label in EXPECTED_OFFICIAL_STATUS_CHOICES}
        self.assertFalse(values & {
            "pre_construction", "suspended", "for_inspection", "for_turnover",
            "turned_over", "cancelled",
        })

    def test_completed_status_cannot_be_reopened(self):
        from apps.system.status_transitions import (
            is_valid_project_status_transition,
        )

        self.assertTrue(
            is_valid_project_status_transition('ongoing', 'on_hold'),
        )
        self.assertTrue(
            is_valid_project_status_transition('on_hold', 'completed'),
        )
        self.assertFalse(
            is_valid_project_status_transition('completed', 'ongoing'),
        )
        self.assertFalse(
            is_valid_project_status_transition('completed', 'on_hold'),
        )
