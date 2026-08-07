from datetime import date

from config import (
    PROJECT_NAME,
    VERSION,
    SELLING_MODEL
)

from database import (
    create_tables,
    save_metric,
    save_risk
)

from services.product_service import ProductService
from services.metrics_service import MetricsService

from services.finance_service import FinanceService
from services.finance_dashboard_service import (
    FinanceDashboardService
)

from services.cost_service import ProductCostService

from services.profit_service import ProfitService
from services.profit_dashboard_service import (
    ProfitDashboardService
)

from services.store_profit_service import (
    StoreProfitService
)

from services.store_profit_dashboard_service import (
    StoreProfitDashboardService
)

from health_history_service import HealthHistoryService

from action_service import ActionService
from action_dashboard_service import ActionDashboardService
from action_automation_service import (
    ActionAutomationService
)

from change_log_service import ChangeLogService
from summary_report_service import SummaryReportService
from ai_orchestrator_service import AIOrchestratorService


class AssistantRunner:

    def __init__(self):

        self.product_service = ProductService()
        self.metrics_service = MetricsService()

        self.finance_service = FinanceService()
        self.finance_dashboard = (
            FinanceDashboardService()
        )

        self.cost_service = ProductCostService()

        self.profit_service = ProfitService()
        self.profit_dashboard = (
            ProfitDashboardService()
        )

        self.store_profit_service = (
            StoreProfitService()
        )

        self.store_profit_dashboard = (
            StoreProfitDashboardService()
        )

        self.health_history = (
            HealthHistoryService()
        )

        self.orchestrator = (
            AIOrchestratorService()
        )

        self.action_service = ActionService()

        self.action_dashboard = (
            ActionDashboardService()
        )

        self.action_automation = (
            ActionAutomationService()
        )

        self.change_log = ChangeLogService()

        self.summary_report_service = (
            SummaryReportService()
        )

        self.finance_date = (
            date.today().isoformat()
        )

        self.store_profits = []

    def format_number(
        self,
        value
    ):

        try:

            return (
                f"{int(value):,}"
                .replace(",", " ")
            )

        except (
            TypeError,
            ValueError
        ):

            return "0"

    def print_header(self):

        print("======================")
        print(PROJECT_NAME)
        print("Версия:", VERSION)
        print(
            "Модель продаж:",
            SELLING_MODEL
        )
        print("======================")
        print("Ассистент запущен!")

    def print_product_status(
        self,
        metrics
    ):

        print()
        print("Статус:")

        if metrics.get("archived"):

            print("❌ Товар в архиве")

        else:

            print("✅ Товар активен")

        print()
        print("Склады:")

        if SELLING_MODEL in (
            "FBO",
            "HYBRID"
        ):

            if metrics.get(
                "has_fbo_stocks"
            ):

                print(
                    "✅ FBO остатки есть"
                )

            else:

                print(
                    "⚠️ Нет FBO остатков"
                )

            if metrics.get(
                "stocks_error"
            ):

                print(
                    "Ошибка получения "
                    "остатков:",
                    metrics[
                        "stocks_error"
                    ]
                )

            else:

                print(
                    "Всего:",
                    self.format_number(
                        metrics.get(
                            "fbo_present",
                            0
                        )
                    ),
                    "шт."
                )

                print(
                    "Зарезервировано:",
                    self.format_number(
                        metrics.get(
                            "fbo_reserved",
                            0
                        )
                    ),
                    "шт."
                )

                print(
                    "Доступно:",
                    self.format_number(
                        metrics.get(
                            "fbo_available",
                            0
                        )
                    ),
                    "шт."
                )

        if SELLING_MODEL in (
            "FBS",
            "HYBRID"
        ):

            if metrics.get(
                "has_fbs_stocks"
            ):

                print(
                    "✅ FBS остатки есть"
                )

            else:

                print(
                    "⚠️ Нет FBS остатков"
                )

    def print_risk(
        self,
        risk
    ):

        print()
        print("Риск:")
        print(
            risk["risk_level"]
        )

        print(
            "Баллы риска:",
            risk["risk_score"]
        )

        reasons = risk.get(
            "reasons",
            []
        )

        if reasons:

            print("Причины:")

            for reason in reasons:

                print(
                    "-",
                    reason
                )

    def print_health(
        self,
        health
    ):

        print()
        print("Здоровье товара:")
        print(
            health["status"]
        )

        print(
            "Баллы:",
            health["score"],
            "/100"
        )

        reasons = health.get(
            "reasons",
            []
        )

        if reasons:

            print("Причины:")

            for reason in reasons:

                print(
                    "-",
                    reason
                )

    def print_health_history(
        self,
        history
    ):

        print()
        print("История здоровья:")

        if not history:

            print(
                "Истории пока нет"
            )

            return

        for row in history[:5]:

            print()
            print(
                "Баллы:",
                row[0]
            )
            print(
                "Статус:",
                row[1]
            )
            print(
                "Дата:",
                row[2]
            )

    def print_health_trend(
        self,
        trend
    ):

        print()
        print("Тренд здоровья:")

        print(
            "Текущее:",
            trend["current"],
            "/100"
        )

        print(
            "Предыдущее:",
            trend["previous"],
            "/100"
        )

        print(
            "Изменение:",
            trend["change"]
        )

        print(
            "Состояние:",
            trend["status"]
        )

    def print_product_memory(
        self,
        memory_analysis
    ):

        print()
        print(
            "AI-память товара:"
        )

        print(
            "Записей проанализировано:",
            memory_analysis[
                "records"
            ]
        )

        print(
            memory_analysis[
                "summary"
            ]
        )

    def print_predictions(
        self,
        predictions
    ):

        print()
        print("AI-прогноз:")

        if not predictions:

            print(
                "Прогнозов нет"
            )

            return

        for prediction in predictions:

            print()

            print(
                "Уровень:",
                prediction[
                    "level"
                ]
            )

            print(
                "Прогноз:",
                prediction[
                    "title"
                ]
            )

            print(
                "Описание:",
                prediction[
                    "message"
                ]
            )

    def print_decisions(
        self,
        decisions
    ):

        print()
        print("AI Решения:")

        if not decisions:

            print(
                "Решений нет"
            )

            return

        for decision in decisions:

            print()

            print(
                "Приоритет:",
                decision[
                    "priority"
                ]
            )

            print(
                "Действие:",
                decision[
                    "action"
                ]
            )

            print(
                "Причина:",
                decision[
                    "reason"
                ]
            )

            print(
                "Влияние:",
                decision[
                    "impact"
                ]
            )

    def process_product(
        self,
        product
    ):

        product_id = product[0]

        metrics_result = (
            self.metrics_service
            .get_product_metrics(
                product_id
            )
        )

        if "metrics" not in metrics_result:

            print()

            print(
                "Не удалось получить "
                "метрики:",
                metrics_result
            )

            return

        metrics = (
            metrics_result[
                "metrics"
            ]
        )

        save_metric(
            metrics
        )

        print()
        print(
            "================================"
        )
        print(
            "Ozon AI Report"
        )
        print(
            "================================"
        )

        print()

        print(
            "Товар:",
            metrics.get(
                "offer_id"
            )
        )

        print(
            "ID:",
            product_id
        )

        self.print_product_status(
            metrics
        )

        analysis = (
            self.orchestrator
            .analyze(
                product_id,
                metrics
            )
        )

        risk = analysis["risk"]
        health = analysis["health"]
        trend = analysis["trend"]

        memory_analysis = (
            analysis[
                "memory_analysis"
            ]
        )

        stock_forecast = (
            analysis[
                "stock_forecast"
            ]
        )

        predictions = (
            analysis[
                "predictions"
            ]
        )

        kpi = analysis["kpi"]

        decisions = (
            analysis[
                "decisions"
            ]
        )

        save_risk(
            risk,
            product_id
        )

        self.health_history.save(
            product_id,
            health
        )

        self.print_risk(
            risk
        )

        self.print_health(
            health
        )

        history = (
            self.health_history
            .get_history(
                product_id
            )
        )

        self.print_health_history(
            history
        )

        self.print_health_trend(
            trend
        )

        self.print_product_memory(
            memory_analysis
        )

        (
            self.orchestrator
            .stock_forecast_service
            .print_forecast(
                stock_forecast
            )
        )

        self.print_predictions(
            predictions
        )

        (
            self.orchestrator
            .kpi_service
            .print_dashboard(
                kpi
            )
        )

        sku = (
            metrics.get("sku")
            or (
                product[2]
                if len(product) > 2
                else None
            )
        )

        if sku is None:

            finance = {
                "error": True,
                "message": (
                    "SKU товара не найден. "
                    "Финансовый отчёт "
                    "не построен."
                )
            }

        else:

            finance = (
                self.finance_service
                .get_daily_finance(
                    self.finance_date,
                    sku
                )
            )

        self.finance_dashboard.print_dashboard(
            finance
        )

        cost = (
            self.cost_service
            .get_cost(
                product_id
            )
        )

        if cost:

            profit = (
                self.profit_service
                .calculate(
                    finance,
                    cost[3]
                )
            )

        else:

            profit = {
                "error": True,
                "message": (
                    "Себестоимость товара "
                    "не задана"
                )
            }

        self.profit_dashboard.print_dashboard(
            profit
        )

        self.store_profits.append(
            profit
        )

        self.print_decisions(
            decisions
        )

        created = (
            self.action_service
            .create_actions(
                product_id,
                decisions
            )
        )

        print()

        print(
            "Создано новых действий:",
            created
        )

        print()
        print(
            "Автоматизация действий:"
        )

        automation_results = (
            self.action_automation
            .execute(
                product_id
            )
        )

        if automation_results:

            for result in automation_results:

                print(
                    "-",
                    result
                )

        else:

            print(
                "Новых действий нет"
            )

        print()
        print(
            "История действий:"
        )

        self.action_dashboard.print_dashboard(
            product_id
        )

        print()
        print("Изменения:")

        changes = (
            self.change_log
            .get_changes(
                product_id
            )
        )

        if changes:

            for change in changes[:5]:

                print(
                    change
                )

        else:

            print(
                "Изменений нет"
            )

        summary_path = (
            self.summary_report_service
            .save_report(
                product_id=product_id,
                offer_id=metrics.get(
                    "offer_id"
                ),
                health=health,
                risk=risk,
                memory_analysis=(
                    memory_analysis
                ),
                predictions=predictions,
                stock_forecast=(
                    stock_forecast
                ),
                kpi=kpi,
                finance=finance,
                profit=profit
            )
        )

        print()
        print(
            "Краткий отчёт сохранён:"
        )

        print(
            summary_path
        )

        print()
        print(
            "Отчёт завершён"
        )

    def print_store_summary(
        self
    ):

        print()
        print(
            "================================"
        )
        print(
            "Итог по магазину"
        )
        print(
            "================================"
        )

        store_result = (
            self.store_profit_service
            .calculate(
                self.store_profits
            )
        )

        (
            self.store_profit_dashboard
            .print_dashboard(
                store_result
            )
        )

    def run(self):

        self.print_header()

        create_tables()

        print(
            "База данных готова"
        )

        count = (
            self.product_service
            .update_products()
        )

        print()

        print(
            "Товары сохранены в базу:",
            count
        )

        products = (
            self.product_service
            .load_products()
        )

        print()
        print(
            "Товары в памяти ассистента:"
        )

        for product in products:

            print(
                product
            )

        print()
        print(
            "AI Отчёты:"
        )

        for product in products:

            self.process_product(
                product
            )

        self.print_store_summary()