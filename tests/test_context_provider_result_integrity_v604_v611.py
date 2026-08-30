from services.assistant_entry_service import (
    AssistantEntryService,
)


class _MainFlow:

    def __init__(self):
        self.report = None

    def process(
        self,
        text,
        report,
        context=None,
        user_id=None,
    ):
        self.report = dict(report)
        return {
            "error": False,
            "report": dict(report),
        }


class _Provider:

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def build(self, *args):
        self.calls += 1
        return self.result


def _entry(
    *,
    stock=None,
    sales=None,
    finance=None,
):
    main = _MainFlow()
    kwargs = {
        "main_flow_service": main,
    }

    if stock is not None:
        kwargs[
            "stock_context_provider"
        ] = _Provider(stock)

    if sales is not None:
        kwargs[
            "sales_context_provider"
        ] = _Provider(sales)

    if finance is not None:
        kwargs[
            "finance_context_provider"
        ] = _Provider(finance)

    return (
        AssistantEntryService(**kwargs),
        main,
    )


def test_v604_malformed_stock_provider_results_become_unknown_evidence():

    cases = [
        [],
        {},
        {
            "low_stock": None,
        },
        {
            "low_stock": True,
        },
        {
            "low_stock": False,
        },
    ]

    for downstream in cases:
        entry, main = _entry(
            stock=downstream
        )

        entry.handle(
            "остатки"
        )

        assert (
            main.report["low_stock"]
            is False
        )
        assert (
            main.report[
                "stock_evidence_available"
            ]
            is False
        )
        assert (
            "stock_context"
            not in main.report
        )


def test_v605_valid_low_stock_provider_result_is_preserved():

    stock_context = {
        "stock_data": {
            "product_id": "1",
            "current_stock": 2,
        },
        "sales_data": {
            "product_id": "1",
            "sales_count": 5,
        },
        "period_days": 7,
    }

    entry, main = _entry(
        stock={
            "low_stock": True,
            "stock_context":
                stock_context,
        }
    )

    entry.handle(
        "остатки"
    )

    assert (
        main.report["low_stock"]
        is True
    )
    assert (
        main.report["stock_context"]
        ==
        stock_context
    )


def test_v606_malformed_sales_report_becomes_unknown_evidence():

    cases = [
        {
            "report": "bad",
            "period_data": None,
        },
        {
            "report": {
                "sales_down": None,
            },
            "period_data": None,
        },
        {
            "report": {
                "sales_down": False,
            },
            "period_data": None,
        },
        {
            "report": {
                "sales_down": True,
            },
            "period_data": None,
        },
    ]

    for downstream in cases:
        entry, main = _entry(
            sales=downstream
        )

        entry.handle(
            "продажи"
        )

        assert (
            main.report["sales_down"]
            is False
        )
        assert (
            main.report[
                "sales_evidence_available"
            ]
            is False
        )
        assert (
            "sales_context"
            not in main.report
        )


def test_v607_valid_sales_down_result_is_preserved():

    sales_context = {
        "profits": [
            {
                "gross_sales": 10,
            }
        ],
        "previous_result": {
            "error": False,
        },
    }

    entry, main = _entry(
        sales={
            "report": {
                "sales_down": True,
                "sales_context":
                    sales_context,
            },
            "period_data": None,
        }
    )

    entry.handle(
        "продажи"
    )

    assert (
        main.report["sales_down"]
        is True
    )
    assert (
        main.report[
            "sales_context"
        ]
        ==
        sales_context
    )


def test_v608_malformed_finance_provider_result_does_not_crash_or_fake_evidence():

    period_data = {
        "current_profits": [
            {
                "gross_sales": 10,
                "gross_profit": 3,
            }
        ],
        "previous_profits": [
            {
                "gross_sales": 9,
                "gross_profit": 2,
            }
        ],
    }

    entry, main = _entry(
        sales={
            "report": {
                "sales_down": False,
                "sales_evidence_available":
                    True,
            },
            "period_data":
                period_data,
        },
        finance="bad",
    )

    entry.handle(
        "финансы"
    )

    assert (
        main.report[
            "finance_evidence_available"
        ]
        is False
    )
    assert (
        "finance_context"
        not in main.report
    )


def test_v609_partial_finance_context_is_rejected():

    entry, main = _entry(
        sales={
            "report": {
                "sales_down": False,
                "sales_evidence_available":
                    True,
            },
            "period_data": {
                "current_profits": [],
                "previous_profits": [],
            },
        },
        finance={
            "finance_context": {
                "finance_data": {},
            }
        },
    )

    entry.handle(
        "финансы"
    )

    assert (
        main.report[
            "finance_evidence_available"
        ]
        is False
    )
    assert (
        "finance_context"
        not in main.report
    )


def test_v610_valid_finance_provider_result_is_preserved():

    finance_context = {
        "finance_data": {
            "revenue": 10,
            "profit": 3,
        },
        "previous_data": {
            "revenue": 9,
            "profit": 2,
        },
    }

    entry, main = _entry(
        sales={
            "report": {
                "sales_down": False,
                "sales_evidence_available":
                    True,
            },
            "period_data": {
                "current_profits": [],
                "previous_profits": [],
            },
        },
        finance={
            "finance_context":
                finance_context,
        },
    )

    entry.handle(
        "финансы"
    )

    assert (
        main.report[
            "finance_context"
        ]
        ==
        finance_context
    )
    assert (
        main.report[
            "finance_evidence_available"
        ]
        is True
    )


def test_v611_unknown_provider_evidence_never_restores_default_problem_flags():

    entry, main = _entry(
        stock={
            "low_stock": False,
            "stock_evidence_available":
                False,
        },
        sales={
            "report": {
                "sales_down": False,
                "sales_evidence_available":
                    False,
            },
            "period_data": None,
        },
    )

    entry.handle(
        "состояние"
    )

    assert (
        main.report["low_stock"]
        is False
    )
    assert (
        main.report[
            "stock_evidence_available"
        ]
        is False
    )
    assert (
        main.report["sales_down"]
        is False
    )
    assert (
        main.report[
            "sales_evidence_available"
        ]
        is False
    )
