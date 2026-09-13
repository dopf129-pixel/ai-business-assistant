import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_realization_offer_quantity_summary_service import (  # noqa: E402
    PeriodProfitRealizationOfferQuantitySummaryService,
)


class PeriodProfitRealizationOfferQuantityTests(unittest.TestCase):
    def service(self):
        return PeriodProfitRealizationOfferQuantitySummaryService.__new__(
            PeriodProfitRealizationOfferQuantitySummaryService
        )

    @staticmethod
    def realization_row(posting_number, sku, offer_id, quantity):
        return {
            "order": {"posting_number": posting_number},
            "item": {
                "sku": sku,
                "offer_id": offer_id,
            },
            "delivery_commission": {"quantity": quantity},
        }

    def test_realization_quantity_uses_upstream_proven_stable_offer(self):
        service = self.service()
        parsed = service._parse_realization({
            "rows": [
                self.realization_row(
                    "live-hook-2-posting",
                    "retired-intermediate-sku",
                    "hook-2",
                    3,
                )
            ]
        })

        quantity = service._quantity_from_identity_map(
            parsed,
            "live-hook-2-posting",
            "3398133813",
            {
                "finance_sku": "3398133813",
                "sku": "3398133813",
                "catalog_sku": "3921245627",
                "product_id": "product-hook-2",
                "offer_id": "hook-2",
            },
            allow_offer=False,
        )

        self.assertEqual(quantity, 3)
        self.assertEqual(
            parsed[("live-hook-2-posting", "@offer:hook-2")],
            3,
        )

    def test_conflicting_exact_sku_and_offer_quantity_fails_closed(self):
        service = self.service()
        quantity_map = {
            ("p-1", "3398133813"): 2,
            ("p-1", "@offer:hook-2"): 3,
        }

        quantity = service._quantity_from_identity_map(
            quantity_map,
            "p-1",
            "3398133813",
            {
                "sku": "3398133813",
                "catalog_sku": "3921245627",
                "offer_id": "hook-2",
            },
            allow_offer=False,
        )

        self.assertIsNone(quantity)

    def test_conflicting_realization_rows_for_same_offer_fail_closed(self):
        parsed = self.service()._parse_realization({
            "rows": [
                self.realization_row("p-1", "sku-a", "hook-2", 2),
                self.realization_row("p-1", "sku-b", "hook-2", 3),
            ]
        })

        self.assertIsNone(parsed)


if __name__ == "__main__":
    unittest.main()
