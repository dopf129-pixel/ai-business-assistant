import os

from period_profit_mapping_recovery_contract import (
    build_registry_migration_preview,
    build_registry_recovery_decision,
    build_registry_recovery_preview,
)


class PeriodProfitMappingRecoveryService:
    """Explicit recovery facade for corrupt registry files; never repairs automatically."""

    def __init__(self, registry_service):
        self.registry_service = registry_service

    def health(self):
        return self.registry_service.health()

    def preview_quarantine(self):
        return build_registry_recovery_preview(self.health(), "QUARANTINE")

    def decide(self, preview, decision):
        return build_registry_recovery_decision(preview, decision)

    def migration_preview(self, target_schema_version):
        return build_registry_migration_preview(self.health(), target_schema_version)

    def apply(self, decision):
        source = dict(decision or {})
        if (
            source.get("status") != "PERIOD_PROFIT_MAPPING_RECOVERY_DECISION_READY"
            or source.get("error") is not False
            or source.get("decision") != "APPLY"
            or source.get("recovery_apply_allowed") is not True
            or source.get("action") != "QUARANTINE"
        ):
            return _blocked("PERIOD_PROFIT_MAPPING_RECOVERY_EXPLICIT_APPLY_REQUIRED")

        health = self.health()
        if health.get("health_status") != "CORRUPT":
            return _blocked("PERIOD_PROFIT_MAPPING_RECOVERY_NOT_REQUIRED")

        path = self.registry_service.storage_path
        if not path or not os.path.exists(path):
            return _blocked("PERIOD_PROFIT_MAPPING_RECOVERY_SOURCE_NOT_FOUND")

        target = path + ".quarantine"
        suffix = 1
        while os.path.exists(target):
            suffix += 1
            target = path + f".quarantine.{suffix}"
        os.replace(path, target)
        after = self.health()
        return {
            "error": False,
            "status": "PERIOD_PROFIT_MAPPING_REGISTRY_QUARANTINED",
            "quarantine_path": target,
            "previous_health_status": "CORRUPT",
            "registry_health_status": after.get("health_status"),
            "load_allowed": after.get("load_allowed"),
            "writable": after.get("writable"),
            "explicit_apply": True,
            "automatic_repair_allowed": False,
            "ozon_mutation": False,
            "profit_adjustment_allowed": False,
            "executed": False,
        }


def _blocked(code):
    return {
        "error": True,
        "code": code,
        "status": "PERIOD_PROFIT_MAPPING_RECOVERY_APPLY_BLOCKED",
        "automatic_repair_allowed": False,
        "ozon_mutation": False,
        "profit_adjustment_allowed": False,
        "executed": False,
    }
