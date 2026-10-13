_ALLOWED_STATUS_TRANSITIONS = {
    'ongoing': {'ongoing', 'on_hold', 'completed'},
    'on_hold': {'ongoing', 'on_hold', 'completed'},
    'completed': {'completed'},
}


def is_valid_project_status_transition(previous_status, proposed_status):
    """Allow operational status to advance, but never reopen completed work."""
    if proposed_status not in {'ongoing', 'on_hold', 'completed'}:
        return False
    if previous_status in (None, ''):
        return True
    return proposed_status in _ALLOWED_STATUS_TRANSITIONS.get(
        previous_status,
        set(),
    )
