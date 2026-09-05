from services.period_profit_finance_sku_scope_service import (
    PeriodProfitFinanceSkuScopeService,
)


class Finance:
    def __init__(self, accruals_by_day):
        self.accruals_by_day = dict(accruals_by_day)

    def _get_accruals_by_day(self, day):
        return {
            "error": False,
            "accruals": list(self.accruals_by_day.get(day, [])),
        }


class Summary:
    def __init__(self):
        self.products = None

    def calculate(self, date_from, date_to, products):
        self.products = list(products)
        return {
            "error": False,
            "status": "PERIOD_PROFIT_SUMMARY_READY",
            "revenue": 100.0,
            "profit": 10.0,
        }


def _posting(*skus):
    return {
        "accrued_category": "POSTING",
        "posting": {
            "products": [
                {"sku": sku}
                for sku in skus
            ]
        },
    }


def test_v1401_finance_scope_uses_only_skus_present_in_period():
    summary = Summary()
    service = PeriodProfitFinanceSkuScopeService(
        summary,
        Finance({"2026-09-01": [_posting("A", "B")]}),
    )

    result = service.calculate(
        "2026-09-01",
        "2026-09-01",
        [
            ("1", "offer-a", "A"),
            ("2", "offer-b", "B"),
            ("3", "stale", "STALE"),
        ],
    )

    assert result["error"] is False
    assert [item["sku"] for item in summary.products] == ["A", "B"]
    assert result["finance_sku_scope_applied"] is True
    assert result["finance_sku_count"] == 2


def test_v1402_duplicate_catalog_sku_is_counted_once():
    summary = Summary()
    service = PeriodProfitFinanceSkuScopeService(
        summary,
        Finance({"2026-09-01": [_posting("A")]}),
    )

    result = service.calculate(
        "2026-09-01",
        "2026-09-01",
        [
            ("1", "offer-a", "A"),
            ("9", "old-offer-a", "A"),
        ],
    )

    assert result["error"] is False
    assert len(summary.products) == 1
    assert summary.products[0]["sku"] == "A"
    assert result["catalog_duplicate_sku_count"] == 1


def test_v1403_missing_finance_sku_fails_closed_with_specific_error():
    summary = Summary()
    service = PeriodProfitFinanceSkuScopeService(
        summary,
        Finance({"2026-09-01": [_posting("A", "MISSING")]}),
    )

    result = service.calculate(
        "2026-09-01",
        "2026-09-01",
        [("1", "offer-a", "A")],
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_FINANCE_SKU_CATALOG_COVERAGE_INCOMPLETE"
    assert "MISSING" in result["message"]
    assert summary.products is None


def test_v1404_non_posting_accrual_does_not_expand_product_scope():
    summary = Summary()
    service = PeriodProfitFinanceSkuScopeService(
        summary,
        Finance({
            "2026-09-01": [
                _posting("A"),
                {"accrued_category": "OTHER", "posting": {"products": [{"sku": "B"}]}},
            ]
        }),
    )

    result = service.calculate(
        "2026-09-01",
        "2026-09-01",
        [("1", "offer-a", "A"), ("2", "offer-b", "B")],
    )

    assert result["error"] is False
    assert [item["sku"] for item in summary.products] == ["A"]


def test_v1405_malformed_finance_sku_fails_closed():
    service = PeriodProfitFinanceSkuScopeService(
        Summary(),
        Finance({"2026-09-01": [_posting("")]}),
    )

    result = service.calculate(
        "2026-09-01",
        "2026-09-01",
        [("1", "offer-a", "A")],
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_FINANCE_SKU_SCOPE_INVALID"


def test_v1406_scope_uses_union_of_all_days():
    summary = Summary()
    service = PeriodProfitFinanceSkuScopeService(
        summary,
        Finance({
            "2026-09-01": [_posting("A")],
            "2026-09-02": [_posting("B")],
        }),
    )

    result = service.calculate(
        "2026-09-01",
        "2026-09-02",
        [("1", "offer-a", "A"), ("2", "offer-b", "B")],
    )

    assert result["error"] is False
    assert [item["sku"] for item in summary.products] == ["A", "B"]


def test_v1407_empty_sale_scope_keeps_unique_catalog_for_zero_revenue_period():
    summary = Summary()
    service = PeriodProfitFinanceSkuScopeService(
        summary,
        Finance({"2026-09-01": []}),
    )

    result = service.calculate(
        "2026-09-01",
        "2026-09-01",
        [("1", "offer-a", "A"), ("2", "old-a", "A")],
    )

    assert result["error"] is False
    assert len(summary.products) == 1
    assert result["finance_sku_count"] == 0


def test_v1408_service_never_executes_ozon_mutation():
    summary = Summary()
    finance = Finance({"2026-09-01": [_posting("A")]})
    service = PeriodProfitFinanceSkuScopeService(summary, finance)

    result = service.calculate(
        "2026-09-01",
        "2026-09-01",
        [("1", "offer-a", "A")],
    )

    assert result["error"] is False
    assert not hasattr(finance, "update_price")


def test_v1409_product_without_sku_is_not_used_for_finance_scope():
    summary = Summary()
    service = PeriodProfitFinanceSkuScopeService(
        summary,
        Finance({"2026-09-01": [_posting("A")]}),
    )

    result = service.calculate(
        "2026-09-01",
        "2026-09-01",
        [("0", "bad", None), ("1", "offer-a", "A")],
    )

    assert result["error"] is False
    assert [item["sku"] for item in summary.products] == ["A"]


def test_v1410_invalid_period_fails_closed_before_summary():
    summary = Summary()
    service = PeriodProfitFinanceSkuScopeService(summary, Finance({}))

    result = service.calculate(
        "2026-09-02",
        "2026-09-01",
        [("1", "offer-a", "A")],
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_PERIOD_INVALID"
    assert summary.products is None
