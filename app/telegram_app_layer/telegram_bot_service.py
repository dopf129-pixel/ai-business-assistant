from telegram_app_layer.telegram_call_compat import call_with_legacy_arity
from services.tenant_context import set_current_tenant_user_id, reset_current_tenant_user_id


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
        return self._with_tenant(user_id, lambda: self._on_message_in_tenant(user_id, text))

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
    def _with_tenant(user_id, function):
        scope = user_id
        try:
            from services.ozon_account_repository import OzonAccountRepository, make_store_tenant_scope
            client_id = OzonAccountRepository().active_client_id(user_id)
            if client_id:
                scope = make_store_tenant_scope(user_id, client_id)
        except Exception:
            scope = user_id
        token = set_current_tenant_user_id(scope)
        try:
            return function()
        finally:
            reset_current_tenant_user_id(token)
