from copy import deepcopy

from services.product_decision_preview_delta_service import (
    ProductDecisionPreviewDeltaService,
)


def _current(**values):
    result = {
        "sku": "hook-2",
        "decision_type": "REPLENISH_NORMAL",
        "priority": "HIGH",
        "confidence": "HIGH",
        "reasons": ["DAYS_OF_STOCK_LOW", "POSITIVE_UNIT_PROFIT"],
        "recorded_at": "2026-08-29T12:00:00+00:00",
    }
    result.update(values)
    return result


def _preview(**values):
    result = {
        "status": "PRODUCT_DECISION_RECOMPUTE_PREVIEW_READY",
        "recompute_preview_id": "product-decision-recompute-preview:recompute-review-authorization:eligibility-1",
        "recompute_authorization_id": "recompute-review-authorization:eligibility-1",
        "recompute_eligibility_id": "eligibility-1",
        "draft_id": "draft-1",
        "sku": "hook-2",
        "recompute_allowed": True,
        "recompute_started": True,
        "recompute_preview_computed": True,
        "preview_decision": {
            "product_id": 42,
            "sku": "hook-2",
            "decision_type": "HOLD_STOCK",
            "priority": "LOW",
            "confidence": "HIGH",
            "reasons": ["POSITIVE_UNIT_PROFIT"],
            "missing_data": [],
        },
        "persistent": False,
        "task_draft_mutated": False,
        "product_decision_recomputed": True,
        "product_decision_mutated": False,
        "product_decision_persisted": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_changed_preview_returns_read_only_delta():
    current = _current()
    preview = _preview()
    current_before = deepcopy(current)
    preview_before = deepcopy(preview)

    result = ProductDecisionPreviewDeltaService().compare(current, preview)

    assert result["status"] == "PRODUCT_DECISION_PREVIEW_DELTA_READY"
    assert result["decision_changed"] is True
    assert result["changed_fields"] == ["decision_type", "priority", "reasons"]
    assert result["changed_field_count"] == 3
    assert result["changes"]["decision_type"] == {
        "before": "REPLENISH_NORMAL",
        "after": "HOLD_STOCK",
    }
    assert result["changes"]["priority"] == {"before": "HIGH", "after": "LOW"}
    assert result["persistent"] is False
    assert result["product_decision_recomputed"] is True
    assert result["product_decision_mutated"] is False
    assert result["product_decision_persisted"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
    assert current == current_before
    assert preview == preview_before


def test_unchanged_preview_returns_empty_delta():
    current = _current()
    preview = _preview(
        preview_decision={
            "sku": "hook-2",
            "decision_type": current["decision_type"],
            "priority": current["priority"],
            "confidence": current["confidence"],
            "reasons": list(current["reasons"]),
        }
    )
    result = ProductDecisionPreviewDeltaService().compare(current, preview)
    assert result["decision_changed"] is False
    assert result["changed_fields"] == []
    assert result["changes"] == {}


def test_forged_preview_id_is_blocked():
    result = ProductDecisionPreviewDeltaService().compare(
        _current(), _preview(recompute_preview_id="forged")
    )
    assert result["code"] == "RECOMPUTE_PREVIEW_ID_MISMATCH"


def test_non_ready_preview_is_blocked():
    result = ProductDecisionPreviewDeltaService().compare(
        _current(), _preview(status="PRODUCT_DECISION_RECOMPUTE_PREVIEW_BLOCKED")
    )
    assert result["code"] == "RECOMPUTE_PREVIEW_STATUS_INVALID"


def test_not_computed_preview_is_blocked():
    result = ProductDecisionPreviewDeltaService().compare(
        _current(), _preview(recompute_preview_computed=False)
    )
    assert result["code"] == "RECOMPUTE_PREVIEW_NOT_COMPUTED"


def test_mutating_preview_boundary_is_blocked():
    result = ProductDecisionPreviewDeltaService().compare(
        _current(), _preview(product_decision_persisted=True)
    )
    assert result["code"] == "DECISION_PREVIEW_DELTA_SAFETY_BOUNDARY_VIOLATION"


def test_execution_boundary_is_blocked():
    result = ProductDecisionPreviewDeltaService().compare(
        _current(), _preview(execution_allowed=True)
    )
    assert result["code"] == "DECISION_PREVIEW_DELTA_SAFETY_BOUNDARY_VIOLATION"


def test_preview_decision_sku_mismatch_is_blocked():
    decision = deepcopy(_preview()["preview_decision"])
    decision["sku"] = "other"
    result = ProductDecisionPreviewDeltaService().compare(
        _current(), _preview(preview_decision=decision)
    )
    assert result["code"] == "PREVIEW_DECISION_SKU_MISMATCH"


def test_current_decision_sku_mismatch_is_blocked():
    result = ProductDecisionPreviewDeltaService().compare(
        _current(sku="other"), _preview()
    )
    assert result["code"] == "CURRENT_DECISION_SKU_MISMATCH"


def test_invalid_current_decision_is_blocked():
    result = ProductDecisionPreviewDeltaService().compare(
        _current(priority=None), _preview()
    )
    assert result["code"] == "CURRENT_DECISION_INVALID"


def test_missing_current_decision_is_blocked():
    result = ProductDecisionPreviewDeltaService().compare({}, _preview())
    assert result["code"] == "CURRENT_DECISION_REQUIRED"
