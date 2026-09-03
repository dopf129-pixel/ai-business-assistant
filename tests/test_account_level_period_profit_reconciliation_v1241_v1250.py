from period_profit_coverage import (
    build_period_profit_coverage,
)
from period_profit_response import (
    build_period_profit_response,
)
from services.period_profit_query_service import (
    PeriodProfitQueryService,
)
from services.period_profit_summary_service import (
    PeriodProfitSummaryService,
)


class Finance:
    def __init__(
        self,
        product_rows,
        account_rows,
    ):
        self.product_rows = product_rows
        self.account_rows = account_rows
        self.session_count = 0
        self.account_calls = []
        self.product_calls = []

    def begin_read_session(self):
        self.session_count += 1

    def get_daily_finance(
        self,
        day,
        sku=None,
    ):
        self.product_calls.append(
            (day, sku)
        )
        return dict(
            self.product_rows[
                (day, sku)
            ]
        )

    def get_daily_account_finance(
        self,
        day,
    ):
        self.account_calls.append(day)
        return dict(
            self.account_rows[day]
        )


class LegacyFinance:
    def __init__(self, rows):
        self.rows = rows

    def get_daily_finance(
        self,
        day,
        sku=None,
    ):
        return dict(
            self.rows[(day, sku)]
        )


class Costs:
    def __init__(self, values):
        self.values = values

    def get_cost(self, product_id):
        return (
            str(product_id),
            "offer",
            "sku",
            self.values[str(product_id)],
            "RUB",
            None,
        )


def _product_row(
    revenue,
    net,
    commission=0.0,
    logistics=0.0,
    acquiring=0.0,
    other=0.0,
):
    return {
        "error": False,
        "sales_count": 1,
        "gross_sales": revenue,
        "net_accrual": net,
        "commission": commission,
        "logistics": logistics,
        "acquiring": acquiring,
        "other_fees": other,
        "fee_breakdown": {},
    }


def _account_row(
    revenue,
    net,
    commission=0.0,
    logistics=0.0,
    acquiring=0.0,
    other=0.0,
    breakdown=None,
):
    return {
        "error": False,
        "sales_count": 2,
        "gross_sales": revenue,
        "net_accrual": net,
        "commission": commission,
        "logistics": logistics,
        "acquiring": acquiring,
        "other_fees": other,
        "fee_breakdown": dict(
            breakdown or {}
        ),
    }


def _service(
    product_rows,
    account_rows,
    costs=None,
):
    return PeriodProfitSummaryService(
        Finance(
            product_rows,
            account_rows,
        ),
        Costs(
            costs
            or {
                "10": 10.0,
                "20": 20.0,
            }
        ),
        tax_rate=0.06,
    )


def _products():
    return [
        {
            "product_id": "10",
            "offer_id": "a",
            "sku": "100",
        },
        {
            "product_id": "20",
            "offer_id": "b",
            "sku": "200",
        },
    ]


def test_v1241_account_level_net_accrual_is_period_monetary_authority():
    service = _service(
        {
            ("2026-09-03", "100"): (
                _product_row(
                    100.0,
                    80.0,
                )
            ),
            ("2026-09-03", "200"): (
                _product_row(
                    200.0,
                    150.0,
                )
            ),
        },
        {
            "2026-09-03": (
                _account_row(
                    300.0,
                    210.0,
                    commission=-30.0,
                    logistics=-40.0,
                    acquiring=-5.0,
                    other=-15.0,
                    breakdown={
                        "Account service": -20.0,
                    },
                )
            ),
        },
    )

    result = service.calculate(
        "2026-09-03",
        "2026-09-03",
        _products(),
    )

    assert result["error"] is False
    assert result["revenue"] == 300.0
    assert result["net_accrual"] == 210.0
    assert result["product_cost"] == 30.0
    assert result["tax"] == 18.0
    assert result["profit"] == 162.0
    assert (
        result[
            "account_level_ozon_accruals_included"
        ]
        is True
    )
    assert (
        result["profit_scope"]
        == "OZON_ACCOUNT_ACCRUALS_COST_AND_CONFIGURED_TAX_V2"
    )


def test_v1242_account_level_adjustment_captures_non_sku_money_once():
    service = _service(
        {
            ("2026-09-03", "100"): (
                _product_row(
                    100.0,
                    80.0,
                )
            ),
            ("2026-09-03", "200"): (
                _product_row(
                    200.0,
                    150.0,
                )
            ),
        },
        {
            "2026-09-03": (
                _account_row(
                    300.0,
                    210.0,
                )
            ),
        },
    )

    result = service.calculate(
        "2026-09-03",
        "2026-09-03",
        _products(),
    )

    assert (
        result["sku_attributed_net_accrual"]
        == 230.0
    )
    assert (
        result["ozon_account_reconciliation"]
        == -20.0
    )
    assert result["profit"] == 162.0


def test_v1243_product_revenue_must_reconcile_to_account_revenue():
    service = _service(
        {
            ("2026-09-03", "100"): (
                _product_row(
                    100.0,
                    80.0,
                )
            ),
            ("2026-09-03", "200"): (
                _product_row(
                    200.0,
                    150.0,
                )
            ),
        },
        {
            "2026-09-03": (
                _account_row(
                    350.0,
                    210.0,
                )
            ),
        },
    )

    result = service.calculate(
        "2026-09-03",
        "2026-09-03",
        _products(),
    )

    assert result["error"] is True
    assert result["code"] == (
        "PERIOD_PROFIT_PRODUCT_REVENUE_COVERAGE_INCOMPLETE"
    )


def test_v1244_account_level_total_corrects_multi_sku_net_duplication():
    service = _service(
        {
            ("2026-09-03", "100"): (
                _product_row(
                    100.0,
                    160.0,
                )
            ),
            ("2026-09-03", "200"): (
                _product_row(
                    200.0,
                    160.0,
                )
            ),
        },
        {
            "2026-09-03": (
                _account_row(
                    300.0,
                    160.0,
                )
            ),
        },
    )

    result = service.calculate(
        "2026-09-03",
        "2026-09-03",
        _products(),
    )

    assert result["error"] is False
    assert (
        result["sku_attributed_net_accrual"]
        == 320.0
    )
    assert (
        result["ozon_account_reconciliation"]
        == -160.0
    )
    assert result["net_accrual"] == 160.0
    assert result["profit"] == 112.0


def test_v1245_account_level_fee_breakdown_replaces_sku_breakdown_sum():
    service = _service(
        {
            ("2026-09-03", "100"): {
                **_product_row(
                    100.0,
                    80.0,
                ),
                "fee_breakdown": {
                    "SKU fee": -1.0,
                },
            },
            ("2026-09-03", "200"): {
                **_product_row(
                    200.0,
                    150.0,
                ),
                "fee_breakdown": {
                    "SKU fee": -2.0,
                },
            },
        },
        {
            "2026-09-03": (
                _account_row(
                    300.0,
                    210.0,
                    breakdown={
                        "Storage": -20.0,
                    },
                )
            ),
        },
    )

    result = service.calculate(
        "2026-09-03",
        "2026-09-03",
        _products(),
    )

    assert result["fee_breakdown"] == {
        "Storage": -20.0,
    }


def test_v1246_account_level_finance_failure_blocks_profit():
    service = _service(
        {
            ("2026-09-03", "100"): (
                _product_row(
                    100.0,
                    80.0,
                )
            ),
            ("2026-09-03", "200"): (
                _product_row(
                    200.0,
                    150.0,
                )
            ),
        },
        {
            "2026-09-03": {
                "error": True,
            },
        },
    )

    result = service.calculate(
        "2026-09-03",
        "2026-09-03",
        _products(),
    )

    assert result["error"] is True
    assert result["code"] == (
        "PERIOD_PROFIT_FINANCE_UNAVAILABLE"
    )


def test_v1247_response_explains_account_reconciliation_and_no_double_subtract():
    source = {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "date_from": "2026-09-03",
        "date_to": "2026-09-03",
        "revenue": 300.0,
        "net_accrual": 210.0,
        "commission": -30.0,
        "logistics": -40.0,
        "acquiring": -5.0,
        "other_fees": -15.0,
        "fee_components_included": True,
        "product_cost": 30.0,
        "tax": 18.0,
        "profit": 162.0,
        "margin_percent": 54.0,
        "returns_included": False,
        "advertising_included": False,
        "storage_included": False,
        "account_level_ozon_accruals_included": True,
        "ozon_account_reconciliation": -20.0,
        "profit_scope": (
            "OZON_ACCOUNT_ACCRUALS_COST_AND_CONFIGURED_TAX_V2"
        ),
    }

    text = build_period_profit_response(
        source
    )["text"]

    assert (
        "Корректировка по итоговому кабинету Ozon: "
        "-20.00 ₽ (-6.67%)"
        in text
    )
    assert (
        "Все денежные начисления и удержания Ozon "
        "уровня кабинета уже входят"
        in text
    )
    assert (
        "Эти операции не вычитаются повторно"
        in text
    )
    assert (
        "не включены полностью"
        not in text
    )


def test_v1248_coverage_exposes_account_level_reconciliation_state():
    summary = {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "fee_components_included": True,
        "returns_included": False,
        "advertising_included": False,
        "storage_included": False,
        "account_level_ozon_accruals_included": True,
        "product_revenue_reconciled": True,
        "ozon_account_reconciliation": -20.0,
    }

    result = build_period_profit_coverage(
        summary
    )

    assert result["error"] is False
    assert (
        result[
            "account_level_ozon_accruals_included"
        ]
        is True
    )
    assert (
        result["product_revenue_reconciled"]
        is True
    )
    assert (
        result["ozon_account_reconciliation"]
        == -20.0
    )
    assert (
        result[
            "accounting_net_profit_claim_allowed"
        ]
        is False
    )


def test_v1249_legacy_finance_without_account_boundary_keeps_v1_contract():
    service = PeriodProfitSummaryService(
        LegacyFinance({
            ("2026-09-03", "100"): (
                _product_row(
                    100.0,
                    80.0,
                )
            ),
        }),
        Costs({
            "10": 10.0,
        }),
        tax_rate=0.06,
    )

    result = service.calculate(
        "2026-09-03",
        "2026-09-03",
        [{
            "product_id": "10",
            "offer_id": "a",
            "sku": "100",
        }],
    )

    assert result["error"] is False
    assert result["profit"] == 64.0
    assert (
        result[
            "account_level_ozon_accruals_included"
        ]
        is False
    )
    assert (
        result["profit_scope"]
        == "OZON_ACCRUALS_COST_AND_CONFIGURED_TAX_V1"
    )


class QuerySummary:
    def calculate(
        self,
        date_from,
        date_to,
        products,
    ):
        return {
            "error": False,
            "status": "PERIOD_PROFIT_SUMMARY_READY",
            "date_from": date_from,
            "date_to": date_to,
            "revenue": 300.0,
            "net_accrual": 210.0,
            "commission": -30.0,
            "logistics": -40.0,
            "acquiring": -5.0,
            "other_fees": -15.0,
            "fee_components_included": True,
            "product_cost": 30.0,
            "tax": 18.0,
            "profit": 162.0,
            "margin_percent": 54.0,
            "products": [],
            "fee_breakdown": {
                "Storage": -20.0,
            },
            "returns_included": False,
            "advertising_included": False,
            "storage_included": False,
            "account_level_ozon_accruals_included": True,
            "product_revenue_reconciled": True,
            "ozon_account_reconciliation": -20.0,
            "profit_scope": (
                "OZON_ACCOUNT_ACCRUALS_COST_AND_CONFIGURED_TAX_V2"
            ),
        }


def _storage_mapping():
    return {
        "error": False,
        "status": (
            "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZED_MAPPING_READY"
        ),
        "scope": "STORAGE",
        "mapping_id": "storage:test",
        "operation_names": [
            "Storage",
        ],
        "mapping_authorized": True,
        "financial_evidence_mapping_allowed": True,
        "profit_adjustment_allowed": False,
        "automatic_activation_allowed": False,
        "immutable_artifact": True,
    }


def test_v1250_mapped_account_expense_is_evidence_not_second_profit_deduction():
    service = PeriodProfitQueryService(
        QuerySummary(),
        lambda: [{"sku": "100"}],
        authorized_storage_mapping=(
            _storage_mapping()
        ),
    )

    result = service.query(
        date_from="2026-09-03",
        date_to="2026-09-03",
    )

    assert result["error"] is False
    assert (
        result["summary"]["profit"]
        == 162.0
    )
    evidence = (
        result[
            "storage_financial_evidence"
        ]
    )
    assert (
        evidence[
            "matched_operation_count"
        ]
        == 1
    )
    assert (
        evidence["matched_amount"]
        == -20.0
    )
    assert (
        evidence[
            "profit_adjustment_allowed"
        ]
        is False
    )
    assert result["read_only"] is True
    assert result["executed"] is False
