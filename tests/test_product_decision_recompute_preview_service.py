from copy import deepcopy

from services.product_decision_recompute_preview_service import (
    ProductDecisionRecomputePreviewService,
)


class FakeDecisionService:
    def __init__(self, result=None, error=None):
        self.result = result or {
            "product_id": 42,
            "sku": "hook-2",
            "decision_type": "HOLD_STOCK",
            "priority": "LOW",
            "reasons": ["POSITIVE_UNIT_PROFIT"],
            "confidence": "HIGH",
            "missing_data": [],
        }
        self.error = error
        self.calls = []

    def decide(self, metrics):
        self.calls.append(deepcopy(metrics))
        if self.error:
            raise self.error
        return deepcopy(self.result)


def _authorization(**values):
    result = {
        "status": "PRODUCT_DECISION_RECOMPUTE_REVIEW_AUTHORIZED",
        "recompute_authorization_id": "recompute-review-authorization:recompute-review-eligibility:freshness-state-promotion:draft-1:hook-2:abc123",
        "recompute_eligibility_id": "recompute-review-eligibility:freshness-state-promotion:draft-1:hook-2:abc123",
        "freshness_promotion_id": "freshness-state-promotion:draft-1:hook-2:abc123",
        "draft_id": "draft-1",
        "sku": "hook-2",
        "decision": "AUTHORIZE",
        "recompute_authorized": True,
        "recompute_rejected": False,
        "recompute_allowed": True,
        "recompute_started": False,
        "authorization_evidence": {
            "sales_source_recorded_at": "2026-08-29T13:00:00+00:00",
            "stock_source_recorded_at": "2026-08-29T13:01:00+00:00",
        },
        "authorization_evidence_count": 2,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def _metrics(**values):
    result = {
        "product_id": 42,
        "sku": "hook-2",
        "sales_velocity": 3.0,
        "current_stock": 20,
        "days_of_stock": 6.6,
        "stock_priority": "LOW",
        "profit_per_unit": 35.1,
        "margin_percent": 36.56,
        "sales_trend": "STABLE",
        "missing_data": [],
    }
    result.update(values)
    return result


def test_authorized_recompute_builds_non_persistent_preview():
    decision_service = FakeDecisionService()
    service = ProductDecisionRecomputePreviewService(decision_service)
    authorization = _authorization()
    metrics = _metrics()
    authorization_before = deepcopy(authorization)
    metrics_before = deepcopy(metrics)

    result = service.recompute_preview(authorization, metrics)

    assert result["status"] == "PRODUCT_DECISION_RECOMPUTE_PREVIEW_READY"
    assert result["recompute_allowed"] is True
    assert result["recompute_started"] is True
    assert result["recompute_preview_computed"] is True
    assert result["product_decision_recomputed"] is True
    assert result["product_decision_mutated"] is False
    assert result["product_decision_persisted"] is False
    assert result["persistent"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
    assert result["preview_decision"]["decision_type"] == "HOLD_STOCK"
    assert decision_service.calls == [metrics_before]
    assert authorization == authorization_before
    assert metrics == metrics_before


def test_rejected_authorization_is_blocked_without_decision_call():
    decision_service = FakeDecisionService()
    result = ProductDecisionRecomputePreviewService(decision_service).recompute_preview(
        _authorization(status="PRODUCT_DECISION_RECOMPUTE_REVIEW_REJECTED", decision="REJECT", recompute_authorized=False, recompute_rejected=True, recompute_allowed=False),
        _metrics(),
    )
    assert result["code"] == "RECOMPUTE_AUTHORIZATION_STATUS_INVALID"
    assert decision_service.calls == []


def test_forged_authorization_id_is_blocked():
    result = ProductDecisionRecomputePreviewService(FakeDecisionService()).recompute_preview(
        _authorization(recompute_authorization_id="forged"), _metrics()
    )
    assert result["code"] == "RECOMPUTE_AUTHORIZATION_ID_MISMATCH"


def test_prestarted_recompute_is_blocked():
    result = ProductDecisionRecomputePreviewService(FakeDecisionService()).recompute_preview(
        _authorization(recompute_started=True), _metrics()
    )
    assert result["code"] == "RECOMPUTE_PREVIEW_AUTHORIZATION_BOUNDARY_VIOLATION"


def test_execution_boundary_violation_is_blocked():
    result = ProductDecisionRecomputePreviewService(FakeDecisionService()).recompute_preview(
        _authorization(execution_ready=True), _metrics()
    )
    assert result["code"] == "RECOMPUTE_PREVIEW_SAFETY_BOUNDARY_VIOLATION"


def test_unsafe_authorization_evidence_is_blocked():
    evidence = deepcopy(_authorization()["authorization_evidence"])
    evidence["decision_type"] = "CHANGE_PRICE"
    result = ProductDecisionRecomputePreviewService(FakeDecisionService()).recompute_preview(
        _authorization(authorization_evidence=evidence, authorization_evidence_count=3),
        _metrics(),
    )
    assert result["code"] == "RECOMPUTE_PREVIEW_EVIDENCE_UNSAFE"


def test_authorization_evidence_count_mismatch_is_blocked():
    result = ProductDecisionRecomputePreviewService(FakeDecisionService()).recompute_preview(
        _authorization(authorization_evidence_count=1), _metrics()
    )
    assert result["code"] == "RECOMPUTE_PREVIEW_EVIDENCE_COUNT_MISMATCH"


def test_metrics_sku_mismatch_is_blocked_before_decision_call():
    decision_service = FakeDecisionService()
    result = ProductDecisionRecomputePreviewService(decision_service).recompute_preview(
        _authorization(), _metrics(sku="other")
    )
    assert result["code"] == "RECOMPUTE_PREVIEW_SKU_MISMATCH"
    assert decision_service.calls == []


def test_decision_failure_is_fail_closed():
    result = ProductDecisionRecomputePreviewService(
        FakeDecisionService(error=RuntimeError("boom"))
    ).recompute_preview(_authorization(), _metrics())
    assert result["code"] == "RECOMPUTE_PREVIEW_CALCULATION_FAILED"
    assert result["product_decision_recomputed"] is False
    assert result["execution_allowed"] is False


def test_invalid_decision_result_is_blocked():
    decision_service = FakeDecisionService(result={"sku": "hook-2"})
    decision_service.result = "bad"
    result = ProductDecisionRecomputePreviewService(decision_service).recompute_preview(
        _authorization(), _metrics()
    )
    assert result["code"] == "RECOMPUTE_PREVIEW_RESULT_INVALID"


def test_preview_result_sku_mismatch_is_blocked():
    result = ProductDecisionRecomputePreviewService(
        FakeDecisionService(result={"sku": "other", "decision_type": "HOLD_STOCK"})
    ).recompute_preview(_authorization(), _metrics())
    assert result["code"] == "RECOMPUTE_PREVIEW_RESULT_SKU_MISMATCH"


def test_missing_context_is_blocked():
    result = ProductDecisionRecomputePreviewService(FakeDecisionService()).recompute_preview(
        _authorization(draft_id=""), _metrics()
    )
    assert result["code"] == "RECOMPUTE_PREVIEW_CONTEXT_REQUIRED"
