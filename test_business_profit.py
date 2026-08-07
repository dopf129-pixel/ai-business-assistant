import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)

from services.business_profit_service import (
    BusinessProfitService
)


class TestBusinessProfitService(unittest.TestCase):

    def setUp(self):

        self.service = BusinessProfitService()

    def test_business_profit_without_extra_expenses(self):

        store_profit = {
            "gross_sales": 100000.0,
            "gross_profit": 30000.0
        }

        tax = {
            "error": False,
            "tax_amount": 6000.0
        }

        result = self.service.calculate(
            store_profit=store_profit,
            tax=tax
        )

        self.assertFalse(
            result["error"]
        )

        self.assertEqual(
            result["gross_sales"],
            100000.0
        )

        self.assertEqual(
            result["gross_profit"],
            30000.0
        )

        self.assertEqual(
            result["tax_amount"],
            6000.0
        )

        self.assertEqual(
            result["business_profit"],
            24000.0
        )

        self.assertEqual(
            result["margin_percent"],
            24.0
        )

    def test_business_profit_with_advertising(self):

        store_profit = {
            "gross_sales": 100000.0,
            "gross_profit": 30000.0
        }

        tax = {
            "error": False,
            "tax_amount": 6000.0
        }

        result = self.service.calculate(
            store_profit=store_profit,
            tax=tax,
            advertising_cost=5000
        )

        self.assertEqual(
            result["advertising_cost"],
            5000.0
        )

        self.assertEqual(
            result["business_profit"],
            19000.0
        )

        self.assertEqual(
            result["margin_percent"],
            19.0
        )

    def test_business_profit_with_other_expenses(self):

        store_profit = {
            "gross_sales": 100000.0,
            "gross_profit": 30000.0
        }

        tax = {
            "error": False,
            "tax_amount": 6000.0
        }

        result = self.service.calculate(
            store_profit=store_profit,
            tax=tax,
            other_expenses=4000
        )

        self.assertEqual(
            result["other_expenses"],
            4000.0
        )

        self.assertEqual(
            result["business_profit"],
            20000.0
        )

        self.assertEqual(
            result["margin_percent"],
            20.0
        )

    def test_business_profit_with_all_expenses(self):

        store_profit = {
            "gross_sales": 100000.0,
            "gross_profit": 30000.0
        }

        tax = {
            "error": False,
            "tax_amount": 6000.0
        }

        result = self.service.calculate(
            store_profit=store_profit,
            tax=tax,
            advertising_cost=5000,
            other_expenses=4000
        )

        self.assertEqual(
            result["business_profit"],
            15000.0
        )

        self.assertEqual(
            result["margin_percent"],
            15.0
        )

    def test_tax_error(self):

        store_profit = {
            "gross_sales": 100000.0,
            "gross_profit": 30000.0
        }

        tax = {
            "error": True,
            "message": "Ошибка налога"
        }

        result = self.service.calculate(
            store_profit=store_profit,
            tax=tax
        )

        self.assertTrue(
            result["error"]
        )

        self.assertEqual(
            result["message"],
            "Ошибка налога"
        )

    def test_empty_store_profit(self):

        tax = {
            "error": False,
            "tax_amount": 0.0
        }

        result = self.service.calculate(
            store_profit=None,
            tax=tax
        )

        self.assertTrue(
            result["error"]
        )

        self.assertEqual(
            result["message"],
            "Нет данных о прибыли магазина"
        )


if __name__ == "__main__":
    unittest.main()