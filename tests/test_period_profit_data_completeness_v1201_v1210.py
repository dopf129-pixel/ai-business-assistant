from period_profit_response import build_period_profit_response
from services.period_profit_return_evidence_service import (
    PeriodProfitReturnEvidenceService,
)
from services.period_profit_summary_service import (
    PeriodProfitSummaryService,
)


class Finance:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def get_daily_finance(self, day, sku=None):
        self.calls.append((day, sku))
        return dict(self.rows[(day, sku)])


class Costs:
    def __init__(self, values):
        self.values = values

    def get_cost(self, product_id):
        return self.values.get(str(product_id))


def test_v1201_sqlite_product_tuple_is_normalized_for_period_profit():
    finance = Finance({
        ("2026-09-03", "100"): {
            "error": False,
            "sales_count": 2,
            "gross_sales": 200.0,
            "net_accrual": 150.0,
            "commission": -20.0,
            "logistics": -15.0,
            "acquiring": -3.0,
            "other_fees": -12.0,
            "fee_breakdown": {},
        }
    })
    costs = Costs({
        "10": ("10", "hook-2", "100", 21.0, "RUB", None),
    })

    result = PeriodProfitSummaryService(
        finance,
        costs,
        tax_rate=0.06,
    ).calculate(
        "2026-09-03",
        "2026-09-03",
        [("10", "hook-2", "100")],
    )

    assert result["error"] is False
    assert result["product_count"] == 1
    assert result["units_sold"] == 2
    assert result["revenue"] == 200.0
    assert result["product_cost"] == 42.0
    assert result["tax"] == 12.0
    assert result["profit"] == 96.0
    assert finance.calls == [("2026-09-03", "100")]


def test_v1202_empty_product_list_fails_instead_of_returning_zero_profit():
    result = PeriodProfitSummaryService(
        Finance({}),
        Costs({}),
    ).calculate(
        "2026-09-03",
        "2026-09-03",
        [],
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_PRODUCTS_UNAVAILABLE"


def test_v1203_malformed_products_fail_instead_of_zero_success():
    result = PeriodProfitSummaryService(
        Finance({}),
        Costs({}),
    ).calculate(
        "2026-09-03",
        "2026-09-03",
        [None, (), ("only", "two"), {"bad": "row"}],
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_PRODUCTS_UNAVAILABLE"


def test_v1204_existing_dict_product_contract_remains_supported():
    finance = Finance({
        ("2026-09-03", "100"): {
            "error": False,
            "sales_count": 1,
            "gross_sales": 100.0,
            "net_accrual": 80.0,
            "fee_breakdown": {},
        }
    })

    result = PeriodProfitSummaryService(
        finance,
        Costs({}),
    ).calculate(
        "2026-09-03",
        "2026-09-03",
        [{
            "product_id": "10",
            "offer_id": "hook-2",
            "sku": "100",
            "cost": 20.0,
        }],
    )

    assert result["error"] is False
    assert result["product_count"] == 1
    assert result["profit"] == 54.0


class ReturnsClient:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get_returns(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.pages.pop(0)


def _return_row(value):
    return {
        "id": value,
        "offer_id": "hook-2",
        "status": "returned",
    }


def test_v1205_return_evidence_paginates_beyond_first_500_records():
    first = [_return_row(i) for i in range(1, 501)]
    second = [_return_row(501), _return_row(502)]
    client = ReturnsClient([
        {
            "returns": first,
            "has_next": True,
        },
        {
            "returns": second,
            "has_next": False,
        },
    ])

    result = PeriodProfitReturnEvidenceService(
        client
    ).load(
        "2026-06-06",
        "2026-09-03",
    )

    assert result["error"] is False
    assert result["complete"] is True
    assert result["return_record_count_exact"] is True
    assert result["return_record_count"] == 502
    assert result["page_count"] == 2


def test_v1206_return_pagination_advances_last_id_cursor():
    first = [_return_row(i) for i in range(1, 501)]
    client = ReturnsClient([
        {
            "returns": first,
            "has_next": True,
        },
        {
            "returns": [],
            "has_next": False,
        },
    ])

    PeriodProfitReturnEvidenceService(
        client
    ).load(
        "2026-06-06",
        "2026-09-03",
    )

    assert client.calls[0]["last_id"] == 0
    assert client.calls[1]["last_id"] == 500
    assert client.calls[0]["limit"] == 500


def test_v1207_page_limit_marks_return_count_as_lower_bound():
    first = [_return_row(i) for i in range(1, 501)]
    client = ReturnsClient([
        {
            "returns": first,
            "has_next": True,
        }
    ])
    service = PeriodProfitReturnEvidenceService(
        client
    )
    service.MAX_PAGES = 1

    result = service.load(
        "2026-06-06",
        "2026-09-03",
    )

    assert result["error"] is False
    assert result["complete"] is False
    assert result["return_record_count_exact"] is False
    assert result["return_record_count"] == 500
    assert result["partial_reason"] == "RETURNS_PAGE_LIMIT_REACHED"


def test_v1208_later_return_page_failure_keeps_partial_evidence_honest():
    first = [_return_row(i) for i in range(1, 501)]
    client = ReturnsClient([
        {
            "returns": first,
            "has_next": True,
        },
        {
            "error": True,
            "message": "temporary failure",
        },
    ])

    result = PeriodProfitReturnEvidenceService(
        client
    ).load(
        "2026-06-06",
        "2026-09-03",
    )

    assert result["error"] is False
    assert result["complete"] is False
    assert result["return_record_count_exact"] is False
    assert result["return_record_count"] == 500
    assert result["partial_reason"] == "RETURNS_PAGE_UNAVAILABLE"


def _summary_for_response():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "date_from": "2026-06-06",
        "date_to": "2026-09-03",
        "revenue": 1000.0,
        "net_accrual": 800.0,
        "commission": -100.0,
        "logistics": -50.0,
        "acquiring": -10.0,
        "other_fees": -40.0,
        "fee_components_included": True,
        "product_cost": 300.0,
        "tax": 60.0,
        "profit": 440.0,
        "margin_percent": 44.0,
        "returns_included": False,
        "advertising_included": False,
        "storage_included": False,
        "profit_scope": "V1",
    }


def test_v1209_partial_return_count_is_not_presented_as_exact():
    evidence = {
        "error": False,
        "status": "PERIOD_PROFIT_RETURN_EVIDENCE_PARTIAL",
        "return_record_count": 500,
        "return_record_count_exact": False,
        "returns_observed": True,
    }

    text = build_period_profit_response(
        _summary_for_response(),
        return_evidence=evidence,
    )["text"]

    assert "как минимум 500" in text
    assert "не точное итоговое количество" in text
    assert "за период: 500." not in text


def test_v1210_exact_return_count_keeps_existing_presentation():
    evidence = {
        "error": False,
        "status": "PERIOD_PROFIT_RETURN_EVIDENCE_READY",
        "return_record_count": 502,
        "return_record_count_exact": True,
        "returns_observed": True,
    }

    text = build_period_profit_response(
        _summary_for_response(),
        return_evidence=evidence,
    )["text"]

    assert "за период: 502." in text
    assert "как минимум" not in text
