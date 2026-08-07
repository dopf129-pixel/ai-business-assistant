import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)

from services.profit_service import ProfitService


class TestProfitService(unittest.TestCase):

    def setUp(self):

        self.service = ProfitService()

    def test_profit_calculation(self):

        finance = {
            "error": False,
            "sales_count": 10,
            "gross_sales": 1000.0,
            "net_accrual": 650.0
        }

        result = self.service.calculate(
            finance,
            20
        )

        self.assertFalse(
            result["error"]
        )

        self.assertEqual(
            result["sales_count"],
            10
        )

        self.assertEqual(
            result["gross_sales"],
            1000.0
        )

        self.assertEqual(
            result["cost_price"],
            20.0
        )

        self.assertEqual(
            result["total_cost"],
            200.0
        )

        self.assertEqual(
            result["net_accrual"],
            650.0
        )

        self.assertEqual(
            result["gross_profit"],
            450.0
        )

        self.assertEqual(
            result["profit_per_unit"],
            45.0
        )

        self.assertEqual(
            result["margin_percent"],
            45.0
        )

    def test_zero_sales(self):

        finance = {
            "error": False,
            "sales_count": 0,
            "gross_sales": 0.0,
            "net_accrual": 0.0
        }

        result = self.service.calculate(
            finance,
            20
        )

        self.assertEqual(
            result["total_cost"],
            0.0
        )

        self.assertEqual(
            result["gross_profit"],
            0.0
        )

        self.assertEqual(
            result["profit_per_unit"],
            0.0
        )

        self.assertEqual(
            result["margin_percent"],
            0.0
        )

    def test_loss_product(self):

        finance = {
            "error": False,
            "sales_count": 5,
            "gross_sales": 500.0,
            "net_accrual": 100.0
        }

        result = self.service.calculate(
            finance,
            30
        )

        self.assertEqual(
            result["total_cost"],
            150.0
        )

        self.assertEqual(
            result["gross_profit"],
            -50.0
        )

        self.assertEqual(
            result["profit_per_unit"],
            -10.0
        )

        self.assertEqual(
            result["margin_percent"],
            -10.0
        )

    def test_finance_error(self):

        finance = {
            "error": True,
            "message": "Тестовая ошибка API"
        }

        result = self.service.calculate(
            finance,
            20
        )

        self.assertTrue(
            result["error"]
        )

        self.assertEqual(
            result["message"],
            "Тестовая ошибка API"
        )


if __name__ == "__main__":
    unittest.main()