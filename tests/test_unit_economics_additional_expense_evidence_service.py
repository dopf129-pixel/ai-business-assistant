from copy import deepcopy
import hashlib
import json

from services.unit_economics_additional_expense_evidence_service import (
    UnitEconomicsAdditionalExpenseEvidenceService,
)
from services.unit_economics_expense_normalizer import UnitEconomicsExpenseNormalizer


IDENTITY = {
    "owner_id": "owner-a", "store_id": "store-a", "product_id": "product-a",
    "offer_id": "offer-a", "sku": "sku-a", "sale_schema": "FBO",
}
WINDOW = {
    "from_date": "2026-09-01", "to_date": "2026-09-30",
    "date_basis": "OZON_ACCRUAL_DATE", "timezone": "Europe/Moscow",
}


def _part(component_id, key, amount, category, **changes):
    result = {
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
    result.update(changes)
    return result


def _snapshot(parts=(), *, expected=(), coverage=None):
    operations = [
        {
            "operation_id": f"posting-{index}",
            "identity": deepcopy(IDENTITY),
            "components": [deepcopy(part)],
        }
        for index, part in enumerate(parts)
    ]
    result = UnitEconomicsExpenseNormalizer.normalize({
        "schema_version": 1,
        "identity": deepcopy(IDENTITY),
        "source": "SELLER_FINANCE",
        "source_method": "/v3/finance/transaction/list",
        "source_contract_version": "v3",
        "source_window": deepcopy(WINDOW),
        "received_at": "2026-10-01T10:00:00Z",
        "as_of": "2026-10-01T10:00:00Z",
        "coverage": coverage or {
            "requested_pages": 1, "received_pages": 1, "has_more": False,
            "stop_reason": "END_OF_DATA", "source_complete": True,
        },
        "expected_component_keys": list(expected),
        "operations": operations,
    })
    return result


def _mapping(rows):
    normalized = sorted(rows, key=lambda row: row["component_key"])
    canonical = json.dumps(
        {
            "error": False,
            "status": "UNIT_ECONOMICS_ADDITIONAL_SERVICE_MAPPING_READY",
            "schema_version": 1,
            "mapping_authorized": True,
            "financial_evidence_mapping_allowed": True,
            "automatic_activation_allowed": False,
            "profit_adjustment_allowed": False,
            "immutable_artifact": True,
            "components": normalized,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    mapping_id = "unit-economics-additional-service-map:" + hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    return {
        "error": False,
        "status": "UNIT_ECONOMICS_ADDITIONAL_SERVICE_MAPPING_READY",
        "schema_version": 1,
        "mapping_id": mapping_id,
        "mapping_authorized": True,
        "financial_evidence_mapping_allowed": True,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "immutable_artifact": True,
        "components": normalized,
    }


def _category(result, name):
    return result["categories"][name]


def test_n07_exact_sku_paid_storage_is_exposed_as_numerator_without_guessing_denominator():
    result = UnitEconomicsAdditionalExpenseEvidenceService.resolve(_snapshot([
        _part("storage-row", "FINANCE_PAID_STORAGE", "-1.74", "STORAGE"),
    ]))

    storage = _category(result, "STORAGE")
    assert storage["status"] == "PRESENT"
    assert storage["observed_expense_rub"] == "1.74"
    assert storage["exact_sku_recurring_expense_rub"] == "1.74"
    assert storage["unit_amount_rub"] is None
    assert storage["denominator_units"] is None
    assert result["full_cost_coverage_confirmed"] is False


def test_confirmed_zero_and_missing_storage_remain_distinct():
    zero = UnitEconomicsAdditionalExpenseEvidenceService.resolve(
        _snapshot(expected=["FINANCE_PAID_STORAGE"])
    )
    missing = UnitEconomicsAdditionalExpenseEvidenceService.resolve(_snapshot())

    assert _category(zero, "STORAGE")["status"] == "CONFIRMED_ZERO"
    assert _category(zero, "STORAGE")["observed_expense_rub"] == "0.00"
    assert _category(missing, "STORAGE")["status"] == "MISSING"
    assert _category(missing, "STORAGE")["observed_expense_rub"] is None
    assert _category(missing, "STORAGE")["exact_sku_recurring_expense_rub"] is None


def test_base_included_storage_is_reported_but_not_added_again():
    result = UnitEconomicsAdditionalExpenseEvidenceService.resolve(_snapshot([
        _part(
            "storage-row", "FINANCE_PAID_STORAGE", "-40.00", "STORAGE",
            ownership="BASE_ALREADY_INCLUDED",
        ),
    ]))

    storage = _category(result, "STORAGE")
    assert storage["observed_expense_rub"] == "40.00"
    assert storage["base_included_expense_rub"] == "40.00"
    assert storage["exact_sku_recurring_expense_rub"] == "0.00"
    assert "ALREADY_INCLUDED_IN_BASE_COST" in storage["reasons"]


def test_account_level_storage_stays_unattributed_and_is_not_allocated_to_sku():
    result = UnitEconomicsAdditionalExpenseEvidenceService.resolve(_snapshot([
        _part(
            "storage-row", "FINANCE_PAID_STORAGE", "-75.00", "STORAGE",
            ownership="UNATTRIBUTED", attribution="UNATTRIBUTED",
        ),
    ]))

    storage = _category(result, "STORAGE")
    assert storage["account_level_expense_rub"] == "75.00"
    assert storage["exact_sku_recurring_expense_rub"] is None
    assert result["status"] == "PARTIAL"
    assert "ACCOUNT_LEVEL_NOT_ALLOCATED" in storage["reasons"]


def test_storage_window_allocation_is_separate_and_never_divided_here():
    result = UnitEconomicsAdditionalExpenseEvidenceService.resolve(_snapshot([
        _part(
            "storage-row", "FINANCE_PAID_STORAGE", "-150.00", "STORAGE",
            attribution="WINDOW_ALLOCATION", origin="DETERMINISTIC_DERIVATION",
        ),
    ]))

    storage = _category(result, "STORAGE")
    assert storage["window_allocation_candidate_rub"] == "150.00"
    assert storage["exact_sku_recurring_expense_rub"] is None
    assert storage["unit_amount_rub"] is None
    assert "WINDOW_ALLOCATION_REQUIRES_EXPLICIT_MODEL" in storage["reasons"]


def test_n04_one_off_credit_is_preserved_as_history_not_recurring_rate():
    parts = [
        _part(
            "storage-charge", "FINANCE_PAID_STORAGE", "-300.00", "STORAGE",
            recurrence="ONE_OFF", correction_state="CORRECTED_AS_OF",
        ),
        _part(
            "storage-credit", "FINANCE_PAID_STORAGE", "350.00", "STORAGE",
            recurrence="ONE_OFF", correction_state="CORRECTED_AS_OF",
        ),
    ]
    result = UnitEconomicsAdditionalExpenseEvidenceService.resolve(_snapshot(parts))

    storage = _category(result, "STORAGE")
    assert storage["observed_expense_rub"] == "-50.00"
    assert storage["one_off_expense_rub"] == "-50.00"
    assert storage["exact_sku_recurring_expense_rub"] is None
    assert "ONE_OFF_CREDIT_NOT_A_RECURRING_RATE" in storage["reasons"]


def test_mapped_other_service_is_exactly_one_additional_bucket():
    mapping = _mapping([{
        "component_key": "FINANCE_LABEL_PRINTING",
        "category": "OTHER_SERVICE",
        "service_key": "LABEL_PRINTING",
    }])
    result = UnitEconomicsAdditionalExpenseEvidenceService.resolve(_snapshot([
        _part("service-row", "FINANCE_LABEL_PRINTING", "-12.50", "OTHER_SERVICE"),
    ]), mapping)

    service = _category(result, "ADDITIONAL_SERVICE:LABEL_PRINTING")
    assert service["exact_sku_recurring_expense_rub"] == "12.50"
    assert result["invalid_component_count"] == 0
    assert "FINANCE_LABEL_PRINTING" not in repr(result)


def test_unmapped_other_service_is_visible_but_not_added():
    result = UnitEconomicsAdditionalExpenseEvidenceService.resolve(_snapshot([
        _part("service-row", "FINANCE_UNKNOWN_SERVICE", "-12.50", "OTHER_SERVICE"),
    ]))

    unmapped = _category(result, "UNMAPPED_ADDITIONAL_SERVICE")
    assert unmapped["status"] == "UNMAPPED"
    assert unmapped["observed_expense_rub"] == "12.50"
    assert unmapped["exact_sku_recurring_expense_rub"] is None
    assert result["status"] == "PARTIAL"


def test_cross_docking_is_delegated_to_existing_source_not_recounted():
    result = UnitEconomicsAdditionalExpenseEvidenceService.resolve(_snapshot([
        _part("crossdock-row", "FINANCE_CROSS_DOCKING", "-100.00", "CROSS_DOCKING"),
    ]))

    cross_docking = _category(result, "CROSS_DOCKING")
    assert cross_docking["status"] == "DELEGATED"
    assert cross_docking["delegated_to_existing_model_rub"] == "100.00"
    assert cross_docking["exact_sku_recurring_expense_rub"] is None


def test_partial_source_keeps_observed_value_but_blocks_applicable_expense():
    result = UnitEconomicsAdditionalExpenseEvidenceService.resolve(_snapshot(
        [_part("storage-row", "FINANCE_PAID_STORAGE", "-1.74", "STORAGE")],
        coverage={
            "requested_pages": 2, "received_pages": 1, "has_more": True,
            "stop_reason": "TIME_BUDGET", "source_complete": False,
        },
    ))

    storage = _category(result, "STORAGE")
    assert storage["status"] == "PARTIAL"
    assert storage["observed_expense_rub"] == "1.74"
    assert storage["exact_sku_recurring_expense_rub"] is None
    assert result["source_complete"] is False


def test_mapping_must_be_authorized_immutable_and_integrity_bound():
    row = {
        "component_key": "FINANCE_LABEL_PRINTING",
        "category": "OTHER_SERVICE",
        "service_key": "LABEL_PRINTING",
    }
    mapping = _mapping([row])
    altered = {**mapping, "components": [{**row, "service_key": "OTHER_BUCKET"}]}
    denied = {**mapping, "mapping_authorized": False}

    assert UnitEconomicsAdditionalExpenseEvidenceService.resolve(
        _snapshot(), altered
    ) == {"error": True, "code": "UNIT_ECONOMICS_ADDITIONAL_EXPENSE_MAPPING_INVALID"}
    assert UnitEconomicsAdditionalExpenseEvidenceService.resolve(
        _snapshot(), denied
    ) == {"error": True, "code": "UNIT_ECONOMICS_ADDITIONAL_EXPENSE_MAPPING_INVALID"}


def test_component_key_and_category_conflict_is_not_applied():
    result = UnitEconomicsAdditionalExpenseEvidenceService.resolve(_snapshot([
        _part("storage-row", "FINANCE_PAID_STORAGE", "-1.74", "PLACEMENT"),
    ]))

    assert result["status"] == "CONFLICT"
    assert _category(result, "STORAGE")["status"] == "CONFLICT"
    assert _category(result, "STORAGE")["exact_sku_recurring_expense_rub"] is None
