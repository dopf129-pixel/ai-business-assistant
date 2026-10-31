from copy import deepcopy
from datetime import datetime, timezone

from services.unit_economics_experiment_phase_collection_service import (
    UnitEconomicsExperimentPhaseCollectionService,
)
from services.unit_economics_experiment_phase_readiness_service import (
    UnitEconomicsExperimentPhaseReadinessService,
)
from services.unit_economics_experiment_phase_maturity_service import (
    UnitEconomicsExperimentPhaseMaturityService,
)
from services.tenant_context import reset_current_tenant_user_id

from test_unit_economics_experiment_phase_collection_service import (
    PhaseEvidenceCollector,
    _active_phase,
    _evidence,
)


def _collect(repo, experiment, phase, confirmed, collector, *, result_revision=0, key="w27-collect01"):
    service = UnitEconomicsExperimentPhaseCollectionService(
        repo, collector,
        clock=lambda: datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc),
    )
    return service.collect_phase(
        experiment["experiment_id"], phase["phase_id"],
        expected_state_revision=confirmed["state_revision"],
        expected_phase_state_revision=confirmed["phase_state_revision"],
        expected_result_revision=result_revision,
        idempotency_key=key, owner_id="owner-1", store_id="store-a",
    )


def _readiness(repo, experiment, phase, confirmed, *, now, result_revision, key):
    service = UnitEconomicsExperimentPhaseReadinessService(
        repo, clock=lambda: now,
    )
    return service.evaluate_latest(
        experiment["experiment_id"], phase["phase_id"],
        expected_state_revision=confirmed["state_revision"],
        expected_phase_state_revision=confirmed["phase_state_revision"],
        expected_result_revision=result_revision,
        idempotency_key=key, owner_id="owner-1", store_id="store-a",
    )


def _mature_evidence(*, sample=35, delivered=30, performance_status="COMPLETE"):
    evidence = _evidence(performance_status=performance_status)
    evidence["metrics"].update({
        "successful_sale_units": delivered,
        "delivered_units": delivered,
        "buyout_sample_size": sample,
        "ordered_units": sample + 5,
        "cancelled_units": 5,
        "returned_units": 0,
        "buyout_rate_percent": (
            format(delivered / sample * 100, ".2f") if sample else None
        ),
    })
    return evidence


def test_maturity_boundary_uses_seven_complete_local_days_and_keeps_price_history_unknown(
    tmp_path,
):
    repo, token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        collector = PhaseEvidenceCollector(_mature_evidence())
        collected = _collect(repo, experiment, phase, confirmed, collector)
        assert collected["error"] is False

        # Nov 12 is six completed local dates after the Nov 5 phase end.
        waiting = _readiness(
            repo, experiment, phase, confirmed,
            now=datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc),
            result_revision=collected["result_revision"], key="w27-maturity-wait01",
        )
        assert waiting["error"] is False
        assert waiting["status"] == "WAITING_FOR_DATA"
        saved_waiting = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
        )["items"][0]["payload"]
        gates = {item["gate"]: item for item in saved_waiting["quality_gates"]}
        assert gates["MATURITY_DELAY"]["reason_code"] == "MATURITY_PENDING"
        assert gates["ELIGIBLE_UNIT_SAMPLE"]["status"] == "PASS"
        assert saved_waiting["baseline_profit_per_unit_rub"] is None
        assert saved_waiting["candidate_profit_per_unit_rub"] is None

        # Waiting does not mature the immutable Nov 6 snapshot. It was collected
        # before the seven-day correction window had elapsed.
        still_waiting = _readiness(
            repo, experiment, phase, confirmed,
            now=datetime(2026, 11, 12, 21, 0, tzinfo=timezone.utc),
            result_revision=waiting["result_revision"], key="w27-maturity-ready01",
        )
        assert still_waiting["error"] is False
        assert still_waiting["status"] == "WAITING_FOR_DATA"
        stale_payload = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
        )["items"][0]["payload"]
        stale_gates = {item["gate"]: item for item in stale_payload["quality_gates"]}
        assert stale_payload["source_as_of"] == "2026-11-06T12:00:00Z"
        assert stale_gates["MATURITY_DELAY"]["reason_code"] == "MATURITY_PENDING"

        collector.evidence["collected_at"] = "2026-11-12T21:00:00Z"
        refreshed = _collect(
            repo, experiment, phase, confirmed, collector,
            result_revision=still_waiting["result_revision"], key="w27-maturity-refresh01",
        )
        ready = _readiness(
            repo, experiment, phase, confirmed,
            now=datetime(2026, 11, 12, 21, 0, tzinfo=timezone.utc),
            result_revision=refreshed["result_revision"], key="w27-maturity-after-refresh01",
        )
        assert ready["error"] is False
        assert ready["status"] == "READY"
        assert collector.calls == [
            (confirmed["observation_id"], "2026-10-30", "2026-11-05"),
            (confirmed["observation_id"], "2026-10-30", "2026-11-05"),
        ]
        results = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
        )["items"]
        latest = results[0]["payload"]
        latest_gates = {item["gate"]: item for item in latest["quality_gates"]}
        assert latest_gates["MATURITY_DELAY"]["status"] == "PASS"
        assert latest_gates["PRICE_HISTORY"]["status"] == "WARNING"
        assert latest_gates["PRICE_HISTORY"]["reason_code"] == "OWNER_DECLARED_PRICE_ONLY"
        assert latest_gates["PRICE_STABILITY"]["status"] == "WARNING"
        assert latest_gates["PRICE_STABILITY"]["reason_code"] == (
            "MIXED_PRICES_NOT_VERIFIABLE_FROM_AVAILABLE_SOURCE"
        )
        assert "MIXED_PRICES_CANNOT_BE_VERIFIED_FROM_AVAILABLE_SOURCE" in latest["limitations"]
        assert latest["quantity_basis"] == "SOLD_UNITS_WINDOW"
        assert latest["baseline_profit_per_unit_rub"] is None
        assert latest["candidate_profit_per_unit_rub"] is None

        result_count = len(results)
        replay = _readiness(
            repo, experiment, phase, confirmed,
            now=datetime(2026, 11, 12, 21, 0, tzinfo=timezone.utc),
            result_revision=refreshed["result_revision"], key="w27-maturity-after-refresh01",
        )
        assert replay["error"] is False
        assert replay["result_revision"] == ready["result_revision"]
        assert len(repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
        )["items"]) == result_count
    finally:
        reset_current_tenant_user_id(token)


def test_maturity_day_boundary_uses_phase_timezone_not_utc_date(tmp_path):
    repo, token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        collected = _collect(
            repo, experiment, phase, confirmed, PhaseEvidenceCollector(),
        )
        stored = repo.list_price_experiment_phase_collections(
            experiment["experiment_id"], phase["phase_id"], limit=1,
        )["items"][0]
        pacific_experiment = deepcopy(repo.get_price_experiment(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["experiment"])
        pacific_phase = deepcopy(repo.list_price_experiment_phases(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["items"][0])
        pacific_phase["config"]["timezone"] = "America/Los_Angeles"
        pacific_phase["confirmation"]["timezone"] = "America/Los_Angeles"
        collection = deepcopy(stored["payload"])
        collection["window"]["timezone"] = "America/Los_Angeles"
        collection["collected_at"] = "2026-11-13T07:59:00Z"

        before_local_midnight = UnitEconomicsExperimentPhaseMaturityService.evaluate(
            pacific_experiment, pacific_phase, collection, stored["collection_id"], [],
            datetime(2026, 11, 13, 7, 59, tzinfo=timezone.utc),
        )
        collection["collected_at"] = "2026-11-13T08:00:00Z"
        at_local_midnight = UnitEconomicsExperimentPhaseMaturityService.evaluate(
            pacific_experiment, pacific_phase, collection, stored["collection_id"], [],
            datetime(2026, 11, 13, 8, 0, tzinfo=timezone.utc),
        )
        assert collected["error"] is False
        assert before_local_midnight["error"] is False
        assert at_local_midnight["error"] is False
        before_gates = {
            item["gate"]: item for item in before_local_midnight["payload"]["quality_gates"]
        }
        at_gates = {
            item["gate"]: item for item in at_local_midnight["payload"]["quality_gates"]
        }
        assert before_gates["MATURITY_DELAY"]["reason_code"] == "MATURITY_PENDING"
        assert at_gates["MATURITY_DELAY"]["reason_code"] == "MATURITY_REACHED"
    finally:
        reset_current_tenant_user_id(token)


def test_q0_and_below_sample_gate_never_create_a_per_unit_profit(tmp_path):
    repo, token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        zero = _mature_evidence(sample=0, delivered=0)
        zero["metrics"]["successful_sale_units"] = None
        collector = PhaseEvidenceCollector(zero)
        collected = _collect(repo, experiment, phase, confirmed, collector)
        assert collected["error"] is False
        result = _readiness(
            repo, experiment, phase, confirmed,
            now=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
            result_revision=collected["result_revision"], key="w27-q0-readiness01",
        )
        assert result["error"] is False
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["outcome"] == "FIX_DATA_OR_CONDITIONS"
        saved = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
        )["items"][0]["payload"]
        gates = {item["gate"]: item for item in saved["quality_gates"]}
        assert gates["ELIGIBLE_UNIT_SAMPLE"]["reason_code"] == "ZERO_ELIGIBLE_UNITS"
        assert gates["SOLD_UNIT_DENOMINATOR"]["status"] == "UNKNOWN"
        assert gates["SOLD_UNIT_DENOMINATOR"]["reason_code"] == "SOLD_UNITS_NOT_CONFIRMED"
        assert saved["quantity_basis"] is None
        assert saved["baseline_profit_per_unit_rub"] is None
        assert saved["candidate_profit_per_unit_rub"] is None
    finally:
        reset_current_tenant_user_id(token)

    enough_non_buyouts_tmp_path = tmp_path / "enough-non-buyouts"
    enough_non_buyouts_tmp_path.mkdir()
    repo, token, experiment, phase, confirmed = _active_phase(enough_non_buyouts_tmp_path)
    try:
        enough_non_buyouts = _mature_evidence(sample=30, delivered=0)
        enough_non_buyouts["metrics"]["successful_sale_units"] = 0
        enough_non_buyouts["metrics"]["ordered_units"] = 40
        enough_non_buyouts["metrics"]["cancelled_units"] = 10
        collector = PhaseEvidenceCollector(enough_non_buyouts)
        collected = _collect(
            repo, experiment, phase, confirmed, collector,
            key="w27-q0-sample30-collect01",
        )
        assert collected["error"] is False
        result = _readiness(
            repo, experiment, phase, confirmed,
            now=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
            result_revision=collected["result_revision"], key="w27-q0-sample30-eval01",
        )
        assert result["error"] is False
        assert result["status"] == "INSUFFICIENT_DATA"
        saved = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
        )["items"][0]["payload"]
        gates = {item["gate"]: item for item in saved["quality_gates"]}
        assert gates["ELIGIBLE_UNIT_SAMPLE"]["status"] == "PASS"
        assert gates["SOLD_UNIT_DENOMINATOR"]["reason_code"] == "ZERO_SOLD_UNITS"
        assert saved["quantity_basis"] is None
        assert saved["candidate_profit_per_unit_rub"] is None
    finally:
        reset_current_tenant_user_id(token)

    small_tmp_path = tmp_path / "small"
    small_tmp_path.mkdir()
    repo, token, experiment, phase, confirmed = _active_phase(small_tmp_path)
    try:
        collector = PhaseEvidenceCollector(_mature_evidence(sample=29, delivered=25))
        collected = _collect(repo, experiment, phase, confirmed, collector, key="w27-small-collect01")
        assert collected["error"] is False
        result = _readiness(
            repo, experiment, phase, confirmed,
            now=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
            result_revision=collected["result_revision"], key="w27-small-readiness01",
        )
        assert result["status"] == "WAITING_FOR_DATA"
        saved = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
        )["items"][0]["payload"]
        gates = {item["gate"]: item for item in saved["quality_gates"]}
        assert gates["ELIGIBLE_UNIT_SAMPLE"]["reason_code"] == "SAMPLE_BELOW_MINIMUM"
        assert saved["baseline_profit_per_unit_rub"] is None
    finally:
        reset_current_tenant_user_id(token)

    low_sold_tmp_path = tmp_path / "low-sold"
    low_sold_tmp_path.mkdir()
    repo, token, experiment, phase, confirmed = _active_phase(low_sold_tmp_path)
    try:
        collector = PhaseEvidenceCollector(_mature_evidence(sample=30, delivered=1))
        collected = _collect(
            repo, experiment, phase, confirmed, collector, key="w42-low-sold-collect01",
        )
        result = _readiness(
            repo, experiment, phase, confirmed,
            now=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
            result_revision=collected["result_revision"], key="w42-low-sold-readiness01",
        )
        assert result["status"] == "WAITING_FOR_DATA"
        saved = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
        )["items"][0]["payload"]
        gates = {item["gate"]: item for item in saved["quality_gates"]}
        assert gates["ELIGIBLE_UNIT_SAMPLE"]["status"] == "PASS"
        assert gates["SOLD_UNIT_DENOMINATOR"]["status"] == "FAIL"
        assert gates["SOLD_UNIT_DENOMINATOR"]["reason_code"] == "SOLD_SAMPLE_BELOW_MINIMUM"
        assert saved["candidate_profit_per_unit_rub"] is None
        blocked_finish = repo.finish_price_experiment_phase(
            experiment["experiment_id"], phase["phase_id"],
            expected_state_revision=confirmed["state_revision"],
            expected_phase_state_revision=confirmed["phase_state_revision"],
            expected_result_revision=result["result_revision"],
            idempotency_key="w42-low-sold-finish01",
            owner_id="owner-1", store_id="store-a",
        )
        assert blocked_finish["code"] == "PLANNING_PRICE_EXPERIMENT_PHASE_NOT_READY"
    finally:
        reset_current_tenant_user_id(token)


def test_partial_cpc_is_unknown_not_zero_and_does_not_mark_phase_ready(tmp_path):
    repo, token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        collector = PhaseEvidenceCollector(
            _mature_evidence(performance_status="NOT_REQUESTED"),
        )
        collected = _collect(repo, experiment, phase, confirmed, collector)
        assert collected["error"] is False
        result = _readiness(
            repo, experiment, phase, confirmed,
            now=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
            result_revision=collected["result_revision"], key="w27-cpc-unknown01",
        )
        assert result["status"] == "INSUFFICIENT_DATA"
        saved = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
        )["items"][0]["payload"]
        gates = {item["gate"]: item for item in saved["quality_gates"]}
        assert gates["ADVERTISING_COVERAGE"]["status"] == "FAIL"
        assert gates["ADVERTISING_COVERAGE"]["reason_code"] == "CPC_NOT_CONFIRMED"
    finally:
        reset_current_tenant_user_id(token)


def test_control_warning_is_read_from_complete_paginated_event_history(tmp_path):
    repo, token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        collected = _collect(repo, experiment, phase, confirmed, PhaseEvidenceCollector())
        assert collected["error"] is False
        phase_row = repo.list_price_experiment_phases(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["items"][0]
        flags = dict(phase_row["config"]["control_flags"])
        flags["promotion"] = "CHANGED"
        current_state_revision = confirmed["state_revision"]
        for index in range(11):
            update = repo.record_price_experiment_control_update(
                experiment["experiment_id"], phase["phase_id"], flags,
                expected_state_revision=current_state_revision,
                idempotency_key=f"w27-control-event-{index:02d}",
                owner_id="owner-1", store_id="store-a",
            )
            assert update["error"] is False
            current_state_revision = update["state_revision"]

        current_confirmed = {**confirmed, "state_revision": current_state_revision}
        result = _readiness(
            repo, experiment, phase, current_confirmed,
            now=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
            result_revision=collected["result_revision"], key="w27-control-history-eval01",
        )
        assert result["error"] is False
        saved = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
        )["items"][0]["payload"]
        gates = {item["gate"]: item for item in saved["quality_gates"]}
        assert gates["CONTROL_CONDITIONS"]["status"] == "WARNING"
        assert gates["CONTROL_CONDITIONS"]["reason_code"] == (
            "OWNER_REPORTED_CONDITIONS_CHANGED_OR_UNKNOWN"
        )
        assert "OWNER_REPORTED_PHASE_CONDITIONS_CHANGED_OR_UNKNOWN" in saved["limitations"]
    finally:
        reset_current_tenant_user_id(token)


def test_late_return_refresh_appends_new_collection_and_new_readiness_revision(tmp_path):
    repo, token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        evidence = _mature_evidence(sample=35, delivered=30)
        evidence["collected_at"] = "2026-11-13T12:00:00Z"
        collector = PhaseEvidenceCollector(evidence)
        first_collection = _collect(repo, experiment, phase, confirmed, collector)
        first_readiness = _readiness(
            repo, experiment, phase, confirmed,
            now=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
            result_revision=first_collection["result_revision"],
            key="w27-first-eval01",
        )
        assert first_readiness["status"] == "READY"

        evidence["collected_at"] = "2026-11-14T12:00:00Z"
        evidence["metrics"]["returned_units"] = 4
        refreshed = _collect(
            repo, experiment, phase, confirmed, collector,
            result_revision=first_readiness["result_revision"],
            key="w27-late-source-refresh01",
        )
        assert refreshed["error"] is False
        assert refreshed["collection_revision"] == 2
        assert refreshed["collection_id"] != first_collection["collection_id"]
        second_readiness = _readiness(
            repo, experiment, phase, confirmed,
            now=datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc),
            result_revision=refreshed["result_revision"],
            key="w27-late-result-revision01",
        )
        assert second_readiness["error"] is False
        results = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
        )["items"]
        assert len(results) == 4
        latest_refs = results[0]["payload"]["snapshot_refs"]
        previous_refs = results[2]["payload"]["snapshot_refs"]
        assert refreshed["collection_id"] in latest_refs
        assert first_collection["collection_id"] in previous_refs
        assert latest_refs != previous_refs
        assert results[2]["payload"]["source_as_of"] == "2026-11-13T12:00:00Z"
        assert results[0]["payload"]["source_as_of"] == "2026-11-14T12:00:00Z"
        assert results[2]["payload"]["baseline_profit_per_unit_rub"] is None
        assert results[0]["payload"]["baseline_profit_per_unit_rub"] is None
    finally:
        reset_current_tenant_user_id(token)


def test_incomplete_return_collection_recovers_to_ready_without_rewriting_history(tmp_path):
    repo, token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        evidence = _evidence(returns_status="PARTIAL")
        collector = PhaseEvidenceCollector(evidence)
        first_collection = _collect(repo, experiment, phase, confirmed, collector)
        first_readiness = _readiness(
            repo, experiment, phase, confirmed,
            now=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
            result_revision=first_collection["result_revision"],
            key="w35-incomplete-readiness01",
        )
        assert first_readiness["error"] is False
        assert first_readiness["status"] == "INSUFFICIENT_DATA"
        first_result = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
        )["items"][0]["payload"]
        first_gates = {item["gate"]: item for item in first_result["quality_gates"]}
        assert first_gates["RETURNS_COVERAGE"]["status"] == "FAIL"
        assert first_gates["SOLD_UNIT_DENOMINATOR"]["reason_code"] == (
            "RETURN_SOURCE_INCOMPLETE"
        )
        assert first_result["quantity_basis"] is None

        evidence["collected_at"] = "2026-11-14T12:00:00Z"
        next(item for item in evidence["sources"] if item["name"] == "RETURNS").update(
            {"status": "COMPLETE", "reason": "NONE"},
        )
        evidence["metrics"].update({
            "successful_sale_units": 30,
            "delivered_units": 30,
            "buyout_sample_size": 35,
            "ordered_units": 40,
            "cancelled_units": 5,
            "returned_units": 4,
            "buyout_rate_percent": "85.71",
        })
        refreshed = _collect(
            repo, experiment, phase, confirmed, collector,
            result_revision=first_readiness["result_revision"],
            key="w35-complete-refresh01",
        )
        assert refreshed["error"] is False
        assert refreshed["collection_revision"] == 2
        second_readiness = _readiness(
            repo, experiment, phase, confirmed,
            now=datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc),
            result_revision=refreshed["result_revision"],
            key="w35-complete-readiness01",
        )
        assert second_readiness["error"] is False
        assert second_readiness["status"] == "READY"
        collections = repo.list_price_experiment_phase_collections(
            experiment["experiment_id"], phase["phase_id"],
        )["items"]
        assert len(collections) == 2
        assert collections[0]["payload"]["metrics"]["returned_units"] == 4
        assert collections[1]["payload"]["metrics"]["returned_units"] is None
        results = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
        )["items"]
        assert len(results) == 4
        assert results[0]["payload"]["status"] == "READY"
        assert results[2]["payload"]["status"] == "INSUFFICIENT_DATA"
        assert refreshed["collection_id"] in results[0]["payload"]["snapshot_refs"]
        assert first_collection["collection_id"] in results[2]["payload"]["snapshot_refs"]
    finally:
        reset_current_tenant_user_id(token)
