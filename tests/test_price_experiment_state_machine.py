import pytest

from services.unit_economics_experiment_state_machine import UnitEconomicsExperimentStateMachine


Machine = UnitEconomicsExperimentStateMachine


@pytest.mark.parametrize(("state", "action", "gates", "target"), [
    ("DRAFT", "mark_ready", {"readiness_passed": True}, "READY"),
    ("DRAFT", "cancel", {}, "CANCELLED"),
    ("READY", "activate_baseline", {
        "phase_confirmed": True, "active_guard_available": True,
    }, "BASELINE_ACTIVE"),
    ("BASELINE_ACTIVE", "finish_baseline", {"evidence_frozen": True}, "BASELINE_REVIEW"),
    ("BASELINE_ACTIVE", "pause", {}, "PAUSED"),
    ("BASELINE_REVIEW", "select_candidate", {
        "candidate_selected": True, "comparable_baseline": True,
    }, "CANDIDATE_READY"),
    ("CANDIDATE_READY", "activate_candidate", {
        "phase_confirmed": True, "active_guard_available": True,
    }, "CANDIDATE_ACTIVE"),
    ("CANDIDATE_ACTIVE", "finish_candidate", {"evidence_frozen": True}, "CANDIDATE_REVIEW"),
    ("CANDIDATE_ACTIVE", "pause", {}, "PAUSED"),
    ("CANDIDATE_REVIEW", "select_candidate", {
        "candidate_selected": True, "comparable_baseline": True,
    }, "CANDIDATE_READY"),
    ("CANDIDATE_REVIEW", "complete", {"decision_recorded": True}, "COMPLETED"),
    ("PAUSED", "resume", {
        "resume_target": "READY", "fresh_confirmation": True,
        "active_guard_available": True,
    }, "BASELINE_ACTIVE"),
    ("PAUSED", "resume", {
        "resume_target": "CANDIDATE_READY", "fresh_confirmation": True,
        "active_guard_available": True,
    }, "CANDIDATE_ACTIVE"),
    ("READY", "cancel", {}, "CANCELLED"),
    ("BASELINE_REVIEW", "cancel", {}, "CANCELLED"),
    ("PAUSED", "cancel", {}, "CANCELLED"),
    ("CANCELLED", "archive", {}, "ARCHIVED"),
    ("COMPLETED", "archive", {}, "ARCHIVED"),
])
def test_transition_matrix_accepts_only_documented_gated_edges(state, action, gates, target):
    result = Machine.transition(state, action, **gates)

    assert result["error"] is False
    assert result["from_state"] == state
    assert result["to_state"] == target
    assert isinstance(result["effects"], list)


@pytest.mark.parametrize(("state", "action"), [
    ("BASELINE_ACTIVE", "cancel"),
    ("CANDIDATE_ACTIVE", "archive"),
    ("COMPLETED", "resume"),
    ("CANCELLED", "activate_baseline"),
    ("ARCHIVED", "cancel"),
    ("DRAFT", "finish_baseline"),
    ("READY", "complete"),
    ("PAUSED", "resume"),
    ("BASELINE_REVIEW", "select_candidate"),
    ("CANDIDATE_REVIEW", "complete"),
])
def test_undocumented_or_ungated_transition_is_rejected(state, action):
    result = Machine.transition(state, action)

    assert result["error"] is True


@pytest.mark.parametrize(("state", "action", "gates", "code"), [
    ("DRAFT", "mark_ready", {}, "EXPERIMENT_READINESS_GATE_FAILED"),
    ("READY", "activate_baseline", {}, "EXPERIMENT_PHASE_CONFIRMATION_REQUIRED"),
    ("READY", "activate_baseline", {
        "phase_confirmed": True,
    }, "EXPERIMENT_ACTIVE_SKU_GUARD_UNAVAILABLE"),
    ("BASELINE_ACTIVE", "finish_baseline", {}, "EXPERIMENT_PHASE_EVIDENCE_REQUIRED"),
    ("BASELINE_REVIEW", "select_candidate", {
        "candidate_selected": True,
    }, "EXPERIMENT_BASELINE_NOT_COMPARABLE"),
    ("CANDIDATE_REVIEW", "complete", {}, "EXPERIMENT_OWNER_DECISION_REQUIRED"),
    ("PAUSED", "resume", {
        "resume_target": "READY", "active_guard_available": True,
    }, "EXPERIMENT_FRESH_CONFIRMATION_REQUIRED"),
])
def test_failed_gate_returns_specific_safe_reason(state, action, gates, code):
    assert Machine.transition(state, action, **gates) == {"error": True, "code": code}


def test_pause_and_active_entry_expose_only_atomic_effects():
    baseline = Machine.transition(
        "READY", "activate_baseline", phase_confirmed=True, active_guard_available=True,
    )
    paused = Machine.transition("BASELINE_ACTIVE", "pause")

    assert baseline["effects"] == ["CREATE_BASELINE_PHASE", "ACQUIRE_ACTIVE_SKU_GUARD"]
    assert paused["effects"] == [
        "CLOSE_ACTIVE_SEGMENT", "STORE_RESUME_TARGET", "RELEASE_ACTIVE_SKU_GUARD",
    ]
    assert paused["resume_target"] == "READY"
