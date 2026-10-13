"""Read-only infrastructure indicators against the planned completion target."""

from datetime import date, datetime

from django.utils import timezone


def _date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def infrastructure_schedule_indicator(
    status, planned_end_date, *, planned_start_date=None, as_of=None,
):
    """Build schedule presentation data without changing project or snapshot state."""
    deadline = _date(planned_end_date)
    start = _date(planned_start_date)
    valid_schedule = deadline is not None and (
        planned_start_date in (None, '')
        or (start is not None and deadline >= start)
    )
    result = {
        'deadline': deadline if valid_schedule else None,
        'days_past_target': 0,
        'kind': 'unavailable',
        'label': 'Schedule not available',
    }
    if status == 'completed':
        return {**result, 'kind': 'completed', 'label': 'Completed'}
    if not valid_schedule:
        return result

    today = timezone.localdate() if as_of is None else _date(as_of)
    if today is None:
        return result

    days = (today - deadline).days
    if days > 0:
        return {
            **result,
            'kind': 'past-target',
            'days_past_target': days,
            'label': f'Past target date — {days} days',
        }
    return {
        **result,
        'kind': 'within-period',
        'label': 'Within scheduled period',
    }
