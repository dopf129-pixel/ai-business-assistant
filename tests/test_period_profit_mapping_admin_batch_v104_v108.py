from period_profit_mapping_admin_contract import (
    build_mapping_admin_decision,
    build_mapping_admin_preview,
)
from period_profit_mapping_admin_response import build_period_profit_mapping_admin_response
from services.period_profit_mapping_admin_service import PeriodProfitMappingAdminService


class Registry:
    def __init__(self):
        self.calls = []

    def history(self, scope):
        return {
            "error": False,
            "status": "PERIOD_PROFIT_MAPPING_HISTORY_READY",
            "scope": scope,
            "active_revision_id": "return-mapping-r1",
            "revisions": [
                {"revision_id": "return-mapping-r1", "mapping_id": "m1"},
                {"revision_id": "return-mapping-r2", "mapping_id": "m2"},
            ],
            "events": [],
        }

    def activate(self, scope, revision_id, actor="USER"):
        self.calls.append(("activate", scope, revision_id, actor))
        return {
            "error": False,
            "status": "PERIOD_PROFIT_MAPPING_REVISION_ACTIVATED",
            "scope": scope,
            "revision_id": revision_id,
            "mapping_id": "m2",
            "profit_adjustment_allowed": False,
            "executed": False,
        }

    def rollback(self, scope, revision_id, actor="USER"):
        self.calls.append(("rollback", scope, revision_id, actor))
        return {
            "error": False,
            "status": "PERIOD_PROFIT_MAPPING_ROLLBACK_APPLIED",
            "scope": scope,
            "revision_id": revision_id,
            "mapping_id": "m1",
            "profit_adjustment_allowed": False,
            "executed": False,
        }


def test_preview_requires_separate_decision_and_does_not_apply():
    registry = Registry()
    service = PeriodProfitMappingAdminService(registry)
    preview = service.preview("RETURN", "ACTIVATE", "return-mapping-r2")
    assert preview["status"] == "PERIOD_PROFIT_MAPPING_ADMIN_PREVIEW_READY"
    assert preview["explicit_decision_required"] is True
    assert preview["automatic_apply_allowed"] is False
    assert registry.calls == []


def test_reject_blocks_registry_mutation():
    registry = Registry()
    service = PeriodProfitMappingAdminService(registry)
    preview = service.preview("RETURN", "ACTIVATE", "return-mapping-r2")
    decision = build_mapping_admin_decision(preview, "REJECT")
    result = service.apply(decision)
    assert result["code"] == "PERIOD_PROFIT_MAPPING_ADMIN_EXPLICIT_APPLY_REQUIRED"
    assert registry.calls == []


def test_apply_activation_is_explicit_and_profit_safe():
    registry = Registry()
    service = PeriodProfitMappingAdminService(registry)
    preview = service.preview("RETURN", "ACTIVATE", "return-mapping-r2")
    decision = build_mapping_admin_decision(preview, "APPLY")
    result = service.apply(decision, actor="USER")
    assert registry.calls == [("activate", "RETURN", "return-mapping-r2", "USER")]
    assert result["admin_explicit_apply"] is True
    assert result["ozon_mutation"] is False
    assert result["profit_adjustment_allowed"] is False


def test_rollback_preview_and_apply_preserve_same_safety():
    registry = Registry()
    service = PeriodProfitMappingAdminService(registry)
    preview = service.preview("RETURN", "ROLLBACK", "return-mapping-r1")
    decision = build_mapping_admin_decision(preview, "APPLY")
    result = service.apply(decision)
    assert registry.calls[0][0] == "rollback"
    assert result["status"] == "PERIOD_PROFIT_MAPPING_ROLLBACK_APPLIED"
    assert result["profit_adjustment_allowed"] is False


def test_audit_response_states_that_profit_and_ozon_are_unchanged():
    result = build_period_profit_mapping_admin_response({
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVISION_ACTIVATED",
        "scope": "RETURN",
        "revision_id": "return-mapping-r2",
        "mapping_id": "m2",
    })
    assert "Ozon и формула прибыли не изменялись" in result["text"]
    assert result["ozon_mutation"] is False
    assert result["profit_adjustment_allowed"] is False
