import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_realization_offer_quantity_summary_service import (  # noqa: E402
    PeriodProfitRealizationOfferQuantitySummaryService,
)


class PeriodProfitRealizationTextHelperTests(unittest.TestCase):
    def test_identity_index_normalizes_finance_sku_without_attribute_error(self):
        products = [
            {
                "product_id": "12345",
                "offer_id": "hook-2",
                "sku": " 3398133813 ",
                "catalog_sku": "3921245627",
            }
        ]

        indexed = PeriodProfitRealizationOfferQuantitySummaryService._identity_by_finance_sku(
            products
        )

        self.assertEqual(set(indexed), {"3398133813"})
        self.assertEqual(indexed["3398133813"]["offer_id"], "hook-2")
        self.assertEqual(indexed["3398133813"]["catalog_sku"], "3921245627")


if __name__ == "__main__":
    unittest.main()
