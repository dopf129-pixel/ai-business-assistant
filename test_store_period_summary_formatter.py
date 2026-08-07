import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.store_period_summary_formatter import (
    StorePeriodSummaryFormatter
)


class TestStorePeriodSummaryFormatter(
    unittest.TestCase
):


    def test_format_success(
        self
    ):

        formatter = (
            StorePeriodSummaryFormatter()
        )


        summary = {
            "error": False,
            "comparison": {
                "status": "🟢 Бизнес растёт",
                "score": 4,
                "comparison": {
                    "revenue": {
                        "name": "Выручка",
                        "change_percent": 20,
                        "trend": "Рост"
                    },
                    "profit": {
                        "name": "Прибыль",
                        "change_percent": 30,
                        "trend": "Рост"
                    }
                }
            }
        }


        result = (
            formatter.format(
                summary
            )
        )


        self.assertIn(
            "🟢 Бизнес растёт",
            result
        )

        self.assertIn(
            "Выручка",
            result
        )

        self.assertIn(
            "20",
            result
        )


    def test_format_error(
        self
    ):

        formatter = (
            StorePeriodSummaryFormatter()
        )


        result = (
            formatter.format(
                {
                    "error": True
                }
            )
        )


        self.assertIn(
            "Не удалось",
            result
        )


if __name__ == "__main__":
    unittest.main()