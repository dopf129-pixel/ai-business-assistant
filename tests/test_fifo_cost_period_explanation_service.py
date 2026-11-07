from decimal import Decimal

from services.fifo_cost_period_explanation_service import (
    FifoCostPeriodExplanationService,
)
from services.period_profit_fifo_explanation_view_service import (
    PeriodProfitFifoExplanationViewService,
)


def _layer(*, sequence=1, quantity=2, unit_cost="10.00", **overrides):
    row = {
        "basis_ref": "fifo-basis-" + f"{sequence:020x}",
        "basis_kind": "LAYER",
        "sequence": sequence,
        "effective_date": "2026-08-01",
        "provenance": "OWNER_CONFIRMED",
        "source_method": "OWNER_CONFIRMED_FIFO_CUTOFF",
        "source_status": "OWNER_CONFIRMED",
        "coverage_status": "OWNER_CONFIRMED",
        "quantity": quantity,
        "unit_cost_rub": unit_cost,
        "total_cogs_rub": f"{float(unit_cost) * quantity:.2f}",
    }
    row.update(overrides)
    return row


class _CorrectionRepository:
    def __init__(self, corrections=None):
        self.corrections = corrections or []

    def read_late_entry_corrections(self, **_kwargs):
        return {"error": False, "corrections": self.corrections}


def _correction(*, period="2026-08", revision=8, previous_allocation=2):
    return {
        "correction_id": "secret-correction-id",
        "stream_revision": revision,
        "allocation_revision": previous_allocation,
        "impact": {"periods": [{
            "period": period,
            "before_sku_cogs_rub": "20.00",
            "after_sku_cogs_rub": "25.00",
            "delta_cogs_rub": "5.00",
            "before_total_cogs_rub": "60.00",
            "after_total_cogs_rub": "65.00",
            "before_tax_rub": "10.00",
            "after_tax_rub": "10.00",
            "delta_tax_rub": "0.00",
            "before_profit_rub": "50.00",
            "after_profit_rub": "45.00",
            "delta_profit_rub": "-5.00",
        }]},
    }


def _allocation(layers=None):
    return {
        "layers": layers if layers is not None else [_layer()],
        "layer_breakdown_complete": True,
        "cutoff_date": "2026-07-31",
        "stream_revision": 8,
        "allocation_revision": 3,
    }


def test_fc28_explanation_sums_confirmed_layers_and_redacts_internal_ids():
    service = FifoCostPeriodExplanationService()
    result = service.build(
        allocation_result=_allocation([_layer(), _layer(sequence=2, unit_cost="15.00")]),
        repository=_CorrectionRepository([_correction()]),
        store_id="store-a",
        product={"product_id": "product-1", "offer_id": "offer-1"},
        sku="sku-1",
        date_from="2026-08-01",
        date_to="2026-08-31",
        units=4,
        product_cost=Decimal("50.00"),
    )

    assert result["status"] == "CONFIRMED"
    assert result["product_cost_rub"] == "50.00"
    assert [layer["total_cogs_rub"] for layer in result["layers"]] == ["20.00", "30.00"]
    assert result["corrections"]["status"] == "AVAILABLE"
    correction = result["corrections"]["revisions"][0]
    assert correction["status"] == "CURRENT_RESULT"
    assert correction["before_sku_cogs_rub"] == "20.00"
    assert correction["after_sku_cogs_rub"] == "25.00"
    assert correction["delta_cogs_rub"] == "5.00"
    assert correction["before_profit_rub"] == "50.00"
    assert correction["after_profit_rub"] == "45.00"
    assert correction["delta_profit_rub"] == "-5.00"
    assert "secret-correction-id" not in str(result)


def test_fc28_partial_month_does_not_claim_full_month_correction_delta():
    result = FifoCostPeriodExplanationService().build(
        allocation_result=_allocation(),
        repository=_CorrectionRepository([_correction()]),
        store_id="store-a",
        product={"product_id": "product-1", "offer_id": "offer-1"},
        sku="sku-1",
        date_from="2026-08-02",
        date_to="2026-08-31",
        units=2,
        product_cost=Decimal("20.00"),
    )

    assert result["status"] == "CONFIRMED"
    assert result["corrections"]["status"] == "NOT_ALIGNED"
    assert result["corrections"]["revisions"] == []
    assert result["corrections"]["reason_code"] == "FIFO_CORRECTION_PERIOD_NOT_ALIGNED"


def test_fc28_unknown_layer_confirmation_keeps_cogs_but_marks_explanation_partial():
    result = FifoCostPeriodExplanationService().build(
        allocation_result=_allocation([_layer(source_status="STALE")]),
        repository=_CorrectionRepository(),
        store_id="store-a",
        product={"product_id": "product-1", "offer_id": "offer-1"},
        sku="sku-1",
        date_from="2026-08-01",
        date_to="2026-08-31",
        units=2,
        product_cost=Decimal("20.00"),
    )

    assert result["status"] == "PARTIAL"
    assert result["product_cost_rub"] == "20.00"
    assert result["layers"][0]["source_status"] == "UNKNOWN"


def test_fc28_shared_view_reconciles_fifo_and_legacy_cost_modes():
    summary = {
        "product_cost": 55.0,
        "effective_cost_reconciled": True,
        "products": [
            {
                "sku": "sku-fifo", "cost_source": "FIFO_ALLOCATION_REVISION",
                "units_sold": 2, "product_cost": 20.0,
                "fifo_stream_revision": 8, "fifo_allocation_revision": 3,
                "fifo_cutoff_date": "2026-07-31",
                "fifo_cost_explanation": {
                    **FifoCostPeriodExplanationService().build(
                        allocation_result=_allocation(),
                        repository=_CorrectionRepository(),
                        store_id="store-a",
                        product={"product_id": "product-1", "offer_id": "offer-1"},
                        sku="sku-fifo",
                        date_from="2026-08-01", date_to="2026-08-31",
                        units=2, product_cost=Decimal("20.00"),
                    ),
                },
            },
            {
                "sku": "sku-legacy", "cost_source": "LEGACY_DATED_COST",
                "units_sold": 1, "product_cost": 35.0,
            },
        ],
    }

    result = PeriodProfitFifoExplanationViewService().build(summary)

    assert result["cost_mode"] == "MIXED"
    assert result["status"] == "CONFIRMED"
    assert result["total_cogs_rub"] == "55.00"
    assert result["fifo_cogs_rub"] == "20.00"
    assert result["legacy_cogs_rub"] == "35.00"
    assert [item["cost_mode"] for item in result["products"]] == [
        "FIFO", "LEGACY_DATED_COST",
    ]
