import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)

from services.store_analytics_service import (
    StoreAnalyticsService
)


class FakeExpenseRepository:

    def __init__(
        self,
        expenses=None
    ):

        self.expenses = expenses or []

    def get_expenses_by_date(
        self,
        expense_date
    ):

        return self.expenses


class TestStoreAnalyticsService(unittest.TestCase):

    def test_full_store_analytics(self):

        expense_repository = FakeExpenseRepository(
            [
                {
                    "category": "Упаковка",
                    "amount": 500.0,
                    "description": ""
                },
                {
                    "category": "Сервисы",
                    "amount": 300.0,
                    "description": ""
                }
            ]
        )

        service = StoreAnalyticsService(
            tax_mode="USN_INCOME",
            tax_rate=6,
            minimum_tax_rate=1,
            advertising_cost=1000,
            analysis_date="2026-08-07",
            expense_repository=expense_repository
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

        result = service.analyze(
            profits
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
            5000.0
        )

        self.assertEqual(
            result[
                "tax"
            ][
                "tax_amount"
            ],
            600.0
        )

        self.assertEqual(
            result[
                "advertising"
            ][
                "advertising_cost"
            ],
            1000.0
        )

        self.assertEqual(
            result[
                "expenses"
            ][
                "other_expenses"
            ],
            800.0
        )

        self.assertEqual(
            result[
                "business_profit"
            ][
                "business_profit"
            ],
            2600.0
        )

        self.assertEqual(
            result[
                "business_profit"
            ][
                "margin_percent"
            ],
            26.0
        )

    def test_store_without_expenses(self):

        service = StoreAnalyticsService(
            tax_mode="USN_INCOME",
            tax_rate=6,
            minimum_tax_rate=1,
            advertising_cost=1000,
            analysis_date="2026-08-07",
            expense_repository=(
                FakeExpenseRepository()
            )
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

        result = service.analyze(
            profits
        )

        self.assertEqual(
            result[
                "expenses"
            ][
                "other_expenses"
            ],
            0.0
        )

        self.assertEqual(
            result[
                "business_profit"
            ][
                "business_profit"
            ],
            3400.0
        )

    def test_store_without_advertising(self):

        service = StoreAnalyticsService(
            tax_mode="USN_INCOME",
            tax_rate=6,
            minimum_tax_rate=1,
            advertising_cost=0,
            analysis_date="2026-08-07",
            expense_repository=(
                FakeExpenseRepository(
                    [
                        {
                            "category": "Упаковка",
                            "amount": 500.0
                        }
                    ]
                )
            )
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

        result = service.analyze(
            profits
        )

        self.assertEqual(
            result[
                "business_profit"
            ][
                "business_profit"
            ],
            3900.0
        )

    def test_none_tax_mode(self):

        service = StoreAnalyticsService(
            tax_mode="NONE",
            tax_rate=0,
            minimum_tax_rate=1,
            advertising_cost=1000,
            analysis_date="2026-08-07",
            expense_repository=(
                FakeExpenseRepository(
                    [
                        {
                            "category": "Упаковка",
                            "amount": 500.0
                        }
                    ]
                )
            )
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

        result = service.analyze(
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
            3500.0
        )


if __name__ == "__main__":
    unittest.main()