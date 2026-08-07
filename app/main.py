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

from health_history_service import HealthHistoryService

from action_service import ActionService
from action_dashboard_service import ActionDashboardService
from action_automation_service import ActionAutomationService

from change_log_service import ChangeLogService
from summary_report_service import SummaryReportService
from ai_orchestrator_service import AIOrchestratorService


def format_number(value):

    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def print_header():

    print("======================")
    print(PROJECT_NAME)
    print("Версия:", VERSION)
    print("Модель продаж:", SELLING_MODEL)
    print("======================")
    print("Ассистент запущен!")


def print_product_status(metrics):

    print()
    print("Статус:")

    if metrics.get("archived"):
        print("❌ Товар в архиве")
    else:
        print("✅ Товар активен")

    print()
    print("Склады:")

    if SELLING_MODEL in ("FBO", "HYBRID"):

        if metrics.get("has_fbo_stocks"):
            print("✅ FBO остатки есть")
        else:
            print("⚠️ Нет FBO остатков")

        if metrics.get("stocks_error"):

            print(
                "Ошибка получения остатков:",
                metrics["stocks_error"]
            )

        else:

            print(
                "Всего:",
                format_number(
                    metrics.get("fbo_present", 0)
                ),
                "шт."
            )

            print(
                "Зарезервировано:",
                format_number(
                    metrics.get("fbo_reserved", 0)
                ),
                "шт."
            )

            print(
                "Доступно:",
                format_number(
                    metrics.get("fbo_available", 0)
                ),
                "шт."
            )

    if SELLING_MODEL in ("FBS", "HYBRID"):

        if metrics.get("has_fbs_stocks"):
            print("✅ FBS остатки есть")
        else:
            print("⚠️ Нет FBS остатков")


def print_risk(risk):

    print()
    print("Риск:")
    print(risk["risk_level"])

    print(
        "Баллы риска:",
        risk["risk_score"]
    )

    reasons = risk.get("reasons", [])

    if reasons:

        print("Причины:")

        for reason in reasons:
            print("-", reason)


def print_health(health):

    print()
    print("Здоровье товара:")
    print(health["status"])

    print(
        "Баллы:",
        health["score"],
        "/100"
    )

    reasons = health.get("reasons", [])

    if reasons:

        print("Причины:")

        for reason in reasons:
            print("-", reason)


def print_health_history(history):

    print()
    print("История здоровья:")

    if not history:
        print("Истории пока нет")
        return

    for row in history[:5]:

        print()
        print("Баллы:", row[0])
        print("Статус:", row[1])
        print("Дата:", row[2])


def print_health_trend(trend):

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


def print_product_memory(memory_analysis):

    print()
    print("AI-память товара:")

    print(
        "Записей проанализировано:",
        memory_analysis["records"]
    )

    print(
        memory_analysis["summary"]
    )


def print_predictions(predictions):

    print()
    print("AI-прогноз:")

    if not predictions:
        print("Прогнозов нет")
        return

    for prediction in predictions:

        print()

        print(
            "Уровень:",
            prediction["level"]
        )

        print(
            "Прогноз:",
            prediction["title"]
        )

        print(
            "Описание:",
            prediction["message"]
        )


def print_decisions(decisions):

    print()
    print("AI Решения:")

    if not decisions:
        print("Решений нет")
        return

    for decision in decisions:

        print()

        print(
            "Приоритет:",
            decision["priority"]
        )

        print(
            "Действие:",
            decision["action"]
        )

        print(
            "Причина:",
            decision["reason"]
        )

        print(
            "Влияние:",
            decision["impact"]
        )


def start():

    print_header()

    create_tables()

    print("База данных готова")

    product_service = ProductService()
    metrics_service = MetricsService()

    finance_service = FinanceService()
    finance_dashboard = FinanceDashboardService()

    health_history = HealthHistoryService()

    orchestrator = AIOrchestratorService()

    action_service = ActionService()
    dashboard = ActionDashboardService()
    automation = ActionAutomationService()

    change_log = ChangeLogService()
    summary_report_service = SummaryReportService()

    finance_date = date.today().isoformat()

    count = product_service.update_products()

    print()

    print(
        "Товары сохранены в базу:",
        count
    )

    products = product_service.load_products()

    print()
    print("Товары в памяти ассистента:")

    for product in products:
        print(product)

    print()
    print("AI Отчёты:")

    for product in products:

        product_id = product[0]

        metrics_result = (
            metrics_service
            .get_product_metrics(product_id)
        )

        if "metrics" not in metrics_result:

            print()

            print(
                "Не удалось получить метрики:",
                metrics_result
            )

            continue

        metrics = metrics_result["metrics"]

        save_metric(metrics)

        print()
        print("================================")
        print("Ozon AI Report")
        print("================================")

        print()

        print(
            "Товар:",
            metrics.get("offer_id")
        )

        print(
            "ID:",
            product_id
        )

        print_product_status(metrics)

        analysis = orchestrator.analyze(
            product_id,
            metrics
        )

        risk = analysis["risk"]
        health = analysis["health"]
        trend = analysis["trend"]
        memory_analysis = analysis["memory_analysis"]
        stock_forecast = analysis["stock_forecast"]
        predictions = analysis["predictions"]
        kpi = analysis["kpi"]
        decisions = analysis["decisions"]

        save_risk(
            risk,
            product_id
        )

        health_history.save(
            product_id,
            health
        )

        print_risk(risk)
        print_health(health)

        history = health_history.get_history(
            product_id
        )

        print_health_history(history)
        print_health_trend(trend)
        print_product_memory(memory_analysis)

        orchestrator.stock_forecast_service.print_forecast(
            stock_forecast
        )

        print_predictions(predictions)

        orchestrator.kpi_service.print_dashboard(
            kpi
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
                    "Финансовый отчёт не построен."
                )
            }

        else:

            finance = finance_service.get_daily_finance(
                finance_date,
                sku
            )

        finance_dashboard.print_dashboard(
            finance
        )

        print_decisions(decisions)

        created = action_service.create_actions(
            product_id,
            decisions
        )

        print()

        print(
            "Создано новых действий:",
            created
        )

        print()
        print("Автоматизация действий:")

        automation_results = automation.execute(
            product_id
        )

        if automation_results:

            for result in automation_results:
                print("-", result)

        else:

            print("Новых действий нет")

        print()
        print("История действий:")

        dashboard.print_dashboard(
            product_id
        )

        print()
        print("Изменения:")

        changes = change_log.get_changes(
            product_id
        )

        if changes:

            for change in changes[:5]:
                print(change)

        else:

            print("Изменений нет")

        summary_path = summary_report_service.save_report(
    product_id=product_id,
    offer_id=metrics.get("offer_id"),
    health=health,
    risk=risk,
    memory_analysis=memory_analysis,
    predictions=predictions,
    stock_forecast=stock_forecast,
    kpi=kpi,
    finance=finance
)

        print()
        print("Краткий отчёт сохранён:")
        print(summary_path)

        print()
        print("Отчёт завершён")


if __name__ == "__main__":
    start()