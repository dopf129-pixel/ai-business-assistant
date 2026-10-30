from copy import deepcopy
from datetime import datetime, timezone

from services.planning_unit_economics_experiment_adapter import (
    PlanningUnitEconomicsExperimentAdapter,
)
from services.unit_economics_experiment_phase_comparison_service import (
    UnitEconomicsExperimentPhaseComparisonService,
)
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.tenant_context import reset_current_tenant_user_id
from test_planning_workspace_unit_economics import (
    _confirm_baseline_phase,
    _context,
    _phase_payload,
    _ready_baseline_phase,
    _result_payload,
    _seed,
)


def _phase(kind, start, end, price, *, snapshot="a" * 64, controls=None):
    return {
        "phase_id": (kind.lower() + "1").ljust(32, "0"),
        "kind": kind,
        "state_revision": 1,
        "config": {
            "planned_price_cents": price,
            "expense_snapshot_id": snapshot,
            "planned_from_date": start,
            "planned_to_date": end,
            "timezone": "Europe/Moscow",
            "control_flags": controls or {
                key: "UNCHANGED" for key in (
                    "inventory", "promotion", "advertising", "card", "cost", "tariff",
                )
            },
        },
    }


def _collection(start, end, collected_at, *, finance_net="1000.00", returned=0):
    return {
        "status": "COMPLETE",
        "collected_at": collected_at,
        "window": {
            "from_date": start, "to_date": end, "timezone": "Europe/Moscow",
        },
        "source_statuses": [
            {"source_key": key, "status": "COMPLETE"}
            for key in ("FINANCE", "RETURNS", "PERFORMANCE")
        ],
        "metrics": {
            "finance_net": finance_net, "gross_seller_revenue": "2000.00",
            "discount_points": "0.00", "acquiring": "-20.00",
            "commission": "-70.00", "logistics": "-105.00",
            "other_fees": "-33.00", "cpc_spend": "100.00",
            "successful_sale_units": 30, "returned_units": returned,
        },
    }


def _ready(revision=2):
    return {
        "result_revision": revision,
        "payload": {
            "schema_version": 1, "status": "READY",
            "quality_gates": [
                {"gate": "CONTROL_CONDITIONS", "status": "PASS",
                 "reason_code": "UNCHANGED_OR_NOT_APPLICABLE"},
                {"gate": "SOLD_UNIT_DENOMINATOR", "status": "PASS",
                 "reason_code": "POSITIVE_SOLD_UNITS"},
            ],
        },
    }


def _frozen_plan(*, cost="10.00", tax_mode="NONE", tax_rate=None, minimum=None):
    return {
        "plan": {
            "payload": {
                "calculation_version": 1,
                "items": [{
                    "identity": {
                        "store_id": "store-a", "offer_id": "offer-1",
                        "sku": "sku-1", "scheme": "FBO",
                    },
                    "inputs": {
                        "cost": cost, "tax_mode": tax_mode,
                        "tax_rate": tax_rate, "minimum_tax_rate": minimum,
                    },
                }],
            },
        },
    }


def _evaluate(*, baseline=None, candidate=None, experiment=None, mode="WINDOW_COST_ALLOCATION",
              frozen=None, now="2026-10-01T12:00:00+00:00"):
    base_phase = _phase("BASELINE", "2026-08-01", "2026-08-07", 10_000)
    candidate_phase = _phase("CANDIDATE", "2026-08-08", "2026-08-14", 9_900)
    baseline_item = {
        "collection_id": "1" * 64,
        "payload": baseline or _collection(
            "2026-08-01", "2026-08-07", "2026-08-08T12:00:00Z",
        ),
    }
    candidate_item = {
        "collection_id": "2" * 64,
        "payload": candidate or _collection(
            "2026-08-08", "2026-08-14", "2026-08-15T12:00:00Z",
            finance_net="1100.00",
        ),
    }
    experiment_row = {
        "store_id": "store-a", "offer_id": "offer-1", "sku": "sku-1",
        "sale_schema": "FBO",
        "config": {"calculation_mode": mode, "decision_threshold_rub": "0.01"},
    }
    if experiment:
        experiment_row.update(experiment)
    return UnitEconomicsExperimentPhaseComparisonService._evaluate(
        experiment_row, base_phase, candidate_phase,
        baseline_item, candidate_item, _ready(), _ready(),
        frozen or _frozen_plan(), datetime.fromisoformat(now),
    )


def test_compatible_mature_phases_compare_observed_net_without_double_subtracting_fees():
    result = _evaluate()
    assert result["error"] is False
    assert result["outcome"] == "CANDIDATE_BETTER_IN_MODEL"
    assert result["baseline_profit_per_unit_rub"] == "23.33"
    assert result["candidate_profit_per_unit_rub"] == "26.67"
    assert result["delta_profit_per_unit_rub"] == "3.34"
    assert result["comparison"]["baseline"]["performance_cpc_reconciliation_rub"] == "100.00"
    assert result["comparison"]["baseline"]["commission_rub"] == "-70.00"
    assert result["comparison"]["baseline"]["profit_total_rub"] == "700.00"
    assert result["comparison"]["relative_delta_percent"] == "14.32"
    assert "OBSERVED_WINDOW_MODEL_NOT_CAUSAL_PRICE_EFFECT" in result["limitations"]


def test_phase_events_are_read_using_repository_page_limit():
    class PagedRepository:
        def __init__(self):
            self.calls = []

        def list_price_experiment_events(self, experiment_id, *, phase_id, limit, offset,
                                        owner_id, store_id):
            self.calls.append((limit, offset))
            assert 1 <= limit <= 10
            rows = [{"event_revision": revision} for revision in range(1, 12)]
            page = rows[offset:offset + limit]
            has_more = offset + limit < len(rows)
            return {
                "error": False, "items": page, "has_more": has_more,
                "next_offset": offset + limit if has_more else None,
            }

    repository = PagedRepository()
    result = UnitEconomicsExperimentPhaseComparisonService(repository)._phase_events(
        "experiment", "phase", "owner", "store",
    )

    assert result["error"] is False
    assert len(result["items"]) == 11
    assert result["latest_revision"] == 11
    assert repository.calls == [(10, 0), (10, 10)]


def test_phase_event_scan_fails_closed_after_bounded_history_limit():
    class PagedRepository:
        def list_price_experiment_events(self, experiment_id, *, phase_id, limit, offset,
                                        owner_id, store_id):
            return {
                "error": False,
                "items": [{"event_revision": offset + index + 1} for index in range(limit)],
                "has_more": True,
                "next_offset": offset + limit,
            }

    result = UnitEconomicsExperimentPhaseComparisonService(PagedRepository())._phase_events(
        "experiment", "phase", "owner", "store",
    )

    assert result == {
        "error": True, "code": "EXPERIMENT_PHASE_EVENT_HISTORY_INCOMPLETE",
        "read_only": True, "source_io": False,
    }


def test_threshold_uses_rounded_rub_per_unit_and_reports_no_clear_difference():
    candidate = _collection(
        "2026-08-08", "2026-08-14", "2026-08-15T12:00:00Z",
        finance_net="1000.30",
    )
    experiment = {"config": {
        "calculation_mode": "WINDOW_COST_ALLOCATION", "decision_threshold_rub": "0.02",
    }}
    result = _evaluate(candidate=candidate, experiment=experiment)
    assert result["baseline_profit_per_unit_rub"] == "23.33"
    assert result["candidate_profit_per_unit_rub"] == "23.34"
    assert result["delta_profit_per_unit_rub"] == "0.01"
    assert result["outcome"] == "NO_CLEAR_DIFFERENCE"
    assert result["status"] == "NO_CLEAR_DIFFERENCE"


def test_each_supported_tax_mode_reuses_canonical_tax_service_with_discount_points():
    discounted_baseline = _collection(
        "2026-08-01", "2026-08-07", "2026-08-08T12:00:00Z",
        finance_net="1000.00",
    )
    discounted_candidate = _collection(
        "2026-08-08", "2026-08-14", "2026-08-15T12:00:00Z",
        finance_net="1100.00",
    )
    for row in (discounted_baseline, discounted_candidate):
        row["metrics"]["gross_seller_revenue"] = "2000.00"
        row["metrics"]["discount_points"] = "100.00"

    income_tax = _evaluate(
        baseline=discounted_baseline, candidate=discounted_candidate,
        frozen=_frozen_plan(tax_mode="USN_INCOME", tax_rate="6.00"),
    )
    assert income_tax["comparison"]["baseline"]["tax_rub"] == "114.00"
    assert income_tax["comparison"]["candidate"]["tax_rub"] == "114.00"
    assert income_tax["comparison"]["baseline"]["profit_per_unit_rub"] == "19.53"

    income_minus_expenses = _evaluate(
        baseline=discounted_baseline, candidate=discounted_candidate,
        frozen=_frozen_plan(
            tax_mode="USN_INCOME_MINUS_EXPENSES",
            tax_rate="15.00", minimum="1.00",
        ),
    )
    assert income_minus_expenses["comparison"]["baseline"]["tax_rub"] == "90.00"
    assert income_minus_expenses["comparison"]["candidate"]["tax_rub"] == "105.00"


def test_nonpositive_baseline_never_gets_relative_improvement_percent():
    baseline = _collection(
        "2026-08-01", "2026-08-07", "2026-08-08T12:00:00Z",
        finance_net="300.00",
    )
    result = _evaluate(baseline=baseline)
    assert result["baseline_profit_per_unit_rub"] == "0.00"
    assert result["candidate_profit_per_unit_rub"] == "26.67"
    assert result["comparison"]["relative_delta_percent"] is None

    negative = _collection(
        "2026-08-01", "2026-08-07", "2026-08-08T12:00:00Z",
        finance_net="0.00",
    )
    result = _evaluate(baseline=negative)
    assert result["baseline_profit_per_unit_rub"] == "-10.00"
    assert result["comparison"]["relative_delta_percent"] is None


def test_returns_without_disposition_and_strict_cohort_mode_are_incomparable():
    baseline = _collection(
        "2026-08-01", "2026-08-07", "2026-08-08T12:00:00Z", returned=1,
    )
    result = _evaluate(baseline=baseline)
    assert result["outcome"] == "INCOMPARABLE"
    assert result["comparison"] is None
    assert any(gate["reason_code"] == "RETURNED_UNIT_DISPOSITION_UNKNOWN"
               for gate in result["quality_gates"])

    result = _evaluate(mode="STRICT_RETAINED_COHORT")
    assert result["outcome"] == "INCOMPARABLE"
    assert any(gate["reason_code"] == "STRICT_RETAINED_COHORT_DISPOSITION_UNAVAILABLE"
               for gate in result["quality_gates"])


def test_overlapping_windows_and_stale_source_as_of_are_not_compared():
    candidate = _collection(
        "2026-08-05", "2026-08-11", "2026-08-12T12:00:00Z",
        finance_net="1100.00",
    )
    result = _evaluate(candidate=candidate)
    assert result["outcome"] == "INCOMPARABLE"
    assert any(gate["reason_code"] == "PHASE_WINDOWS_OVERLAP_OR_REVERSED"
               for gate in result["quality_gates"])

    candidate = _collection(
        "2026-08-08", "2026-08-14", "2026-08-17T12:00:00Z",
        finance_net="1100.00",
    )
    result = _evaluate(candidate=candidate)
    assert result["outcome"] == "INCOMPARABLE"
    assert any(gate["reason_code"] == "SOURCE_AS_OF_MATURITY_DIFFERS"
               for gate in result["quality_gates"])


def test_changed_controls_and_different_cost_snapshot_block_comparison():
    candidate_phase = _phase(
        "CANDIDATE", "2026-08-08", "2026-08-14", 9_900, snapshot="b" * 64,
    )
    baseline_phase = _phase("BASELINE", "2026-08-01", "2026-08-07", 10_000)
    experiment = {"config": {
        "calculation_mode": "WINDOW_COST_ALLOCATION", "decision_threshold_rub": "0.01",
    }, "store_id": "store-a", "offer_id": "offer-1", "sku": "sku-1", "sale_schema": "FBO"}
    base_item = {"collection_id": "1" * 64,
                 "payload": _collection("2026-08-01", "2026-08-07", "2026-08-08T12:00:00Z")}
    cand_item = {"collection_id": "2" * 64,
                 "payload": _collection("2026-08-08", "2026-08-14", "2026-08-15T12:00:00Z")}
    result = UnitEconomicsExperimentPhaseComparisonService._evaluate(
        experiment, baseline_phase, candidate_phase, base_item, cand_item,
        _ready(), _ready(), _frozen_plan(), datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    assert result["outcome"] == "INCOMPARABLE"
    assert any(gate["reason_code"] == "COST_OR_EXPENSE_SNAPSHOT_CHANGED"
               for gate in result["quality_gates"])

    changed = deepcopy(candidate_phase)
    changed["config"]["expense_snapshot_id"] = "a" * 64
    changed["config"]["control_flags"]["promotion"] = "CHANGED"
    result = UnitEconomicsExperimentPhaseComparisonService._evaluate(
        experiment, baseline_phase, changed, base_item, cand_item,
        _ready(), _ready(), _frozen_plan(), datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    assert result["outcome"] == "INCOMPARABLE"
    reasons = {gate["reason_code"] for gate in result["quality_gates"]}
    assert "PHASE_CONTROL_FLAGS_CHANGED_OR_UNKNOWN" in reasons


def test_v2_result_is_allowlisted_and_v1_result_remains_readable():
    result = _evaluate()
    payload = {
        "schema_version": 2, "status": result["status"],
        "source_as_of": result["source_as_of"],
        "snapshot_refs": ["a" * 64, "1" * 64, "2" * 64],
        "baseline_profit_per_unit_rub": result["baseline_profit_per_unit_rub"],
        "candidate_profit_per_unit_rub": result["candidate_profit_per_unit_rub"],
        "delta_profit_per_unit_rub": result["delta_profit_per_unit_rub"],
        "quantity_basis": "SOLD_UNITS_WINDOW",
        "window": {"from_date": "2026-08-08", "to_date": "2026-08-14",
                   "timezone": "Europe/Moscow"},
        "quality_gates": result["quality_gates"],
        "limitations": result["limitations"], "outcome": result["outcome"],
        "comparison": result["comparison"],
    }
    assert PlanningUnitEconomicsExperimentAdapter.normalize_result(payload) is not None
    malformed = deepcopy(payload)
    malformed["comparison"]["baseline"]["profit_total_rub"] = "999.99"
    assert PlanningUnitEconomicsExperimentAdapter.normalize_result(malformed) is None
    legacy = {
        key: value for key, value in payload.items()
        if key != "comparison"
    }
    legacy["schema_version"] = 1
    assert PlanningUnitEconomicsExperimentAdapter.normalize_result(legacy) is not None


def test_repository_rejects_comparison_if_baseline_revision_changed_before_append(tmp_path):
    repo = PlanningWorkspaceRepository(
        db_path=tmp_path / "comparison-guard.sqlite",
        clock=lambda: datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc),
    )
    saved, snapshot, experiment = _seed(repo)
    token = _context()
    try:
        baseline = _ready_baseline_phase(repo, saved, snapshot, experiment)
        confirmed = _confirm_baseline_phase(repo, experiment, baseline)
        assert confirmed["error"] is False
        ready_payload = _result_payload(snapshot["snapshot_id"])
        ready_payload.update({"status": "READY", "outcome": "CONTINUE_COLLECTING"})
        first = repo.append_price_experiment_result(
            experiment["experiment_id"], baseline["phase_id"], ready_payload,
            expected_state_revision=confirmed["state_revision"],
            expected_phase_state_revision=confirmed["phase_state_revision"],
            expected_result_revision=0, idempotency_key="w28-base-result01",
        )
        assert first["error"] is False
        finished = repo.finish_price_experiment_phase(
            experiment["experiment_id"], baseline["phase_id"],
            expected_state_revision=confirmed["state_revision"],
            expected_phase_state_revision=confirmed["phase_state_revision"],
            expected_result_revision=1, idempotency_key="w28-base-finish01",
        )
        assert finished["error"] is False
        candidate_payload = _phase_payload(
            snapshot["snapshot_id"], kind="CANDIDATE", segment=2, price=9_900,
        )
        candidate_payload.update({
            "planned_from_date": "2026-11-07", "planned_to_date": "2026-11-13",
        })
        candidate = repo.create_price_experiment_phase(
            experiment["experiment_id"], candidate_payload,
            expected_state_revision=finished["state_revision"],
            idempotency_key="w28-cand-phase01",
        )
        assert candidate["error"] is False
        confirmed_candidate = repo.confirm_price_experiment_phase(
            experiment["experiment_id"], candidate["phase_id"],
            seller_price_cents=9_900,
            effective_from="2026-11-06T12:00:00+03:00", owner_confirmed=True,
            expected_state_revision=candidate["experiment_state_revision"],
            expected_phase_state_revision=candidate["phase_state_revision"],
            idempotency_key="w28-confirm-candidate1",
        )
        assert confirmed_candidate["error"] is False
        baseline_row = repo.list_price_experiment_phases(
            experiment["experiment_id"], limit=10,
        )["items"][0]
        changed_baseline = repo.append_price_experiment_result(
            experiment["experiment_id"], baseline["phase_id"], ready_payload,
            expected_state_revision=confirmed_candidate["state_revision"],
            expected_phase_state_revision=baseline_row["state_revision"],
            expected_result_revision=1, idempotency_key="w28-base-result02",
        )
        assert changed_baseline["error"] is False
        stale = repo.append_price_experiment_result(
            experiment["experiment_id"], candidate["phase_id"],
            _result_payload(snapshot["snapshot_id"]),
            expected_state_revision=confirmed_candidate["state_revision"],
            expected_phase_state_revision=confirmed_candidate["phase_state_revision"],
            expected_result_revision=0, idempotency_key="w28-stale-compare01",
            comparison_guard={
                "baseline_phase_id": baseline["phase_id"],
                "baseline_state_revision": finished["phase_state_revision"],
                "baseline_result_revision": 1,
                "baseline_collection_id": "1" * 64,
                "candidate_collection_id": "2" * 64,
                "baseline_control_event_revision": 0,
                "candidate_control_event_revision": 0,
            },
        )
        assert stale["error"] is True
        assert stale["code"] == "PLANNING_PRICE_EXPERIMENT_COMPARISON_CONFLICT"
        history = repo.list_price_experiment_results(
            experiment["experiment_id"], candidate["phase_id"],
        )
        assert history["error"] is False
        assert history["items"] == []
    finally:
        reset_current_tenant_user_id(token)
