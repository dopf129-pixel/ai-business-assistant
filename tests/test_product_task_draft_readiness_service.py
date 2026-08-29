from app.services.product_task_draft_readiness_service import (
    ProductTaskDraftReadinessService,
)


def _draft(**overrides):
    result = {
        "draft_id": "d1",
        "status": "DRAFT",
        "proposal_type": "REVIEW_REPLENISHMENT",
        "current_stock": 8,
        "sales_velocity": 4.0,
        "days_of_stock": 2.0,
        "profit_per_unit": 35.1,
        "margin_percent": 36.5,
        "economics_basis": "ESTIMATED_RETURNS",
    }
    result.update(overrides)
    return result


def test_replenishment_draft_can_be_ready_for_review_but_not_execution():
    result = ProductTaskDraftReadinessService().evaluate(_draft())

    assert result["review_ready"] is True
    assert result["review_status"] == "READY_FOR_REVIEW"
    assert result["missing_fields"] == []
    assert result["execution_ready"] is False
    assert result["execution_blockers"] == [
        "EXECUTION_WORKFLOW_NOT_CONNECTED",
        "REPLENISHMENT_QUANTITY_POLICY_MISSING",
        "SUPPLIER_LEAD_TIME_MISSING",
    ]
    assert result["executed"] is False


def test_missing_review_data_is_reported_without_inference():
    result = ProductTaskDraftReadinessService().evaluate(_draft(
        current_stock=None,
        sales_velocity=None,
    ))

    assert result["review_ready"] is False
    assert result["missing_fields"] == [
        "current_stock",
        "sales_velocity",
    ]
    assert "REQUIRED_DATA_MISSING" in result["review_blockers"]


def test_stale_draft_is_not_ready_even_with_complete_data():
    result = ProductTaskDraftReadinessService().evaluate(
        _draft(status="STALE")
    )

    assert result["review_ready"] is False
    assert result["missing_fields"] == []
    assert result["review_blockers"] == ["DRAFT_NOT_CURRENT"]


def test_each_review_type_has_explicit_execution_policy_blockers():
    service = ProductTaskDraftReadinessService()

    economics = service.evaluate(_draft(
        proposal_type="REVIEW_UNIT_ECONOMICS"
    ))
    margin = service.evaluate(_draft(proposal_type="REVIEW_MARGIN"))

    assert economics["review_ready"] is True
    assert economics["execution_blockers"][-1] == (
        "ACTION_POLICY_NOT_DEFINED"
    )
    assert margin["review_ready"] is True
    assert margin["execution_blockers"][-2:] == [
        "PRICE_CHANGE_POLICY_MISSING",
        "TARGET_MARGIN_POLICY_MISSING",
    ]


def test_readiness_summary_counts_review_state_and_zero_executable():
    service = ProductTaskDraftReadinessService()

    result = service.summarize([
        _draft(draft_id="d1"),
        _draft(draft_id="d2", status="STALE"),
    ])

    assert result["counts"] == {
        "READY_FOR_REVIEW": 1,
        "NEEDS_DATA_OR_REFRESH": 1,
    }
    assert result["execution_ready_count"] == 0
    assert result["executed_count"] == 0
    assert len(result["items"]) == 2
