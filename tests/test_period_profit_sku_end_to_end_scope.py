from services.period_profit_sku_runtime_service import PeriodProfitSkuRuntimeService


class _BaseQuery:
    def __init__(self):
        self.product_provider = lambda: [
            ("1", "wanted", "catalog-wanted"),
            ("2", "other", "catalog-other"),
        ]

    def query(self, **kwargs):
        products = self.product_provider()
        if len(products) != 1 or products[0]["sku"] != "catalog-wanted":
            return {
                "error": True,
                "code": "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE",
                "message": "Не найдена подтвержденная себестоимость для SKU из финансов Ozon: unrelated",
            }
        return {
            "error": False,
            "summary": {
                "products": [{
                    "product_id": "1",
                    "offer_id": "wanted",
                    "catalog_sku": "catalog-wanted",
                    "sku": "finance-wanted",
                    "revenue": 1000,
                    "net_accrual": 800,
                    "commission": 100,
                    "logistics": 50,
                    "acquiring": 10,
                    "other_fees": 40,
                    "product_cost": 0,
                    "tax": 0,
                    "profit": 800,
                    "units_sold": 2,
                }],
                "date_from": "2026-09-13",
                "date_to": "2026-09-19",
                "tax_mode": "NONE",
                "tax_rate_percent": 0,
                "minimum_tax_rate_percent": 0,
            },
            "previous_summary": None,
        }


class _FinalQuery:
    def __init__(self, base):
        self.base_service = base
        self.product_provider = base.product_provider

    def query(self, **kwargs):
        return self.base_service.query(**kwargs)


class _Costs:
    def get_all_costs(self):
        return [("1", "catalog-wanted", "wanted", 200.0, "RUB", "")]

    def get_effective_cost_evidence(self, at_date, **identity):
        assert identity == {
            "product_id": "1",
            "sku": "catalog-wanted",
            "offer_id": "wanted",
        }
        return {
            "error": False,
            "effective_cost_confirmed": True,
            "historical_cost_confirmed": True,
            "cost_price": 200.0,
        }


def test_selected_sku_query_is_not_blocked_by_unrelated_missing_cost():
    base = _BaseQuery()
    final = _FinalQuery(base)
    runtime = PeriodProfitSkuRuntimeService(final, cost_service=_Costs())

    result = runtime.handle_callback(
        "period_profit_sku:catalog-wanted:7D",
        today="2026-09-19",
    )

    assert result["error"] is False
    assert result["status"] == "PERIOD_PROFIT_SKU_READY"
    assert result["summary"]["product_cost"] == 400.0
    assert result["summary"]["profit"] == 400.0
    assert len(base.product_provider()) == 2


def test_selected_identity_group_uses_one_canonical_query_and_exact_catalog_scope():
    base = _BaseQuery()
    final = _FinalQuery(base)
    calls = []

    def selected_query(**kwargs):
        rows = base.product_provider()
        calls.append((kwargs, rows))
        assert [row["sku"] for row in rows] == ["catalog-wanted", "catalog-other"]
        return {
            "error": False,
            "status": "PERIOD_PROFIT_QUERY_READY",
            "request": {"date_from": kwargs["date_from"], "date_to": kwargs["date_to"]},
            "summary": {"products": [], "product_count": 0},
        }

    final.query = selected_query
    runtime = PeriodProfitSkuRuntimeService(final, cost_service=_Costs())
    result = runtime.query_selected_identities(
        [
            {"product_id": "1", "offer_id": "wanted", "sku": "catalog-wanted"},
            {"product_id": "2", "offer_id": "other", "sku": "catalog-other"},
        ],
        date_from="2026-08-01", date_to="2026-08-31",
    )

    assert result["error"] is False
    assert result["request"] == {"date_from": "2026-08-01", "date_to": "2026-08-31"}
    assert len(calls) == 1
    assert calls[0][0]["compare_previous"] is False
    assert all(row.get("_period_profit_selected_scope") is True for row in calls[0][1])
    assert len(base.product_provider()) == 2


def test_selected_identity_group_rejects_unmapped_identity_before_query():
    base = _BaseQuery()
    final = _FinalQuery(base)
    calls = []
    final.query = lambda **kwargs: calls.append(kwargs)
    runtime = PeriodProfitSkuRuntimeService(final, cost_service=_Costs())

    result = runtime.query_selected_identities(
        [{"product_id": "different", "offer_id": "wanted", "sku": "catalog-wanted"}],
        date_from="2026-08-01", date_to="2026-08-31",
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_SELECTED_GROUP_IDENTITY_UNRESOLVED"
    assert calls == []
