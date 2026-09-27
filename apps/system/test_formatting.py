from decimal import Decimal

from django.template import Context, Template
from django.test import SimpleTestCase

from .formatting import format_peso


class PesoFormattingTests(SimpleTestCase):
    def test_amounts_have_grouping_and_two_decimal_places(self):
        for value, expected in (
            (Decimal('1000'), '₱1,000.00'),
            (Decimal('1250000.5'), '₱1,250,000.50'),
            (Decimal('1000.75'), '₱1,000.75'),
            (Decimal('0'), '₱0.00'),
        ):
            with self.subTest(value=value):
                self.assertEqual(format_peso(value), expected)

    def test_null_is_not_confused_with_zero(self):
        self.assertEqual(format_peso(None), 'N/A')
        self.assertEqual(format_peso(''), 'N/A')
        self.assertEqual(format_peso(None, missing='Not recorded'), 'Not recorded')
        self.assertEqual(format_peso(0), '₱0.00')

    def test_template_filter_formats_money_without_changing_percentages(self):
        template = Template(
            '{% load project_formatting %}'
            '{{ amount|peso }} / {{ progress|floatformat:1 }}%'
        )
        self.assertEqual(
            template.render(Context({'amount': Decimal('1250000.5'),
                                     'progress': Decimal('42.75')})),
            '₱1,250,000.50 / 42.8%',
        )
