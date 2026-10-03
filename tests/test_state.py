import pytest

from app.state import TRANSITIONS, TransitionError, next_state


def test_spec_transitions_present():
    spec = {
        ("NEW", "START_SESSION"): "ACTIVE",
        ("ACTIVE", "BRANCH_LATERAL"): "PAUSED",
        ("ACTIVE", "IDLE_TIMEOUT"): "DORMANT",
        ("PAUSED", "IDLE_TIMEOUT"): "DORMANT",
        ("DORMANT", "RESUME_CLICKED"): "PAUSED",
        ("PAUSED", "PRIMER_ACKNOWLEDGED"): "ACTIVE",
        ("ACTIVE", "MARK_RESOLVED"): "RESOLVED",
    }
    for k, v in spec.items():
        assert TRANSITIONS[k] == v


def test_dormant_cannot_jump_straight_to_active():
    with pytest.raises(TransitionError):
        next_state("DORMANT", "RESUME")
    with pytest.raises(TransitionError):
        next_state("DORMANT", "PRIMER_ACKNOWLEDGED")


def test_resolved_is_not_terminal_forever():
    assert next_state("RESOLVED", "REOPEN") == "PAUSED"
