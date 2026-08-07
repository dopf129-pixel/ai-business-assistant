from risk_analyzer import analyze_risk

from health_score import HealthScore
from health_trend_service import HealthTrendService
from product_memory_service import ProductMemoryService
from prediction_service import PredictionService
from stock_forecast_service import StockForecastService
from kpi_service import KPIService
from decision_engine import DecisionEngine


class AIOrchestratorService:

    def __init__(self):

        self.health_service = HealthScore()
        self.health_trend_service = HealthTrendService()
        self.product_memory_service = ProductMemoryService()
        self.prediction_service = PredictionService()
        self.stock_forecast_service = StockForecastService()
        self.kpi_service = KPIService()
        self.decision_engine = DecisionEngine()

    def analyze(
        self,
        product_id,
        metrics
    ):

        risk = analyze_risk(
            metrics
        )

        health = self.health_service.calculate(
            metrics
        )

        trend = self.health_trend_service.calculate(
            product_id
        )

        self.product_memory_service.save_snapshot(
            product_id,
            metrics,
            health,
            risk
        )

        memory_analysis = (
            self.product_memory_service.analyze(
                product_id,
                limit=7
            )
        )

        stock_history = (
            self.product_memory_service.get_history(
                product_id,
                limit=30
            )
        )

        stock_forecast = (
            self.stock_forecast_service.calculate(
                stock_history
            )
        )

        predictions = self.prediction_service.predict(
            metrics,
            memory_analysis
        )

        kpi = self.kpi_service.calculate(
            metrics,
            health,
            risk,
            memory_analysis,
            trend
        )

        decisions = self.decision_engine.generate(
            metrics,
            health
        )

        return {
            "risk": risk,
            "health": health,
            "trend": trend,
            "memory_analysis": memory_analysis,
            "stock_forecast": stock_forecast,
            "predictions": predictions,
            "kpi": kpi,
            "decisions": decisions
        }