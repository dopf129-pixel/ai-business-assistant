from copy import deepcopy

import pytest

from services.unit_economics_expense_normalizer import UnitEconomicsExpenseNormalizer


IDENTITY = {
    "owner_id": "owner-a", "store_id": "store-a", "product_id": "product-a",
    "offer_id": "offer-a", "sku": "sku-a", "sale_schema": "FBO",
}


def _component(component_id, key, amount, **changes):
    value = {
        "component_id": component_id,
        "component_key": key,
        "category": "OTHER_SERVICE",
        "signed_source_amount_rub": amount,
        "ownership": "ADDITIONAL",
        "attribution": "EXACT_SKU",
        "origin": "OFFICIAL_SOURCE",
        "recurrence": "UNKNOWN",
        "correction_state": "FINAL_AS_OF",
    }
    value.update(changes)
    return value


def _operation(operation_id, components, identity=None):
    return {
        "operation_id": operation_id,
        "identity": deepcopy(identity or IDENTITY),
        "components": deepcopy(components),
    }


def _evidence(operations, **changes):
    value = {
        "schema_version": 1,
        "identity": deepcopy(IDENTITY),
        "source": "SELLER_FINANCE",
        "source_method": "/v3/finance/transaction/list",
        "source_contract_version": "v3",
        "source_window": {
            "from_date": "2026-10-01", "to_date": "2026-10-07",
            "date_basis": "OZON_ACCRUAL_DATE", "timezone": "Europe/Moscow",
        },
        "received_at": "2026-10-08T10:00:00Z",
        "as_of": "2026-10-08T10:00:00Z",
        "coverage": {
            "requested_pages": 1, "received_pages": 1, "has_more": False,
            "stop_reason": "END_OF_DATA", "source_complete": True,
        },
        "expected_component_keys": [],
        "operations": deepcopy(operations),
    }
    value.update(changes)
    return value


def _by_key(result):
    return {item["component_key"]: item for item in result["components"]}


def test_multi_service_operation_and_exact_duplicate_are_counted_once_without_raw_ids():
    service_x = _component("part-x", "SERVICE_X", "-30.00")
    service_y = _component("part-y", "SERVICE_Y", "-20.00")
    evidence = _evidence([
        _operation("posting-A", [service_x, service_y]),
        _operation("posting-A", [service_x, service_y]),
        _operation("posting-B", [_component("part-z", "SERVICE_Z", "-10.00")]),
    ])

    result = UnitEconomicsExpenseNormalizer.normalize(evidence)

    assert result["error"] is False
    assert result["completeness"] == "COMPLETE"
    assert result["coverage"]["accepted_component_rows"] == 3
    assert result["coverage"]["duplicate_rows_ignored"] == 2
    assert result["ownership_ledger"]["ADDITIONAL"]["signed_source_amount_rub"] == "-60.00"
    assert result["ownership_ledger"]["ADDITIONAL"]["normalized_expense_rub"] == "60.00"
    assert "posting-A" not in repr(result)
    assert "part-x" not in repr(result)


def test_changed_duplicate_is_conflict_and_disputed_amount_is_not_exposed():
    evidence = _evidence([
        _operation("posting-A", [_component("part-x", "SERVICE_X", "-30.00")]),
        _operation("posting-A", [_component("part-x", "SERVICE_X", "-31.00")]),
        _operation("posting-A", [_component("part-y", "SERVICE_Y", "-20.00")]),
    ])

    result = UnitEconomicsExpenseNormalizer.normalize(evidence)

    assert result["completeness"] == "CONFLICT"
    assert result["coverage"]["conflict_count"] == 1
    assert _by_key(result)["SERVICE_X"]["status"] == "CONFLICT"
    assert _by_key(result)["SERVICE_X"]["signed_source_amount_rub"] is None
    assert _by_key(result)["SERVICE_X"]["normalized_expense_rub"] is None
    assert _by_key(result)["SERVICE_Y"]["normalized_expense_rub"] == "20.00"


def test_related_correction_preserves_signed_credit_and_normalizes_net_expense():
    evidence = _evidence([
        _operation("posting-charge", [_component("charge", "RETURN_FEE", "-300.00")]),
        _operation("posting-correction", [_component("correction", "RETURN_FEE", "50.00")]),
    ], expected_component_keys=["RETURN_FEE"])

    result = UnitEconomicsExpenseNormalizer.normalize(evidence)

    component = _by_key(result)["RETURN_FEE"]
    assert component["status"] == "PRESENT"
    assert component["signed_source_amount_rub"] == "-250.00"
    assert component["normalized_expense_rub"] == "250.00"
    assert result["ownership_ledger"]["ADDITIONAL"]["normalized_expense_rub"] == "250.00"


def test_same_source_operation_id_is_scoped_independently_by_store():
    operation = _operation("same-provider-id", [_component("part", "SERVICE_X", "-30.00")])
    first = UnitEconomicsExpenseNormalizer.normalize(_evidence([operation]))
    second_identity = {**IDENTITY, "store_id": "store-b"}
    second_operation = _operation("same-provider-id", operation["components"], identity=second_identity)
    second = UnitEconomicsExpenseNormalizer.normalize(_evidence(
        [second_operation], identity=second_identity,
    ))

    assert _by_key(first)["SERVICE_X"]["normalized_expense_rub"] == "30.00"
    assert _by_key(second)["SERVICE_X"]["normalized_expense_rub"] == "30.00"
    assert first["identity"]["store_id"] != second["identity"]["store_id"]
    assert first["source_revision"] != second["source_revision"]


def test_partial_pages_do_not_become_confirmed_zero_but_complete_empty_source_does():
    partial = _evidence([], expected_component_keys=["STORAGE"], coverage={
        "requested_pages": 2, "received_pages": 1, "has_more": True,
        "stop_reason": "TIME_BUDGET", "source_complete": False,
    })
    partial_result = UnitEconomicsExpenseNormalizer.normalize(partial)

    empty = _evidence([], expected_component_keys=["STORAGE"], coverage={
        "requested_pages": 1, "received_pages": 1, "has_more": False,
        "stop_reason": "CONFIRMED_EMPTY", "source_complete": True,
    })
    empty_result = UnitEconomicsExpenseNormalizer.normalize(empty)

    assert partial_result["completeness"] == "PARTIAL"
    assert _by_key(partial_result)["STORAGE"]["status"] == "PARTIAL"
    assert _by_key(partial_result)["STORAGE"]["normalized_expense_rub"] is None
    assert empty_result["completeness"] == "CONFIRMED_ZERO"
    assert _by_key(empty_result)["STORAGE"]["status"] == "CONFIRMED_ZERO"
    assert _by_key(empty_result)["STORAGE"]["normalized_expense_rub"] == "0.00"


def test_identity_mismatch_is_not_attributed_to_requested_sku_or_marked_complete():
    other_identity = {**IDENTITY, "sku": "sku-other"}
    evidence = _evidence([_operation(
        "posting-other-sku", [_component("part", "SERVICE_X", "-30.00")], identity=other_identity,
    )], expected_component_keys=["SERVICE_X"])

    result = UnitEconomicsExpenseNormalizer.normalize(evidence)

    assert result["completeness"] == "CONFLICT"
    assert result["coverage"]["identity_mismatch_rows"] == 1
    assert _by_key(result)["SERVICE_X"]["status"] == "PARTIAL"
    assert _by_key(result)["SERVICE_X"]["normalized_expense_rub"] is None
    assert "posting-other-sku" not in repr(result)


@pytest.mark.parametrize("invalid_amount", [True, float("nan"), float("inf"), "NaN", "Infinity", "1e30"])
def test_invalid_or_unsafe_money_is_rejected_without_echoing_input(invalid_amount):
    evidence = _evidence([_operation("sensitive-posting-id", [
        _component("sensitive-part-id", "SERVICE_X", invalid_amount),
    ])])

    result = UnitEconomicsExpenseNormalizer.normalize(evidence)

    assert result["error"] is False
    assert result["completeness"] == "PARTIAL"
    assert result["coverage"]["invalid_rows"] == 1
    assert "sensitive-posting-id" not in repr(result)
    assert "sensitive-part-id" not in repr(result)
    assert "Infinity" not in repr(result)
    assert "NaN" not in repr(result)


def test_unknown_schema_is_rejected_and_unrecognized_raw_fields_are_not_returned():
    incompatible = _evidence([], schema_version=2)
    assert UnitEconomicsExpenseNormalizer.normalize(incompatible) == {
        "error": True, "code": "UNIT_ECONOMICS_EVIDENCE_SCHEMA_UNSUPPORTED",
    }
    assert UnitEconomicsExpenseNormalizer.normalize(_evidence([], schema_version=True))["error"] is True

    evidence = _evidence([_operation("raw-id", [
        {**_component("part", "SERVICE_X", "-1.00"), "posting_number": "secret-posting"},
    ])], raw_response={"api_key": "must-not-escape"})
    result = UnitEconomicsExpenseNormalizer.normalize(evidence)

    assert result["error"] is False
    assert result["coverage"]["unknown_field_count"] == 2
    assert "raw_response" not in repr(result)
    assert "api_key" not in repr(result)
    assert "secret-posting" not in repr(result)
    assert "raw-id" not in repr(result)


def test_unknown_timezone_is_preserved_as_unknown_and_negative_zero_is_canonicalized():
    evidence = _evidence([_operation("posting-A", [
        _component("part", "SERVICE_X", "-0.004", attribution="WINDOW_ALLOCATION"),
    ])])
    evidence["source_window"]["timezone"] = "UNKNOWN"

    result = UnitEconomicsExpenseNormalizer.normalize(evidence)

    assert result["error"] is False
    assert result["source_window"]["timezone"] == "UNKNOWN"
    assert _by_key(result)["SERVICE_X"]["signed_source_amount_rub"] == "0.00"
    assert _by_key(result)["SERVICE_X"]["normalized_expense_rub"] == "0.00"


def test_unattributed_amount_cannot_be_marked_as_an_additional_sku_expense():
    evidence = _evidence([_operation("posting-account", [
        _component(
            "part", "ACCOUNT_AD", "-300.00", category="ADVERTISING_OTHER",
            attribution="UNATTRIBUTED",
        ),
    ])])

    result = UnitEconomicsExpenseNormalizer.normalize(evidence)

    assert result["completeness"] == "PARTIAL"
    assert result["coverage"]["invalid_rows"] == 1
    assert result["ownership_ledger"]["ADDITIONAL"]["normalized_expense_rub"] == "0.00"
    assert "posting-account" not in repr(result)


def test_component_metadata_conflict_blocks_the_whole_component_group():
    evidence = _evidence([
        _operation("posting-A", [_component("part-1", "SERVICE_X", "-30.00")]),
        _operation("posting-A", [_component(
            "part-2", "SERVICE_X", "-20.00", ownership="BASE_ALREADY_INCLUDED",
        )]),
    ])

    result = UnitEconomicsExpenseNormalizer.normalize(evidence)

    assert result["completeness"] == "CONFLICT"
    assert result["coverage"]["conflict_count"] == 1
    assert _by_key(result)["SERVICE_X"]["status"] == "CONFLICT"
    assert _by_key(result)["SERVICE_X"]["signed_source_amount_rub"] is None
    assert result["ownership_ledger"]["ADDITIONAL"]["normalized_expense_rub"] == "0.00"
