from period_profit_mapping_admin_contract import build_mapping_admin_preview


class PeriodProfitMappingAdminService:
    """Admin facade for reviewed registry changes; requires explicit APPLY decision."""

    def __init__(self, registry_service):
        self.registry_service = registry_service

    def history(self, scope):
        return self.registry_service.history(scope)

    def preview(self, scope, action, revision_id):
        history = self.registry_service.history(scope)
        return build_mapping_admin_preview(history, scope, action, revision_id)

    def apply(self, decision, actor="USER"):
        source = dict(decision or {})
        if (
            source.get("status") != "PERIOD_PROFIT_MAPPING_ADMIN_DECISION_READY"
            or source.get("error") is not False
            or source.get("decision") != "APPLY"
            or source.get("registry_apply_allowed") is not True
        ):
            return {
                "error": True,
                "code": "PERIOD_PROFIT_MAPPING_ADMIN_EXPLICIT_APPLY_REQUIRED",
                "status": "PERIOD_PROFIT_MAPPING_ADMIN_APPLY_BLOCKED",
                "ozon_mutation": False,
                "profit_adjustment_allowed": False,
                "executed": False,
            }

        action = source.get("action")
        if action == "ACTIVATE":
            result = self.registry_service.activate(
                source.get("scope"), source.get("target_revision_id"), actor=actor
            )
        elif action == "ROLLBACK":
            result = self.registry_service.rollback(
                source.get("scope"), source.get("target_revision_id"), actor=actor
            )
        else:
            return {
                "error": True,
                "code": "PERIOD_PROFIT_MAPPING_ADMIN_ACTION_INVALID",
                "status": "PERIOD_PROFIT_MAPPING_ADMIN_APPLY_BLOCKED",
                "ozon_mutation": False,
                "profit_adjustment_allowed": False,
                "executed": False,
            }

        if isinstance(result, dict):
            result = dict(result)
            result["admin_explicit_apply"] = True
            result["ozon_mutation"] = False
            result["profit_adjustment_allowed"] = False
        return result
