from datetime import datetime, timezone

from app.services.product_action_task_draft_service import (
    ProductActionTaskDraftService,
)
from app.services.product_business_decision_query_service import (
    ProductBusinessDecisionQueryService,
)
from app.services.product_decision_input_provider import (
    ProductDecisionInputProvider,
)
from app.services.product_task_draft_freshness_service import (
    ProductTaskDraftFreshnessService,
)


class _ProductService:
    def load_products(self):
        return [
            {
                "product_id": "p1",
                "offer_id": "sku-1",
                "sku": "sku-1",
            }
        ]


class _EconomicsQuery:
    def __init__(self, result):
        self.result = dict(result)

    def query(self, sku):
        return dict(self.result)


class _DecisionService:
    def decide(self, metrics):
        return {
            "product_id": metrics.get("product_id"),
            "sku": metrics.get("sku"),
            "decision_type": "HOLD_STOCK",
            "priority": "LOW",
            "reasons": [],
            "confidence": "HIGH",
            "missing_data": list(metrics.get("missing_data") or []),
        }


def _query_service(sales, stock, economics):
    return ProductBusinessDecisionQueryService(
        product_service=_ProductService(),
        sales_metrics_source=lambda sku: dict(sales),
        stock_metrics_source=lambda sku: dict(stock),
        unit_economics_query_service=_EconomicsQuery(economics),
        decision_input_provider=ProductDecisionInputProvider(),
        decision_service=_DecisionService(),
        cache_ttl_seconds=0,
    )


def _sales(**overrides):
    result = {
        "product_id": "p1",
        "sku": "sku-1",
        "sales_velocity": 2.0,
        "sales_trend": "STABLE",
        "missing_data": [],
    }
    result.update(overrides)
    return result


def _stock(**overrides):
    result = {
        "product_id": "p1",
        "sku": "sku-1",
        "current_stock": 20,
        "days_of_stock": 10.0,
        "stock_priority": "LOW",
        "missing_data": [],
    }
    result.update(overrides)
    return result


def _economics(**overrides):
    result = {
        "error": False,
        "product_id": "p1",
        "sku": "sku-1",
        "net_profit_per_unit": 30.0,
        "margin_percent": 25.0,
        "missing_data": [],
    }
    result.update(overrides)
    return result


def test_decision_input_provider_copies_explicit_evidence_fields():
    provider = ProductDecisionInputProvider()

    result = provider.build(
        sales_metrics=_sales(
            sales_source_recorded_at="2026-08-29T09:00:00+00:00",
            sales_observed_at="2026-08-29T09:05:00+00:00",
        ),
        stock_metrics=_stock(
            stock_source_recorded_at="2026-08-29T09:01:00+00:00",
            stock_observed_at="2026-08-29T09:06:00+00:00",
        ),
        unit_economics={
            "product_id": "p1",
            "sku": "sku-1",
            "net_profit_per_unit": 30.0,
            "margin_percent": 25.0,
            "missing_data": [],
            "unit_economics_source_recorded_at": (
                "2026-08-29T09:02:00+00:00"
            ),
            "unit_economics_observed_at": (
                "2026-08-29T09:07:00+00:00"
            ),
        },
    )

    assert result["sales_source_recorded_at"] == "2026-08-29T09:00:00+00:00"
    assert result["sales_observed_at"] == "2026-08-29T09:05:00+00:00"
    assert result["stock_source_recorded_at"] == "2026-08-29T09:01:00+00:00"
    assert result["stock_observed_at"] == "2026-08-29T09:06:00+00:00"
    assert result["unit_economics_source_recorded_at"] == (
        "2026-08-29T09:02:00+00:00"
    )
    assert result["unit_economics_observed_at"] == (
        "2026-08-29T09:07:00+00:00"
    )


def test_decision_input_provider_does_not_fabricate_missing_evidence():
    result = ProductDecisionInputProvider().build(
        sales_metrics=_sales(),
        stock_metrics=_stock(),
        unit_economics={
            "product_id": "p1",
            "sku": "sku-1",
            "net_profit_per_unit": 30.0,
            "margin_percent": 25.0,
            "missing_data": [],
        },
    )

    assert not any(
        key.endswith("_source_recorded_at") or key.endswith("_observed_at")
        for key in result
    )


def test_current_economics_as_of_becomes_observed_time_only():
    service = _query_service(_sales(), _stock(), _economics())

    normalized = service._normalize_economics(
        _economics(as_of="2026-08-29T09:10:00+00:00"),
        product_id="p1",
        sku="sku-1",
    )

    assert normalized["unit_economics_observed_at"] == (
        "2026-08-29T09:10:00+00:00"
    )
    assert "unit_economics_source_recorded_at" not in normalized


def test_explicit_source_evidence_reaches_final_decision():
    result = _query_service(
        _sales(
            sales_source_recorded_at="2026-08-29T09:00:00+00:00",
            sales_observed_at="2026-08-29T09:05:00+00:00",
        ),
        _stock(
            stock_source_recorded_at="2026-08-29T09:01:00+00:00",
            stock_observed_at="2026-08-29T09:06:00+00:00",
        ),
        _economics(
            unit_economics_source_recorded_at=(
                "2026-08-29T09:02:00+00:00"
            ),
            as_of="2026-08-29T09:07:00+00:00",
        ),
    ).query("sku-1")

    assert result["sales_source_recorded_at"] == "2026-08-29T09:00:00+00:00"
    assert result["stock_source_recorded_at"] == "2026-08-29T09:01:00+00:00"
    assert result["unit_economics_source_recorded_at"] == (
        "2026-08-29T09:02:00+00:00"
    )
    assert result["unit_economics_observed_at"] == (
        "2026-08-29T09:07:00+00:00"
    )


def test_observed_economics_time_does_not_make_draft_fresh():
    decision = _query_service(
        _sales(),
        _stock(),
        _economics(as_of="2026-08-29T09:55:00+00:00"),
    ).query("sku-1")
    decision["recorded_at"] = "2026-08-29T09:50:00+00:00"

    draft_result = ProductActionTaskDraftService().create_from_confirmation(
        decision,
        {
            "proposal_type": "REVIEW_UNIT_ECONOMICS",
            "action_required": True,
        },
    )
    draft = draft_result["task_draft"]

    freshness = ProductTaskDraftFreshnessService(
        clock=lambda: datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)
    ).evaluate(draft)

    assert draft["unit_economics_observed_at"] == (
        "2026-08-29T09:55:00+00:00"
    )
    assert "unit_economics_source_recorded_at" not in draft
    assert freshness["components"]["unit_economics"]["status"] == "UNKNOWN"
    assert freshness["status"] == "UNKNOWN"
    assert freshness["execution_ready"] is False
    assert freshness["executed"] is False
