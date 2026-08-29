from period_profit_breakdown import build_period_profit_breakdown


def _summary():
    return {
        "error": False, "status": "PERIOD_PROFIT_SUMMARY_READY", "date_from": "2026-08-01", "date_to": "2026-08-07",
        "revenue": 1000, "net_accrual": 800, "product_cost": 300, "tax": 60, "profit": 440, "margin_percent": 44,
        "profit_scope": "OZON_ACCRUALS_COST_AND_CONFIGURED_TAX_V1", "returns_included": False, "advertising_included": False, "storage_included": False,
        "products": [{"sku": "2", "offer_id": "b", "profit": 140}, {"sku": "1", "offer_id": "a", "profit": 300}],
    }


def test_ranks_products_by_profit():
    result = build_period_profit_breakdown(_summary())
    assert result["status"] == "PERIOD_PROFIT_BREAKDOWN_READY"
    assert result["best_product"]["offer_id"] == "a"
    assert result["worst_product"]["offer_id"] == "b"
    assert [x["profit_rank"] for x in result["products_by_profit"]] == [1, 2]


def test_preserves_completeness_scope():
    result = build_period_profit_breakdown(_summary())
    assert result["returns_included"] is False
    assert result["advertising_included"] is False
    assert result["storage_included"] is False


def test_invalid_summary_blocks():
    result = build_period_profit_breakdown({"error": True})
    assert result["code"] == "PERIOD_PROFIT_BREAKDOWN_SUMMARY_REQUIRED"
