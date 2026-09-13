"""Reference-only progress calculations for project presentation."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP


PERCENT_QUANTUM = Decimal('0.01')


def _percent(value):
    return min(Decimal('100'), max(Decimal('0'), value)).quantize(
        PERCENT_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def active_schedule_end(start_date, planned_end_date, revised_end_date=None):
    """Use a revised end only when it is a valid schedule extension."""
    if (
        revised_end_date
        and start_date
        and planned_end_date
        and revised_end_date >= planned_end_date >= start_date
    ):
        return revised_end_date
    return planned_end_date


def expected_progress(
    start_date,
    planned_end_date,
    *,
    revised_end_date=None,
    as_of=None,
):
    """Return linear scheduled progress, or None for an invalid schedule."""
    if not start_date or not planned_end_date:
        return None
    end_date = active_schedule_end(
        start_date,
        planned_end_date,
        revised_end_date,
    )
    if not end_date or end_date < start_date:
        return None

    current_date = as_of or date.today()
    if current_date <= start_date:
        return Decimal('0.00')
    if current_date >= end_date:
        return Decimal('100.00')

    total_days = (end_date - start_date).days
    if total_days == 0:
        return Decimal('100.00')
    elapsed_days = (current_date - start_date).days
    return _percent(Decimal(elapsed_days) / Decimal(total_days) * 100)


def progress_variance(actual_progress, expected_progress_value):
    """Return actual minus expected without mutating either source value."""
    if actual_progress is None or expected_progress_value is None:
        return None
    return (Decimal(actual_progress) - Decimal(expected_progress_value)).quantize(
        PERCENT_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def derived_cost_progress(actual_expenditure, contract_price):
    """Return expenditure as a percentage of authoritative contract price."""
    if actual_expenditure is None or contract_price is None:
        return None
    price = Decimal(contract_price)
    if price <= 0:
        return None
    return _percent(Decimal(actual_expenditure) / price * 100)
