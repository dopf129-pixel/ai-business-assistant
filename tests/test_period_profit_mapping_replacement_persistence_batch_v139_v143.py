from period_profit_expense_operation_authorized_mapping import (
    build_period_profit_expense_operation_authorized_mapping,
)
from period_profit_mapping_rereview import (
    build_mapping_rereview_candidate,
    build_mapping_rereview_confirmation,
    build_mapping_replacement_authorization,
    build_mapping_replacement_diff,
    build_mapping_replacement_draft,
)
from period_profit_mapping_replacement_persistence import (
    build_authorized_replacement_mapping,
    build_replacement_activation_handoff,
    build_replacement_persistence_preview,
    build_replacement_save_decision,
    persist_replacement_as_inactive,
)
from return_financial_operation_authorized_mapping import (
    build_return_financial_operation_authorized_mapping,
)
from services.period_profit_mapping_admin_service import PeriodProfitMappingAdminService
from services.period_profit_mapping_registry_service import PeriodProfitMappingRegistryService


def _return_mapping(operations):
    return build_return_financial_operation_authorized_mapping({
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_SELECTION_AUTHORIZED",
        "mapping_authorized": True,
        "financial_evidence_mapping_allowed": True,
        "selected_operations": operations,
    })


def _expense_mapping(scope, operations):
    return build_period_profit_expense_operation_authorized_mapping({
        "error": False,
        "status": "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZED",
        "scope": scope,
        "mapping_authorized": True,
        "financial_evidence_mapping_allowed": True,
        "selected_operations": operations,
    })


def _ops():
    return [
        {"type_id": 1, "name": "Old Return", "description": "old", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
        {"type_id": 9, "name": "Gone", "description": "gone", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
        {"type_id": 5, "name": "Stable", "description": "stable", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
    ]


def _authorized_chain(active_mapping):
    quality = {
        "scope": "RETURN",
        "mapping_available": True,
        "review_required": True,
        "missing_type_ids": [9],
        "renamed_operations": [
            {"type_id": 1, "mapped_name": "Old Return", "current_name": "Return Fee"},
        ],
    }
    catalog = {
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_CATALOG_READY",
        "operations": [
            {"type_id": 1, "name": "Return Fee", "description": "current", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
            {"type_id": 5, "name": "Stable", "description": "stable", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
        ],
    }
    candidate = build_mapping_rereview_candidate(quality, active_mapping, catalog)
    confirmation = build_mapping_rereview_confirmation(candidate, [
        {"type_id": 1, "decision": "USE_CURRENT"},
        {"type_id": 9, "decision": "REMOVE"},
    ])
    draft = build_mapping_replacement_draft(confirmation)
    diff = build_mapping_replacement_diff(active_mapping, draft)
    authorization = build_mapping_replacement_authorization(diff, "AUTHORIZE")
    return diff, authorization


def _registry(tmp_path):
    return PeriodProfitMappingRegistryService(
        str(tmp_path / "mapping-registry.json"),
        clock=lambda: "2026-08-29T20:00:00+00:00",
    )


def test_v139_return_builder_reuses_canonical_production_hash():
    active = _return_mapping(_ops())
    _, authorization = _authorized_chain(active)
    result = build_authorized_replacement_mapping(authorization)
    expected = _return_mapping(authorization["replacement_operations"])
    assert result["mapping_id"] == expected["mapping_id"]
    assert result["status"] == "RETURN_FINANCIAL_OPERATION_AUTHORIZED_MAPPING_READY"
    assert result["immutable_artifact"] is True
    assert result["automatic_activation_allowed"] is False


def test_v139_expense_builder_reuses_canonical_production_hash():
    operations = [{"type_id": 41, "name": "Reviewed Storage", "description": None, "source": "OZON_FINANCE_ACCRUAL_TYPES"}]
    authorization = {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REPLACEMENT_AUTHORIZED",
        "scope": "STORAGE",
        "decision": "AUTHORIZE",
        "active_mapping_id": "old",
        "replacement_operations": operations,
        "mapping_build_allowed": True,
        "mapping_authorized": True,
        "registry_save_allowed": False,
        "activation_allowed": False,
    }
    result = build_authorized_replacement_mapping(authorization)
    expected = _expense_mapping("STORAGE", operations)
    assert result["mapping_id"] == expected["mapping_id"]
    assert result["scope"] == "STORAGE"
    assert result["profit_adjustment_allowed"] is False


def test_v140_preview_is_read_only_and_predicts_next_inactive_revision(tmp_path):
    registry = _registry(tmp_path)
    active = _return_mapping(_ops())
    registry.save("RETURN", active, activate=True)
    diff, authorization = _authorized_chain(active)
    artifact = build_authorized_replacement_mapping(authorization)
    before = registry.history("RETURN")
    preview = build_replacement_persistence_preview(registry, authorization, artifact, diff)
    after = registry.history("RETURN")
    assert preview["expected_revision_id"] == "return-mapping-r2"
    assert preview["current_active_revision_id"] == "return-mapping-r1"
    assert preview["new_mapping_id"] == artifact["mapping_id"]
    assert preview["registry_save_allowed"] is False
    assert before["revisions"] == after["revisions"]


def test_v140_preview_rejects_valid_but_unauthorized_artifact(tmp_path):
    registry = _registry(tmp_path)
    active = _return_mapping(_ops())
    registry.save("RETURN", active, activate=True)
    diff, authorization = _authorized_chain(active)
    unauthorized = _return_mapping([
        {"type_id": 777, "name": "Different", "description": None, "source": "OZON_FINANCE_ACCRUAL_TYPES"},
    ])
    result = build_replacement_persistence_preview(registry, authorization, unauthorized, diff)
    assert result["code"] == "PERIOD_PROFIT_MAPPING_REPLACEMENT_PREVIEW_INPUT_INVALID"
    assert result["registry_save_allowed"] is False


def test_v141_reject_never_allows_registry_save(tmp_path):
    registry = _registry(tmp_path)
    active = _return_mapping(_ops())
    registry.save("RETURN", active, activate=True)
    diff, authorization = _authorized_chain(active)
    artifact = build_authorized_replacement_mapping(authorization)
    preview = build_replacement_persistence_preview(registry, authorization, artifact, diff)
    decision = build_replacement_save_decision(preview, "REJECT")
    result = persist_replacement_as_inactive(registry, artifact, decision)
    assert decision["registry_save_allowed"] is False
    assert decision["activation_allowed"] is False
    assert result["code"] == "PERIOD_PROFIT_MAPPING_REPLACEMENT_EXPLICIT_SAVE_REQUIRED"
    assert len(registry.history("RETURN")["revisions"]) == 1


def test_v142_save_persists_inactive_and_keeps_active_revision(tmp_path):
    registry = _registry(tmp_path)
    active = _return_mapping(_ops())
    registry.save("RETURN", active, activate=True)
    diff, authorization = _authorized_chain(active)
    artifact = build_authorized_replacement_mapping(authorization)
    preview = build_replacement_persistence_preview(registry, authorization, artifact, diff)
    decision = build_replacement_save_decision(preview, "SAVE")
    result = persist_replacement_as_inactive(registry, artifact, decision, actor="HUMAN_REVIEWER")
    history = registry.history("RETURN")
    assert result["revision_id"] == "return-mapping-r2"
    assert result["active"] is False
    assert history["active_revision_id"] == "return-mapping-r1"
    assert history["revisions"][-1]["mapping_id"] == artifact["mapping_id"]
    assert history["events"][-1]["event"] == "SAVE"
    assert result["activation_allowed"] is False


def test_v142_stale_preview_fails_closed_before_save(tmp_path):
    registry = _registry(tmp_path)
    active = _return_mapping(_ops())
    registry.save("RETURN", active, activate=True)
    diff, authorization = _authorized_chain(active)
    artifact = build_authorized_replacement_mapping(authorization)
    preview = build_replacement_persistence_preview(registry, authorization, artifact, diff)
    decision = build_replacement_save_decision(preview, "SAVE")
    registry.save("RETURN", active, activate=False)
    result = persist_replacement_as_inactive(registry, artifact, decision)
    assert result["code"] == "PERIOD_PROFIT_MAPPING_REPLACEMENT_SAVE_PREVIEW_STALE"
    assert len(registry.history("RETURN")["revisions"]) == 2


def test_v143_handoff_only_creates_existing_activation_preview(tmp_path):
    registry = _registry(tmp_path)
    admin = PeriodProfitMappingAdminService(registry)
    active = _return_mapping(_ops())
    registry.save("RETURN", active, activate=True)
    diff, authorization = _authorized_chain(active)
    artifact = build_authorized_replacement_mapping(authorization)
    preview = build_replacement_persistence_preview(registry, authorization, artifact, diff)
    decision = build_replacement_save_decision(preview, "SAVE")
    persisted = persist_replacement_as_inactive(registry, artifact, decision)
    handoff = build_replacement_activation_handoff(admin, persisted)
    history = registry.history("RETURN")
    assert handoff["status"] == "PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_HANDOFF_READY"
    assert handoff["action"] == "ACTIVATE"
    assert handoff["target_revision_id"] == "return-mapping-r2"
    assert handoff["explicit_decision_required"] is True
    assert handoff["automatic_apply_allowed"] is False
    assert handoff["activation_allowed"] is False
    assert history["active_revision_id"] == "return-mapping-r1"


def test_v139_rejected_authorization_cannot_build_mapping():
    result = build_authorized_replacement_mapping({
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REPLACEMENT_REJECTED",
        "decision": "REJECT",
        "mapping_build_allowed": False,
        "registry_save_allowed": False,
        "activation_allowed": False,
    })
    assert result["code"] == "PERIOD_PROFIT_MAPPING_REPLACEMENT_BUILD_AUTHORIZATION_REQUIRED"
    assert result["registry_save_allowed"] is False
    assert result["activation_allowed"] is False
