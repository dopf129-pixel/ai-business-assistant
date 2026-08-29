from services.assistant_period_profit_mapping_admin_runtime_service import (
    AssistantPeriodProfitMappingAdminRuntimeService,
)


class AdminService:
    def __init__(self):
        self.applied = []

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

    def apply(self, decision, actor="USER"):
        self.applied.append((decision, actor))
        return {
            "error": False,
            "status": "PERIOD_PROFIT_MAPPING_REVISION_ACTIVATED",
            "scope": decision["scope"],
            "revision_id": decision["target_revision_id"],
            "mapping_id": decision["target_mapping_id"],
            "ozon_mutation": False,
            "profit_adjustment_allowed": False,
            "executed": False,
        }


def test_history_route_is_read_only():
    admin = AdminService()
    runtime = AssistantPeriodProfitMappingAdminRuntimeService(admin)
    result = runtime.handle_text("покажи историю mapping возвратов")
    assert result["status"] == "ASSISTANT_PERIOD_PROFIT_MAPPING_HISTORY_READY"
    assert admin.applied == []


def test_revision_command_without_apply_only_previews():
    admin = AdminService()
    runtime = AssistantPeriodProfitMappingAdminRuntimeService(admin)
    result = runtime.handle_text("mapping возвраты revision 2")
    assert result["status"] == "ASSISTANT_PERIOD_PROFIT_MAPPING_PREVIEW_READY"
    assert result["preview"]["target_revision_id"] == "return-mapping-r2"
    assert admin.applied == []


def test_explicit_apply_can_switch_registry_revision_only():
    admin = AdminService()
    runtime = AssistantPeriodProfitMappingAdminRuntimeService(admin)
    result = runtime.handle_text("mapping возвраты revision 2 применить")
    assert result["status"] == "ASSISTANT_PERIOD_PROFIT_MAPPING_AUDIT_READY"
    assert len(admin.applied) == 1
    assert result["ozon_mutation"] is False
    assert result["profit_adjustment_allowed"] is False
    assert result["executed"] is False


def test_reject_never_calls_apply():
    admin = AdminService()
    runtime = AssistantPeriodProfitMappingAdminRuntimeService(admin)
    result = runtime.handle_text("mapping возвраты revision 2 отклонить")
    assert result["decision"]["decision"] == "REJECT"
    assert admin.applied == []


def test_unrelated_text_does_not_intercept():
    runtime = AssistantPeriodProfitMappingAdminRuntimeService(AdminService())
    assert runtime.handle_text("сколько я заработал за 7 дней") is None
