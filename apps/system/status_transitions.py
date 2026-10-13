_STATUS_STAGES = {
    'planned': 0,
    'ongoing': 1,
    'on_hold': 1,
    'completed': 2,
}


def is_valid_project_status_transition(previous_status, proposed_status):
    """Return whether a status change moves forward without reopening completed work."""
    proposed_stage = _STATUS_STAGES.get(proposed_status)
    if proposed_stage is None:
        return False
    if previous_status in (None, ''):
        return True
    if previous_status == 'not_yet_started':
        return proposed_status in {'ongoing', 'on_hold', 'completed'}
    previous_stage = _STATUS_STAGES.get(previous_status)
    if previous_stage is None:
        return False
    if proposed_stage > previous_stage:
        return True
    return (
        previous_stage == proposed_stage == 1
        and {previous_status, proposed_status} == {'ongoing', 'on_hold'}
    )
