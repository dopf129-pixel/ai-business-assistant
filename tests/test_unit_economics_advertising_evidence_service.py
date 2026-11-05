from copy import deepcopy

from services.unit_economics_advertising_evidence_service import (
    UnitEconomicsAdvertisingEvidenceService,
)
from services.unit_economics_expense_normalizer import UnitEconomicsExpenseNormalizer


IDENTITY = {
    "owner_id": "owner-a", "store_id": "store-a", "product_id": "product-a",
    "offer_id": "offer-a", "sku": "sku-a", "sale_schema": "FBO",
}
FINANCE_KEYS = [
    "FINANCE_ADVERTISING_CPC", "FINANCE_ADVERTISING_CPO", "FINANCE_ADVERTISING_OTHER",
]
WINDOW = {
    "from_date": "2026-10-01", "to_date": "2026-10-07",
    "date_basis": "OZON_ACCRUAL_DATE", "timezone": "Europe/Moscow",
}


def _part(component_id, key, amount, category, **changes):
    value = {
        "component_id": component_id,
        "component_key": key,
        "category": category,
        "signed_source_amount_rub": amount,
        "ownership": "ADDITIONAL",
        "attribution": "EXACT_SKU",
        "origin": "OFFICIAL_SOURCE",
        "recurrence": "RECURRING",
        "correction_state": "FINAL_AS_OF",
    }
    value.update(changes)
    return value


def _operation(operation_id, parts, identity=None):
    return {
        "operation_id": operation_id,
        "identity": deepcopy(identity or IDENTITY),
        "components": deepcopy(parts),
    }


def _snapshot(source, operations, expected_keys, *, date_basis=None, identity=None, coverage=None):
    evidence = {
        "schema_version": 1,
        "identity": deepcopy(identity or IDENTITY),
        "source": source,
        "source_method": "/v3/finance/transaction/list" if source == "SELLER_FINANCE"
        else "/v1/performance/historical/list",
        "source_contract_version": "v3" if source == "SELLER_FINANCE" else "v1",
        "source_window": {**WINDOW, "date_basis": date_basis or WINDOW["date_basis"]},
        "received_at": "2026-10-08T10:00:00Z",
        "as_of": "2026-10-08T10:00:00Z",
        "coverage": coverage or {
            "requested_pages": 1, "received_pages": 1, "has_more": False,
            "stop_reason": "END_OF_DATA", "source_complete": True,
        },
        "expected_component_keys": list(expected_keys),
        "operations": deepcopy(operations),
    }
    return UnitEconomicsExpenseNormalizer.normalize(evidence)


def _financial(*parts, expected_keys=FINANCE_KEYS, coverage=None):
    operations = [_operation(f"op-{index}", [part]) for index, part in enumerate(parts)]
    return _snapshot("SELLER_FINANCE", operations, expected_keys, coverage=coverage)


def _performance(amount="-1000.00", *, date_basis=None, identity=None, changes=None):
    part = _part(
        "performance-cpc", "PERFORMANCE_ADVERTISING_CPC", amount, "ADVERTISING_CPC",
        ownership="RECONCILIATION_ONLY",
    )
    if changes:
        part.update(changes)
    return _snapshot(
        "PERFORMANCE", [_operation("performance-op", [part], identity=identity)],
        ["PERFORMANCE_ADVERTISING_CPC"], date_basis=date_basis, identity=identity,
    )


def _quantity(units=100, *, identity=None, source_window=None, complete=True):
    return {
        "identity": deepcopy(identity or IDENTITY),
        "source_window": deepcopy(source_window or WINDOW),
        "complete": complete,
        "status": "COMPLETE" if complete else "PARTIAL",
        "denominator_units": units,
        "denominator_kind": "ORDERED_UNITS_WINDOW",
    }


def test_finance_cpc_and_cpo_are_primary_and_performance_cpc_is_reconciliation_only():
    finance = _financial(
        _part("cpc", FINANCE_KEYS[0], "-1000.00", "ADVERTISING_CPC"),
        _part("cpo", FINANCE_KEYS[1], "-200.00", "ADVERTISING_CPO"),
    )
    performance = _performance("-1000.00")

    result = UnitEconomicsAdvertisingEvidenceService.resolve(
        finance, performance, _quantity(100),
    )

    assert result["financial"]["sku_primary_expense_rub"] == "1200.00"
    assert result["absolute_unit_cost"]["unit_expense_rub"] == "12.00"
    assert result["performance_reconciliation"]["performance_reconciliation_rub"] == "1000.00"
    assert result["performance_reconciliation"]["difference_rub"] == "0.00"
    assert result["performance_reconciliation"]["performance_is_additional_expense"] is False


def test_unattributed_account_ads_stay_separate_even_when_net_amount_is_zero():
    finance = _financial(
        _part("cpc", FINANCE_KEYS[0], "-100.00", "ADVERTISING_CPC"),
        _part(
            "account-charge", "FINANCE_ADVERTISING_OTHER_ACCOUNT", "-300.00",
            "ADVERTISING_OTHER", ownership="UNATTRIBUTED", attribution="UNATTRIBUTED",
        ),
        _part(
            "account-correction", "FINANCE_ADVERTISING_OTHER_ACCOUNT", "300.00",
            "ADVERTISING_OTHER", ownership="UNATTRIBUTED", attribution="UNATTRIBUTED",
        ),
        expected_keys=[*FINANCE_KEYS, "FINANCE_ADVERTISING_OTHER_ACCOUNT"],
    )

    result = UnitEconomicsAdvertisingEvidenceService.resolve(finance)

    assert result["financial"]["account_level_expense_rub"] == "0.00"
    assert result["financial"]["account_component_count"] == 1
    assert result["financial"]["complete_for_sku"] is False
    assert result["financial"]["sku_primary_expense_rub"] is None
    assert "ACCOUNT_LEVEL_ADVERTISING_NOT_ALLOCATED_TO_SKU" in result["warnings"]


def test_missing_cpo_is_not_the_same_as_a_confirmed_zero_cpo():
    cpc = _part("cpc", FINANCE_KEYS[0], "-100.00", "ADVERTISING_CPC")
    missing = _financial(cpc, expected_keys=[FINANCE_KEYS[0], FINANCE_KEYS[2]])
    zero = _financial(cpc)

    missing_result = UnitEconomicsAdvertisingEvidenceService.resolve(missing)
    zero_result = UnitEconomicsAdvertisingEvidenceService.resolve(zero)

    assert missing_result["financial"]["component_status"]["CPO"]["status"] == "MISSING"
    assert missing_result["financial"]["sku_primary_expense_rub"] is None
    assert zero_result["financial"]["component_status"]["CPO"]["status"] == "COMPLETE"
    assert zero_result["financial"]["sku_primary_expense_rub"] == "100.00"


def test_performance_alone_never_becomes_financial_primary_expense():
    finance = _financial(
        expected_keys=[FINANCE_KEYS[0], FINANCE_KEYS[2]],
        coverage={
            "requested_pages": 1, "received_pages": 1, "has_more": False,
            "stop_reason": "END_OF_DATA", "source_complete": True,
        },
    )

    result = UnitEconomicsAdvertisingEvidenceService.resolve(
        finance, _performance("-500.00"), _quantity(10),
    )

    assert result["financial"]["sku_primary_expense_rub"] is None
    assert result["performance_reconciliation"]["status"] == "COMPARABLE_WINDOW"
    assert result["performance_reconciliation"]["financial_primary_rub"] == "0.00"
    assert result["performance_reconciliation"]["difference_rub"] == "500.00"
    assert result["absolute_unit_cost"]["status"] == "UNAVAILABLE"


def test_performance_cpc_reconciliation_requires_same_identity_window_and_date_basis():
    finance = _financial(_part("cpc", FINANCE_KEYS[0], "-100.00", "ADVERTISING_CPC"))
    other_identity = {**IDENTITY, "sku": "sku-other"}

    identity_mismatch = UnitEconomicsAdvertisingEvidenceService.resolve(
        finance, _performance("-100.00", identity=other_identity),
    )
    date_mismatch = UnitEconomicsAdvertisingEvidenceService.resolve(
        finance, _performance("-100.00", date_basis="CAMPAIGN_DATE"),
    )
    mismatched_snapshot = _performance("-100.00")
    mismatched_snapshot["source_window"]["to_date"] = "2026-10-06"
    different_window = UnitEconomicsAdvertisingEvidenceService.resolve(finance, mismatched_snapshot)

    assert identity_mismatch["performance_reconciliation"]["status"] == "IDENTITY_MISMATCH"
    assert identity_mismatch["performance_reconciliation"]["performance_reconciliation_rub"] is None
    assert date_mismatch["performance_reconciliation"]["status"] == "DATE_BASIS_MISMATCH"
    assert different_window["performance_reconciliation"]["difference_rub"] is None
    assert different_window["performance_reconciliation"]["status"] == "CALENDAR_WINDOW_MISMATCH"


def test_absolute_window_cost_can_exceed_item_price_and_discloses_denominator():
    finance = _financial(_part("cpc", FINANCE_KEYS[0], "-1200.00", "ADVERTISING_CPC"))

    result = UnitEconomicsAdvertisingEvidenceService.resolve(finance, quantity_evidence=_quantity(10))

    assert result["absolute_unit_cost"]["unit_expense_rub"] == "120.00"
    assert result["absolute_unit_cost"]["denominator_kind"] == "ORDERED_UNITS_WINDOW"
    assert result["absolute_unit_cost"]["model_scope"] == "WINDOW_COST_ALLOCATION"


def test_unit_cost_blocks_zero_incomplete_or_wrong_scope_quantity():
    finance = _financial(_part("cpc", FINANCE_KEYS[0], "-120.00", "ADVERTISING_CPC"))
    wrong_identity = {**IDENTITY, "store_id": "store-b"}
    wrong_window = {**WINDOW, "from_date": "2026-10-02"}

    zero = UnitEconomicsAdvertisingEvidenceService.resolve(finance, quantity_evidence=_quantity(0))
    partial = UnitEconomicsAdvertisingEvidenceService.resolve(
        finance, quantity_evidence=_quantity(10, complete=False),
    )
    mismatch = UnitEconomicsAdvertisingEvidenceService.resolve(
        finance, quantity_evidence=_quantity(10, identity=wrong_identity),
    )
    window_mismatch = UnitEconomicsAdvertisingEvidenceService.resolve(
        finance, quantity_evidence=_quantity(10, source_window=wrong_window),
    )

    assert zero["absolute_unit_cost"]["reason"] == "COMPATIBLE_DENOMINATOR_UNAVAILABLE"
    assert partial["absolute_unit_cost"]["reason"] == "QUANTITY_EVIDENCE_INCOMPLETE_OR_MISMATCHED"
    assert mismatch["absolute_unit_cost"]["reason"] == "QUANTITY_EVIDENCE_INCOMPLETE_OR_MISMATCHED"
    assert window_mismatch["absolute_unit_cost"]["reason"] == "QUANTITY_WINDOW_MISMATCH"


def test_one_off_and_unverified_mapping_do_not_produce_planned_unit_cost():
    one_off = _financial(_part(
        "cpc", FINANCE_KEYS[0], "-120.00", "ADVERTISING_CPC", recurrence="ONE_OFF",
    ))
    unverified = _financial(_part(
        "cpc", FINANCE_KEYS[0], "-120.00", "ADVERTISING_CPC", origin="UNVERIFIED_SOURCE",
    ))

    one_off_result = UnitEconomicsAdvertisingEvidenceService.resolve(
        one_off, quantity_evidence=_quantity(10),
    )
    unverified_result = UnitEconomicsAdvertisingEvidenceService.resolve(
        unverified, quantity_evidence=_quantity(10),
    )

    assert one_off_result["absolute_unit_cost"]["reason"] == "ONE_OFF_OR_UNKNOWN_RECURRENCE"
    assert unverified_result["financial"]["complete_for_sku"] is False
    assert unverified_result["absolute_unit_cost"]["reason"] == "FINANCIAL_ADVERTISING_SCOPE_INCOMPLETE"


def test_net_advertising_credit_is_preserved_but_requires_review_before_unit_rate():
    finance = _financial(
        _part("charge", FINANCE_KEYS[0], "-100.00", "ADVERTISING_CPC"),
        _part("credit", FINANCE_KEYS[0], "150.00", "ADVERTISING_CPC"),
    )

    result = UnitEconomicsAdvertisingEvidenceService.resolve(finance, quantity_evidence=_quantity(10))

    assert result["financial"]["sku_primary_expense_rub"] == "-50.00"
    assert result["absolute_unit_cost"]["status"] == "REVIEW_REQUIRED"
    assert result["absolute_unit_cost"]["expense_rub"] == "-50.00"
    assert result["absolute_unit_cost"]["unit_expense_rub"] is None


def test_mismatched_component_category_is_a_conflict_not_a_relabelled_ad_type():
    finance = _financial(
        _part("cpc", FINANCE_KEYS[0], "-100.00", "ADVERTISING_OTHER"),
    )

    result = UnitEconomicsAdvertisingEvidenceService.resolve(finance)

    assert result["financial"]["component_status"]["CPC"]["status"] == "CONFLICT"
    assert result["financial"]["sku_primary_expense_rub"] is None
    assert result["status"] == "INCOMPLETE"


def test_incomplete_snapshot_rows_are_rejected_instead_of_silently_dropped():
    finance = _financial(_part("cpc", FINANCE_KEYS[0], "-100.00", "ADVERTISING_CPC"))
    finance["components"].append("malformed-row")

    result = UnitEconomicsAdvertisingEvidenceService.resolve(finance)

    assert result == {"error": True, "code": "UNIT_ECONOMICS_AD_FINANCE_SNAPSHOT_INVALID"}


def test_malformed_calendar_window_cannot_be_used_for_advertising_reconciliation():
    finance = _financial(_part("cpc", FINANCE_KEYS[0], "-100.00", "ADVERTISING_CPC"))
    finance["source_window"]["from_date"] = "not-a-date"

    result = UnitEconomicsAdvertisingEvidenceService.resolve(finance)

    assert result == {"error": True, "code": "UNIT_ECONOMICS_AD_FINANCE_SNAPSHOT_INVALID"}


def test_resolver_is_inspection_only_and_reports_performance_amount_separately():
    finance = _financial(_part("cpc", FINANCE_KEYS[0], "-100.00", "ADVERTISING_CPC"))

    result = UnitEconomicsAdvertisingEvidenceService.resolve(finance, _performance("-90.00"))

    assert result["read_only"] is True
    assert result["executed"] is False
    assert result["performance_reconciliation"]["financial_primary_rub"] == "100.00"
    assert result["performance_reconciliation"]["performance_reconciliation_rub"] == "90.00"
    assert result["performance_reconciliation"]["difference_rub"] == "-10.00"


def test_unmapped_financial_advertising_category_blocks_sku_total():
    finance = _financial(
        _part("cpc", FINANCE_KEYS[0], "-100.00", "ADVERTISING_CPC"),
        _part("unknown", "FINANCE_ADVERTISING_CPM", "-25.00", "ADVERTISING_OTHER"),
    )

    result = UnitEconomicsAdvertisingEvidenceService.resolve(finance)

    assert result["financial"]["unmapped_advertising_count"] == 1
    assert result["financial"]["sku_primary_expense_rub"] is None


def test_partial_source_and_performance_component_in_finance_snapshot_fail_closed():
    partial_finance = _financial(
        _part("cpc", FINANCE_KEYS[0], "-100.00", "ADVERTISING_CPC"),
        coverage={
            "requested_pages": 2, "received_pages": 1, "has_more": True,
            "stop_reason": "TIME_BUDGET", "source_complete": False,
        },
    )
    partial_result = UnitEconomicsAdvertisingEvidenceService.resolve(partial_finance)
    contaminated_finance = _financial(
        _part("cpc", "PERFORMANCE_ADVERTISING_CPC", "-100.00", "ADVERTISING_CPC"),
    )
    contaminated_result = UnitEconomicsAdvertisingEvidenceService.resolve(contaminated_finance)

    assert partial_result["financial"]["source_complete"] is False
    assert partial_result["financial"]["sku_primary_expense_rub"] is None
    assert contaminated_result["financial"]["unmapped_advertising_count"] == 1
    assert contaminated_result["financial"]["sku_primary_expense_rub"] is None


def test_performance_cpc_without_reconciliation_ownership_is_not_used():
    invalid_performance = _performance(
        "-100.00", changes={"ownership": "ADDITIONAL"},
    )
    finance = _financial(_part("cpc", FINANCE_KEYS[0], "-100.00", "ADVERTISING_CPC"))

    result = UnitEconomicsAdvertisingEvidenceService.resolve(finance, invalid_performance)

    assert result["performance_reconciliation"]["status"] == "MISSING_CPC"
    assert result["performance_reconciliation"]["difference_rub"] is None


def test_performance_component_with_non_cpc_category_is_not_relabelled_as_cpc():
    invalid_performance = _performance(
        "-100.00", changes={"category": "ADVERTISING_OTHER"},
    )
    finance = _financial(_part("cpc", FINANCE_KEYS[0], "-100.00", "ADVERTISING_CPC"))

    result = UnitEconomicsAdvertisingEvidenceService.resolve(finance, invalid_performance)

    assert result["performance_reconciliation"]["status"] == "MISSING_CPC"
    assert result["performance_reconciliation"]["performance_reconciliation_rub"] is None
    assert result["performance_reconciliation"]["difference_rub"] is None


def test_quantity_date_basis_difference_is_disclosed_for_window_allocation():
    finance = _financial(_part("cpc", FINANCE_KEYS[0], "-100.00", "ADVERTISING_CPC"))
    quantity_window = {**WINDOW, "date_basis": "ORDER_DATE"}

    result = UnitEconomicsAdvertisingEvidenceService.resolve(
        finance, quantity_evidence=_quantity(10, source_window=quantity_window),
    )

    assert result["absolute_unit_cost"]["status"] == "AVAILABLE"
    assert result["absolute_unit_cost"]["date_basis_warning"] == (
        "SOURCE_DATE_BASES_DIFFER; THIS_IS_ONLY_A_WINDOW_ALLOCATION"
    )
