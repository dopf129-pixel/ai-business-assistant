import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.store_report_presentation_service import (
    StoreReportPresentationService
)


class FakeDashboardService:

    def build(
        self,
        report
    ):

        return {
            "error": False,
            "dashboard": True
        }



class TestStoreReportPresentationService(
    unittest.TestCase
):


    def test_build(
        self
    ):

        service = (
            StoreReportPresentationService(
                dashboard_service=(
                    FakeDashboardService()
                )
            )
        )


        result = (
            service.build(
                {
                    "period": "28D"
                }
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertTrue(
            result["dashboard"]
        )


if __name__ == "__main__":
    unittest.main()