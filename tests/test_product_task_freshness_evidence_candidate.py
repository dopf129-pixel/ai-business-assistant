from copy import deepcopy

from app.product_task_freshness_evidence_candidate import (
    build_freshness_evidence_candidate,
)


def _refresh(*results):
    return {
        "request_id": "refresh:d1",
        "draft_id": "d1",
        "sku": "hook-2",
        "status": "COMPLETED",
        "results": list(results),
        "source_freshness_proven": False,
        "executed": False,
    }


def _result(component, data, provider="Provider", method="read"):
    return {
        "component": component,
        "provider": provider,
        "method": method,
        "data": data,
        "source_freshness_proven": False,
    }


def test_observation_only_builds_candidate_without_proving_source_freshness():
    refresh = _refresh(
        _result("sales", {
            "sales_observed_at": "2026-08-29T12:00:00+00:00",
        }),
        _result("stock", {
            "stock_observed_at": "2026-08-29T12:00:01+00:00",
        }),
    )

    result = build_freshness_evidence_candidate(refresh)

    assert result["status"] == "CANDIDATE_READY"
    assert result["source_evidence_count"] == 0
    assert result["observation_evidence_count"] == 2
    assert result["source_evidence_candidate_present"] is False
    assert result["source_freshness_proven"] is False
    assert result["evidence_update"] == {
        "sales_observed_at": "2026-08-29T12:00:00+00:00",
        "stock_observed_at": "2026-08-29T12:00:01+00:00",
    }
    assert result["task_draft_mutated"] is False
    assert result["executed"] is False


def test_real_canonical_source_timestamp_is_candidate_until_guard_validates_it():
    refresh = _refresh(
        _result("sales", {
            "sales_source_recorded_at": "2026-08-29T11:59:00+00:00",
            "sales_observed_at": "2026-08-29T12:00:00+00:00",
        })
    )

    result = build_freshness_evidence_candidate(refresh)
    candidate = result["candidates"][0]

    assert result["source_evidence_count"] == 1
    assert result["source_evidence_candidate_present"] is True
    assert result["source_freshness_proven"] is False
    assert result["requires_freshness_guard_validation"] is True
    assert candidate["source_freshness_proven"] is False
    assert candidate["requires_freshness_guard_validation"] is True
    assert result["evidence_update"]["sales_source_recorded_at"] == (
        "2026-08-29T11:59:00+00:00"
    )


def test_unit_economics_as_of_is_observation_only_and_cache_time_is_ignored():
    refresh = _refresh(
        _result("unit_economics", {
            "as_of": "2026-08-29T12:00:00+00:00",
            "cache": {
                "status": "hit",
                "cached_at": "2026-08-29T11:58:00+00:00",
            },
        })
    )

    result = build_freshness_evidence_candidate(refresh)
    candidate = result["candidates"][0]

    assert result["evidence_update"] == {
        "unit_economics_observed_at": "2026-08-29T12:00:00+00:00",
    }
    assert candidate["cache_metadata_ignored"] is True
    assert candidate["source_evidence_present"] is False
    assert result["source_freshness_proven"] is False


def test_unrelated_timestamps_are_not_promoted_to_freshness_evidence():
    original = _refresh(
        _result("stock", {
            "updated_at": "2026-08-29T12:00:00+00:00",
            "created_at": "2026-08-29T11:00:00+00:00",
            "requested_at": "2026-08-29T12:00:00+00:00",
        })
    )
    snapshot = deepcopy(original)

    result = build_freshness_evidence_candidate(original)

    assert result["status"] == "NO_EVIDENCE_CANDIDATE"
    assert result["evidence_update"] == {}
    assert result["source_freshness_proven"] is False
    assert original == snapshot


def test_unknown_component_is_ignored_without_execution_or_mutation():
    result = build_freshness_evidence_candidate(
        _refresh(_result("advertising", {"observed_at": "now"}))
    )

    assert result["status"] == "NO_EVIDENCE_CANDIDATE"
    assert result["candidate_count"] == 0
    assert result["persistent"] is False
    assert result["product_decision_mutated"] is False
    assert result["task_draft_mutated"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
