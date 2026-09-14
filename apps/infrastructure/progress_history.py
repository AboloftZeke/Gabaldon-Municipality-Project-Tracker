from apps.system.models import InfrastructureProgressUpdate


def record_progress_update(
    infrastructure,
    actor,
    *,
    previous_status,
    previous_physical_progress,
    remarks='',
):
    """Record one Head decision only when official status/progress changed."""
    if (
        previous_status == infrastructure.award_status
        and previous_physical_progress
        == infrastructure.physical_progress_percentage
    ):
        return None

    return InfrastructureProgressUpdate.objects.create(
        infrastructure=infrastructure,
        previous_official_status=previous_status or '',
        new_official_status=infrastructure.award_status or '',
        previous_physical_progress=previous_physical_progress,
        new_physical_progress=infrastructure.physical_progress_percentage,
        head_remarks=(remarks or '').strip(),
        updated_by=actor,
    )
