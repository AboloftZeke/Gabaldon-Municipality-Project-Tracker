"""Display-only formatting for project financial amounts."""

from decimal import Decimal

from .choices import BARANGAY_CHOICES


def format_peso(value, missing='N/A'):
    """Show a stored amount in pesos without changing its database value."""
    if value is None or value == '':
        return missing
    return f'₱{Decimal(str(value)):,.2f}'


def format_barangay(value, missing=''):
    """Show a stored barangay key using its human-readable label."""
    if value is None or value == '':
        return missing

    value = str(value).strip()
    labels = dict(BARANGAY_CHOICES)
    return labels.get(value.lower(), value.replace('_', ' ').title())
