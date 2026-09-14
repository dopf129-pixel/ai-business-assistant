import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_legacy_sku_identity_scope_service import (  # noqa: E402
    PeriodProfitLegacySkuIdentityScopeService,
)


LEGACY_SKU = "3398133813"
CURRENT_SKU = "3921245627"
OFFER_ID = "hook-2"
PRODUCT_ID = "product-hook-2"
POSTING_NUMBER = "live-hook-2-posting"


class _CostService:
    def get_historical_cost_evidence(self, _at_date, **_identity):
        if _identity.get("sku") != LEGACY_SKU:
            return {"error": False, "status": "PRODUCT_COST_HISTORY_MISSING", "historical_cost_confirmed": False}
        return {
            "error": False,
            "status": "PRODUCT_COST_HISTORY_READY",
            "historical_cost_confirmed": True,
            "history_id": 41,
            "product_id": PRODUCT_ID,
            "sku": LEGACY_SKU,
            "offer_id": None,
            "cost_price": 17.0,
            "currency": "RUB",
            "effective_from": "2026-08-01",
            "effective_through": "2026-09-10",
            "source": "SELLER_CONFIRMED",
        }

    def get_all_costs(self):
        return []


class _Summary:
    def __init__(self):
        self.cost_service = _CostService()
        self.tax_rate = 0.0

    def calculate(self, _date_from, _date_to, products):
        return {"error": False, "products": products}


class _Finance:
    pass


class _Ozon:
    def get_accruals_by_day(self, day):
        return {
            "error": False,
            "accruals": [
                {
                    "accrued_category": "POSTING",
                    "unit_number": POSTING_NUMBER,
                    "posting": {"products": [{"sku": LEGACY_SKU}]},
                }
            ] if day == "2026-09-10" else [],
        }

    def get_fbo_postings(self, *_args, **_kwargs):
        return {
            "error": False,
            "result": {
                "postings": [
                    {
                        "posting_number": POSTING_NUMBER,
                        "products": [
                            {
                                "sku": CURRENT_SKU,
                                "offer_id": OFFER_ID,
                                "quantity": 3,
                            }
                        ],
                    }
                ]
            },
            "has_next": False,
        }


class PeriodProfitHistoricalCostLegacyIdentityTests(unittest.TestCase):
    def test_confirmed_history_does_not_hide_stable_offer_and_current_catalog_sku(self):
        service = PeriodProfitLegacySkuIdentityScopeService(
            _Summary(),
            _Finance(),
            sku_ozon_client=_Ozon(),
        )

        result = service._scope_products(
            "2026-09-10",
            "2026-09-10",
            [
                {
                    "product_id": PRODUCT_ID,
                    "offer_id": OFFER_ID,
                    "sku": CURRENT_SKU,
                }
            ],
        )

        self.assertFalse(result["error"])
        self.assertEqual(result["historical_sku_recovery_count"], 1)
        product = result["products"][0]
        self.assertEqual(product["sku"], LEGACY_SKU)
        self.assertEqual(product["product_id"], PRODUCT_ID)
        self.assertEqual(product["offer_id"], OFFER_ID)
        self.assertEqual(product["catalog_sku"], CURRENT_SKU)
        self.assertEqual(product["cost_price"], 17.0)
        self.assertTrue(product["historical_cost_evidence"])
        self.assertTrue(product["historical_sku_identity_recovered"])
        self.assertEqual(
            product["historical_sku_identity_source"],
            "OZON_FINANCE_UNIT_TO_FBO_POSTING_OFFER_ID",
        )

    def test_conflicting_historical_product_identity_fails_closed(self):
        class _ConflictingCost(_CostService):
            def get_historical_cost_evidence(self, at_date, **identity):
                row = super().get_historical_cost_evidence(at_date, **identity)
                if row.get("historical_cost_confirmed") is True:
                    row = dict(row)
                    row["product_id"] = "different-product"
                return row

        summary = _Summary()
        summary.cost_service = _ConflictingCost()
        service = PeriodProfitLegacySkuIdentityScopeService(
            summary,
            _Finance(),
            sku_ozon_client=_Ozon(),
        )

        result = service._scope_products(
            "2026-09-10",
            "2026-09-10",
            [
                {
                    "product_id": PRODUCT_ID,
                    "offer_id": OFFER_ID,
                    "sku": CURRENT_SKU,
                }
            ],
        )

        self.assertTrue(result["error"])
        self.assertEqual(
            result["code"],
            "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE",
        )
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])


if __name__ == "__main__":
    unittest.main()
