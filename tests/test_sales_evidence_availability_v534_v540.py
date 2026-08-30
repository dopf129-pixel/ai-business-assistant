import sys

sys.path.insert(
    0,
    "app"
)

from services.assistant_entry_service import (
    AssistantEntryService,
)
from services.assistant_recommendation_service import (
    AssistantRecommendationService,
)
from services.assistant_sales_executor_service import (
    AssistantSalesExecutorService,
)
from services.sales_context_provider import (
    SalesContextProvider,
)
from services.sales_intelligence_service import (
    SalesIntelligenceService,
)


class _Products:

    def __init__(
        self,
        products=None
    ):
        self.products = (
            products
            if products is not None
            else [
                {
                    "product_id": 1,
                    "offer_id": "offer-1",
                    "sku": "sku-1",
                }
            ]
        )

    def load_products(
        self
    ):
        return self.products


class _PeriodProfit:

    def __init__(
        self,
        current=None,
        previous=None
    ):
        self.current = (
            current
            if current is not None
            else [
                {
                    "error": False,
                    "gross_sales": 100,
                    "gross_profit": 30,
                }
            ]
        )
        self.previous = (
            previous
            if previous is not None
            else [
                {
                    "error": False,
                    "gross_sales": 120,
                    "gross_profit": 40,
                }
            ]
        )

    def calculate_period_profit(
        self,
        date_from,
        date_to,
        products
    ):
        profits = (
            self.current
            if date_from == "2026-08-30"
            else self.previous
        )

        return {
            "error": False,
            "profits": profits,
        }


class _Analytics:

    def __init__(
        self,
        change_percent=-10,
        comparison_override=None
    ):
        self.change_percent = change_percent
        self.comparison_override = (
            comparison_override
        )

    def get_period(
        self
    ):
        return {
            "error": False,
            "date_from": "2026-08-30",
            "date_to": "2026-08-30",
        }

    def get_previous_period(
        self
    ):
        return {
            "error": False,
            "date_from": "2026-08-29",
            "date_to": "2026-08-29",
        }

    def analyze(
        self,
        profits,
        previous_result=None
    ):
        if previous_result is None:
            return {
                "error": False,
                "store_profit": {
                    "gross_sales": 120,
                    "gross_profit": 40,
                },
            }

        comparison = (
            self.comparison_override
            if self.comparison_override is not None
            else {
                "error": False,
                "comparison": {
                    "revenue": {
                        "change_percent": (
                            self.change_percent
                        )
                    }
                },
            }
        )

        return {
            "error": False,
            "store_profit": {
                "gross_sales": 100,
                "gross_profit": 30,
            },
            "comparison": comparison,
        }


def _provider(
    products=None,
    current=None,
    previous=None,
    change_percent=-10,
    comparison_override=None
):
    return SalesContextProvider(
        product_service=_Products(
            products
        ),
        period_profit_service=_PeriodProfit(
            current=current,
            previous=previous
        ),
        analytics_service=_Analytics(
            change_percent=change_percent,
            comparison_override=(
                comparison_override
            )
        ),
    )


def test_v534_no_dependencies_preserve_legacy_provider_result():

    result = SalesContextProvider().build()

    assert result == {
        "report": None,
        "period_data": None,
    }


def test_v534_malformed_products_are_unavailable_not_safe():

    result = _provider(
        products=[
            "bad-product"
        ]
    ).build()

    assert result == {
        "report": {
            "sales_down": False,
            "sales_evidence_available": False,
        },
        "period_data": None,
    }


def test_v535_missing_revenue_change_is_unavailable():

    result = _provider(
        comparison_override={
            "error": False,
            "comparison": {
                "revenue": {}
            },
        }
    ).build()

    assert result["report"] == {
        "sales_down": False,
        "sales_evidence_available": False,
    }
    assert result["period_data"][
        "current_profits"
    ][0]["gross_sales"] == 100


def test_v535_non_finite_revenue_change_is_unavailable():

    result = _provider(
        comparison_override={
            "error": False,
            "comparison": {
                "revenue": {
                    "change_percent": float(
                        "nan"
                    )
                }
            },
        }
    ).build()

    assert result["report"] == {
        "sales_down": False,
        "sales_evidence_available": False,
    }


def test_v536_complete_non_decline_evidence_is_available():

    result = _provider(
        change_percent=5
    ).build()

    assert result["report"][
        "sales_down"
    ] is False
    assert result["report"][
        "sales_evidence_available"
    ] is True
    assert result["report"][
        "sales_context"
    ]["profits"][0]["gross_sales"] == 100


def test_v536_confirmed_decline_preserves_action_context_shape():

    result = _provider(
        change_percent=-10
    ).build()

    assert result["report"] == {
        "sales_down": True,
        "sales_context": {
            "profits": [
                {
                    "error": False,
                    "gross_sales": 100,
                    "gross_profit": 30,
                }
            ],
            "previous_result": {
                "error": False,
                "store_profit": {
                    "gross_sales": 120,
                    "gross_profit": 40,
                },
            },
        },
    }
    assert (
        "sales_evidence_available"
        not in result["report"]
    )


def test_v536_empty_profit_evidence_is_unavailable():

    result = _provider(
        current=[]
    ).build()

    assert result == {
        "report": {
            "sales_down": False,
            "sales_evidence_available": False,
        },
        "period_data": None,
    }


def test_v537_configured_partial_entry_path_suppresses_sales_action():

    class _MainFlow:

        def __init__(
            self
        ):
            self.report = None

        def process(
            self,
            text,
            report,
            context,
            user_id
        ):
            self.report = report

            return {
                "error": False,
            }

    main_flow = _MainFlow()

    AssistantEntryService(
        main_flow_service=main_flow,
        product_service=_Products(),
    ).handle(
        "Проверь бизнес",
        user_id=1,
    )

    assert main_flow.report[
        "sales_down"
    ] is False
    assert main_flow.report[
        "sales_evidence_available"
    ] is False
    assert "sales_context" not in (
        main_flow.report
    )

    recommendations = (
        AssistantRecommendationService()
        .analyze(
            main_flow.report
        )
    )

    assert all(
        item["type"] != "sales"
        for item in recommendations[
            "recommendations"
        ]
    )


def test_v538_general_fallback_is_not_clean_when_sales_unknown():

    result = AssistantRecommendationService().analyze(
        {
            "sales_down": False,
            "low_stock": False,
            "sales_evidence_available": False,
            "stock_evidence_available": True,
        }
    )

    assert result["recommendations"] == [
        {
            "type": "general",
            "message": (
                "Недостаточно данных "
                "для полной оценки бизнеса"
            ),
        }
    ]


class _IntelligenceAnalytics:

    def __init__(
        self,
        result
    ):
        self.result = result
        self.calls = []

    def analyze(
        self,
        profits,
        previous_result=None
    ):
        self.calls.append(
            {
                "profits": profits,
                "previous_result": previous_result,
            }
        )

        return self.result


def test_v539_malformed_sales_action_context_fails_before_analytics():

    analytics = _IntelligenceAnalytics(
        {
            "error": False,
        }
    )
    service = SalesIntelligenceService(
        analytics
    )

    result = service.analyze(
        "bad-profits"
    )

    assert result["error"] is True
    assert analytics.calls == []


def test_v539_missing_required_store_metrics_fail_closed():

    service = SalesIntelligenceService(
        _IntelligenceAnalytics(
            {
                "error": False,
                "store_profit": {
                    "gross_sales": 100,
                },
            }
        )
    )

    result = service.analyze(
        []
    )

    assert result["error"] is True
    assert result["metrics"] == {
        "revenue": None,
        "gross_profit": None,
        "business_profit": None,
        "margin_percent": None,
    }


def test_v539_unknown_business_metrics_remain_none():

    service = SalesIntelligenceService(
        _IntelligenceAnalytics(
            {
                "error": False,
                "store_profit": {
                    "gross_sales": 100,
                    "gross_profit": 30,
                },
                "business_profit": {
                    "business_profit": None,
                    "margin_percent": None,
                },
            }
        )
    )

    result = service.analyze(
        []
    )

    assert result["error"] is False
    assert result["metrics"] == {
        "revenue": 100,
        "gross_profit": 30,
        "business_profit": None,
        "margin_percent": None,
    }


def test_v539_explicit_zero_sales_metrics_remain_valid_zero():

    service = SalesIntelligenceService(
        _IntelligenceAnalytics(
            {
                "error": False,
                "store_profit": {
                    "gross_sales": 0,
                    "gross_profit": 0,
                },
            }
        )
    )

    result = service.analyze(
        []
    )

    assert result["error"] is False
    assert result["metrics"][
        "revenue"
    ] == 0
    assert result["metrics"][
        "gross_profit"
    ] == 0


def test_v539_missing_comparison_change_does_not_become_stable():

    service = SalesIntelligenceService(
        _IntelligenceAnalytics(
            {
                "error": False,
                "store_profit": {
                    "gross_sales": 100,
                    "gross_profit": 30,
                },
                "comparison": {
                    "error": False,
                    "comparison": {
                        "revenue": {}
                    },
                },
            }
        )
    )

    result = service.analyze(
        []
    )

    assert result["error"] is False
    assert result["insights"] == []


def test_v539_explicit_zero_change_remains_stable():

    service = SalesIntelligenceService(
        _IntelligenceAnalytics(
            {
                "error": False,
                "store_profit": {
                    "gross_sales": 100,
                    "gross_profit": 30,
                },
                "comparison": {
                    "error": False,
                    "comparison": {
                        "revenue": {
                            "change_percent": 0,
                        }
                    },
                },
            }
        )
    )

    result = service.analyze(
        []
    )

    assert result["insights"] == [
        {
            "type": "sales_stable",
            "severity": "neutral",
            "change_percent": 0,
            "message": (
                "Продажи не изменились "
                "относительно предыдущего периода"
            ),
        }
    ]


def test_v540_sales_executor_renders_unknown_metrics_as_dash():

    class _Intelligence:

        def analyze(
            self,
            profits,
            previous_result=None
        ):
            return {
                "error": False,
                "metrics": {
                    "revenue": None,
                    "gross_profit": None,
                    "business_profit": None,
                    "margin_percent": None,
                },
                "insights": [],
            }

    result = AssistantSalesExecutorService(
        sales_intelligence_service=(
            _Intelligence()
        )
    ).execute(
        {
            "type": "sales",
            "context": {
                "profits": [],
            },
        }
    )

    assert result["error"] is False
    assert result["result"]["details"] == [
        "Выручка: —",
        "Валовая прибыль: —",
        "Прибыль после расходов: —",
        "Маржинальность: —",
    ]
