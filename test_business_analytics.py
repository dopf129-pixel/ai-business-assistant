import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)

from services.business_analytics_service import (
    BusinessAnalyticsService
)


class TestBusinessAnalyticsService(unittest.TestCase):

    def test_full_business_analytics(self):

        service = BusinessAnalyticsService(
            tax_mode="USN_INCOME",
            tax_rate=6,
            minimum_tax_rate=1,
            advertising_cost=1250
        )

        profits = [
            {
                "error": False,
                "sales_count": 10,
                "gross_sales": 10000.0,
                "net_accrual": 7000.0,
                "total_cost": 2000.0,
                "gross_profit": 5000.0
            }
        ]

        result = service.calculate(
            profits
        )

        self.assertFalse(
            result["error"]
        )

        store_profit = result[
            "store_profit"
        ]

        tax = result[
            "tax"
        ]

        advertising = result[
            "advertising"
        ]

        business_profit = result[
            "business_profit"
        ]

        self.assertEqual(
            store_profit["gross_sales"],
            10000.0
        )

        self.assertEqual(
            store_profit["gross_profit"],
            5000.0
        )

        self.assertEqual(
            tax["tax_amount"],
            600.0
        )

        self.assertEqual(
            advertising[
                "advertising_cost"
            ],
            1250.0
        )

        self.assertEqual(
            business_profit[
                "business_profit"
            ],
            3150.0
        )

        self.assertEqual(
            business_profit[
                "margin_percent"
            ],
            31.5
        )

    def test_zero_advertising(self):

        service = BusinessAnalyticsService(
            tax_mode="USN_INCOME",
            tax_rate=6,
            minimum_tax_rate=1,
            advertising_cost=0
        )

        profits = [
            {
                "error": False,
                "sales_count": 10,
                "gross_sales": 10000.0,
                "net_accrual": 7000.0,
                "total_cost": 2000.0,
                "gross_profit": 5000.0
            }
        ]

        result = service.calculate(
            profits
        )

        self.assertEqual(
            result[
                "advertising"
            ][
                "advertising_cost"
            ],
            0.0
        )

        self.assertEqual(
            result[
                "business_profit"
            ][
                "business_profit"
            ],
            4400.0
        )

    def test_none_tax_mode(self):

        service = BusinessAnalyticsService(
            tax_mode="NONE",
            tax_rate=0,
            minimum_tax_rate=1,
            advertising_cost=1000
        )

        profits = [
            {
                "error": False,
                "sales_count": 10,
                "gross_sales": 10000.0,
                "net_accrual": 7000.0,
                "total_cost": 2000.0,
                "gross_profit": 5000.0
            }
        ]

        result = service.calculate(
            profits
        )

        self.assertEqual(
            result[
                "tax"
            ][
                "tax_amount"
            ],
            0.0
        )

        self.assertEqual(
            result[
                "business_profit"
            ][
                "business_profit"
            ],
            4000.0
        )

    def test_empty_profits(self):

        service = BusinessAnalyticsService(
            tax_mode="USN_INCOME",
            tax_rate=6,
            minimum_tax_rate=1,
            advertising_cost=0
        )

        result = service.calculate(
            []
        )

        self.assertFalse(
            result["error"]
        )

        self.assertEqual(
            result[
                "store_profit"
            ][
                "gross_profit"
            ],
            0.0
        )

        self.assertEqual(
            result[
                "tax"
            ][
                "tax_amount"
            ],
            0.0
        )

        self.assertEqual(
            result[
                "business_profit"
            ][
                "business_profit"
            ],
            0.0
        )


if __name__ == "__main__":
    unittest.main()