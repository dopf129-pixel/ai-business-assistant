import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)

from services.tax_service import TaxService


class TestTaxService(unittest.TestCase):

    def setUp(self):

        self.service = TaxService()

    def test_usn_income_default_rate(self):

        result = self.service.calculate(
            mode="USN_INCOME",
            revenue=100000,
            gross_profit=30000
        )

        self.assertFalse(
            result["error"]
        )

        self.assertEqual(
            result["mode"],
            "USN_INCOME"
        )

        self.assertEqual(
            result["tax_base"],
            100000.0
        )

        self.assertEqual(
            result["tax_rate"],
            6.0
        )

        self.assertEqual(
            result["tax_amount"],
            6000.0
        )

    def test_usn_income_custom_rate(self):

        result = self.service.calculate(
            mode="USN_INCOME",
            revenue=50000,
            gross_profit=20000,
            tax_rate=5
        )

        self.assertEqual(
            result["tax_rate"],
            5.0
        )

        self.assertEqual(
            result["tax_amount"],
            2500.0
        )

    def test_usn_income_minus_expenses_regular_tax(self):

        result = self.service.calculate(
            mode="USN_INCOME_MINUS_EXPENSES",
            revenue=100000,
            gross_profit=40000
        )

        self.assertFalse(
            result["error"]
        )

        self.assertEqual(
            result["tax_rate"],
            15.0
        )

        self.assertEqual(
            result["tax_base"],
            40000.0
        )

        self.assertEqual(
            result["regular_tax"],
            6000.0
        )

        self.assertEqual(
            result["minimum_tax"],
            1000.0
        )

        self.assertEqual(
            result["tax_amount"],
            6000.0
        )

    def test_usn_income_minus_expenses_minimum_tax(self):

        result = self.service.calculate(
            mode="USN_INCOME_MINUS_EXPENSES",
            revenue=100000,
            gross_profit=1000
        )

        self.assertEqual(
            result["regular_tax"],
            150.0
        )

        self.assertEqual(
            result["minimum_tax"],
            1000.0
        )

        self.assertEqual(
            result["tax_amount"],
            1000.0
        )

    def test_none_mode(self):

        result = self.service.calculate(
            mode="NONE",
            revenue=100000,
            gross_profit=50000
        )

        self.assertFalse(
            result["error"]
        )

        self.assertEqual(
            result["tax_amount"],
            0.0
        )

        self.assertEqual(
            result["tax_rate"],
            0.0
        )

    def test_unknown_mode(self):

        result = self.service.calculate(
            mode="UNKNOWN",
            revenue=100000,
            gross_profit=50000
        )

        self.assertTrue(
            result["error"]
        )

        self.assertEqual(
            result["message"],
            "Неподдерживаемый налоговый режим"
        )


if __name__ == "__main__":
    unittest.main()