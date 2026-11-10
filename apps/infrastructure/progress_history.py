from django.core.exceptions import ValidationError
from django.db import transaction

from apps.system.models import InfrastructureProgressUpdate


@transaction.atomic
def record_progress_update(
    infrastructure,
    actor,
    *,
    previous_status,
    previous_physical_progress,
    remarks='',
    supporting_inspections=(),
    require_supporting_inspections=True,
):
    """Record one Head decision only when official status/progress changed."""
    supporting_inspections = list(supporting_inspections)
    if require_supporting_inspections and not supporting_inspections:
        raise ValidationError(
            'At least one supporting inspection is required for an Infrastructure progress update.'
        )

    if any(
        inspection.project_id != infrastructure.project_id
        for inspection in supporting_inspections
    ):
        raise ValidationError(
            'Supporting inspections must belong to this Infrastructure project.'
        )

    if any(not inspection.evidence.exists() for inspection in supporting_inspections):
        raise ValidationError(
            'Every supporting inspection must include inspection evidence.'
        )

    latest_recorded_progress = InfrastructureProgressUpdate.objects.filter(
        infrastructure=infrastructure,
        new_physical_progress__isnull=False,
    ).order_by(
        '-created_at',
        '-progress_update_id',
    ).values_list('new_physical_progress', flat=True).first()
    official_progress = max(
        (
            value
            for value in (
                previous_physical_progress,
                latest_recorded_progress,
            )
            if value is not None
        ),
        default=None,
    )
    current_progress = infrastructure.physical_progress_percentage
    if (
        official_progress is not None
        and (
            current_progress is None
            or current_progress < official_progress
        )
    ):
        previous = format(official_progress.normalize(), 'f')
        raise ValidationError(
            'Physical progress cannot be lower than the previous official '
            f'progress of {previous}%. Please enter a value equal to or '
            f'greater than {previous}%.'
        )

    if (
        previous_status == infrastructure.status
        and official_progress == current_progress
    ):
        return None

    progress_update = InfrastructureProgressUpdate.objects.create(
        infrastructure=infrastructure,
        previous_official_status=previous_status or '',
        new_official_status=infrastructure.status or '',
        previous_physical_progress=official_progress,
        new_physical_progress=current_progress,
        head_remarks=(remarks or '').strip(),
        updated_by=actor,
    )
    progress_update.supporting_inspections.set(supporting_inspections)
    return progress_update
