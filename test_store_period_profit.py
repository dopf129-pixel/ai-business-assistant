import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.store_period_profit_service import (
    StorePeriodProfitService
)


class FakeFinanceAnalytics:

    def get_period_finance(
        self,
        date_from,
        date_to,
        sku
    ):

        return {
            "error": False,
            "gross_sales": 10000,
            "net_accrual": 7000,
            "commission": -1000,
            "logistics": -500,
            "acquiring": -100,
            "other_fees": -200
        }


class FakeCostService:

    def get_cost(
        self,
        product_id
    ):

        return (
            1,
            product_id,
            "TEST",
            2000
        )


class FakeProfitService:

    def calculate(
        self,
        finance,
        cost
    ):

        return {
            "error": False,
            "business_profit": 3000,
            "gross_profit": 5000
        }


class FakeFinanceService:

    pass



class TestStorePeriodProfitService(
    unittest.TestCase
):


    def test_period_profit_calculation(
        self
    ):

        service = StorePeriodProfitService(
            FakeFinanceService(),
            FakeCostService(),
            FakeProfitService()
        )


        # заменяем внутренний агрегатор
        service.finance_analytics = (
            FakeFinanceAnalytics()
        )


        result = (
            service.calculate_period_profit(
                "2026-07-11",
                "2026-08-07",
                [
                    {
                        "product_id": 1,
                        "sku": "123"
                    }
                ]
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["products_count"],
            1
        )


        self.assertEqual(
            result["profits"][0]["business_profit"],
            3000
        )


    def test_empty_products(
        self
    ):

        service = StorePeriodProfitService(
            FakeFinanceService(),
            FakeCostService(),
            FakeProfitService()
        )


        result = (
            service.calculate_period_profit(
                "2026-07-11",
                "2026-08-07",
                []
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["products_count"],
            0
        )


if __name__ == "__main__":
    unittest.main()