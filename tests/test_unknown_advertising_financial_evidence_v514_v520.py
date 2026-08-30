import io
from contextlib import redirect_stdout

from services.advertising_dashboard_service import (
    AdvertisingDashboardService,
)
from services.advertising_service import (
    AdvertisingService,
)
from services.business_analytics_service import (
    BusinessAnalyticsService,
)
from services.business_profit_dashboard_service import (
    BusinessProfitDashboardService,
)
from services.sales_intelligence_service import (
    SalesIntelligenceService,
)
from services.assistant_sales_executor_service import (
    AssistantSalesExecutorService,
)
from telegram_core_factory import create_telegram_core


class _EmptyExpenseRepository:
    def get_expenses_by_date(self, expense_date):
        return []


def _profits():
    return [
        {
            "error": False,
            "sales_count": 10,
            "gross_sales": 10000.0,
            "net_accrual": 7000.0,
            "total_cost": 2000.0,
            "gross_profit": 5000.0,
        }
    ]


def test_v514_production_core_keeps_missing_advertising_unknown():
    core = create_telegram_core()

    analytics = (
        core["action_router"]
        .executors["sales"]
        .sales_intelligence_service
        .analytics_service
    )

    assert analytics.business_analytics.advertising_cost is None


def test_v514_explicit_zero_advertising_remains_explicit_zero():
    core = create_telegram_core(
        advertising_cost=0
    )

    analytics = (
        core["action_router"]
        .executors["sales"]
        .sales_intelligence_service
        .analytics_service
    )

    assert analytics.business_analytics.advertising_cost == 0


def test_v515_unknown_advertising_blocks_business_profit():
    service = BusinessAnalyticsService(
        tax_mode="USN_INCOME",
        tax_rate=6,
        minimum_tax_rate=1,
        advertising_cost=None,
        analysis_date="2026-08-07",
        expense_repository=_EmptyExpenseRepository(),
    )

    result = service.calculate(_profits())

    assert result["error"] is False
    assert result["advertising"] == {
        "error": False,
        "configured": False,
        "advertising_cost": None,
    }
    assert result["business_profit"]["configured"] is False
    assert result["business_profit"]["business_profit"] is None
    assert result["business_profit"]["margin_percent"] is None
    assert result["business_profit"]["missing_fields"] == [
        "advertising"
    ]


def test_v516_unknown_tax_and_advertising_report_both_missing():
    service = BusinessAnalyticsService(
        tax_mode=None,
        tax_rate=0,
        minimum_tax_rate=1,
        advertising_cost=None,
        analysis_date="2026-08-07",
        expense_repository=_EmptyExpenseRepository(),
    )

    result = service.calculate(_profits())

    assert result["tax"]["configured"] is False
    assert result["business_profit"]["business_profit"] is None
    assert result["business_profit"]["missing_fields"] == [
        "advertising",
        "tax",
    ]


def test_v516_explicit_zero_advertising_still_calculates():
    service = BusinessAnalyticsService(
        tax_mode="USN_INCOME",
        tax_rate=6,
        minimum_tax_rate=1,
        advertising_cost=0,
        analysis_date="2026-08-07",
        expense_repository=_EmptyExpenseRepository(),
    )

    result = service.calculate(_profits())

    assert result["advertising"]["configured"] is True
    assert result["advertising"]["advertising_cost"] == 0.0
    assert result["business_profit"]["business_profit"] == 4400.0
    assert result["business_profit"]["margin_percent"] == 44.0


def test_v517_advertising_dashboard_does_not_render_unknown_as_zero():
    dashboard = AdvertisingDashboardService()

    assert dashboard.format_money(None) == "—"
    assert dashboard.format_money(0) == "0,00 ₽"


def test_v517_business_profit_dashboard_does_not_render_unknown_as_zero():
    dashboard = BusinessProfitDashboardService()

    assert dashboard.format_money(None) == "—"
    assert dashboard.format_money(0) == "0,00 ₽"

    stream = io.StringIO()
    with redirect_stdout(stream):
        dashboard.print_dashboard({
            "error": False,
            "gross_sales": 10000.0,
            "gross_profit": 5000.0,
            "tax_amount": 600.0,
            "advertising_cost": None,
            "other_expenses": 0.0,
            "business_profit": None,
            "margin_percent": None,
        })

    output = stream.getvalue()
    assert "Реклама: —" in output
    assert "Прибыль после налога: —" in output
    assert "Маржинальность после налога: —" in output


def test_v518_sales_executor_formats_unknown_profit_metrics_as_dash():
    class _SalesIntelligence:
        def analyze(self, profits, previous_result=None):
            return {
                "error": False,
                "metrics": {
                    "revenue": 10000.0,
                    "gross_profit": 5000.0,
                    "business_profit": None,
                    "margin_percent": None,
                },
                "insights": [],
            }

    service = AssistantSalesExecutorService(
        sales_intelligence_service=_SalesIntelligence()
    )

    result = service.execute({
        "context": {
            "profits": [],
            "previous_result": None,
        }
    })

    details = result["result"]["details"]
    assert "Прибыль после расходов: —" in details
    assert "Маржинальность: —" in details
    assert all("None" not in item for item in details)


def test_v519_sales_intelligence_preserves_unknown_profit_as_none():
    analytics = BusinessAnalyticsService(
        tax_mode="USN_INCOME",
        tax_rate=6,
        minimum_tax_rate=1,
        advertising_cost=None,
        analysis_date="2026-08-07",
        expense_repository=_EmptyExpenseRepository(),
    )
    intelligence = SalesIntelligenceService(
        analytics_service=analytics
    )

    result = intelligence.analyze(_profits())

    assert result["error"] is False
    assert result["metrics"]["revenue"] == 10000.0
    assert result["metrics"]["gross_profit"] == 5000.0
    assert result["metrics"]["business_profit"] is None
    assert result["metrics"]["margin_percent"] is None


def test_v519_tax_error_is_not_hidden_by_unknown_advertising():
    service = BusinessAnalyticsService(
        tax_mode="UNSUPPORTED",
        tax_rate=6,
        minimum_tax_rate=1,
        advertising_cost=None,
        analysis_date="2026-08-07",
        expense_repository=_EmptyExpenseRepository(),
    )

    result = service.calculate(_profits())

    assert result["tax"]["error"] is True
    assert result["business_profit"]["error"] is True
    assert result["business_profit"]["message"] == (
        "Неподдерживаемый налоговый режим"
    )


def test_v515_advertising_service_distinguishes_missing_from_zero():
    service = AdvertisingService()

    missing = service.calculate(None)
    empty = service.calculate("")
    zero = service.calculate(0)

    assert missing == {
        "error": False,
        "configured": False,
        "advertising_cost": None,
    }
    assert empty == missing
    assert zero == {
        "error": False,
        "configured": True,
        "advertising_cost": 0.0,
    }
