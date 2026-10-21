from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from services.cross_docking_financial_evidence_service import (
    CrossDockingFinancialEvidenceService,
)
from services.experimental_store_economics_runtime_service import (
    ExperimentalStoreEconomicsRuntimeService,
)


SERVICE = CrossDockingFinancialEvidenceService()
START = date(2026, 8, 1)
END = date(2026, 8, 2)
TYPES = {
    41: {"name": "CrossDocking", "description": "Кросс-докинг"},
    42: {"name": "ReverseLogistics", "description": "Обратная логистика"},
}


def _fee(type_id, amount):
    return {"type_id": type_id, "accrued": {"amount": str(amount)}}


def _row(accrual_id, *, item_fees=None, non_item_fee=None, container_fees=None, posting=None):
    row = {"accrual_id": accrual_id, "accrued_category": "NON_ITEM"}
    if item_fees is not None:
        row["item_fees"] = item_fees
    if non_item_fee is not None:
        row["non_item_fee"] = non_item_fee
    if container_fees is not None:
        row["container_fees"] = container_fees
    if posting is not None:
        row["posting"] = posting
    return row


def _window(day_one=None, day_two=None):
    return {
        "2026-08-01": {"error": False, "accruals": list(day_one or [])},
        "2026-08-02": {"error": False, "accruals": list(day_two or [])},
    }


def _collect(daily=None, types=TYPES):
    return SERVICE.collect_window(
        daily_responses=daily if daily is not None else _window(),
        accrual_types=types,
        date_from=START,
        date_to=END,
    )


def _supplies(units_by_sku, *, total=None, status="COMPLETE"):
    total = sum(quantity for _, quantity in units_by_sku) if total is None else total
    return SimpleNamespace(
        status=status,
        complete=status in {"COMPLETE", "NO_CROSSDOCK_SUPPLIES"},
        total_units=total,
        units_by_sku=tuple(units_by_sku),
    )


def _rate(financial, supplies, sku="A"):
    return SERVICE.calculate_rate(financial=financial, supplies=supplies, sku=sku)


def test_signed_leaf_expenses_include_adjustments_shared_nodes_and_exact_sku_costs():
    rows_day_one = [
        _row(
            1,
            item_fees={"fees": [{"sku": "A", "fees": [_fee(41, "-1200.00")]}]},
        ),
        _row(2, non_item_fee=_fee(41, "100.00")),
    ]
    rows_day_two = [
        _row(
            3,
            container_fees={"fees": [_fee(41, "-400.00")]},
        ),
        _row(4, non_item_fee=_fee(42, "-5000.00")),
    ]

    result = _collect(_window(rows_day_one, rows_day_two))

    assert result.complete is True
    assert result.expense_total == Decimal("1500.00")
    assert result.expense_by_sku == (("A", Decimal("1200.00")),)
    assert result.shared_expense_total == Decimal("300.00")
    assert result.has_unattributed_expense is True
    assert result.matched_leaf_count == 3
    assert result.positive_accrual_count == 1
    rate = _rate(result, _supplies([("A", 100), ("B", 50)]))
    assert rate.amount_per_unit == Decimal("10.00")
    assert rate.method == "store_accrual_cost_per_delivered_crossdock_unit"
    assert rate.expense_total == Decimal("1500.00")
    assert rate.shared_expense_total == Decimal("300.00")


def test_fully_attributed_sku_cost_uses_weighted_sku_denominator():
    rows = [
        _row(1, item_fees={"fees": [{"sku": "A", "fees": [_fee(41, "-900.00")]}]}),
        _row(2, item_fees={"fees": [{"sku": "B", "fees": [_fee(41, "-300.00")]}]}),
    ]
    financial = _collect(_window(rows, []))

    rate = _rate(financial, _supplies([("A", 100), ("B", 50)]))

    assert financial.expense_total == Decimal("1200.00")
    assert rate.status == "SKU_SUPPLY_PERIOD_AVERAGE"
    assert rate.amount_per_unit == Decimal("9.00")
    assert rate.expense_by_sku == Decimal("900.00")
    assert rate.supplied_units_sku == 100
    assert rate.supplied_units_store == 150


def test_posting_delivery_leaf_uses_the_product_sku():
    rows = [
        _row(
            1,
            posting={
                "products": [
                    {
                        "sku": "A",
                        "delivery": {"services": [_fee(41, "-100.00")]},
                    }
                ]
            },
        )
    ]
    financial = _collect(_window(rows, []))

    assert financial.expense_by_sku == (("A", Decimal("100.00")),)
    assert financial.has_unattributed_expense is False


def test_existing_store_report_and_new_evidence_share_the_same_fee_matchers():
    for category, labels in ExperimentalStoreEconomicsRuntimeService.FEE_LABEL_MATCHERS.items():
        for label in labels:
            assert ExperimentalStoreEconomicsRuntimeService._matches_fee_category(
                [label], category, labels
            )


def test_missing_finance_day_never_publishes_partial_cost():
    financial = _collect({"2026-08-01": {"error": False, "accruals": []}})

    assert financial.complete is False
    assert financial.expense_total is None
    assert "FINANCE_DAYS_INCOMPLETE" in financial.issue_codes
    assert _rate(financial, _supplies([("A", 10)])).amount_per_unit is None


def test_failed_or_malformed_day_is_not_treated_as_zero():
    for response in (
        {"error": True, "code": "RATE_LIMITED"},
        {"error": False, "accruals": "not-a-list"},
    ):
        financial = _collect({"2026-08-01": response, "2026-08-02": {"error": False, "accruals": []}})
        assert financial.complete is False
        assert financial.expense_total is None


def test_unknown_type_or_missing_type_dictionary_fails_closed():
    row = _row(1, non_item_fee=_fee(99, "-12.00"))
    unknown = _collect(_window([row], []))
    missing_dictionary = _collect(_window([_row(1)], []), types={})

    assert "ACCRUAL_TYPE_UNKNOWN" in unknown.issue_codes
    assert unknown.expense_total is None
    assert "ACCRUAL_TYPE_DICTIONARY_UNAVAILABLE" in missing_dictionary.issue_codes
    assert missing_dictionary.expense_total is None


def test_invalid_leaf_amount_and_missing_accrual_identity_fail_closed():
    bad_amount = _row(1, non_item_fee=_fee(41, "NaN"))
    missing_id = _row(None, non_item_fee=_fee(41, "-10.00"))

    assert "FEE_AMOUNT_INVALID" in _collect(_window([bad_amount], [])).issue_codes
    assert "ACCRUAL_ID_MISSING_OR_INVALID" in _collect(_window([missing_id], [])).issue_codes


def test_overflow_amount_fails_closed():
    oversized = _row(1, non_item_fee=_fee(41, "1e30"))

    result = _collect(_window([oversized], []))

    assert "FEE_AMOUNT_INVALID" in result.issue_codes
    assert result.expense_total is None


def test_repeated_exact_pagination_row_is_deduplicated_but_conflicting_id_is_not():
    row = _row(1, non_item_fee=_fee(41, "-50.00"))
    repeated = _collect(_window([row, row], []))
    conflict = _collect(
        _window([row, _row(1, non_item_fee=_fee(41, "-60.00"))], [])
    )

    assert repeated.expense_total == Decimal("50.00")
    assert repeated.matched_leaf_count == 1
    assert conflict.expense_total is None
    assert "CONFLICTING_DUPLICATE_ACCRUAL" in conflict.issue_codes


def test_old_supply_adjustment_is_included_by_finance_date_without_changing_q():
    # The correction carries no supply quantity: Q comes only from accepted act facts.
    correction = _row(7, non_item_fee=_fee(41, "100.00"))
    financial = _collect(_window([], [correction]))
    supplies = _supplies([("A", 10)])

    assert financial.expense_total == Decimal("-100.00")
    assert financial.positive_accrual_count == 1
    rate = _rate(financial, supplies)
    assert rate.reason == "NET_REFUND_PERIOD"
    assert rate.amount_per_unit is None
    assert rate.supplied_units_sku == 10


def test_financial_total_and_supply_quantity_do_not_depend_on_sale_count():
    financial = _collect(_window([_row(1, non_item_fee=_fee(41, "-12000.00"))], []))
    first = _rate(financial, _supplies([("A", 100)]))
    # The service accepts no sales count; the same expense/supply evidence gives the same rate.
    second = _rate(financial, _supplies([("A", 100)]))

    assert first.amount_per_unit == second.amount_per_unit == Decimal("120.00")


def test_direct_fbo_units_do_not_enter_the_supply_denominator():
    financial = _collect(_window([_row(1, non_item_fee=_fee(41, "-1200.00"))], []))
    # Supply normalization supplies only cross-docked SKU quantities.
    rate = _rate(financial, _supplies([("A", 100)]))

    assert rate.supplied_units_store == 100
    assert rate.amount_per_unit == Decimal("12.00")


def test_no_crossdock_supply_or_target_sku_participation_has_no_generic_rate():
    financial = _collect(_window([_row(1, non_item_fee=_fee(41, "-500.00"))], []))
    no_supplies = _rate(financial, _supplies([]))
    other_sku_only = _rate(financial, _supplies([("B", 20)]), sku="A")

    assert no_supplies.status == "NO_CROSSDOCK_SUPPLIES"
    assert no_supplies.amount_per_unit is None
    assert other_sku_only.reason == "SKU_NOT_IN_CROSSDOCK_WINDOW"
    assert other_sku_only.amount_per_unit is None


def test_incomplete_supply_facts_do_not_publish_rate():
    financial = _collect(_window([], []))
    supplies = _supplies([("A", 10)], status="INCOMPLETE")

    rate = _rate(financial, supplies)

    assert rate.amount_per_unit is None
    assert rate.reason == "SUPPLY_EVIDENCE_INCOMPLETE"


def test_zero_expense_is_observed_zero_only_with_positive_supply_units():
    financial = _collect(_window([], []))
    rate = _rate(financial, _supplies([("A", 25)]))

    assert financial.expense_total == Decimal("0")
    assert rate.status == "OBSERVED_ZERO"
    assert rate.amount_per_unit == Decimal("0.00")
    assert "не" not in (rate.reason or "")


def test_zero_or_net_refund_financial_period_is_not_a_numeric_rate():
    zero_denominator = _rate(
        _collect(_window([])),
        _supplies([("A", 0)], total=0),
    )
    net_refund_financial = _collect(
        _window([_row(1, non_item_fee=_fee(41, "25.00"))], [])
    )
    net_refund = _rate(net_refund_financial, _supplies([("A", 5)]))

    assert zero_denominator.amount_per_unit is None
    assert zero_denominator.reason == "CROSSDOCK_DENOMINATOR_ZERO"
    assert net_refund.amount_per_unit is None
    assert net_refund.reason == "NET_REFUND_PERIOD"


def test_decimal_rounding_and_residual_are_preserved():
    financial = _collect(
        _window([_row(1, non_item_fee=_fee(41, "-1000.00"))], [])
    )
    rate = _rate(financial, _supplies([("A", 3)]))

    assert rate.raw_rate == Decimal("1000") / Decimal("3")
    assert rate.amount_per_unit == Decimal("333.33")
    assert rate.rounding_residual == Decimal("0.01")


def test_date_window_and_out_of_window_finance_days_are_validated():
    outside = _collect(
        {
            "2026-07-31": {"error": False, "accruals": []},
            "2026-08-01": {"error": False, "accruals": []},
            "2026-08-02": {"error": False, "accruals": []},
        }
    )
    invalid = SERVICE.collect_window(
        daily_responses={}, accrual_types=TYPES, date_from=END, date_to=START
    )

    assert "FINANCE_DAY_OUTSIDE_WINDOW" in outside.issue_codes
    assert outside.expense_total is None
    assert "INVALID_DATE_WINDOW" in invalid.issue_codes

