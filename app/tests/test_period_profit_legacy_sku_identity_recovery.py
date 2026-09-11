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


class _CostService:
    def __init__(self, current_cost=True):
        self.current_cost = current_cost

    def get_historical_cost_evidence(self, _at_date, **_identity):
        return {
            "error": False,
            "status": "PRODUCT_COST_HISTORY_MISSING",
            "historical_cost_confirmed": False,
            "cost_price": None,
        }

    def get_all_costs(self):
        if not self.current_cost:
            return []
        return [
            (PRODUCT_ID, CURRENT_SKU, OFFER_ID, 21.0, "RUB", "2026-09-11")
        ]

    def get_cost(self, product_id):
        if not self.current_cost or str(product_id) != PRODUCT_ID:
            return None
        return (PRODUCT_ID, CURRENT_SKU, OFFER_ID, 21.0, "RUB", "2026-09-11")


class _SummaryService:
    def __init__(self, cost_service):
        self.cost_service = cost_service
        self.tax_rate = 0.0

    def calculate(self, _date_from, _date_to, products):
        return {
            "error": False,
            "products": products,
        }


class _FinanceService:
    pass


class _OzonClient:
    def __init__(self, offers=None):
        self.offers = list(offers or [OFFER_ID])
        self.fbo_calls = 0

    def get_accruals_by_day(self, _date):
        return {
            "error": False,
            "accruals": [
                {
                    "accrued_category": "POSTING",
                    "unit_number": "posting-legacy-hook-2",
                    "posting": {
                        "products": [
                            {"sku": LEGACY_SKU},
                        ]
                    },
                }
            ],
        }

    def get_fbo_postings(
        self,
        _since,
        _to,
        limit=1000,
        offset=0,
        direction="ASC",
        status="",
    ):
        del limit, offset, direction, status
        self.fbo_calls += 1
        return {
            "error": False,
            "result": {
                "postings": [
                    {
                        "posting_number": f"posting-{index}",
                        "products": [
                            {
                                "sku": LEGACY_SKU,
                                "offer_id": offer_id,
                                "quantity": 1,
                            }
                        ],
                    }
                    for index, offer_id in enumerate(self.offers)
                ],
                "has_next": False,
            },
        }


class PeriodProfitLegacySkuIdentityRecoveryTests(unittest.TestCase):
    def _service(self, *, offers=None, current_cost=True):
        cost_service = _CostService(current_cost=current_cost)
        ozon = _OzonClient(offers=offers)
        service = PeriodProfitLegacySkuIdentityScopeService(
            _SummaryService(cost_service),
            _FinanceService(),
            sku_ozon_client=ozon,
        )
        return service, ozon

    @staticmethod
    def _catalog():
        return [
            {
                "product_id": PRODUCT_ID,
                "offer_id": OFFER_ID,
                "sku": CURRENT_SKU,
            }
        ]

    def test_live_hook_2_legacy_finance_sku_recovers_stable_product_identity(self):
        service, ozon = self._service()

        result = service._scope_products(
            "2026-08-01",
            "2026-08-31",
            self._catalog(),
        )

        self.assertFalse(result["error"])
        self.assertEqual(result["finance_sku_count"], 1)
        self.assertEqual(result["historical_sku_recovery_count"], 1)
        self.assertEqual(len(result["products"]), 1)
        product = result["products"][0]
        self.assertEqual(product["product_id"], PRODUCT_ID)
        self.assertEqual(product["sku"], LEGACY_SKU)
        self.assertEqual(product["offer_id"], OFFER_ID)
        self.assertTrue(product["historical_sku_identity_recovered"])
        self.assertEqual(
            product["historical_sku_identity_source"],
            "OZON_FBO_POSTING_OFFER_ID",
        )
        self.assertNotIn("cost", product)
        self.assertNotIn("cost_price", product)
        self.assertEqual(ozon.fbo_calls, 1)

    def test_conflicting_offer_identity_stays_fail_closed(self):
        service, _ozon = self._service(offers=[OFFER_ID, "different-offer"])

        result = service._scope_products(
            "2026-08-01",
            "2026-08-31",
            self._catalog(),
        )

        self.assertTrue(result["error"])
        self.assertEqual(
            result["code"],
            "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE",
        )
        self.assertIn(LEGACY_SKU, result["message"])

    def test_identity_recovery_requires_existing_seller_cost_identity(self):
        service, _ozon = self._service(current_cost=False)

        result = service._scope_products(
            "2026-08-01",
            "2026-08-31",
            self._catalog(),
        )

        self.assertTrue(result["error"])
        self.assertEqual(
            result["code"],
            "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE",
        )


if __name__ == "__main__":
    unittest.main()
