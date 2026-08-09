import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.store_report_manager import (
    StoreReportManager
)


class FakeOrchestrator:

    def build(
        self,
        period_code,
        date_to,
        products
    ):

        return {
            "error": False
        }



class TestStoreReportManagerValidation(
    unittest.TestCase
):


    def setUp(
        self
    ):

        self.manager = (
            StoreReportManager(
                orchestrator=(
                    FakeOrchestrator()
                )
            )
        )


    def test_missing_period_code(
        self
    ):

        result = (
            self.manager
            .build_store_report(
                period_code=None,
                date_to="2026-08-09",
                products=[]
            )
        )


        self.assertTrue(
            result["error"]
        )


        self.assertEqual(
            result["message"],
            "Не указан период анализа"
        )


    def test_missing_products(
        self
    ):

        result = (
            self.manager
            .build_store_report(
                period_code="28D",
                date_to="2026-08-09",
                products=None
            )
        )


        self.assertTrue(
            result["error"]
        )


        self.assertEqual(
            result["message"],
            "Не переданы товары"
        )



if __name__ == "__main__":
    unittest.main()