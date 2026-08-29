from period_profit_mapping_recovery_contract import (
    build_registry_recovery_decision,
)


class AssistantPeriodProfitMappingRecoveryRuntimeService:
    """Natural-language health/recovery route with explicit quarantine APPLY."""

    def __init__(self, recovery_service):
        self.recovery_service = recovery_service

    def handle_text(self, text):
        normalized = str(text or "").strip().lower()
        if not self._looks_like_recovery_command(normalized):
            return None

        if any(token in normalized for token in ("health", "здоров", "состояни")):
            health = self.recovery_service.health()
            return self._wrap(
                "ASSISTANT_PERIOD_PROFIT_MAPPING_HEALTH_READY",
                health,
                self._health_text(health),
            )

        if any(token in normalized for token in ("migration", "миграц", "schema", "схем")):
            target = 2 if "2" in normalized else None
            preview = self.recovery_service.migration_preview(target)
            if preview.get("error"):
                return preview
            text = (
                f"Migration preview: schema {preview.get('source_schema_version')} → "
                f"{preview.get('target_schema_version')}. Автоматическая миграция запрещена; "
                "реализация миграции пока недоступна."
            )
            return self._wrap("ASSISTANT_PERIOD_PROFIT_MAPPING_MIGRATION_PREVIEW_READY", preview, text)

        preview = self.recovery_service.preview_quarantine()
        if preview.get("error"):
            return preview

        if any(token in normalized for token in ("reject", "отклон", "не применять")):
            decision = build_registry_recovery_decision(preview, "REJECT")
            return self._wrap(
                "ASSISTANT_PERIOD_PROFIT_MAPPING_RECOVERY_DECISION_READY",
                decision,
                "Quarantine отклонён; registry-файл не изменён.",
            )

        if not any(token in normalized for token in ("apply", "примен", "подтверждаю")):
            text = (
                "Registry повреждён. Можно изолировать исходный файл в quarantine. "
                "Изменение ещё не применено; нужен отдельный явный APPLY."
            )
            return self._wrap("ASSISTANT_PERIOD_PROFIT_MAPPING_RECOVERY_PREVIEW_READY", preview, text)

        decision = build_registry_recovery_decision(preview, "APPLY")
        result = self.recovery_service.apply(decision)
        if result.get("error"):
            return result
        text = (
            "Повреждённый registry-файл перемещён в quarantine. "
            f"Текущее состояние registry: {result.get('registry_health_status')}. "
            "Ozon и формула прибыли не изменялись."
        )
        return self._wrap("ASSISTANT_PERIOD_PROFIT_MAPPING_RECOVERY_AUDIT_READY", result, text)

    def _looks_like_recovery_command(self, text):
        mapping = any(token in text for token in ("mapping", "маппинг", "registry", "реестр"))
        recovery = any(token in text for token in (
            "health", "здоров", "состояни", "recovery", "восстанов", "quarantine", "карантин",
            "migration", "миграц", "schema", "схем",
        ))
        return mapping and recovery

    def _health_text(self, health):
        issues = ", ".join(health.get("issues") or []) or "нет"
        return (
            f"Mapping registry: {health.get('health_status')}. "
            f"Load allowed: {health.get('load_allowed')}; writable: {health.get('writable')}. "
            f"Issues: {issues}."
        )

    def _wrap(self, status, payload, text):
        return {
            "error": False,
            "status": status,
            "payload": payload,
            "text": text,
            "read_only_business_data": True,
            "automatic_repair_allowed": False,
            "ozon_mutation": False,
            "profit_adjustment_allowed": False,
            "executed": False,
        }
