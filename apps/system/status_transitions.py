_STATUS_STAGES = {
    'planned': 0,
    'not_yet_started': 0,
    'ongoing': 1,
    'on_hold': 1,
    'completed': 2,
}


def is_valid_project_status_transition(previous_status, proposed_status):
    """Return whether a status change moves forward without reopening completed work."""
    previous_stage = _STATUS_STAGES.get(previous_status)
    proposed_stage = _STATUS_STAGES.get(proposed_status)
    if previous_stage is None or proposed_stage is None:
        return False
    if proposed_stage > previous_stage:
        return True
    return (
        previous_stage == proposed_stage == 1
        and {previous_status, proposed_status} == {'ongoing', 'on_hold'}
    )
