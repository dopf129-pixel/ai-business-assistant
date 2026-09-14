import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_legacy_sku_identity_scope_service import (  # noqa: E402
    PeriodProfitLegacySkuIdentityScopeService,
)
from services.period_profit_tax_policy_summary_service import (  # noqa: E402
    PeriodProfitTaxPolicySummaryService,
)


class _SummaryService:
    cost_service = object()
    tax_rate = 0.0

    def calculate(self, _date_from, _date_to, _products):
        raise AssertionError("summary must not run without a valid product catalog")


class _FinanceService:
    pass


class _TaxService:
    def calculate(self, *_args, **_kwargs):
        raise AssertionError("tax must not run when product scope is unavailable")


class PeriodProfitEmptyCatalogFailClosedTests(unittest.TestCase):
    def test_empty_catalog_is_not_masked_as_tax_base_exception(self):
        base = PeriodProfitLegacySkuIdentityScopeService(
            _SummaryService(),
            _FinanceService(),
        )
        service = PeriodProfitTaxPolicySummaryService(
            base,
            _TaxService(),
            {
                "error": False,
                "configured": True,
                "policy": {
                    "mode": "NONE",
                    "tax_rate": 0.0,
                },
            },
        )

        result = service.calculate("2026-09-01", "2026-09-07", [])

        self.assertTrue(result["error"])
        self.assertEqual(result["code"], "PERIOD_PROFIT_PRODUCTS_UNAVAILABLE")
        self.assertNotEqual(result["code"], "PERIOD_PROFIT_TAX_BASE_EXCEPTION")
        self.assertEqual(result["status"], "PERIOD_PROFIT_QUERY_UNAVAILABLE")
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])


if __name__ == "__main__":
    unittest.main()
