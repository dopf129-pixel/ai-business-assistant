import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_effective_cost_sale_quantity_summary_service import (  # noqa: E402
    PeriodProfitEffectiveCostSaleQuantitySummaryService,
)


LEGACY_SKU = "3398133813"
CURRENT_SKU = "3921245627"
OFFER_ID = "hook-2"
PRODUCT_ID = "product-hook-2"
POSTING_NUMBER = "live-hook-2-posting"


class _Finance:
    def get_daily_sale_posting_evidence(self, day):
        if day != "2026-09-10":
            return {"error": False, "complete": True, "records": []}
        return {
            "error": False,
            "complete": True,
            "records": [
                {
                    "posting_number": POSTING_NUMBER,
                    "sku": LEGACY_SKU,
                    "accrual_date": day,
                    "source": "OZON_FINANCE_ACCRUAL_BY_DAY",
                }
            ],
        }


class _HistoricalCost:
    def __init__(self):
        self.calls = []

    def get_effective_cost_evidence(
        self,
        at_date,
        product_id=None,
        sku=None,
        offer_id=None,
    ):
        self.calls.append((at_date, product_id, sku, offer_id))
        if product_id != PRODUCT_ID or offer_id != OFFER_ID:
            return {"error": True}
        return {
            "error": False,
            "effective_cost_confirmed": True,
            "historical_cost_confirmed": True,
            "history_id": 41,
            "cost_price": 17.0,
            "effective_from": "2026-08-01",
            "effective_through": "2026-09-10",
            "source": "SELLER_CONFIRMED",
            "cost_basis": "SELLER_CONFIRMED_BOUNDED_PERIOD",
        }


class _OzonCurrentSku:
    def get_realization_posting(self, _year, _month):
        return {"rows": []}

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
                            },
                            {
                                "sku": "9999999999",
                                "offer_id": "other-offer",
                                "quantity": 7,
                            },
                        ],
                    }
                ]
            },
            "has_next": False,
        }

    def get_fbo_posting(self, _posting_number):
        return {"error": True}

    def get_fbs_posting(self, _posting_number):
        return {"error": True}


class _OzonAmbiguousOffer(_OzonCurrentSku):
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
                                "quantity": 1,
                            },
                            {
                                "sku": "rewritten-again",
                                "offer_id": OFFER_ID,
                                "quantity": 2,
                            },
                        ],
                    }
                ]
            },
            "has_next": False,
        }


def _summary_fixture():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "products": [
            {
                "sku": LEGACY_SKU,
                "finance_sku": LEGACY_SKU,
                "product_id": PRODUCT_ID,
                "offer_id": OFFER_ID,
                "cost_per_unit": 21.0,
                "units_sold": 1,
                "revenue": 100.0,
                "net_accrual": 80.0,
                "commission": 0.0,
                "logistics": 0.0,
                "acquiring": 0.0,
                "other_fees": 0.0,
                "product_cost": 21.0,
                "tax": 0.0,
                "profit": 59.0,
                "margin_percent": 59.0,
                "fee_breakdown": {},
                "historical_sku_identity_recovered": True,
                "historical_sku_identity_source": (
                    "OZON_FINANCE_UNIT_TO_FBO_POSTING_OFFER_ID"
                ),
            }
        ],
        "units_sold": 1,
        "revenue": 100.0,
        "net_accrual": 80.0,
        "commission": 0.0,
        "logistics": 0.0,
        "acquiring": 0.0,
        "other_fees": 0.0,
        "product_cost": 21.0,
        "tax": 0.0,
        "profit": 59.0,
        "margin_percent": 59.0,
        "fee_breakdown": {},
    }


def _service(ozon):
    service = PeriodProfitEffectiveCostSaleQuantitySummaryService.__new__(
        PeriodProfitEffectiveCostSaleQuantitySummaryService
    )
    service.finance_service = _Finance()
    service.cost_service = _HistoricalCost()
    service.sale_quantity_ozon_client = ozon
    service._realization_quantity_cache = {}
    service._posting_quantity_cache = {}
    service._fbo_list_quantity_cache = {}
    return service


class PeriodProfitLegacySkuQuantityChainTests(unittest.TestCase):
    def test_live_legacy_finance_sku_uses_current_fbo_offer_quantity_and_historical_cost(self):
        service = _service(_OzonCurrentSku())

        result = service._reconcile_sale_quantities(
            _summary_fixture(),
            "2026-09-10",
            "2026-09-10",
        )

        self.assertFalse(result["error"])
        self.assertEqual(result["units_sold"], 3)
        self.assertEqual(result["product_cost"], 51.0)
        self.assertEqual(result["profit"], 29.0)
        self.assertEqual(result["products"][0]["sku"], LEGACY_SKU)
        self.assertEqual(result["products"][0]["product_id"], PRODUCT_ID)
        self.assertEqual(result["products"][0]["offer_id"], OFFER_ID)
        self.assertEqual(result["products"][0]["cost_per_unit"], 17.0)
        self.assertEqual(
            service.cost_service.calls,
            [("2026-09-10", PRODUCT_ID, LEGACY_SKU, OFFER_ID)],
        )
        self.assertEqual(result["legacy_current_cost_bucket_count"], 0)

    def test_duplicate_offer_quantity_in_one_posting_fails_closed(self):
        service = _service(_OzonAmbiguousOffer())

        result = service._reconcile_sale_quantities(
            _summary_fixture(),
            "2026-09-10",
            "2026-09-10",
        )

        self.assertTrue(result["error"])
        self.assertEqual(
            result["code"],
            "PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE",
        )
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])

    def test_identity_index_keeps_stable_product_fields_for_finance_sku(self):
        indexed = PeriodProfitEffectiveCostSaleQuantitySummaryService._identity_by_finance_sku(
            [
                {
                    "product_id": PRODUCT_ID,
                    "offer_id": OFFER_ID,
                    "sku": LEGACY_SKU,
                    "historical_sku_identity_recovered": True,
                }
            ]
        )

        self.assertEqual(indexed[LEGACY_SKU]["product_id"], PRODUCT_ID)
        self.assertEqual(indexed[LEGACY_SKU]["offer_id"], OFFER_ID)
        self.assertTrue(indexed[LEGACY_SKU]["historical_sku_identity_recovered"])


if __name__ == "__main__":
    unittest.main()
