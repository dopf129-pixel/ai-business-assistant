import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)

from services.finance_analytics_service import (
    FinanceAnalyticsService
)


class FakeFinanceService:

    def __init__(
        self,
        daily_results
    ):
        self.daily_results = daily_results

    def get_daily_finance(
        self,
        accrual_date,
        sku=None
    ):
        return self.daily_results.get(
            accrual_date,
            {
                "error": False,
                "operations": 0,
                "sales_count": 0,
                "gross_sales": 0,
                "net_accrual": 0,
                "commission": 0,
                "logistics": 0,
                "acquiring": 0,
                "other_fees": 0,
                "fee_breakdown": {}
            }
        )


class TestFinanceAnalyticsService(
    unittest.TestCase
):

    def test_period_aggregation(self):

        fake = FakeFinanceService(
            {
                "2026-08-01": {
                    "error": False,
                    "operations": 2,
                    "sales_count": 1,
                    "gross_sales": 100,
                    "net_accrual": 60,
                    "commission": -10,
                    "logistics": -20,
                    "acquiring": -2,
                    "other_fees": -8,
                    "fee_breakdown": {
                        "Логистика": -20
                    }
                },
                "2026-08-02": {
                    "error": False,
                    "operations": 3,
                    "sales_count": 2,
                    "gross_sales": 200,
                    "net_accrual": 120,
                    "commission": -20,
                    "logistics": -40,
                    "acquiring": -4,
                    "other_fees": -16,
                    "fee_breakdown": {
                        "Логистика": -40
                    }
                }
            }
        )

        service = FinanceAnalyticsService(
            fake
        )

        result = (
            service.get_period_finance(
                "2026-08-01",
                "2026-08-02",
                "123"
            )
        )

        self.assertFalse(
            result["error"]
        )

        self.assertEqual(
            result["days_requested"],
            2
        )

        self.assertEqual(
            result["days_loaded"],
            2
        )

        self.assertEqual(
            result["days_failed"],
            0
        )

        self.assertEqual(
            result["operations"],
            5
        )

        self.assertEqual(
            result["sales_count"],
            3
        )

        self.assertEqual(
            result["gross_sales"],
            300.0
        )

        self.assertEqual(
            result["net_accrual"],
            180.0
        )

        self.assertEqual(
            result["commission"],
            -30.0
        )

        self.assertEqual(
            result["logistics"],
            -60.0
        )

        self.assertEqual(
            result["acquiring"],
            -6.0
        )

        self.assertEqual(
            result["other_fees"],
            -24.0
        )

        self.assertEqual(
            result[
                "fee_breakdown"
            ][
                "Логистика"
            ],
            -60.0
        )

    def test_partial_day_error(self):

        fake = FakeFinanceService(
            {
                "2026-08-01": {
                    "error": False,
                    "operations": 2,
                    "sales_count": 1,
                    "gross_sales": 100,
                    "net_accrual": 60,
                    "commission": -10,
                    "logistics": -20,
                    "acquiring": -2,
                    "other_fees": -8,
                    "fee_breakdown": {}
                },
                "2026-08-02": {
                    "error": True,
                    "message": "Rate limit"
                },
                "2026-08-03": {
                    "error": False,
                    "operations": 4,
                    "sales_count": 3,
                    "gross_sales": 300,
                    "net_accrual": 180,
                    "commission": -30,
                    "logistics": -60,
                    "acquiring": -6,
                    "other_fees": -24,
                    "fee_breakdown": {}
                }
            }
        )

        service = FinanceAnalyticsService(
            fake
        )

        result = (
            service.get_period_finance(
                "2026-08-01",
                "2026-08-03"
            )
        )

        self.assertFalse(
            result["error"]
        )

        self.assertEqual(
            result["days_requested"],
            3
        )

        self.assertEqual(
            result["days_loaded"],
            2
        )

        self.assertEqual(
            result["days_failed"],
            1
        )

        self.assertEqual(
            result["gross_sales"],
            400.0
        )

        self.assertEqual(
            len(
                result["errors"]
            ),
            1
        )

        self.assertEqual(
            result["errors"][0]["date"],
            "2026-08-02"
        )

    def test_all_days_failed(self):

        fake = FakeFinanceService(
            {
                "2026-08-01": {
                    "error": True,
                    "message": "Ошибка 1"
                },
                "2026-08-02": {
                    "error": True,
                    "message": "Ошибка 2"
                }
            }
        )

        service = FinanceAnalyticsService(
            fake
        )

        result = (
            service.get_period_finance(
                "2026-08-01",
                "2026-08-02"
            )
        )

        self.assertTrue(
            result["error"]
        )

        self.assertEqual(
            result["days_loaded"],
            0
        )

        self.assertEqual(
            result["days_failed"],
            2
        )

        self.assertEqual(
            result["message"],
            (
                "Не удалось получить "
                "финансовые данные "
                "ни за один день периода"
            )
        )

    def test_invalid_date_range(self):

        fake = FakeFinanceService(
            {}
        )

        service = FinanceAnalyticsService(
            fake
        )

        result = (
            service.get_period_finance(
                "bad-date",
                "2026-08-02"
            )
        )

        self.assertTrue(
            result["error"]
        )

        self.assertEqual(
            result["message"],
            "Некорректный диапазон дат"
        )

    def test_missing_dates(self):

        fake = FakeFinanceService(
            {}
        )

        service = FinanceAnalyticsService(
            fake
        )

        result = (
            service.get_period_finance(
                None,
                "2026-08-02"
            )
        )

        self.assertTrue(
            result["error"]
        )

    def test_sku_is_preserved(self):

        fake = FakeFinanceService(
            {
                "2026-08-01": {
                    "error": False,
                    "operations": 0,
                    "sales_count": 0,
                    "gross_sales": 0,
                    "net_accrual": 0,
                    "commission": 0,
                    "logistics": 0,
                    "acquiring": 0,
                    "other_fees": 0,
                    "fee_breakdown": {}
                }
            }
        )

        service = FinanceAnalyticsService(
            fake
        )

        result = (
            service.get_period_finance(
                "2026-08-01",
                "2026-08-01",
                "3921245627"
            )
        )

        self.assertEqual(
            result["sku"],
            "3921245627"
        )


if __name__ == "__main__":
    unittest.main()