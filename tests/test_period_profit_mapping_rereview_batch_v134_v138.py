from period_profit_mapping_rereview import (
    build_mapping_rereview_candidate,
    build_mapping_rereview_confirmation,
    build_mapping_replacement_authorization,
    build_mapping_replacement_diff,
    build_mapping_replacement_draft,
)


def _mapping():
    return {
        "mapping_id": "active:m1",
        "operations": [
            {"type_id": 1, "name": "Old Return", "description": "old", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
            {"type_id": 9, "name": "Gone", "description": "gone", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
            {"type_id": 5, "name": "Stable", "description": "stable", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
        ],
    }


def _quality():
    return {
        "scope": "RETURN",
        "mapping_available": True,
        "review_required": True,
        "missing_type_ids": [9],
        "renamed_operations": [
            {"type_id": 1, "mapped_name": "Old Return", "current_name": "Return Fee"},
        ],
    }


def _catalog():
    return {
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_CATALOG_READY",
        "operations": [
            {"type_id": 1, "name": "Return Fee", "description": "current", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
            {"type_id": 2, "name": "Replacement", "description": "human selected", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
            {"type_id": 5, "name": "Stable", "description": "stable", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
        ],
    }


def test_candidate_contains_only_drifted_type_ids():
    result = build_mapping_rereview_candidate(_quality(), _mapping(), _catalog())
    assert result["affected_type_ids"] == [1, 9]
    assert [row["type_id"] for row in result["targets"]] == [1, 9]
    assert result["automatic_remap_allowed"] is False


def test_all_drift_targets_require_human_confirmation():
    candidate = build_mapping_rereview_candidate(_quality(), _mapping(), _catalog())
    result = build_mapping_rereview_confirmation(candidate, [{"type_id": 1, "decision": "USE_CURRENT"}])
    assert result["code"] == "PERIOD_PROFIT_MAPPING_REREVIEW_ALL_TARGETS_REQUIRE_CONFIRMATION"


def test_confirmation_can_use_current_and_explicit_replacement_only():
    candidate = build_mapping_rereview_candidate(_quality(), _mapping(), _catalog())
    result = build_mapping_rereview_confirmation(candidate, [
        {"type_id": 1, "decision": "USE_CURRENT"},
        {"type_id": 9, "decision": "REPLACE", "replacement_type_id": 2},
    ])
    assert result["human_confirmed"] is True
    assert result["confirmations"][0]["replacement_operation"]["name"] == "Return Fee"
    assert result["confirmations"][1]["replacement_operation"]["type_id"] == 2


def test_replacement_cannot_overwrite_unaffected_active_type_id():
    candidate = build_mapping_rereview_candidate(_quality(), _mapping(), _catalog())
    result = build_mapping_rereview_confirmation(candidate, [
        {"type_id": 1, "decision": "USE_CURRENT"},
        {"type_id": 9, "decision": "REPLACE", "replacement_type_id": 5},
    ])
    assert result["code"] == "PERIOD_PROFIT_MAPPING_REREVIEW_REPLACEMENT_COLLIDES_WITH_ACTIVE_OPERATION"
    assert result["automatic_remap_allowed"] is False


def test_draft_and_diff_preserve_unaffected_operations():
    candidate = build_mapping_rereview_candidate(_quality(), _mapping(), _catalog())
    confirmation = build_mapping_rereview_confirmation(candidate, [
        {"type_id": 1, "decision": "USE_CURRENT"},
        {"type_id": 9, "decision": "REMOVE"},
    ])
    draft = build_mapping_replacement_draft(confirmation)
    diff = build_mapping_replacement_diff(_mapping(), draft)
    assert 5 in draft["type_ids"]
    assert 9 not in draft["type_ids"]
    assert diff["change_count"] == 2
    assert diff["changed_operations"][0]["type_id"] == 1


def test_authorization_still_blocks_save_and_activation():
    candidate = build_mapping_rereview_candidate(_quality(), _mapping(), _catalog())
    confirmation = build_mapping_rereview_confirmation(candidate, [
        {"type_id": 1, "decision": "USE_CURRENT"},
        {"type_id": 9, "decision": "REMOVE"},
    ])
    draft = build_mapping_replacement_draft(confirmation)
    diff = build_mapping_replacement_diff(_mapping(), draft)
    result = build_mapping_replacement_authorization(diff, "AUTHORIZE")
    assert result["mapping_build_allowed"] is True
    assert result["registry_save_allowed"] is False
    assert result["activation_allowed"] is False
    assert result["profit_adjustment_allowed"] is False
    assert result["executed"] is False


def test_malformed_mapping_fails_closed_without_exception():
    result = build_mapping_rereview_candidate(_quality(), ["not", "a", "mapping"], _catalog())
    assert result["code"] == "PERIOD_PROFIT_MAPPING_REREVIEW_ACTIVE_MAPPING_REQUIRED"
    assert result["automatic_remap_allowed"] is False


def test_malformed_operation_is_ignored_and_required_target_blocks():
    mapping = _mapping()
    mapping["operations"] = [{"name": "missing id"}, mapping["operations"][2]]
    result = build_mapping_rereview_candidate(_quality(), mapping, _catalog())
    assert result["code"] == "PERIOD_PROFIT_MAPPING_REREVIEW_MAPPING_TARGET_MISSING"
    assert result["automatic_activation_allowed"] is False
