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
):
    """Record one Head decision only when official status/progress changed."""
    supporting_inspections = list(supporting_inspections)
    if any(
        inspection.project_id != infrastructure.project_id
        for inspection in supporting_inspections
    ):
        raise ValidationError(
            'Supporting inspections must belong to this Infrastructure project.'
        )

    if (
        previous_status == infrastructure.status
        and previous_physical_progress
        == infrastructure.physical_progress_percentage
    ):
        return None

    progress_update = InfrastructureProgressUpdate.objects.create(
        infrastructure=infrastructure,
        previous_official_status=previous_status or '',
        new_official_status=infrastructure.status or '',
        previous_physical_progress=previous_physical_progress,
        new_physical_progress=infrastructure.physical_progress_percentage,
        head_remarks=(remarks or '').strip(),
        updated_by=actor,
    )
    progress_update.supporting_inspections.set(supporting_inspections)
    return progress_update
