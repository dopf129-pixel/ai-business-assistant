from copy import deepcopy

from services.planning_plan_readiness_service import PlanningPlanReadinessService


def _document(*, quantity=None, missing=(), invalid=(), exact_identity=True):
    identity = {
        "product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
        "store_id": "store-a", "product_name": "Fixture",
    }
    if not exact_identity:
        identity["product_id"] = None
    item = {
        "row_id": "row-1", "identity": identity,
        "projection": {
            "available": not bool(missing or invalid),
            "status": "READY" if not (missing or invalid) else "INCOMPLETE_INPUTS",
            "missing_inputs": list(missing), "invalid_inputs": list(invalid),
        },
    }
    payload = {"items": [item]}
    if quantity is not ...:
        payload["sales_mix"] = {
            "period_label": "01.08.2026 - 31.08.2026",
            "quantities": {"row-1": quantity}, "expenses": [], "confirmed": True,
        }
    return {"document": {
        "document_id": "doc-1", "owner_id": "owner-1", "store_id": "store-a",
        "revision": 2, "current_revision": 2, "status": "ACTIVE", "payload": payload,
    }}


def test_readiness_keeps_math_freshness_and_fact_as_separate_dimensions():
    result = PlanningPlanReadinessService().project(
        _document(quantity=0), active_owner="owner-1", active_store="store-a",
    )

    assert result["error"] is False
    assert result["calculation_status"] == "READY"
    assert result["assumption_status"] == "HISTORICAL_ASSUMPTIONS"
    assert result["fact_status"] == "NOT_CHECKED"
    assert result["sales_mix_status"] == "READY"
    assert result["counts"] == {
        "items": 1, "identity_confirmed": 1,
        "calculations_ready": 1, "quantities_confirmed": 1,
    }


def test_unknown_quantity_is_distinct_from_explicit_zero_and_missing_input_is_actionable():
    unknown = PlanningPlanReadinessService().project(
        _document(quantity=None, missing=("cost",)),
        active_owner="owner-1", active_store="store-a",
    )
    zero = PlanningPlanReadinessService().project(
        _document(quantity=0), active_owner="owner-1", active_store="store-a",
    )

    assert unknown["items"][0]["quantity_status"] == "UNKNOWN"
    assert unknown["items"][0]["editable_field"] == "cost"
    assert unknown["calculation_status"] == "INCOMPLETE_INPUTS"
    assert zero["items"][0]["quantity_status"] == "CONFIRMED"
    assert zero["items"][0]["quantity"] == 0


def test_identity_or_tenant_mismatch_fails_closed():
    unresolved = PlanningPlanReadinessService().project(
        _document(quantity=None, exact_identity=False),
        active_owner="owner-1", active_store="store-a",
    )
    foreign = PlanningPlanReadinessService().project(
        _document(quantity=None), active_owner="owner-2", active_store="store-a",
    )

    assert unresolved["items"][0]["identity_status"] == "IDENTITY_UNRESOLVED"
    assert foreign["code"] == "PLANNING_TENANT_SCOPE_MISMATCH"


def test_source_status_is_not_misreported_as_ready_math():
    document = deepcopy(_document(quantity=1))
    document["document"]["payload"]["items"][0]["projection"].update(
        available=True, status="SOURCE_STALE",
    )
    result = PlanningPlanReadinessService().project(
        document, active_owner="owner-1", active_store="store-a",
    )

    assert result["calculation_status"] == "INCOMPLETE_INPUTS"
    assert result["items"][0]["calculation_status"] == "SOURCE_STALE"
    assert result["assumption_status"] == "HISTORICAL_ASSUMPTIONS"
