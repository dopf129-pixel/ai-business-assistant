import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.store_period_summary_service import (
    StorePeriodSummaryService
)


class FakePeriodRunner:

    def build_store_period_report(
        self,
        period_code,
        date_to,
        products
    ):

        return {
            "error": False,
            "comparison": {
                "status": "🟢 Бизнес растёт",
                "score": 4
            }
        }



class TestStorePeriodSummaryService(
    unittest.TestCase
):


    def test_build_summary(
        self
    ):

        service = (
            StorePeriodSummaryService(
                period_runner=(
                    FakePeriodRunner()
                )
            )
        )


        result = (
            service.build(
                period_code="28D",
                date_to="2026-08-07",
                products=[]
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["comparison"]["status"],
            "🟢 Бизнес растёт"
        )


    def test_error_report(
        self
    ):

        class ErrorRunner:

            def build_store_period_report(
                self,
                period_code,
                date_to,
                products
            ):

                return {
                    "error": True,
                    "message": "Ошибка"
                }


        service = (
            StorePeriodSummaryService(
                period_runner=ErrorRunner()
            )
        )


        result = (
            service.build(
                period_code="28D",
                date_to="2026-08-07",
                products=[]
            )
        )


        self.assertTrue(
            result["error"]
        )


if __name__ == "__main__":
    unittest.main()