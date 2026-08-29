from period_profit_mapping_recovery_contract import (
    build_registry_migration_preview,
    build_registry_recovery_decision,
    build_registry_recovery_preview,
)
from services.assistant_period_profit_mapping_recovery_runtime_service import (
    AssistantPeriodProfitMappingRecoveryRuntimeService,
)
from services.period_profit_mapping_recovery_service import (
    PeriodProfitMappingRecoveryService,
)


class Registry:
    def __init__(self, path, health_status="CORRUPT"):
        self.storage_path = str(path)
        self.health_status = health_status

    def health(self):
        corrupt = self.health_status == "CORRUPT"
        return {
            "error": corrupt,
            "status": "PERIOD_PROFIT_MAPPING_REGISTRY_HEALTH_READY",
            "health_status": self.health_status,
            "schema_version": None if corrupt else 1,
            "load_allowed": not corrupt,
            "writable": not corrupt,
            "issues": ["REGISTRY_READ_ERROR:ValueError"] if corrupt else [],
            "scopes": {},
        }


def test_recovery_preview_requires_explicit_apply():
    preview = build_registry_recovery_preview(Registry("x").health())
    assert preview["explicit_decision_required"] is True
    assert preview["automatic_repair_allowed"] is False
    assert preview["registry_write_allowed"] is False


def test_reject_never_allows_recovery_apply():
    preview = build_registry_recovery_preview(Registry("x").health())
    decision = build_registry_recovery_decision(preview, "REJECT")
    assert decision["recovery_apply_allowed"] is False


def test_quarantine_moves_corrupt_file_only_after_apply(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text("{broken", encoding="utf-8")
    registry = Registry(path)
    service = PeriodProfitMappingRecoveryService(registry)
    preview = service.preview_quarantine()
    decision = service.decide(preview, "APPLY")
    result = service.apply(decision)
    assert result["status"] == "PERIOD_PROFIT_MAPPING_REGISTRY_QUARANTINED"
    assert not path.exists()
    assert (tmp_path / "registry.json.quarantine").exists()
    assert result["ozon_mutation"] is False
    assert result["profit_adjustment_allowed"] is False


def test_migration_preview_is_non_mutating_and_not_implemented():
    health = Registry("x", health_status="HEALTHY").health()
    preview = build_registry_migration_preview(health, 2)
    assert preview["migration_required"] is True
    assert preview["migration_implementation_available"] is False
    assert preview["migration_apply_allowed"] is False
    assert preview["automatic_migration_allowed"] is False


def test_assistant_health_route_is_read_only():
    service = PeriodProfitMappingRecoveryService(Registry("x"))
    runtime = AssistantPeriodProfitMappingRecoveryRuntimeService(service)
    result = runtime.handle_text("покажи здоровье mapping registry")
    assert result["status"] == "ASSISTANT_PERIOD_PROFIT_MAPPING_HEALTH_READY"
    assert result["automatic_repair_allowed"] is False
    assert result["ozon_mutation"] is False


def test_assistant_quarantine_without_apply_returns_preview():
    service = PeriodProfitMappingRecoveryService(Registry("x"))
    runtime = AssistantPeriodProfitMappingRecoveryRuntimeService(service)
    result = runtime.handle_text("mapping registry quarantine")
    assert result["status"] == "ASSISTANT_PERIOD_PROFIT_MAPPING_RECOVERY_PREVIEW_READY"
    assert "нужен отдельный явный APPLY" in result["text"]
