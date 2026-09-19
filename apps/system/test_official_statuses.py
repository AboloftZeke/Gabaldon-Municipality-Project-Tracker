from django.test import SimpleTestCase

from apps.infrastructure.forms import InfrastructureOperationalForm
from apps.system.models import InfrastructureProject, InfrastructureProgressUpdate


EXPECTED_OFFICIAL_STATUS_CHOICES = [
    ("not_yet_started", "Not Yet Started"),
    ("pre_construction", "Pre-Construction"),
    ("ongoing", "Ongoing"),
    ("on_hold", "On Hold"),
    ("suspended", "Suspended"),
    ("completed", "Completed"),
    ("for_inspection", "For Inspection"),
    ("for_turnover", "For Turnover"),
    ("turned_over", "Turned Over"),
    ("cancelled", "Cancelled"),
]


class OfficialStatusChoicesTests(SimpleTestCase):
    def test_infrastructure_status_choices_have_the_required_order(self):
        self.assertEqual(
            InfrastructureProject.OFFICIAL_STATUS_CHOICES,
            EXPECTED_OFFICIAL_STATUS_CHOICES,
        )
        self.assertEqual(
            InfrastructureProject.AWARD_STATUS_CHOICES,
            EXPECTED_OFFICIAL_STATUS_CHOICES,
        )

    def test_operational_form_and_history_use_official_status_choices(self):
        form = InfrastructureOperationalForm()
        self.assertEqual(
            list(form.fields["award_status"].choices),
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
        self.assertFalse(values & {"awarded", "ongoing_bidding", "rebid"})
