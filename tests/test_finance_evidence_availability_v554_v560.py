from services.assistant_entry_service import (
    AssistantEntryService,
)
from services.assistant_recommendation_service import (
    AssistantRecommendationService,
)


class _MainFlow:

    def __init__(self):
        self.report = None

    def process(
        self,
        text,
        report,
        context,
        user_id,
    ):
        self.report = report

        return {
            "error": False,
            "report": report,
        }


class _SalesProvider:

    def __init__(
        self,
        period_data=None,
        report=None,
    ):
        self.period_data = (
            period_data
            if period_data is not None
            else {
                "current_profits": [
                    {
                        "error": False,
                        "gross_sales": 1000,
                        "gross_profit": 300,
                    }
                ],
                "previous_profits": [
                    {
                        "error": False,
                        "gross_sales": 900,
                        "gross_profit": 250,
                    }
                ],
            }
        )
        self.report = (
            report
            if report is not None
            else {
                "sales_down": False,
                "sales_evidence_available": True,
            }
        )

    def build(self):
        return {
            "report": dict(
                self.report
            ),
            "period_data": self.period_data,
        }


class _StockProvider:

    def build(self):
        return {
            "low_stock": False,
            "stock_evidence_available": True,
        }


class _FinanceProvider:

    def __init__(
        self,
        result,
    ):
        self.result = result
        self.calls = []

    def build(
        self,
        period_data,
    ):
        self.calls.append(
            period_data
        )

        return self.result


def _entry(
    finance_result,
    sales_provider=None,
):
    main = _MainFlow()
    finance = _FinanceProvider(
        finance_result
    )

    entry = AssistantEntryService(
        main_flow_service=main,
        sales_context_provider=(
            sales_provider
            or _SalesProvider()
        ),
        stock_context_provider=(
            _StockProvider()
        ),
        finance_context_provider=finance,
    )

    return entry, main, finance


def test_v554_derived_finance_failure_is_explicitly_unavailable():

    entry, main, finance = _entry(
        None
    )

    result = entry.handle(
        "Проверь бизнес",
        user_id=1,
    )

    assert result["error"] is False
    assert main.report["sales_down"] is False
    assert main.report["sales_evidence_available"] is True
    assert main.report["low_stock"] is False
    assert main.report["stock_evidence_available"] is True
    assert (
        main.report["finance_evidence_available"]
        is False
    )
    assert "finance_context" not in main.report
    assert len(finance.calls) == 1


def test_v555_verified_derived_finance_is_marked_available():

    finance_context = {
        "finance_context": {
            "finance_data": {
                "revenue": 1000,
                "expenses": 700,
                "profit": 300,
                "margin": 30,
            },
            "previous_data": {
                "revenue": 900,
                "expenses": 650,
                "profit": 250,
                "margin": 27.78,
            },
        }
    }

    entry, main, _ = _entry(
        finance_context
    )

    entry.handle(
        "Проверь бизнес",
        user_id=1,
    )

    assert main.report[
        "finance_evidence_available"
    ] is True
    assert main.report[
        "finance_context"
    ] == finance_context[
        "finance_context"
    ]


def test_v556_explicit_finance_context_overrides_failed_derived_context():

    entry, main, _ = _entry(
        None
    )

    explicit = {
        "finance_data": {
            "revenue": 500,
            "expenses": 300,
            "profit": 200,
            "margin": 40,
        },
        "previous_data": {
            "revenue": 450,
            "expenses": 300,
            "profit": 150,
            "margin": 33.33,
        },
    }

    entry.handle(
        "Проверь бизнес",
        context={
            "finance_context": explicit,
        },
        user_id=1,
    )

    assert main.report[
        "finance_context"
    ] == explicit
    assert main.report[
        "finance_evidence_available"
    ] is True


def test_v557_no_period_data_does_not_invent_finance_availability():

    entry, main, _ = _entry(
        None,
        sales_provider=_SalesProvider(
            period_data=None,
            report={
                "sales_down": False,
                "sales_evidence_available": False,
            },
        ),
    )

    # Force an actual None period payload rather than the helper default.
    entry.sales_context_provider.period_data = None

    entry.handle(
        "Проверь бизнес",
        user_id=1,
    )

    assert (
        main.report["sales_evidence_available"]
        is False
    )
    assert "finance_evidence_available" not in (
        main.report
    )


def test_v558_unavailable_finance_prevents_clean_business_fallback():

    result = AssistantRecommendationService().analyze({
        "sales_down": False,
        "low_stock": False,
        "sales_evidence_available": True,
        "stock_evidence_available": True,
        "finance_evidence_available": False,
    })

    assert result["recommendations"] == [{
        "type": "general",
        "message": "Недостаточно данных для полной оценки бизнеса",
    }]


def test_v559_false_finance_availability_suppresses_finance_action():

    result = AssistantRecommendationService().analyze({
        "sales_down": False,
        "low_stock": False,
        "sales_evidence_available": True,
        "stock_evidence_available": True,
        "finance_evidence_available": False,
        "finance_context": {
            "finance_data": {
                "revenue": 100,
            }
        },
    })

    assert all(
        item["type"] != "finance"
        for item in result["recommendations"]
    )
    assert result["recommendations"] == [{
        "type": "general",
        "message": "Недостаточно данных для полной оценки бизнеса",
    }]


def test_v560_legacy_finance_context_without_availability_stays_compatible():

    result = AssistantRecommendationService().analyze({
        "finance_context": {
            "finance_data": {
                "revenue": 100,
            }
        },
    })

    assert result["recommendations"][0][
        "type"
    ] == "finance"
