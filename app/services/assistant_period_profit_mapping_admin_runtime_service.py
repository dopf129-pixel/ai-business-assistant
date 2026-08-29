import re

from period_profit_mapping_admin_contract import (
    build_mapping_admin_decision,
    build_mapping_admin_preview,
)
from period_profit_mapping_admin_response import (
    build_period_profit_mapping_admin_response,
)


class AssistantPeriodProfitMappingAdminRuntimeService:
    """Explicit assistant route for period-profit mapping registry administration."""

    SCOPE_ALIASES = {
        "return": "RETURN",
        "returns": "RETURN",
        "возврат": "RETURN",
        "возвраты": "RETURN",
        "advertising": "ADVERTISING",
        "ads": "ADVERTISING",
        "реклама": "ADVERTISING",
        "storage": "STORAGE",
        "хранение": "STORAGE",
        "склад": "STORAGE",
    }

    def __init__(self, admin_service):
        self.admin_service = admin_service

    def handle_text(self, text):
        raw = str(text or "").strip()
        normalized = raw.lower()
        if not self._looks_like_admin_command(normalized):
            return None

        scope = self._parse_scope(normalized)
        if scope is None:
            return self._error("PERIOD_PROFIT_MAPPING_ADMIN_SCOPE_REQUIRED")

        history = self.admin_service.history(scope)
        if history.get("error"):
            return history

        if self._is_history_request(normalized):
            response = build_period_profit_mapping_admin_response(history)
            return self._wrap("ASSISTANT_PERIOD_PROFIT_MAPPING_HISTORY_READY", response, history=history)

        revision_id = self._parse_revision_id(normalized, scope)
        if revision_id is None:
            return self._error("PERIOD_PROFIT_MAPPING_ADMIN_REVISION_REQUIRED")

        action = "ROLLBACK" if ("rollback" in normalized or "откат" in normalized) else "ACTIVATE"
        preview = build_mapping_admin_preview(history, scope, action, revision_id)
        if preview.get("error"):
            return preview

        if self._has_reject_decision(normalized):
            decision = build_mapping_admin_decision(preview, "REJECT")
            return {
                "error": False,
                "status": "ASSISTANT_PERIOD_PROFIT_MAPPING_DECISION_READY",
                "preview": preview,
                "decision": decision,
                "text": "Изменение mapping отклонено; active revision не изменена.",
                "read_only": True,
                "executed": False,
            }

        if not self._has_apply_decision(normalized):
            response = build_period_profit_mapping_admin_response(preview, history)
            return self._wrap("ASSISTANT_PERIOD_PROFIT_MAPPING_PREVIEW_READY", response, preview=preview)

        decision = build_mapping_admin_decision(preview, "APPLY")
        applied = self.admin_service.apply(decision, actor="USER")
        if applied.get("error"):
            return applied
        audit_history = self.admin_service.history(scope)
        response = build_period_profit_mapping_admin_response(applied, audit_history)
        return self._wrap(
            "ASSISTANT_PERIOD_PROFIT_MAPPING_AUDIT_READY",
            response,
            preview=preview,
            decision=decision,
            applied=applied,
            history=audit_history,
        )

    def _looks_like_admin_command(self, text):
        return any(token in text for token in (
            "mapping", "маппинг", "revision", "ревиз", "rollback", "откат"
        ))

    def _parse_scope(self, text):
        for alias, scope in self.SCOPE_ALIASES.items():
            if alias in text:
                return scope
        return None

    def _parse_revision_id(self, text, scope):
        prefix = scope.lower()
        match = re.search(rf"{prefix}-mapping-r\d+", text)
        if match:
            return match.group(0)
        generic = re.search(r"(?:revision|ревиз(?:ия|ию|ии)?)[\s:#-]*(\d+)", text)
        if generic:
            return f"{prefix}-mapping-r{int(generic.group(1))}"
        return None

    def _is_history_request(self, text):
        return any(token in text for token in ("history", "история", "покажи", "список")) and not any(
            token in text for token in ("activate", "актив", "rollback", "откат", "apply", "примен")
        )

    def _has_apply_decision(self, text):
        return any(token in text for token in (" apply", "применить", "подтверждаю", "активировать"))

    def _has_reject_decision(self, text):
        return any(token in text for token in ("reject", "отклонить", "не применять"))

    def _wrap(self, status, response, **payload):
        if response.get("error"):
            return response
        result = {
            "error": False,
            "status": status,
            "text": response.get("text"),
            "read_only_business_data": True,
            "ozon_mutation": False,
            "profit_adjustment_allowed": False,
            "executed": False,
        }
        result.update(payload)
        return result

    def _error(self, code):
        return {
            "error": True,
            "code": code,
            "status": "ASSISTANT_PERIOD_PROFIT_MAPPING_ADMIN_UNAVAILABLE",
            "ozon_mutation": False,
            "profit_adjustment_allowed": False,
            "executed": False,
        }
