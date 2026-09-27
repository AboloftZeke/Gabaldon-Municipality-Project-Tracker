"""Display-only formatting for project financial amounts."""

from decimal import Decimal


def format_peso(value, missing='N/A'):
    """Show a stored amount in pesos without changing its database value."""
    if value is None or value == '':
        return missing
    return f'₱{Decimal(str(value)):,.2f}'
