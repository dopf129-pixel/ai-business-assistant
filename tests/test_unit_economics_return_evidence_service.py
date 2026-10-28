from copy import deepcopy

import pytest

from services.unit_economics_expense_normalizer import UnitEconomicsExpenseNormalizer
from services.unit_economics_return_evidence_service import UnitEconomicsReturnEvidenceService


IDENTITY = {
    "owner_id": "owner-a", "store_id": "store-a", "product_id": "product-a",
    "offer_id": "offer-a", "sku": "sku-a", "sale_schema": "FBO",
}
COHORT_REF = "a" * 64
OTHER_COHORT_REF = "b" * 64
WINDOW = {
    "from_date": "2026-10-01", "to_date": "2026-10-07",
    "date_basis": "ORDER_DATE", "timezone": "Europe/Moscow",
}
FEE_KEYS = ["FINANCE_CUSTOMER_RETURN_FEES", "FINANCE_CUSTOMER_NONBUYOUT_FEES"]


def _part(component_id, key, amount, **changes):
    value = {
        "component_id": component_id,
        "component_key": key,
        "category": "RETURN_NONBUYOUT",
        "signed_source_amount_rub": amount,
        "ownership": "ADDITIONAL",
        "attribution": "EXACT_COHORT",
        "origin": "OFFICIAL_SOURCE",
        "recurrence": "ONE_OFF",
        "correction_state": "FINAL_AS_OF",
    }
    value.update(changes)
    return value


def _finance(
    *parts, expected_keys=FEE_KEYS, source_window=WINDOW, coverage=None,
    cohort_ref=COHORT_REF,
):
    operations = [
        {
            "operation_id": f"operation-{index}",
            "identity": deepcopy(IDENTITY),
            "components": [deepcopy(part)],
        }
        for index, part in enumerate(parts)
    ]
    evidence = {
        "schema_version": 1,
        "identity": deepcopy(IDENTITY),
        "source": "SELLER_FINANCE",
        "source_method": "/v3/finance/transaction/list",
        "source_contract_version": "v3",
        "source_window": deepcopy(source_window),
        "cohort_ref": cohort_ref,
        "received_at": "2026-10-08T10:00:00Z",
        "as_of": "2026-10-08T10:00:00Z",
        "coverage": coverage or {
            "requested_pages": 1, "received_pages": 1, "has_more": False,
            "stop_reason": "END_OF_DATA", "source_complete": True,
        },
        "expected_component_keys": list(expected_keys),
        "operations": operations,
    }
    return UnitEconomicsExpenseNormalizer.normalize(evidence)


def _quantity(delivered=110, returned=10, retained=100, **changes):
    value = {
        "schema_version": 1,
        "identity": deepcopy(IDENTITY),
        "source_window": deepcopy(WINDOW),
        "cohort_ref": COHORT_REF,
        "status": "COMPLETE",
        "attribution": "EXACT_COHORT",
        "source_coverage": {
            "postings_complete": True, "returns_complete": True,
            "unit_links_complete": True,
        },
        "delivered_units": delivered,
        "confirmed_returned_units_from_deliveries": returned,
        "retained_units": retained,
    }
    value.update(changes)
    return value


def _inventory(dispositions, *, source_window=WINDOW, coverage=None, status="COMPLETE", **changes):
    value = {
        "schema_version": 1,
        "identity": deepcopy(IDENTITY),
        "source_window": deepcopy(source_window),
        "cohort_ref": COHORT_REF,
        "status": status,
        "source_coverage": coverage or {
            "disposition_complete": True, "cogs_complete": True,
            "compensation_complete": True,
        },
        "dispositions": deepcopy(dispositions),
    }
    value.update(changes)
    return value


def _irrecoverable(quantity=10, cogs="60.00", compensation="10.00", treatment="NON_OVERLAPPING", **changes):
    value = {
        "disposition": "IRRECOVERABLE_CONFIRMED",
        "quantity": quantity,
        "irrecoverable_cogs_rub": cogs,
        "cogs_ownership": "ADDITIONAL",
        "compensation_rub": compensation,
        "compensation_treatment": treatment,
    }
    value.update(changes)
    return value


def _resolve(finance=None, quantity=None, inventory=None):
    finance = finance or _finance(
        _part("return-fee", FEE_KEYS[0], "-200.00"),
        _part("nonbuyout-fee", FEE_KEYS[1], "-100.00"),
    )
    quantity = quantity or _quantity()
    if inventory is False:
        inventory = None
    elif inventory is None:
        inventory = _inventory([_irrecoverable()])
    return UnitEconomicsReturnEvidenceService.resolve(finance, quantity, inventory)


def test_n02_exact_return_nonbuyout_cogs_and_nonoverlapping_compensation_reconcile_once():
    result = _resolve()

    loss = result["strict_retained_cohort_loss"]
    assert result["status"] == "COMPLETE"
    assert result["fees"]["additional_exact_cohort_rub"] == "300.00"
    assert loss["fee_loss_pool_rub"] == "300.00"
    assert loss["inventory_loss_cogs_rub"] == "60.00"
    assert loss["compensation_deduction_rub"] == "10.00"
    assert loss["loss_pool_rub"] == "350.00"
    assert loss["loss_per_retained_unit_rub"] == "3.50"
    assert loss["denominator_units"] == 100
    assert loss["denominator_kind"] == "RETAINED_UNITS_EXACT_COHORT"


def test_pending_inventory_disposition_is_not_zero_cogs():
    result = _resolve(inventory=_inventory([{
        "disposition": "PENDING", "quantity": 10,
        "irrecoverable_cogs_rub": None, "cogs_ownership": "UNKNOWN",
        "compensation_rub": None, "compensation_treatment": "UNKNOWN",
    }]))

    assert result["inventory"]["status"] == "PARTIAL"
    assert result["inventory"]["inventory_loss_cogs_rub"] is None
    assert result["inventory"]["observed_inventory_loss_cogs_rub"] == "0.00"
    assert result["strict_retained_cohort_loss"]["status"] == "UNAVAILABLE"
    assert result["strict_retained_cohort_loss"]["loss_per_retained_unit_rub"] is None
    assert "PENDING_OR_UNKNOWN_COGS_IS_NOT_ZERO" in result["warnings"]


def test_saleable_restored_inventory_does_not_create_a_cogs_loss():
    result = _resolve(inventory=_inventory([{
        "disposition": "SALEABLE_RESTORED", "quantity": 10,
        "irrecoverable_cogs_rub": None, "cogs_ownership": "ADDITIONAL",
        "compensation_rub": None, "compensation_treatment": "NONE_CONFIRMED",
    }]))

    assert result["inventory"]["status"] == "COMPLETE"
    assert result["inventory"]["inventory_loss_cogs_rub"] == "0.00"
    assert result["strict_retained_cohort_loss"]["loss_pool_rub"] == "300.00"
    assert result["strict_retained_cohort_loss"]["loss_per_retained_unit_rub"] == "3.00"


def test_compensation_already_included_is_reported_but_not_subtracted_again():
    result = _resolve(inventory=_inventory([_irrecoverable(treatment="ALREADY_INCLUDED")]))

    assert result["inventory"]["confirmed_compensation_rub"] == "10.00"
    assert result["inventory"]["compensation_deduction_rub"] == "0.00"
    assert result["strict_retained_cohort_loss"]["loss_pool_rub"] == "360.00"
    assert result["strict_retained_cohort_loss"]["loss_per_retained_unit_rub"] == "3.60"


def test_base_included_cogs_is_not_added_to_the_additional_return_loss_pool():
    result = _resolve(inventory=_inventory([_irrecoverable(
        cogs_ownership="BASE_ALREADY_INCLUDED", treatment="ALREADY_INCLUDED",
    )]))

    assert result["inventory"]["base_included_cogs_rub"] == "60.00"
    assert result["inventory"]["inventory_loss_cogs_rub"] == "0.00"
    assert result["strict_retained_cohort_loss"]["loss_pool_rub"] == "300.00"


def test_returned_unit_disposition_quantity_mismatch_blocks_strict_loss():
    result = _resolve(inventory=_inventory([_irrecoverable(quantity=9)]))

    assert result["inventory"]["status"] == "CONFLICT"
    assert result["strict_retained_cohort_loss"]["status"] == "UNAVAILABLE"
    assert result["strict_retained_cohort_loss"]["loss_per_retained_unit_rub"] is None


def test_return_must_be_linked_to_the_same_exact_cohort_as_finance_and_inventory():
    mismatched_quantity = _quantity(cohort_ref=OTHER_COHORT_REF)

    result = _resolve(quantity=mismatched_quantity)

    assert result["quantity"]["status"] == "PARTIAL"
    assert result["fees"]["status"] == "PARTIAL"
    assert result["strict_retained_cohort_loss"]["status"] == "UNAVAILABLE"
    assert "COHORT_BINDING_MISMATCH" in result["warnings"]


@pytest.mark.parametrize("missing_side", ["finance", "quantity"])
def test_missing_optional_cohort_binding_returns_incomplete_not_invalid(missing_side):
    finance = _finance(
        _part("return-fee", FEE_KEYS[0], "-200.00"),
        _part("nonbuyout-fee", FEE_KEYS[1], "-100.00"),
        cohort_ref=None if missing_side == "finance" else COHORT_REF,
    )
    quantity = _quantity(cohort_ref=None if missing_side == "quantity" else COHORT_REF)

    result = _resolve(finance=finance, quantity=quantity)

    assert result["error"] is False
    assert result["status"] == "INCOMPLETE"
    assert result["strict_retained_cohort_loss"]["status"] == "UNAVAILABLE"
    assert "EXACT_COHORT_BINDING_UNAVAILABLE" in result["warnings"]
    assert "cohort_ref" not in repr(result)


def test_wrong_store_or_sku_quantity_cannot_match_finance_scope():
    other_identity = {**IDENTITY, "store_id": "store-b"}

    result = _resolve(quantity=_quantity(identity=other_identity))

    assert result == {"error": True, "code": "UNIT_ECONOMICS_RETURN_IDENTITY_MISMATCH"}


def test_cancelled_or_returned_units_are_not_inferred_from_partial_source_pages():
    partial = _quantity(source_coverage={
        "postings_complete": True, "returns_complete": False,
        "unit_links_complete": False,
    })

    result = _resolve(quantity=partial)

    assert result["quantity"]["status"] == "PARTIAL"
    assert result["strict_retained_cohort_loss"]["status"] == "UNAVAILABLE"


def test_returned_units_cannot_exceed_delivered_or_disagree_with_retained_count():
    too_many_returns = _resolve(quantity=_quantity(delivered=10, returned=11, retained=0))
    wrong_retained = _resolve(quantity=_quantity(delivered=110, returned=10, retained=99))

    assert too_many_returns["quantity"]["status"] == "CONFLICT"
    assert wrong_retained["quantity"]["status"] == "CONFLICT"
    assert too_many_returns["strict_retained_cohort_loss"]["loss_per_retained_unit_rub"] is None
    assert wrong_retained["strict_retained_cohort_loss"]["loss_per_retained_unit_rub"] is None


def test_zero_retained_units_do_not_produce_a_rate():
    result = _resolve(quantity=_quantity(delivered=10, returned=10, retained=0))

    assert result["quantity"]["retained_units"] is None
    assert result["quantity"]["observed_retained_units"] == 0
    assert result["quantity"]["status"] == "INCOMPLETE"
    assert result["strict_retained_cohort_loss"]["loss_per_retained_unit_rub"] is None


def test_missing_return_fee_is_distinct_from_confirmed_zero():
    cogs_only = _finance(
        _part("return-fee", FEE_KEYS[0], "-200.00"),
        expected_keys=[FEE_KEYS[0]],
    )
    confirmed_zero = _finance(_part("return-fee", FEE_KEYS[0], "-200.00"))

    missing = _resolve(finance=cogs_only)
    zero = _resolve(finance=confirmed_zero)

    assert missing["fees"]["by_kind"]["CUSTOMER_NONBUYOUT"]["status"] == "MISSING"
    assert missing["strict_retained_cohort_loss"]["status"] == "UNAVAILABLE"
    assert zero["fees"]["by_kind"]["CUSTOMER_NONBUYOUT"]["status"] == "COMPLETE"
    assert zero["fees"]["additional_exact_cohort_rub"] == "200.00"


def test_account_level_fees_remain_separate_even_if_a_correction_nets_to_zero():
    finance = _finance(
        _part("fee-charge", FEE_KEYS[0], "-200.00", ownership="UNATTRIBUTED", attribution="UNATTRIBUTED"),
        _part("fee-credit", FEE_KEYS[0], "200.00", ownership="UNATTRIBUTED", attribution="UNATTRIBUTED"),
        _part("nonbuyout", FEE_KEYS[1], "-100.00"),
    )

    result = _resolve(finance=finance)

    assert result["fees"]["account_level_rub"] == "0.00"
    assert result["fees"]["account_component_count"] == 1
    assert result["fees"]["status"] == "PARTIAL"
    assert result["strict_retained_cohort_loss"]["status"] == "UNAVAILABLE"


def test_return_fee_credit_is_preserved_but_not_silently_used_as_loss_rate():
    finance = _finance(
        _part("return-charge", FEE_KEYS[0], "-200.00"),
        _part("return-credit", FEE_KEYS[0], "250.00"),
        _part("nonbuyout", FEE_KEYS[1], "-100.00"),
    )

    result = _resolve(finance=finance)

    assert result["fees"]["by_kind"]["CUSTOMER_RETURN"]["additional_exact_cohort_rub"] is None
    assert result["fees"]["by_kind"]["CUSTOMER_RETURN"]["observed_additional_exact_cohort_rub"] == "-50.00"
    assert result["strict_retained_cohort_loss"]["status"] == "UNAVAILABLE"
    assert result["strict_retained_cohort_loss"]["loss_per_retained_unit_rub"] is None


def test_inventory_compensation_credit_larger_than_cogs_requires_review():
    result = _resolve(inventory=_inventory([_irrecoverable(cogs="60.00", compensation="70.00")]))

    assert result["inventory"]["compensation_deduction_rub"] is None
    assert result["inventory"]["observed_compensation_deduction_rub"] == "70.00"
    assert result["inventory"]["status"] == "PARTIAL"
    assert result["strict_retained_cohort_loss"]["status"] == "UNAVAILABLE"


def test_compensation_marked_none_cannot_carry_a_nonzero_amount():
    result = _resolve(inventory=_inventory([_irrecoverable(
        compensation="10.00", treatment="NONE_CONFIRMED",
    )]))

    assert result["inventory"]["status"] == "CONFLICT"
    assert result["strict_retained_cohort_loss"]["status"] == "UNAVAILABLE"


def test_different_event_windows_can_join_only_through_matching_opaque_cohort_binding():
    financial_window = {**WINDOW, "from_date": "2026-10-08", "to_date": "2026-10-14"}
    finance = _finance(
        _part("return-fee", FEE_KEYS[0], "-200.00"),
        _part("nonbuyout", FEE_KEYS[1], "-100.00"),
        source_window=financial_window,
    )

    result = _resolve(finance=finance)

    assert result["strict_retained_cohort_loss"]["status"] == "AVAILABLE"
    assert "SOURCE_WINDOWS_DIFFER; COHORT_MATCH_IS_THE_STRICT_LINK" in result["warnings"]
    assert "cohort_ref" not in repr(result)


def test_aggregate_posting_totals_and_averages_are_not_used_as_return_expenses():
    finance = _finance(
        _part("return-fee", FEE_KEYS[0], "-200.00"),
        _part("nonbuyout", FEE_KEYS[1], "-100.00"),
    )
    finance["observed_net_amount_total"] = "-999999.00"
    finance["observed_net_amount_average"] = "-9999.00"

    result = _resolve(finance=finance)

    assert result["fees"]["additional_exact_cohort_rub"] == "300.00"
    assert result["strict_retained_cohort_loss"]["loss_pool_rub"] == "350.00"


def test_no_return_units_allows_only_complete_confirmed_zero_inventory():
    finance = _finance(expected_keys=FEE_KEYS)
    result = _resolve(
        finance=finance,
        quantity=_quantity(delivered=100, returned=0, retained=100),
        inventory=False,
    )

    assert result["inventory"]["status"] == "CONFIRMED_ZERO"
    assert result["strict_retained_cohort_loss"]["status"] == "AVAILABLE"
    assert result["strict_retained_cohort_loss"]["loss_per_retained_unit_rub"] == "0.00"


def test_zero_inventory_is_not_confirmed_when_return_cohort_link_is_mismatched():
    result = _resolve(
        quantity=_quantity(delivered=100, returned=0, retained=100, cohort_ref=OTHER_COHORT_REF),
        inventory=False,
    )

    assert result["inventory"]["status"] == "PARTIAL"
    assert result["inventory"]["inventory_loss_cogs_rub"] is None
    assert result["strict_retained_cohort_loss"]["status"] == "UNAVAILABLE"


def test_inventory_disposition_from_another_cohort_is_rejected():
    inventory = _inventory([_irrecoverable()], cohort_ref=OTHER_COHORT_REF)

    result = _resolve(inventory=inventory)

    assert result["inventory"]["status"] == "PARTIAL"
    assert result["inventory"]["inventory_loss_cogs_rub"] is None
    assert result["strict_retained_cohort_loss"]["status"] == "UNAVAILABLE"


def test_resolver_never_returns_raw_cohort_reference_or_changes_business_data():
    result = _resolve()

    assert result["read_only"] is True
    assert result["executed"] is False
    assert COHORT_REF not in repr(result)
