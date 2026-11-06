from decimal import Decimal

from period_profit_compact_response import compact_period_profit_result
from services.fifo_cost_period_explanation_service import (
    FifoCostPeriodExplanationService,
)
from services.period_profit_fifo_explanation_view_service import (
    PeriodProfitFifoExplanationViewService,
)
from telegram_app_layer.telegram_progress_feedback import split_telegram_text


class _Repository:
    def read_late_entry_corrections(self, **_kwargs):
        return {"error": False, "corrections": []}


def _summary(*, layer_count=140, source_status="OWNER_CONFIRMED"):
    layers = [{
        "basis_ref": "fifo-basis-" + f"{number:020x}",
        "basis_kind": "LAYER",
        "sequence": number + 1,
        "effective_date": "2026-08-01",
        "provenance": "OWNER_CONFIRMED",
        "source_method": "OWNER_CONFIRMED_FIFO_CUTOFF",
        "source_status": source_status,
        "coverage_status": "OWNER_CONFIRMED",
        "quantity": 1,
        "unit_cost_rub": "1.00",
        "total_cogs_rub": "1.00",
    } for number in range(layer_count)]
    amount = Decimal(layer_count).quantize(Decimal("0.01"))
    raw = FifoCostPeriodExplanationService().build(
        allocation_result={
            "layers": layers, "layer_breakdown_complete": True,
            "cutoff_date": "2026-07-31", "stream_revision": 8,
            "allocation_revision": 3,
        },
        repository=_Repository(),
        store_id="store-a",
        product={"product_id": "product-1", "offer_id": "offer-1"},
        sku="sku-1",
        date_from="2026-08-01", date_to="2026-08-31",
        units=layer_count, product_cost=amount,
    )
    summary = {
        "date_from": "2026-08-01", "date_to": "2026-08-31",
        "revenue": 1000.0, "discount_points": 0.0,
        "revenue_tax_base": 1000.0, "units_sold": layer_count,
        "net_accrual": 800.0, "product_cost": float(amount),
        "tax": 60.0, "profit": 800.0 - float(amount) - 60.0,
        "margin_percent": (800.0 - float(amount) - 60.0) / 1000 * 100,
        "effective_cost_reconciled": True,
        "products": [{
            "sku": "sku-1", "cost_source": "FIFO_ALLOCATION_REVISION",
            "units_sold": layer_count, "product_cost": float(amount),
            "fifo_cost_explanation": raw,
        }],
    }
    summary["fifo_cost_explanation"] = PeriodProfitFifoExplanationViewService().build(summary)
    return summary


def _result(summary):
    return {
        "error": False, "status": "PERIOD_PROFIT_QUERY_READY",
        "text": "Детальная финансовая часть.", "summary": summary,
    }


def test_fc28_long_fifo_detail_is_retained_in_telegram_safe_chunks():
    result = compact_period_profit_result(_result(_summary()))
    detail = result["details_text"]
    chunks = split_telegram_text(detail)

    assert result["text"].find("FIFO-себестоимость:") >= 0
    assert len(chunks) > 1
    assert all(len(chunk) <= 3800 for chunk in chunks)
    assert "fifo-basis-0000000000000000008b" in detail
    assert "Итог за период: 140.00 ₽" in detail
    assert "полнота CONFIRMED" in detail


def test_fc28_incomplete_layer_cause_is_visible_in_compact_and_full_detail():
    result = compact_period_profit_result(
        _result(_summary(layer_count=1, source_status="STALE"))
    )

    assert "Причина: неполные данные по слоям или их подтверждению." in result["text"]
    assert "статус источника UNKNOWN" in result["details_text"]
    assert "FIFO_LAYER_EXPLANATION_INCOMPLETE" not in result["details_text"]
