from services.unit_economics_experiment_control_service import (
    UnitEconomicsExperimentControlService as Control,
)


def _flags(**overrides):
    value = {key: "UNCHANGED" for key in Control.CONTROL_KEYS}
    value.update(overrides)
    return value


def test_control_flags_are_allowlisted_and_changed_conditions_get_reason_codes():
    baseline = _flags()
    changed = _flags(promotion="CHANGED", advertising="UNKNOWN", inventory="CHANGED")

    assert Control.compatibility(baseline, changed) == {
        "status": "INCOMPATIBLE",
        "reason_codes": [
            "EXPERIMENT_CONTROL_CHANGED_INVENTORY",
            "EXPERIMENT_CONTROL_CHANGED_PROMOTION",
            "EXPERIMENT_CONTROL_UNKNOWN_ADVERTISING",
        ],
    }
    assert Control.compatibility(_flags()) == {
        "status": "COMPATIBLE", "reason_codes": [],
    }
    assert Control.compatibility(_flags(cost="NOT_APPLICABLE"))["status"] == (
        "COMPATIBLE"
    )
    assert Control.normalize_flags({**baseline, "product_name": "leak"}) is None
    assert Control.normalize_flags(_flags(card="unexpected")) is None
    assert Control.normalize_flags(_flags(card=[])) is None


def test_control_event_is_owner_reported_and_normalized_without_free_text():
    phase_id = "a" * 32
    event = Control.normalize_event({
        "schema_version": 1, "event_kind": "CONTROL_UPDATE", "phase_id": phase_id,
        "control_flags": _flags(tariff="CHANGED"), "source": "OWNER_REPORTED",
    }, expected_phase_id=phase_id)

    assert event["compatibility"]["reason_codes"] == [
        "EXPERIMENT_CONTROL_CHANGED_TARIFF",
    ]
    assert event["source"] == "OWNER_REPORTED"
    assert "reason" not in event
    assert Control.normalize_event({
        "schema_version": 1, "event_kind": "CONTROL_UPDATE", "phase_id": phase_id,
        "control_flags": _flags(), "source": "OZON_VERIFIED",
    }) is None
    assert Control.normalize_event({
        "schema_version": 1, "event_kind": "CONTROL_UPDATE", "phase_id": phase_id,
        "control_flags": _flags(), "source": "OWNER_REPORTED", "note": "raw",
    }) is None


def test_pause_and_resume_events_bind_distinct_exact_phase_links():
    phase_id, next_phase_id, observation_id = "a" * 32, "b" * 32, "c" * 32
    paused = Control.normalize_pause_event({
        "schema_version": 1, "event_kind": "PAUSE", "phase_id": phase_id,
        "observation_id": observation_id, "resume_target": "READY",
        "source": "OWNER_ACTION",
    }, expected_phase_id=phase_id)
    resumed = Control.normalize_resume_event({
        "schema_version": 1, "event_kind": "RESUME_SEGMENT_PREPARED",
        "previous_phase_id": phase_id, "phase_id": next_phase_id,
        "resume_target": "READY", "source": "OWNER_ACTION",
    }, expected_resume_target="READY")

    assert paused["observation_id"] == observation_id
    assert resumed["previous_phase_id"] == phase_id
    assert resumed["phase_id"] == next_phase_id
    assert Control.normalize_resume_event({
        "schema_version": 1, "event_kind": "RESUME_SEGMENT_PREPARED",
        "previous_phase_id": phase_id, "phase_id": next_phase_id,
        "resume_target": "CANDIDATE_READY", "source": "OWNER_ACTION",
    }, expected_resume_target="READY") is None
