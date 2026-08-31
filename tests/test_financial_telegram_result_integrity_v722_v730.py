from services.assistant_button_handler_service import (
    AssistantButtonHandlerService,
)


class _Assistant:

    def ask(
        self,
        text,
        user_id=None,
    ):

        return {
            "error": False,
            "message": "ok",
        }


class _UnitQuery:

    def __init__(
        self,
        result,
    ):

        self.result = result
        self.format_calls = 0

    def query(
        self,
        sku,
    ):

        return self.result

    def format_response(
        self,
        result,
    ):

        self.format_calls += 1

        if result.get(
            "error"
        ):

            return (
                result.get(
                    "message"
                )
                or "Юнит-экономика недоступна"
            )

        return (
            "Unit Economics — "
            + str(
                result.get(
                    "sku"
                )
            )
        )


class _ReturnsQuery:

    def __init__(
        self,
        result,
    ):

        self.result = result

    def query(
        self,
        sku,
    ):

        return self.result


def _handler(
    unit_result=None,
    returns_result=None,
):

    return AssistantButtonHandlerService(
        assistant=_Assistant(),
        unit_economics_query=(
            _UnitQuery(
                unit_result
            )
            if unit_result is not None
            else None
        ),
        returns_finance_impact_query=(
            _ReturnsQuery(
                returns_result
            )
            if returns_result is not None
            else None
        ),
    )


def _unit_success(
    available=True,
):

    return {
        "error": False,
        "available": available,
        "source": "historical",
        "sku": "hook-2",
        "unit_price": (
            96.0
            if available
            else None
        ),
        "cost": (
            21.0
            if available
            else None
        ),
        "marketplace_fees": (
            34.0
            if available
            else None
        ),
        "tax": (
            5.76
            if available
            else None
        ),
        "net_profit_per_unit": (
            35.1
            if available
            else None
        ),
        "margin_percent": (
            36.56
            if available
            else None
        ),
        "missing_fields": (
            [
                "advertising",
                "storage",
                "returns",
            ]
            if available
            else [
                "unit_price",
                "cost",
                "marketplace_fees",
                "tax",
                "net_profit_per_unit",
                "margin_percent",
                "advertising",
                "storage",
                "returns",
            ]
        ),
    }


def _returns_success(
    complete=False,
):

    return {
        "error": False,
        "complete": complete,
        "missing_data": (
            []
            if complete
            else [
                "finance_postings_unmatched",
            ]
        ),
        "categories": {
            "customer_non_buyout": {
                "label": "Невыкуп",
                "event_posting_count": 1,
                "finance_matched_posting_count": 0,
                "finance_coverage_percent": 0.0,
                "observed_cost_total": None,
                "observed_cost_average": None,
            },
            "customer_return": {
                "label": "Возврат",
                "event_posting_count": 0,
                "finance_matched_posting_count": 0,
                "finance_coverage_percent": 100.0,
                "observed_cost_total": 0.0,
                "observed_cost_average": None,
            },
        },
        "product_id": "101",
        "sku": "hook-2",
        "finance_sku": "3921245627",
        "requested_sku": "hook-2",
        "period_days": 30,
        "period_complete_days": True,
    }


def test_v722_malformed_unit_result_fails_closed_before_formatter():

    for malformed in (
        None,
        [],
        {},
        {
            "error": False,
        },
        {
            "error": "false",
            "available": True,
        },
    ):

        query = _UnitQuery(
            malformed
        )
        handler = AssistantButtonHandlerService(
            assistant=_Assistant(),
            unit_economics_query=query,
        )

        result = handler.handle(
            "unit_economics:hook-2"
        )

        assert result == {
            "error": True,
            "message":
                "INVALID_UNIT_ECONOMICS_RESULT",
        }
        assert query.format_calls == 0


def test_v723_unit_success_requires_explicit_evidence_shape():

    invalid = _unit_success()
    invalid.pop(
        "source"
    )

    handler = _handler(
        unit_result=invalid
    )

    assert handler.handle(
        "unit_economics:hook-2"
    ) == {
        "error": True,
        "message":
            "INVALID_UNIT_ECONOMICS_RESULT",
    }


def test_v724_explicit_unit_failure_is_preserved_and_formatted():

    failure = {
        "error": True,
        "code": "SKU_NOT_FOUND",
        "sku": "missing",
        "message": "SKU не найден",
    }
    query = _UnitQuery(
        failure
    )
    handler = AssistantButtonHandlerService(
        assistant=_Assistant(),
        unit_economics_query=query,
    )

    result = handler.handle(
        "unit_economics:missing"
    )

    assert result["error"] is True
    assert result[
        "message"
    ] == "SKU не найден"
    assert result[
        "unit_economics"
    ] is failure
    assert query.format_calls == 1


def test_v725_legitimate_unavailable_unit_result_remains_success():

    payload = _unit_success(
        available=False
    )
    handler = _handler(
        unit_result=payload
    )

    result = handler.handle(
        "unit_economics:hook-2"
    )

    assert result["error"] is False
    assert result[
        "unit_economics"
    ] is payload


def test_v726_valid_unit_result_remains_compatible():

    payload = _unit_success()
    handler = _handler(
        unit_result=payload
    )

    result = handler.handle(
        "unit_economics:hook-2"
    )

    assert result["error"] is False
    assert result[
        "unit_economics"
    ] is payload
    assert "hook-2" in result[
        "message"
    ]


def test_v727_malformed_returns_result_fails_closed():

    for malformed in (
        None,
        [],
        {},
        {
            "error": False,
        },
        {
            "error": "false",
            "complete": False,
        },
    ):

        handler = _handler(
            returns_result=malformed
        )

        result = handler.handle(
            "returns_finance_impact:hook-2"
        )

        assert result == {
            "error": True,
            "message":
                "INVALID_RETURNS_FINANCE_IMPACT_RESULT",
        }


def test_v728_returns_success_requires_safe_category_shape():

    malformed = _returns_success()
    malformed[
        "categories"
    ][
        "customer_return"
    ] = "bad"

    handler = _handler(
        returns_result=malformed
    )

    assert handler.handle(
        "returns_finance_impact:hook-2"
    ) == {
        "error": True,
        "message":
            "INVALID_RETURNS_FINANCE_IMPACT_RESULT",
    }


def test_v729_explicit_returns_failure_is_preserved():

    failure = {
        "error": True,
        "code": "FINANCE_UNAVAILABLE",
        "message": "Финансы недоступны",
        "complete": False,
        "missing_data": [
            "finance",
        ],
    }
    handler = _handler(
        returns_result=failure
    )

    result = handler.handle(
        "returns_finance_impact:hook-2"
    )

    assert result["error"] is True
    assert result[
        "message"
    ] == "Финансы недоступны"
    assert result[
        "returns_finance_impact"
    ] is failure


def test_v730_valid_incomplete_returns_result_remains_success():

    payload = _returns_success(
        complete=False
    )
    handler = _handler(
        returns_result=payload
    )

    result = handler.handle(
        "returns_finance_impact:hook-2"
    )

    assert result["error"] is False
    assert result[
        "returns_finance_impact"
    ] is payload
    assert "Данные неполные" in result[
        "message"
    ]
