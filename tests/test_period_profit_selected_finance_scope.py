from services.period_profit_finance_sku_scope_service import PeriodProfitFinanceSkuScopeService


class _Summary:
    cost_service = object()

    def calculate(self, date_from, date_to, products):
        return {"error": False, "products": products}


class _Scope(PeriodProfitFinanceSkuScopeService):
    def _load_period_skus(self, date_from, date_to):
        return {
            "error": False,
            "skus": ["1124761908", "1124761937", "1214389162", "989101156"],
        }

    def _recover_missing_product(self, sku, at_date):
        if sku == "1124761908":
            return {
                "product_id": "selected-product",
                "sku": sku,
                "catalog_sku": "989101156",
                "offer_id": "10002_white_01",
            }
        return None


def test_selected_catalog_product_ignores_unrelated_finance_skus():
    service = _Scope(_Summary(), finance_service=object())
    result = service.calculate(
        "2026-09-13",
        "2026-09-19",
        [{
            "product_id": "selected-product",
            "sku": "989101156",
            "offer_id": "10002_white_01",
            "_period_profit_selected_scope": True,
        }],
    )

    assert result["error"] is False
    assert result["finance_sku_count"] == 2
    assert [row["sku"] for row in result["products"]] == [
        "1124761908",
        "989101156",
    ]
    assert all("_period_profit_selected_scope" not in row for row in result["products"])


def test_store_wide_scope_still_fails_closed_for_unresolved_finance_skus():
    service = _Scope(_Summary(), finance_service=object())
    result = service.calculate(
        "2026-09-13",
        "2026-09-19",
        [{
            "product_id": "selected-product",
            "sku": "989101156",
            "offer_id": "10002_white_01",
        }],
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE"
    assert "1124761937" in result["message"]


def test_selected_scope_preserves_exact_current_finance_sku_without_recovery():
    class ExactScope(PeriodProfitFinanceSkuScopeService):
        def _load_period_skus(self, date_from, date_to):
            return {"error": False, "skus": ["989101156", "unrelated"]}

        def _recover_missing_product(self, sku, at_date):
            return None

    service = ExactScope(_Summary(), finance_service=object())
    result = service.calculate(
        "2026-09-13",
        "2026-09-19",
        [{
            "product_id": "selected-product",
            "sku": "989101156",
            "offer_id": "10002_white_01",
            "_period_profit_selected_scope": True,
        }],
    )

    assert result["error"] is False
    assert result["finance_sku_count"] == 1
    assert result["products"] == [{
        "product_id": "selected-product",
        "sku": "989101156",
        "offer_id": "10002_white_01",
    }]


def test_selected_scope_rejects_other_offer_even_when_product_id_collides():
    class VariantScope(PeriodProfitFinanceSkuScopeService):
        def _load_period_skus(self, date_from, date_to):
            return {"error": False, "skus": ["legacy-white", "legacy-gray"]}

        def _recover_missing_product(self, sku, at_date):
            if sku == "legacy-white":
                return {
                    "product_id": "shared-product",
                    "sku": sku,
                    "catalog_sku": "989101156",
                    "offer_id": "10002_white_01",
                    "cost_price": 100,
                }
            return {
                "product_id": "shared-product",
                "sku": sku,
                "catalog_sku": "989101157",
                "offer_id": "10012_gray_01",
            }

    service = VariantScope(_Summary(), finance_service=object())
    result = service.calculate(
        "2026-09-13",
        "2026-09-19",
        [{
            "product_id": "shared-product",
            "sku": "989101156",
            "offer_id": "10002_white_01",
            "_period_profit_selected_scope": True,
        }],
    )

    assert result["error"] is False
    assert [row["offer_id"] for row in result["products"]] == ["10002_white_01"]
    assert [row["sku"] for row in result["products"]] == ["legacy-white"]
