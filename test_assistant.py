import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)

from decision_engine import DecisionEngine
from health_score import HealthScore
from kpi_service import KPIService
from prediction_service import PredictionService
from risk_analyzer import analyze_risk
from services.finance_service import FinanceService


class FakeFinanceClient:

    def get_accrual_types(self):

        return {
            "accrual_types": [
                {
                    "id": 1,
                    "name": "Acquiring",
                    "description": "Эквайринг"
                },
                {
                    "id": 29,
                    "name": "LastMileCourier",
                    "description": "Доставка до места выдачи"
                },
                {
                    "id": 32,
                    "name": "Logistic",
                    "description": "Логистика"
                },
                {
                    "id": 69,
                    "name": "SaleCommission",
                    "description": "Вознаграждение за продажу"
                }
            ]
        }

    def get_accruals_by_day(
        self,
        accrual_date
    ):

        return {
            "accruals": [
                {
                    "accrual_id": 1,
                    "date": accrual_date,
                    "total_amount": {
                        "amount": "56.00",
                        "currency": "RUB"
                    },
                    "accrued_category": "POSTING",
                    "posting": {
                        "delivery_schema": "Fbo",
                        "products": [
                            {
                                "sku": 111,
                                "delivery": {
                                    "services": [
                                        {
                                            "type_id": 32,
                                            "accrued": {
                                                "amount": "-20.00",
                                                "currency": "RUB"
                                            }
                                        },
                                        {
                                            "type_id": 29,
                                            "accrued": {
                                                "amount": "-1.40",
                                                "currency": "RUB"
                                            }
                                        }
                                    ]
                                },
                                "commission": {
                                    "sale_amount": {
                                        "amount": "90.00",
                                        "currency": "RUB"
                                    },
                                    "sale_commission": {
                                        "amount": "-12.60",
                                        "currency": "RUB"
                                    }
                                }
                            }
                        ]
                    },
                    "item_fees": None
                },
                {
                    "accrual_id": 2,
                    "date": accrual_date,
                    "total_amount": {
                        "amount": "-1.00",
                        "currency": "RUB"
                    },
                    "accrued_category": "ITEM",
                    "posting": None,
                    "item_fees": {
                        "fees": [
                            {
                                "sku": 111,
                                "fees": [
                                    {
                                        "type_id": 1,
                                        "accrued": {
                                            "amount": "-1.00",
                                            "currency": "RUB"
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                },
                {
                    "accrual_id": 3,
                    "date": accrual_date,
                    "total_amount": {
                        "amount": "30.00",
                        "currency": "RUB"
                    },
                    "accrued_category": "POSTING",
                    "posting": {
                        "delivery_schema": "Fbo",
                        "products": [
                            {
                                "sku": 222,
                                "delivery": {
                                    "services": []
                                },
                                "commission": {
                                    "sale_amount": {
                                        "amount": "50.00",
                                        "currency": "RUB"
                                    },
                                    "sale_commission": {
                                        "amount": "-10.00",
                                        "currency": "RUB"
                                    }
                                }
                            }
                        ]
                    },
                    "item_fees": None
                }
            ]
        }


class FakeFinanceErrorClient:

    def get_accrual_types(self):

        return {
            "error": True,
            "message": "Тестовая ошибка API"
        }


class TestAssistant(unittest.TestCase):

    def setUp(self):

        self.health_service = HealthScore()
        self.decision_engine = DecisionEngine()
        self.prediction_service = PredictionService()
        self.kpi_service = KPIService()

    def test_fbo_product_without_discount(self):

        metrics = {
            "archived": False,
            "has_fbo_stocks": True,
            "has_fbs_stocks": False,
            "is_discounted": False
        }

        risk = analyze_risk(metrics)
        health = self.health_service.calculate(metrics)

        self.assertEqual(
            risk["risk_score"],
            5
        )

        self.assertEqual(
            health["score"],
            60
        )

    def test_product_without_fbo_stock(self):

        metrics = {
            "archived": False,
            "has_fbo_stocks": False,
            "has_fbs_stocks": False,
            "is_discounted": False
        }

        risk = analyze_risk(metrics)
        health = self.health_service.calculate(metrics)

        self.assertEqual(
            risk["risk_score"],
            55
        )

        self.assertEqual(
            health["score"],
            0
        )

    def test_archived_product(self):

        metrics = {
            "archived": True,
            "has_fbo_stocks": True,
            "has_fbs_stocks": False,
            "is_discounted": False
        }

        risk = analyze_risk(metrics)

        self.assertEqual(
            risk["risk_score"],
            105
        )

        self.assertEqual(
            risk["risk_level"],
            "🔴 Высокий риск"
        )

    def test_decision_without_discount(self):

        metrics = {
            "archived": False,
            "has_fbo_stocks": True,
            "has_fbs_stocks": False,
            "is_discounted": False
        }

        health = {
            "score": 60,
            "status": "🟡 Требует внимания",
            "reasons": []
        }

        decisions = self.decision_engine.generate(
            metrics,
            health
        )

        actions = [
            item["action"]
            for item in decisions
        ]

        self.assertIn(
            "Рассмотреть запуск акции",
            actions
        )

        self.assertNotIn(
            "Подключить FBS",
            actions
        )

    def test_prediction_stable_state(self):

        metrics = {
            "has_fbo_stocks": True
        }

        memory_analysis = {
            "health_change": 0,
            "risk_change": 0,
            "days_without_discount": 1,
            "fbo_stable": True
        }

        predictions = self.prediction_service.predict(
            metrics,
            memory_analysis
        )

        titles = [
            item["title"]
            for item in predictions
        ]

        self.assertIn(
            "Стабильное состояние",
            titles
        )

    def test_kpi_normal_reserve(self):

        metrics = {
            "has_fbo_stocks": True,
            "is_discounted": False,
            "fbo_present": 10338,
            "fbo_reserved": 83,
            "fbo_available": 10255
        }

        health = {
            "score": 60
        }

        risk = {
            "risk_score": 5
        }

        memory_analysis = {
            "days_without_discount": 1,
            "stock_change": 0
        }

        trend = {
            "status": "🟡 Стабильно",
            "change": 0
        }

        kpi = self.kpi_service.calculate(
            metrics,
            health,
            risk,
            memory_analysis,
            trend
        )

        self.assertEqual(
            kpi["fbo_available"],
            10255
        )

        self.assertEqual(
            kpi["stock_status"],
            "🟢 Нормальный резерв"
        )

        self.assertAlmostEqual(
            kpi["reserved_percent"],
            0.8
        )

        self.assertEqual(
            kpi["ai_score"],
            70
        )

        self.assertEqual(
            kpi["status"],
            "🟡 Требует внимания"
        )

    def test_kpi_high_reserve(self):

        metrics = {
            "has_fbo_stocks": True,
            "is_discounted": False,
            "fbo_present": 100,
            "fbo_reserved": 60,
            "fbo_available": 40
        }

        health = {
            "score": 60
        }

        risk = {
            "risk_score": 5
        }

        memory_analysis = {
            "days_without_discount": 1,
            "stock_change": -10
        }

        trend = {
            "status": "🟡 Стабильно",
            "change": 0
        }

        kpi = self.kpi_service.calculate(
            metrics,
            health,
            risk,
            memory_analysis,
            trend
        )

        self.assertEqual(
            kpi["reserved_percent"],
            60.0
        )

        self.assertEqual(
            kpi["stock_status"],
            "🔴 Высокий резерв"
        )

        self.assertEqual(
            kpi["ai_score"],
            55
        )

    def test_kpi_without_fbo_stock(self):

        metrics = {
            "has_fbo_stocks": False,
            "is_discounted": False,
            "fbo_present": 0,
            "fbo_reserved": 0,
            "fbo_available": 0
        }

        health = {
            "score": 0
        }

        risk = {
            "risk_score": 55
        }

        memory_analysis = {
            "days_without_discount": 1,
            "stock_change": 0
        }

        trend = {
            "status": "🔴 Ухудшение",
            "change": -10
        }

        kpi = self.kpi_service.calculate(
            metrics,
            health,
            risk,
            memory_analysis,
            trend
        )

        self.assertEqual(
            kpi["stock_status"],
            "🔴 Остатков нет"
        )

        self.assertEqual(
            kpi["ai_score"],
            0
        )

        self.assertEqual(
            kpi["status"],
            "🔴 Высокий приоритет"
        )

    def test_finance_calculation_by_sku(self):

        finance_service = FinanceService()
        finance_service.ozon = FakeFinanceClient()

        result = finance_service.get_daily_finance(
            "2026-08-06",
            "111"
        )

        self.assertFalse(
            result["error"]
        )

        self.assertEqual(
            result["operations"],
            2
        )

        self.assertEqual(
            result["sales_count"],
            1
        )

        self.assertEqual(
            result["gross_sales"],
            90.0
        )

        self.assertEqual(
            result["commission"],
            -12.6
        )

        self.assertEqual(
            result["logistics"],
            -21.4
        )

        self.assertEqual(
            result["acquiring"],
            -1.0
        )

        self.assertEqual(
            result["net_accrual"],
            55.0
        )

        self.assertEqual(
            result["other_fees"],
            0.0
        )

    def test_finance_filters_other_sku(self):

        finance_service = FinanceService()
        finance_service.ozon = FakeFinanceClient()

        result = finance_service.get_daily_finance(
            "2026-08-06",
            "222"
        )

        self.assertEqual(
            result["operations"],
            1
        )

        self.assertEqual(
            result["sales_count"],
            1
        )

        self.assertEqual(
            result["gross_sales"],
            50.0
        )

        self.assertEqual(
            result["commission"],
            -10.0
        )

        self.assertEqual(
            result["net_accrual"],
            30.0
        )

    def test_finance_fee_breakdown(self):

        finance_service = FinanceService()
        finance_service.ozon = FakeFinanceClient()

        result = finance_service.get_daily_finance(
            "2026-08-06",
            "111"
        )

        self.assertEqual(
            result["fee_breakdown"]["Эквайринг"],
            -1.0
        )

        self.assertEqual(
            result["fee_breakdown"]["Логистика"],
            -20.0
        )

        self.assertEqual(
            result["fee_breakdown"][
                "Доставка до места выдачи"
            ],
            -1.4
        )

    def test_finance_api_error(self):

        finance_service = FinanceService()
        finance_service.ozon = FakeFinanceErrorClient()

        result = finance_service.get_daily_finance(
            "2026-08-06",
            "111"
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