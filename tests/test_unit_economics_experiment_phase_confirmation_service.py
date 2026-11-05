from services.unit_economics_experiment_phase_confirmation_service import (
    UnitEconomicsExperimentPhaseConfirmationService as Confirmation,
)


def _phase(**overrides):
    value = {
        "kind": "BASELINE", "planned_price_cents": 10_000,
        "planned_from_date": "2026-10-30", "planned_to_date": "2026-11-05",
        "timezone": "Europe/Moscow",
    }
    value.update(overrides)
    return value


def test_midday_confirmation_starts_first_full_local_day_after_price_change():
    result = Confirmation.preview(
        _phase(), "READY", "PLANNED", 10_000,
        "2026-10-29T12:00:00+03:00", "2026-10-29T12:05:00+03:00",
    )

    assert result["status"] == "PREVIEW_ONLY"
    assert result["first_full_local_day"] == "2026-10-30"
    assert result["price_history_verified"] is False
    assert result["read_only"] is True and result["executed"] is False


def test_price_effective_at_local_midnight_can_use_that_full_calendar_day():
    result = Confirmation.preview(
        _phase(planned_from_date="2026-10-29"), "READY", "PLANNED", 10_000,
        "2026-10-29T00:00:00+03:00", "2026-10-29T00:00:00+03:00",
    )

    assert result["error"] is False
    assert result["first_full_local_day"] == "2026-10-29"


def test_owner_confirmation_creates_allowlisted_record_but_not_api_price_proof():
    result = Confirmation.preview(
        _phase(), "READY", "PLANNED", 10_000,
        "2026-10-29T09:00:00Z", "2026-10-29T12:00:00Z",
        owner_confirmed=True,
    )

    assert result["status"] == "READY_TO_CONFIRM"
    confirmation = result["confirmation"]
    assert confirmation["first_full_local_day"] == "2026-10-30"
    assert confirmation["price_evidence_kind"] == "OWNER_DECLARED"
    assert confirmation["price_history_verified"] is False
    assert Confirmation.normalize_confirmation(confirmation, _phase()) == confirmation


def test_future_price_change_time_is_rejected():
    result = Confirmation.preview(
        _phase(), "READY", "PLANNED", 10_000,
        "2026-10-30T10:00:00+03:00", "2026-10-29T12:00:00+03:00",
        owner_confirmed=True,
    )

    assert result == {
        "error": True, "code": "EXPERIMENT_PHASE_CONFIRMATION_TIME_FUTURE",
    }


def test_stale_phase_wrong_state_and_price_mismatch_fail_closed():
    assert Confirmation.preview(
        _phase(), "READY", "ACTIVE", 10_000,
        "2026-10-29T09:00:00Z", "2026-10-29T12:00:00Z",
    )["code"] == "EXPERIMENT_PHASE_NOT_PLANNED"
    assert Confirmation.preview(
        _phase(), "BASELINE_ACTIVE", "PLANNED", 10_000,
        "2026-10-29T09:00:00Z", "2026-10-29T12:00:00Z",
    )["code"] == "EXPERIMENT_PHASE_CONFIRMATION_STATE_INVALID"
    assert Confirmation.preview(
        _phase(), "READY", "PLANNED", 10_001,
        "2026-10-29T09:00:00Z", "2026-10-29T12:00:00Z",
    )["code"] == "EXPERIMENT_CONFIRMED_PRICE_MISMATCH"


def test_phase_window_cannot_start_before_first_full_day_or_after_it_ends():
    before = Confirmation.preview(
        _phase(planned_from_date="2026-10-29"), "READY", "PLANNED", 10_000,
        "2026-10-29T12:00:00+03:00", "2026-10-29T12:05:00+03:00",
    )
    after = Confirmation.preview(
        _phase(planned_from_date="2026-10-29", planned_to_date="2026-10-29"),
        "READY", "PLANNED", 10_000, "2026-10-29T12:00:00+03:00",
        "2026-10-29T12:05:00+03:00",
    )

    assert before["code"] == "EXPERIMENT_PHASE_WINDOW_BEFORE_NEXT_FULL_DAY"
    assert after["code"] == "EXPERIMENT_PHASE_WINDOW_BEFORE_NEXT_FULL_DAY"


def test_candidate_must_be_selected_in_experiment_configuration():
    candidate = _phase(kind="CANDIDATE")
    result = Confirmation.preview(
        candidate, "CANDIDATE_READY", "PLANNED", 10_000,
        "2026-10-29T09:00:00Z", "2026-10-29T12:00:00Z",
        candidate_prices_cents=[9_900],
    )

    assert result["code"] == "EXPERIMENT_CANDIDATE_NOT_SELECTED"


def test_resume_confirmation_requires_matching_stored_target_and_fresh_price_evidence():
    phase = _phase(planned_from_date="2026-10-31")
    resumed = Confirmation.preview(
        phase, "PAUSED", "PLANNED", 10_000,
        "2026-10-29T12:00:00+03:00", "2026-10-29T12:05:00+03:00",
        owner_confirmed=True, resume_target="READY",
    )
    wrong_target = Confirmation.preview(
        phase, "PAUSED", "PLANNED", 10_000,
        "2026-10-29T12:00:00+03:00", "2026-10-29T12:05:00+03:00",
        owner_confirmed=True, resume_target="CANDIDATE_READY",
    )

    assert resumed["error"] is False
    assert resumed["confirmation"]["first_full_local_day"] == "2026-10-30"
    assert resumed["confirmation"]["price_history_verified"] is False
    assert wrong_target["code"] == "EXPERIMENT_PHASE_CONFIRMATION_STATE_INVALID"


def test_candidate_resume_confirmation_requires_candidate_ready_target():
    phase = _phase(kind="CANDIDATE", planned_from_date="2026-10-31")
    resumed = Confirmation.preview(
        phase, "PAUSED", "PLANNED", 10_000,
        "2026-10-29T12:00:00+03:00", "2026-10-29T12:05:00+03:00",
        owner_confirmed=True, candidate_prices_cents=[10_000],
        resume_target="CANDIDATE_READY",
    )
    wrong_target = Confirmation.preview(
        phase, "PAUSED", "PLANNED", 10_000,
        "2026-10-29T12:00:00+03:00", "2026-10-29T12:05:00+03:00",
        owner_confirmed=True, candidate_prices_cents=[10_000],
        resume_target="READY",
    )

    assert resumed["error"] is False
    assert resumed["confirmation"]["first_full_local_day"] == "2026-10-30"
    assert wrong_target["code"] == "EXPERIMENT_PHASE_CONFIRMATION_STATE_INVALID"


def test_confirmation_normalizer_rejects_tampered_date_and_price_history_claim():
    confirmation = Confirmation.preview(
        _phase(), "READY", "PLANNED", 10_000,
        "2026-10-29T09:00:00Z", "2026-10-29T12:00:00Z",
        owner_confirmed=True,
    )["confirmation"]
    tampered_date = {**confirmation, "first_full_local_day": "2026-10-29"}
    false_proof = {**confirmation, "price_history_verified": True}

    assert Confirmation.normalize_confirmation(tampered_date, _phase()) is None
    assert Confirmation.normalize_confirmation(false_proof, _phase()) is None
