from services.assistant_finance_executor_service import (
    AssistantFinanceExecutorService,
)
from services.finance_context_provider import (
    FinanceContextProvider,
)
from services.finance_intelligence_service import (
    FinanceIntelligenceService,
)


def _period_data(
    current=None,
    previous=None,
):
    return {
        "current_profits": (
            current
            if current is not None
            else [{
                "error": False,
                "gross_sales": 1000,
                "gross_profit": 300,
            }]
        ),
        "previous_profits": (
            previous
            if previous is not None
            else [{
                "error": False,
                "gross_sales": 900,
                "gross_profit": 250,
            }]
        ),
    }


def test_v521_finance_context_rejects_non_dict_period_payload():
    assert FinanceContextProvider().build([]) is None


def test_v522_finance_context_rejects_missing_required_finance_fact():
    provider = FinanceContextProvider()

    missing_sales = provider.build(
        _period_data(
            current=[{
                "error": False,
                "gross_profit": 300,
            }]
        )
    )
    missing_profit = provider.build(
        _period_data(
            previous=[{
                "error": False,
                "gross_sales": 900,
            }]
        )
    )

    assert missing_sales is None
    assert missing_profit is None


def test_v522_finance_context_rejects_malformed_or_non_finite_fact():
    provider = FinanceContextProvider()

    malformed = provider.build(
        _period_data(
            current=[{
                "error": False,
                "gross_sales": "not-a-number",
                "gross_profit": 300,
            }]
        )
    )
    non_finite = provider.build(
        _period_data(
            current=[{
                "error": False,
                "gross_sales": float("nan"),
                "gross_profit": 300,
            }]
        )
    )
    boolean_value = provider.build(
        _period_data(
            current=[{
                "error": False,
                "gross_sales": True,
                "gross_profit": 300,
            }]
        )
    )
    malformed_item = provider.build(
        _period_data(
            current=["not-a-dict"]
        )
    )

    assert malformed is None
    assert non_finite is None
    assert boolean_value is None
    assert malformed_item is None


def test_v523_finance_context_preserves_explicit_zero_and_scope():
    result = FinanceContextProvider().build(
        _period_data(
            current=[{
                "error": False,
                "gross_sales": 0,
                "gross_profit": 0,
            }]
        )
    )

    current = result["finance_context"]["finance_data"]

    assert current == {
        "revenue": 0.0,
        "expenses": 0.0,
        "profit": 0.0,
        "margin": 0,
        "profit_scope": "PERIOD_GROSS_PROFIT",
    }


def test_v524_finance_intelligence_uses_non_accounting_wording():
    result = FinanceIntelligenceService().analyze(
        {
            "revenue": 1000,
            "expenses": 700,
            "profit": 300,
            "margin": 30,
            "profit_scope": "PERIOD_GROSS_PROFIT",
        }
    )

    assert result["error"] is False
    assert result["profit_scope"] == "PERIOD_GROSS_PROFIT"
    messages = [
        item["message"]
        for item in result["insights"]
    ]
    assert "Расчётный валовый результат положительный" in messages
    assert all(
        "Бизнес работает с положительной прибылью" not in message
        for message in messages
    )


def test_v524_decline_wording_stays_within_gross_profit_scope():
    result = FinanceIntelligenceService().analyze(
        {
            "revenue": 1000,
            "expenses": 800,
            "profit": 200,
            "margin": 20,
            "profit_scope": "PERIOD_GROSS_PROFIT",
        },
        previous_data={
            "revenue": 1000,
            "expenses": 600,
            "profit": 400,
            "margin": 40,
            "profit_scope": "PERIOD_GROSS_PROFIT",
        },
    )

    decline = next(
        item
        for item in result["insights"]
        if item["type"] == "profit_decline"
    )

    assert decline["message"] == (
        "Расчётный валовый результат снизился "
        "относительно предыдущего периода"
    )


def test_v525_finance_executor_presents_scoped_result():
    class _Intelligence:
        def analyze(
            self,
            finance_data,
            previous_data=None,
        ):
            return {
                "error": False,
                "profit_scope": "PERIOD_GROSS_PROFIT",
                "metrics": {
                    "revenue": 1000.0,
                    "expenses": 700.0,
                    "profit": 300.0,
                    "margin": 30.0,
                },
                "insights": [],
            }

    result = AssistantFinanceExecutorService(
        finance_intelligence_service=_Intelligence()
    ).execute({
        "context": {
            "finance_data": {},
        }
    })

    details = result["result"]["details"]

    assert "Расчётный валовый результат: 300.0" in details
    assert "Расходы по доступным данным: 700.0" in details
    assert "Маржинальность по доступным данным: 30.0%" in details
    assert all(
        not item.startswith("Прибыль:")
        for item in details
    )


def test_v526_finance_context_error_items_do_not_become_zero_facts():
    result = FinanceContextProvider().build(
        _period_data(
            current=[{
                "error": True,
                "gross_sales": 0,
                "gross_profit": 0,
            }]
        )
    )

    assert result is None


def test_v524_direct_finance_input_uses_derived_scope_and_generic_wording():
    result = FinanceIntelligenceService().analyze({
        "revenue": 1000,
        "expenses": 600,
    })

    assert result["profit_scope"] == (
        "DERIVED_REVENUE_MINUS_EXPENSES"
    )
    messages = [
        item["message"]
        for item in result["insights"]
    ]
    assert (
        "Расчётный финансовый результат положительный"
        in messages
    )
    assert all(
        "валовый" not in message.lower()
        for message in messages
    )


def test_v524_caller_provided_profit_uses_caller_scope():
    result = FinanceIntelligenceService().analyze({
        "revenue": 1000,
        "expenses": 700,
        "profit": 300,
        "margin": 30,
    })

    assert result["profit_scope"] == "CALLER_PROVIDED"


def test_v526_finance_intelligence_rejects_malformed_current_context():
    service = FinanceIntelligenceService()

    non_dict = service.analyze(["bad"])
    boolean_value = service.analyze({
        "revenue": True,
        "expenses": 10,
    })
    non_finite = service.analyze({
        "revenue": 100,
        "expenses": float("inf"),
    })

    for result in (
        non_dict,
        boolean_value,
        non_finite,
    ):
        assert result["error"] is True
        assert result["metrics"]["profit"] is None
        assert result["insights"] == []


def test_v526_finance_intelligence_rejects_malformed_previous_context():
    result = FinanceIntelligenceService().analyze(
        {
            "revenue": 1000,
            "expenses": 600,
        },
        previous_data={
            "revenue": 900,
            "expenses": "bad",
        },
    )

    assert result["error"] is True
    assert result["metrics"] == {
        "revenue": None,
        "expenses": None,
        "profit": None,
        "margin": None,
    }
    assert result["insights"] == []
