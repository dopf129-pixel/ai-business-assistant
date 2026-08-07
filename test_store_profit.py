import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)

from services.store_profit_service import StoreProfitService


class TestStoreProfitService(unittest.TestCase):

    def setUp(self):

        self.service = StoreProfitService()

    def test_store_profit_calculation(self):

        profits = [
            {
                "error": False,
                "sales_count": 10,
                "gross_sales": 1000.0,
                "net_accrual": 650.0,
                "total_cost": 200.0,
                "gross_profit": 450.0
            },
            {
                "error": False,
                "sales_count": 5,
                "gross_sales": 500.0,
                "net_accrual": 300.0,
                "total_cost": 200.0,
                "gross_profit": 100.0
            }
        ]

        result = self.service.calculate(
            profits
        )

        self.assertEqual(
            result["sales_count"],
            15
        )

        self.assertEqual(
            result["gross_sales"],
            1500.0
        )

        self.assertEqual(
            result["net_accrual"],
            950.0
        )

        self.assertEqual(
            result["total_cost"],
            400.0
        )

        self.assertEqual(
            result["gross_profit"],
            550.0
        )

        self.assertAlmostEqual(
            result["margin_percent"],
            36.67
        )

        self.assertEqual(
            result["profitable_products"],
            2
        )

        self.assertEqual(
            result["loss_products"],
            0
        )

    def test_store_with_loss_product(self):

        profits = [
            {
                "error": False,
                "sales_count": 10,
                "gross_sales": 1000.0,
                "net_accrual": 650.0,
                "total_cost": 200.0,
                "gross_profit": 450.0
            },
            {
                "error": False,
                "sales_count": 5,
                "gross_sales": 500.0,
                "net_accrual": 100.0,
                "total_cost": 150.0,
                "gross_profit": -50.0
            }
        ]

        result = self.service.calculate(
            profits
        )

        self.assertEqual(
            result["gross_profit"],
            400.0
        )

        self.assertEqual(
            result["profitable_products"],
            1
        )

        self.assertEqual(
            result["loss_products"],
            1
        )

    def test_store_skips_error_products(self):

        profits = [
            {
                "error": False,
                "sales_count": 10,
                "gross_sales": 1000.0,
                "net_accrual": 650.0,
                "total_cost": 200.0,
                "gross_profit": 450.0
            },
            {
                "error": True,
                "message": "Ошибка API"
            }
        ]

        result = self.service.calculate(
            profits
        )

        self.assertEqual(
            result["sales_count"],
            10
        )

        self.assertEqual(
            result["gross_profit"],
            450.0
        )

        self.assertEqual(
            result["profitable_products"],
            1
        )

        self.assertEqual(
            result["loss_products"],
            0
        )

    def test_empty_store(self):

        result = self.service.calculate(
            []
        )

        self.assertEqual(
            result["sales_count"],
            0
        )

        self.assertEqual(
            result["gross_sales"],
            0.0
        )

        self.assertEqual(
            result["gross_profit"],
            0.0
        )

        self.assertEqual(
            result["margin_percent"],
            0.0
        )


if __name__ == "__main__":
    unittest.main()