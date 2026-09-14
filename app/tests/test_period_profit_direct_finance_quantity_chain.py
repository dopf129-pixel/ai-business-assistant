import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_realization_offer_quantity_summary_service import (  # noqa: E402
    PeriodProfitRealizationOfferQuantitySummaryService,
)


LEGACY_SKU = "3398133813"
CURRENT_SKU = "3921245627"
OFFER_ID = "hook-2"
PRODUCT_ID = "product-hook-2"
POSTING_NUMBER = "live-hook-2-posting"


class _Finance:
    def __init__(self, conflict=False, quantity_sku=LEGACY_SKU, extra_quantity_record=None):
        self.conflict = conflict
        self.quantity_sku = quantity_sku
        self.extra_quantity_record = extra_quantity_record
        self.quantity_calls = []

    def get_daily_sale_posting_evidence(self, day):
        if day != "2026-09-10":
            return {"error": False, "complete": True, "records": []}
        return {
            "error": False,
            "complete": True,
            "records": [{
                "posting_number": POSTING_NUMBER,
                "sku": LEGACY_SKU,
                "accrual_date": day,
                "source": "OZON_FINANCE_ACCRUAL_BY_DAY",
            }],
        }

    def get_sale_posting_quantity_evidence(self, posting_numbers):
        self.quantity_calls.append(list(posting_numbers))
        if self.conflict:
            return {
                "error": True,
                "code": "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_CONFLICT",
                "complete": False,
                "records": [],
            }
        records = [{
            "posting_number": POSTING_NUMBER,
            "sku": self.quantity_sku,
            "quantity": 3,
            "source": "OZON_FINANCE_ACCRUAL_POSTINGS",
        }]
        if self.extra_quantity_record is not None:
            records.append(dict(self.extra_quantity_record))
        return {
            "error": False,
            "complete": True,
            "records": records,
        }


class _Cost:
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


class _NoPhysicalFallback:
    def __getattr__(self, name):
        raise AssertionError("fallback Ozon quantity source must not be used: " + name)


class _UnavailablePhysicalFallback:
    def get_realization_posting(self, year, month):
        return {"error": True}

    def get_fbo_postings(self, *args, **kwargs):
        return {"error": True}

    def get_fbo_posting(self, posting_number):
        return {"error": True}

    def get_fbs_posting(self, posting_number):
        return {"error": True}


def _summary():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "products": [{
            "sku": LEGACY_SKU,
            "finance_sku": LEGACY_SKU,
            "catalog_sku": CURRENT_SKU,
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
        }],
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


def _service(finance, physical_client=None):
    service = PeriodProfitRealizationOfferQuantitySummaryService.__new__(
        PeriodProfitRealizationOfferQuantitySummaryService
    )
    service.finance_service = finance
    service.cost_service = _Cost()
    service.sale_quantity_ozon_client = physical_client or _NoPhysicalFallback()
    service._realization_quantity_cache = {}
    service._posting_quantity_cache = {}
    service._fbo_list_quantity_cache = {}
    return service


class PeriodProfitDirectFinanceQuantityChainTests(unittest.TestCase):
    def test_direct_finance_quantity_reconciles_legacy_sku_with_historical_cost(self):
        finance = _Finance()
        service = _service(finance)

        result = service._reconcile_sale_quantities(
            _summary(),
            "2026-09-10",
            "2026-09-10",
        )

        self.assertFalse(result["error"])
        self.assertEqual(result["units_sold"], 3)
        self.assertEqual(result["product_cost"], 51.0)
        self.assertEqual(result["profit"], 29.0)
        self.assertEqual(result["products"][0]["sku"], LEGACY_SKU)
        self.assertEqual(result["products"][0]["offer_id"], OFFER_ID)
        self.assertEqual(result["products"][0]["cost_per_unit"], 17.0)
        self.assertEqual(result["direct_finance_quantity_record_count"], 1)
        self.assertEqual(finance.quantity_calls, [[POSTING_NUMBER]])
        self.assertEqual(
            service.cost_service.calls,
            [("2026-09-10", PRODUCT_ID, LEGACY_SKU, OFFER_ID)],
        )
        self.assertIn("OZON_FINANCE_ACCRUAL_POSTINGS", result["sale_quantity_source"])
        self.assertEqual(result["legacy_current_cost_bucket_count"], 0)

    def test_single_line_posting_bridges_legacy_finance_sku_to_current_quantity_sku(self):
        finance = _Finance(quantity_sku=CURRENT_SKU)
        service = _service(finance)

        result = service._reconcile_sale_quantities(
            _summary(),
            "2026-09-10",
            "2026-09-10",
        )

        self.assertFalse(result["error"])
        self.assertEqual(result["units_sold"], 3)
        self.assertEqual(result["product_cost"], 51.0)
        self.assertEqual(result["profit"], 29.0)
        self.assertEqual(result["products"][0]["sku"], LEGACY_SKU)
        self.assertEqual(result["products"][0]["catalog_sku"], CURRENT_SKU)
        self.assertEqual(result["legacy_current_cost_bucket_count"], 0)
        self.assertEqual(finance.quantity_calls, [[POSTING_NUMBER]])

    def test_multi_line_posting_does_not_guess_across_sku_drift(self):
        finance = _Finance(
            quantity_sku=CURRENT_SKU,
            extra_quantity_record={
                "posting_number": POSTING_NUMBER,
                "sku": "another-sku",
                "quantity": 1,
                "source": "OZON_FINANCE_ACCRUAL_POSTINGS",
            },
        )
        service = _service(finance, _UnavailablePhysicalFallback())

        result = service._reconcile_sale_quantities(
            _summary(),
            "2026-09-10",
            "2026-09-10",
        )

        self.assertTrue(result["error"])
        self.assertEqual(result["code"], "PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE")
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])

    def test_direct_finance_quantity_conflict_fails_closed_before_fallback(self):
        service = _service(_Finance(conflict=True))

        result = service._reconcile_sale_quantities(
            _summary(),
            "2026-09-10",
            "2026-09-10",
        )

        self.assertTrue(result["error"])
        self.assertEqual(
            result["code"],
            "PERIOD_PROFIT_SALE_QUANTITY_FINANCE_POSTING_CONFLICT",
        )
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])


if __name__ == "__main__":
    unittest.main()
