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
            "error": False,
            "period": period_code,
            "date": date_to,
            "products": products
        }



class TestStoreReportManager(
    unittest.TestCase
):


    def test_build_store_report(
        self
    ):

        manager = (
            StoreReportManager(
                orchestrator=(
                    FakeOrchestrator()
                )
            )
        )


        result = (
            manager.build_store_report(
                period_code="28D",
                date_to="2026-08-09",
                products=[]
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["period"],
            "28D"
        )


if __name__ == "__main__":
    unittest.main()