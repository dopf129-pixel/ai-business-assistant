from services.period_profit_sku_runtime_service import PeriodProfitSkuRuntimeService


class _Query:
    def __init__(self, summary):
        self.summary = summary
        self.product_provider = lambda: [{
            "product_id": "p1",
            "offer_id": "10002_white_01",
            "sku": "989101156",
        }]

    def query(self, **kwargs):
        return {
            "error": False,
            "summary": dict(self.summary),
            "previous_summary": None,
        }


def _summary(**overrides):
    row = {
        "product_id": "p1",
        "offer_id": "10002_white_01",
        "sku": "989101156",
        "catalog_sku": "989101156",
        "units_sold": 0,
        "revenue": 0.0,
        "net_accrual": 0.0,
        "commission": 0.0,
        "logistics": 0.0,
        "acquiring": 0.0,
        "other_fees": 0.0,
        "product_cost": 0.0,
        "tax": 0.0,
        "profit": 0.0,
    }
    result = {
        "date_from": "2026-08-23",
        "date_to": "2026-09-19",
        "products": [row],
        "finance_sku_count": 1,
        "sale_quantity_record_count": 0,
        "sale_quantity_reconciled": True,
        "tax_mode": "NONE",
        "tax_rate_percent": 0.0,
        "minimum_tax_rate_percent": 0.0,
    }
    result.update(overrides)
    return result


def test_runtime_never_presents_unproven_all_zero_selected_sku_as_success():
    service = PeriodProfitSkuRuntimeService(_Query(_summary()))
    result = service.handle_callback(
        "period_profit_sku:989101156:28D",
        today="2026-09-19",
    )
    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_SELECTED_SKU_FINANCE_EVIDENCE_MISSING"


def test_runtime_allows_selected_sku_when_positive_finance_evidence_exists():
    summary = _summary()
    summary["products"][0]["revenue"] = 100.0
    summary["products"][0]["net_accrual"] = 80.0
    service = PeriodProfitSkuRuntimeService(_Query(summary))
    result = service.handle_callback(
        "period_profit_sku:989101156:28D",
        today="2026-09-19",
    )
    assert result["error"] is False
    assert result["summary"]["revenue"] == 100.0
