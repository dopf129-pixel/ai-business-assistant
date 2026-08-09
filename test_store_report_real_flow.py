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

from services.store_period_insight_service import (
    StorePeriodInsightService
)

from services.store_period_summary_formatter import (
    StorePeriodSummaryFormatter
)

from services.store_report_orchestrator import (
    StoreReportOrchestrator
)

from services.store_report_manager import (
    StoreReportManager
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
                "comparison": {
                    "revenue": {
                        "change_percent": 10
                    },
                    "business_profit": {
                        "change_percent": 15
                    },
                    "margin": {
                        "trend": "Рост"
                    }
                }
            }
        }


class TestStoreReportRealFlow(
    unittest.TestCase
):

    def test_real_store_report_flow(
        self
    ):

        summary_service = (
            StorePeriodSummaryService(
                period_runner=(
                    FakePeriodRunner()
                )
            )
        )

        insight_service = (
            StorePeriodInsightService()
        )

        formatter = (
            StorePeriodSummaryFormatter()
        )

        orchestrator = (
            StoreReportOrchestrator(
                summary_service=summary_service,
                insight_service=insight_service,
                formatter=formatter
            )
        )

        manager = (
            StoreReportManager(
                orchestrator=orchestrator
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

        self.assertIn(
            "period_summary",
            result
        )

        self.assertIn(
            "period_insights",
            result
        )

        self.assertIn(
            "period_text",
            result
        )


        self.assertTrue(
            len(
                result["period_insights"]["insights"]
            ) > 0
        )


if __name__ == "__main__":
    unittest.main()