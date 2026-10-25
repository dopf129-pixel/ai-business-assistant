import threading

from telegram_app_layer.telegram_call_compat import call_with_legacy_arity
from services.tenant_context import set_current_tenant_user_id, reset_current_tenant_user_id


_INFLIGHT_CALCULATION_LOCK = threading.Lock()
_INFLIGHT_CALCULATION_KEYS = set()


class TelegramBotService:
    def __init__(self, adapter, command_service=None):
        self.adapter = adapter
        self.command_service = command_service

    def on_start(self, user_id=None):
        return self._with_tenant(user_id, lambda: call_with_legacy_arity(self.adapter.get_start_response, (user_id,), ()))

    def on_message(self, user_id, text=None):
        if text is None:
            text = user_id
            user_id = None
        tenant_scope = self._resolve_tenant_scope(user_id) if user_id else None
        result = self._with_tenant(
            user_id,
            lambda: self._on_message_in_tenant(user_id, text),
            tenant_scope=tenant_scope,
        )
        if (
            user_id
            and isinstance(result, dict)
            and result.get("read_only") is True
            and self._resolve_tenant_scope(user_id) != tenant_scope
        ):
            return self._calculation_store_changed()
        return result

    def _on_message_in_tenant(self, user_id, text):
        if self.command_service:
            try:
                command_result = self.command_service.handle(user_id, text)
            except Exception:
                return {"error": True, "message": "TELEGRAM_COMMAND_DISPATCH_FAILED"}
            if command_result is not None:
                if not isinstance(command_result, dict) or type(command_result.get("error")) is not bool:
                    return {"error": True, "message": "INVALID_TELEGRAM_COMMAND_RESULT"}
                return command_result
        return call_with_legacy_arity(self.adapter.handle_text, (text, user_id), (text,))

    def on_document(self, user_id, content, filename=None):
        return self._with_tenant(user_id, lambda: self.adapter.handle_document(content, user_id, filename))

    def on_callback(self, user_id, callback=None):
        if callback is None:
            callback = user_id
            user_id = None
        if user_id and self._is_calculation_callback(callback):
            tenant_scope = self._resolve_tenant_scope(user_id)
            key = (str(tenant_scope or ""), str(callback or ""))
            with _INFLIGHT_CALCULATION_LOCK:
                if key in _INFLIGHT_CALCULATION_KEYS:
                    return {
                        "error": False,
                        "message": "Этот расчёт уже выполняется. Дождитесь ответа на первое нажатие.",
                        "code": "TELEGRAM_CALCULATION_ALREADY_RUNNING",
                        "read_only": True,
                        "executed": False,
                    }
                _INFLIGHT_CALCULATION_KEYS.add(key)
            try:
                result = self._with_tenant(
                    user_id,
                    lambda: self._on_callback_in_tenant(user_id, callback),
                    tenant_scope=tenant_scope,
                )
                if self._resolve_tenant_scope(user_id) != tenant_scope:
                    return self._calculation_store_changed()
                return result
            finally:
                with _INFLIGHT_CALCULATION_LOCK:
                    _INFLIGHT_CALCULATION_KEYS.discard(key)
        return self._with_tenant(user_id, lambda: self._on_callback_in_tenant(user_id, callback))

    def _on_callback_in_tenant(self, user_id, callback):
        if self.command_service and hasattr(self.command_service, "handle_callback"):
            try:
                result = self.command_service.handle_callback(user_id, callback)
            except Exception:
                return {"error": True, "message": "TELEGRAM_COMMAND_CALLBACK_FAILED"}
            if result is not None:
                return result
        return call_with_legacy_arity(self.adapter.handle_button, (callback, user_id), (callback,))

    @staticmethod
    def _is_calculation_callback(callback):
        parts = str(callback or "").strip().split(":")
        if len(parts) < 2:
            return False
        if parts[0] in {
            "period_profit",
            "period_profit_pre_cogs",
                "period_profit_refresh",
            "experimental_store_economics",
        }:
            return parts[1].strip().lower() != "custom"
        if parts[0] == "period_profit_sku" and len(parts) >= 3:
            return parts[2].strip().lower() != "custom"
        return False

    @staticmethod
    def _calculation_store_changed():
        return {
            "error": False,
            "status": "TELEGRAM_CALCULATION_STORE_CHANGED",
            "message": (
                "Активный магазин изменился во время расчёта. "
                "Результат старого магазина не показан; запустите расчёт "
                "ещё раз в текущем магазине."
            ),
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _resolve_tenant_scope(user_id):
        scope = user_id
        try:
            from services.ozon_account_repository import OzonAccountRepository, make_store_tenant_scope
            client_id = OzonAccountRepository().active_client_id(user_id)
            if client_id:
                scope = make_store_tenant_scope(user_id, client_id)
        except Exception:
            scope = user_id
        return scope

    @staticmethod
    def _with_tenant(user_id, function, tenant_scope=None):
        scope = (
            tenant_scope
            if tenant_scope is not None
            else TelegramBotService._resolve_tenant_scope(user_id)
        )
        token = set_current_tenant_user_id(scope)
        try:
            return function()
        finally:
            reset_current_tenant_user_id(token)
