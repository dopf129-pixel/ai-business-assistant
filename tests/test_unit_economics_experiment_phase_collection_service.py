from datetime import datetime, timezone

from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    current_period_profit_trace,
)
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.unit_economics_experiment_phase_collection_service import (
    UnitEconomicsExperimentPhaseCollectionService,
)
from services.tenant_context import reset_current_tenant_user_id

from test_planning_workspace_unit_economics import (
    _confirm_baseline_phase,
    _context,
    _ready_baseline_phase,
    _seed,
)


class PhaseEvidenceCollector:
    def __init__(self, evidence=None, callback=None):
        self.evidence = evidence or _evidence()
        self.callback = callback
        self.calls = []

    def collect_window(self, observation_id, *, date_from, date_to):
        self.calls.append((observation_id, date_from, date_to))
        if self.callback:
            self.callback()
        return self.evidence


def _evidence(*, returns_status="COMPLETE", performance_status="COMPLETE"):
    return {
        "error": False,
        "status": "INSUFFICIENT_DATA",
        "identity": {
            "store_id": "store-a", "product_id": "product-1",
            "offer_id": "offer-1", "sku": "sku-1", "sale_schema": "FBO",
        },
        "seller_price_cents": 10_000,
        "window": {
            "from": "2026-10-30", "to": "2026-11-05",
            "timezone": "Europe/Moscow", "date_basis": "SOURCE_CALENDAR_DATE",
        },
        "collected_at": "2026-11-06T12:00:00Z",
        "sources": [
            {"name": "FINANCE", "status": "COMPLETE", "reason": "NONE"},
            {"name": "RETURNS", "status": returns_status, "reason": "SAMPLE_PENDING"},
            {"name": "PERFORMANCE", "status": performance_status,
             "reason": "PERFORMANCE_NOT_CONFIGURED" if performance_status != "COMPLETE" else "NONE"},
            {"name": "OWNER_DECLARED_PRICE", "status": "COMPLETE", "reason": "NONE"},
            {"name": "SELLER_PRICE", "status": "SOURCE_UNAVAILABLE", "reason": "NO_PRICE_HISTORY"},
            {"name": "COST", "status": "NOT_REQUESTED", "reason": "NONE"},
        ],
        "metrics": {
            "gross_seller_revenue": "700.00", "discount_points": "0.00",
            "finance_net": "300.00", "acquiring": "-2.00", "commission": "-70.00",
            "logistics": "-105.00", "other_fees": "-33.00", "cpc_spend": "12.50",
            "successful_sale_units": 4 if returns_status == "COMPLETE" else None,
            "ordered_units": 5, "delivered_units": 4 if returns_status == "COMPLETE" else None,
            "cancelled_units": 1, "returned_units": 0 if returns_status == "COMPLETE" else None,
            "buyout_rate_percent": "80.00" if returns_status == "COMPLETE" else None,
            "buyout_sample_size": 4 if returns_status == "COMPLETE" else None,
        },
        "read_only": True, "executed": False,
    }


def _active_phase(tmp_path):
    now = datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc)
    repo = PlanningWorkspaceRepository(
        db_path=tmp_path / "planning.sqlite", clock=lambda: now,
    )
    token = _context()
    saved, snapshot, experiment = _seed(repo)
    phase = _ready_baseline_phase(repo, saved, snapshot, experiment)
    confirmed = _confirm_baseline_phase(repo, experiment, phase)
    assert confirmed["error"] is False
    return repo, token, experiment, phase, confirmed


def _service(repo, collector, *, now=None):
    return UnitEconomicsExperimentPhaseCollectionService(
        repo, collector,
        clock=lambda: now or datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc),
    )


def _collect(
    service, experiment, phase, confirmed, *, key="w26-collect-phase01",
    operation_trace=None,
):
    return service.collect_phase(
        experiment["experiment_id"], phase["phase_id"],
        expected_state_revision=confirmed["state_revision"],
        expected_phase_state_revision=confirmed["phase_state_revision"],
        expected_result_revision=0, idempotency_key=key,
        owner_id="owner-1", store_id="store-a",
        operation_trace=operation_trace,
    )


def test_collects_exact_completed_phase_and_atomically_links_pending_result(tmp_path):
    repo, token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        collector = PhaseEvidenceCollector()
        result = _collect(_service(repo, collector), experiment, phase, confirmed)
        assert result["error"] is False
        assert result["status"] == "COMPLETE"
        assert result["result_status"] == "WAITING_FOR_DATA"
        assert result["outcome"] == "CONTINUE_COLLECTING"
        assert collector.calls == [(
            confirmed["observation_id"], "2026-10-30", "2026-11-05",
        )]

        collections = repo.list_price_experiment_phase_collections(
            experiment["experiment_id"], phase["phase_id"],
        )
        results = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
        )
        assert collections["error"] is False and len(collections["items"]) == 1
        assert results["error"] is False and len(results["items"]) == 1
        collection = collections["items"][0]
        payload = collection["payload"]
        assert collection["collection_id"] == result["collection_id"]
        assert payload["metrics"]["commission"] == "-70.00"
        assert payload["metrics"]["cpc_spend"] == "12.50"
        assert payload["metrics"]["successful_sale_units"] == 4
        assert payload["price_history_verified"] is False
        saved_result = results["items"][0]["payload"]
        assert result["result_revision"] == 1
        assert collection["collection_revision"] == result["collection_revision"] == 1
        assert saved_result["status"] == "WAITING_FOR_DATA"
        assert saved_result["baseline_profit_per_unit_rub"] is None
        assert saved_result["candidate_profit_per_unit_rub"] is None
        assert collection["collection_id"] in saved_result["snapshot_refs"]
        assert len(saved_result["snapshot_refs"]) == 2
        assert "raw" not in repr(payload).lower()
    finally:
        reset_current_tenant_user_id(token)


def test_partial_sources_keep_signed_credits_unknown_units_and_never_claim_profit(tmp_path):
    repo, token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        evidence = _evidence(returns_status="PARTIAL", performance_status="NOT_REQUESTED")
        evidence["metrics"]["commission"] = "1.25"  # net credit stays signed
        evidence["metrics"]["successful_sale_units"] = None
        evidence["sources"][0]["reason"] = "12345678901234567890"
        collector = PhaseEvidenceCollector(evidence)
        result = _collect(_service(repo, collector), experiment, phase, confirmed)
        assert result["error"] is False
        assert result["status"] == "PARTIAL"
        collection = repo.list_price_experiment_phase_collections(
            experiment["experiment_id"], phase["phase_id"],
        )["items"][0]["payload"]
        finance = next(
            item for item in collection["source_statuses"]
            if item["source_key"] == "FINANCE"
        )
        assert finance["reason_code"] == "UNCLASSIFIED_SOURCE_REASON"
        assert "12345678901234567890" not in repr(collection)
        assert collection["metrics"]["commission"] == "1.25"
        assert collection["metrics"]["successful_sale_units"] is None
        saved_result = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
        )["items"][0]["payload"]
        assert saved_result["status"] == "WAITING_FOR_DATA"
        assert saved_result["quantity_basis"] is None
        assert saved_result["outcome"] == "CONTINUE_COLLECTING"
    finally:
        reset_current_tenant_user_id(token)


def test_idempotent_callback_returns_saved_collection_without_second_source_read(tmp_path):
    repo, token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        collector = PhaseEvidenceCollector()
        service = _service(repo, collector)
        first = _collect(service, experiment, phase, confirmed)
        replay = _collect(service, experiment, phase, confirmed)
        assert first["error"] is False and replay["error"] is False
        assert replay["idempotent_replay"] is True
        assert replay["collection_id"] == first["collection_id"]
        assert collector.calls == [(confirmed["observation_id"], "2026-10-30", "2026-11-05")]
    finally:
        reset_current_tenant_user_id(token)


def test_late_source_response_after_pause_is_rejected_without_persisting_snapshot(tmp_path):
    repo, token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        def pause_during_read():
            paused = repo.pause_price_experiment_phase(
                experiment["experiment_id"], phase["phase_id"],
                expected_state_revision=confirmed["state_revision"],
                expected_phase_state_revision=confirmed["phase_state_revision"],
                idempotency_key="w26-pause-during-read01",
                owner_id="owner-1", store_id="store-a",
            )
            assert paused["error"] is False

        collector = PhaseEvidenceCollector(callback=pause_during_read)
        result = _collect(_service(repo, collector), experiment, phase, confirmed)
        assert result["error"] is True
        assert result["code"] == "PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT"
        assert repo.list_price_experiment_phase_collections(
            experiment["experiment_id"], phase["phase_id"],
        )["items"] == []
        assert repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
        )["items"] == []
    finally:
        reset_current_tenant_user_id(token)


def test_cooperative_cancellation_discards_late_response(tmp_path):
    repo, token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        def cancel_during_read():
            active = current_period_profit_trace()
            assert active is not None
            active.cancel()

        collector = PhaseEvidenceCollector(callback=cancel_during_read)
        result = _collect(_service(repo, collector), experiment, phase, confirmed)
        assert result["error"] is True
        assert result["code"] == "EXPERIMENT_COLLECTION_CANCELLED"
        assert repo.list_price_experiment_phase_collections(
            experiment["experiment_id"], phase["phase_id"],
        )["items"] == []
    finally:
        reset_current_tenant_user_id(token)


def test_phase_rejects_observation_with_different_confirmed_time_or_timezone(tmp_path):
    repo, token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        original_get = repo.get_unit_price_observation
        observation = original_get(
            confirmed["observation_id"], owner_id="owner-1", store_id="store-a",
        )["observation"]

        for changed in (
            {**observation, "effective_from": "2026-10-29T13:00:00+03:00"},
            {**observation, "window_timezone": "UTC"},
        ):
            repo.get_unit_price_observation = lambda *args, **kwargs: {
                "error": False, "observation": changed,
            }
            collector = PhaseEvidenceCollector()
            result = _collect(_service(repo, collector), experiment, phase, confirmed)
            assert result["error"] is True
            assert result["code"] == "EXPERIMENT_PHASE_OBSERVATION_MISMATCH"
            assert collector.calls == []
        repo.get_unit_price_observation = original_get
    finally:
        reset_current_tenant_user_id(token)


def test_child_collection_uses_remaining_parent_request_budget_and_downgrades_status(
    tmp_path,
):
    repo, token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        parent = PeriodProfitOperationTrace(
            operation="owner_request", time_budget_seconds=30,
            ozon_request_budget=3,
        )
        assert parent.reserve_ozon_request("previous_operation")["error"] is False
        assert parent.reserve_ozon_request("previous_operation")["error"] is False

        def exhaust_shared_budget():
            active = current_period_profit_trace()
            assert active is not None
            assert active.parent is parent
            assert active.ozon_request_budget == 1
            assert active.reserve_ozon_request("synthetic")["error"] is False
            assert active.reserve_ozon_request("synthetic")["error"] is True

        collector = PhaseEvidenceCollector(callback=exhaust_shared_budget)
        result = _collect(
            _service(repo, collector), experiment, phase, confirmed,
            operation_trace=parent,
        )
        assert result["error"] is False
        assert result["status"] == "PARTIAL"
        payload = repo.list_price_experiment_phase_collections(
            experiment["experiment_id"], phase["phase_id"],
        )["items"][0]["payload"]
        assert payload["budget"]["http_attempts"] == 1
        assert payload["budget"]["http_attempt_limit"] == 1
        assert payload["budget"]["reason_code"] == "HTTP_ATTEMPT_BUDGET_EXHAUSTED"
        assert parent.ozon_requests_reserved == 3
    finally:
        reset_current_tenant_user_id(token)


def test_late_response_after_shared_time_budget_is_discarded(tmp_path):
    repo, token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        fake_now = [0.0]
        parent = PeriodProfitOperationTrace(
            operation="owner_request", time_budget_seconds=30,
            ozon_request_budget=10, clock=lambda: fake_now[0],
        )

        def exceed_shared_time_budget():
            fake_now[0] = 31.0

        collector = PhaseEvidenceCollector(callback=exceed_shared_time_budget)
        result = _collect(
            _service(repo, collector), experiment, phase, confirmed,
            operation_trace=parent,
        )
        assert result["error"] is True
        assert result["code"] == "EXPERIMENT_COLLECTION_TIME_BUDGET_EXHAUSTED"
        assert repo.list_price_experiment_phase_collections(
            experiment["experiment_id"], phase["phase_id"],
        )["items"] == []
    finally:
        reset_current_tenant_user_id(token)


def test_window_must_be_complete_before_any_source_is_called(tmp_path):
    repo, token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        collector = PhaseEvidenceCollector()
        service = _service(
            repo, collector,
            now=datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc),
        )
        result = _collect(service, experiment, phase, confirmed)
        assert result["error"] is True
        assert result["code"] == "EXPERIMENT_PHASE_WINDOW_NOT_COMPLETED"
        assert collector.calls == []
    finally:
        reset_current_tenant_user_id(token)


def test_snapshot_and_result_rollback_together_when_result_insert_fails(tmp_path):
    repo, token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        experiment_revisions_before = repo.list_price_experiment_revisions(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["items"]
        phase_revisions_before = repo.list_price_experiment_phase_revisions(
            experiment["experiment_id"], phase["phase_id"],
            owner_id="owner-1", store_id="store-a",
        )["items"]
        connection = repo.get_connection()
        try:
            connection.execute("""CREATE TRIGGER reject_w26_result BEFORE INSERT
                ON planning_price_experiment_results
                BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
            connection.commit()
        finally:
            connection.close()
        collector = PhaseEvidenceCollector()
        result = _collect(_service(repo, collector), experiment, phase, confirmed)
        assert result["error"] is True
        assert result["code"] == "PLANNING_PRICE_EXPERIMENT_COLLECTION_CONFLICT"
        assert repo.list_price_experiment_phase_collections(
            experiment["experiment_id"], phase["phase_id"],
        )["items"] == []
        assert repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
        )["items"] == []
        experiment_after = repo.get_price_experiment(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["experiment"]
        phase_after = repo.list_price_experiment_phases(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["items"][0]
        assert experiment_after["result_revision"] == 0
        assert phase_after["result_revision"] == 0
        assert phase_after["state_revision"] == confirmed["phase_state_revision"]
        assert repo.list_price_experiment_revisions(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["items"] == experiment_revisions_before
        assert repo.list_price_experiment_phase_revisions(
            experiment["experiment_id"], phase["phase_id"],
            owner_id="owner-1", store_id="store-a",
        )["items"] == phase_revisions_before
    finally:
        reset_current_tenant_user_id(token)
