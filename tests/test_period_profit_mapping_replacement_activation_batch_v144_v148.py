from period_profit_mapping_admin_contract import build_mapping_admin_decision
from period_profit_mapping_replacement_activation import (
    apply_replacement_activation,
    build_replacement_activation_audit,
    build_replacement_activation_decision,
    build_replacement_canonical_activation_preview,
    verify_replacement_activation,
)
from period_profit_mapping_replacement_persistence import build_replacement_activation_handoff
from return_financial_operation_authorized_mapping import build_return_financial_operation_authorized_mapping
from services.period_profit_mapping_admin_service import PeriodProfitMappingAdminService
from services.period_profit_mapping_registry_service import PeriodProfitMappingRegistryService


def _mapping(name):
    return build_return_financial_operation_authorized_mapping({
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_SELECTION_AUTHORIZED",
        "mapping_authorized": True,
        "financial_evidence_mapping_allowed": True,
        "selected_operations": [{"type_id": 1, "name": name, "description": None, "source": "OZON_FINANCE_ACCRUAL_TYPES"}],
    })


def _setup(tmp_path):
    registry = PeriodProfitMappingRegistryService(str(tmp_path / "registry.json"), clock=lambda: "2026-08-29T21:00:00+00:00")
    admin = PeriodProfitMappingAdminService(registry)
    old = _mapping("Old")
    new = _mapping("New")
    registry.save("RETURN", old, activate=True)
    saved = registry.save("RETURN", new, activate=False)
    persisted = {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REPLACEMENT_INACTIVE_REVISION_SAVED",
        "scope": "RETURN",
        "revision_id": saved["revision_id"],
        "mapping_id": saved["mapping_id"],
        "active": False,
        "active_revision_id": "return-mapping-r1",
        "activation_handoff_required": True,
        "activation_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "executed": False,
    }
    handoff = build_replacement_activation_handoff(admin, persisted)
    return registry, admin, persisted, handoff


def test_v144_restores_existing_canonical_admin_preview(tmp_path):
    registry, admin, persisted, handoff = _setup(tmp_path)
    result = build_replacement_canonical_activation_preview(admin, handoff)
    assert result["status"] == "PERIOD_PROFIT_MAPPING_ADMIN_PREVIEW_READY"
    assert result["target_revision_id"] == persisted["revision_id"]
    assert result["automatic_apply_allowed"] is False
    assert registry.history("RETURN")["active_revision_id"] == "return-mapping-r1"


def test_v145_reject_reuses_existing_admin_decision_and_keeps_lineage(tmp_path):
    registry, admin, _, handoff = _setup(tmp_path)
    preview = build_replacement_canonical_activation_preview(admin, handoff)
    decision = build_replacement_activation_decision(preview, "REJECT")
    expected = build_mapping_admin_decision(preview, "REJECT")
    for key, value in expected.items():
        assert decision[key] == value
    assert decision["expected_current_active_revision_id"] == "return-mapping-r1"
    assert decision["registry_apply_allowed"] is False
    assert registry.history("RETURN")["active_revision_id"] == "return-mapping-r1"


def test_v146_requires_explicit_apply_and_activates_only_target(tmp_path):
    registry, admin, persisted, handoff = _setup(tmp_path)
    preview = build_replacement_canonical_activation_preview(admin, handoff)
    rejected = build_replacement_activation_decision(preview, "REJECT")
    blocked = apply_replacement_activation(admin, persisted, rejected)
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_REPLACEMENT_EXPLICIT_ACTIVATION_APPLY_REQUIRED"
    assert registry.history("RETURN")["active_revision_id"] == "return-mapping-r1"

    applied = build_replacement_activation_decision(preview, "APPLY")
    result = apply_replacement_activation(admin, persisted, applied, actor="HUMAN_REVIEWER")
    assert result["revision_id"] == persisted["revision_id"]
    assert result["admin_explicit_apply"] is True
    assert registry.history("RETURN")["active_revision_id"] == persisted["revision_id"]


def test_v146_stale_apply_decision_fails_closed(tmp_path):
    registry, admin, persisted, handoff = _setup(tmp_path)
    preview = build_replacement_canonical_activation_preview(admin, handoff)
    decision = build_replacement_activation_decision(preview, "APPLY")
    registry.activate("RETURN", persisted["revision_id"], actor="OTHER_REVIEWER")
    result = apply_replacement_activation(admin, persisted, decision)
    assert result["code"] == "PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_DECISION_STALE"


def test_v147_verifies_registry_and_activation_event(tmp_path):
    registry, admin, persisted, handoff = _setup(tmp_path)
    preview = build_replacement_canonical_activation_preview(admin, handoff)
    decision = build_replacement_activation_decision(preview, "APPLY")
    applied = apply_replacement_activation(admin, persisted, decision)
    result = verify_replacement_activation(registry, persisted, applied)
    assert result["registry_verified"] is True
    assert result["active_revision_id"] == persisted["revision_id"]
    assert result["activation_event_count"] >= 1
    assert result["profit_adjustment_allowed"] is False


def test_v148_builds_read_only_explicit_activation_audit(tmp_path):
    registry, admin, persisted, handoff = _setup(tmp_path)
    preview = build_replacement_canonical_activation_preview(admin, handoff)
    decision = build_replacement_activation_decision(preview, "APPLY")
    applied = apply_replacement_activation(admin, persisted, decision)
    verified = verify_replacement_activation(registry, persisted, applied)
    audit = build_replacement_activation_audit(verified, decision)
    assert audit["status"] == "PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_AUDIT_READY"
    assert audit["explicit_human_apply"] is True
    assert audit["automatic_activation"] is False
    assert audit["ozon_mutation"] is False
    assert audit["executed"] is False


def test_tampered_handoff_and_target_mismatch_fail_closed(tmp_path):
    _, admin, persisted, handoff = _setup(tmp_path)
    tampered = dict(handoff, target_mapping_id="other")
    result = build_replacement_canonical_activation_preview(admin, tampered)
    assert result["code"] == "PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_PREVIEW_STALE"

    preview = build_replacement_canonical_activation_preview(admin, handoff)
    decision = build_replacement_activation_decision(preview, "APPLY")
    wrong = dict(persisted, mapping_id="other")
    blocked = apply_replacement_activation(admin, wrong, decision)
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_REPLACEMENT_EXPLICIT_ACTIVATION_APPLY_REQUIRED"
