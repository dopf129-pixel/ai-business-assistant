from telegram_app_layer.telegram_call_compat import call_with_legacy_arity
from services.tenant_context import (
    set_current_tenant_user_id,
    reset_current_tenant_user_id,
    set_current_tenant_store_id, reset_current_tenant_store_id,
)


class TelegramBotService:
    def __init__(self, adapter, command_service=None, store_resolver=None):
        self.adapter = adapter
        self.command_service = command_service
        self.store_resolver = store_resolver

    def on_start(self, user_id=None):
        return self._with_tenant(
            user_id,
            lambda: call_with_legacy_arity(
                self.adapter.get_start_response,
                (user_id,),
                (),
            ),
        )

    def on_message(self, user_id, text=None):
        if text is None:
            text = user_id
            user_id = None

        return self._with_tenant(
            user_id,
            lambda: self._on_message_in_tenant(user_id, text),
        )

    def _on_message_in_tenant(self, user_id, text):
        if self.command_service:
            try:
                command_result = self.command_service.handle(user_id, text)
            except Exception:
                return {
                    "error": True,
                    "message": "TELEGRAM_COMMAND_DISPATCH_FAILED",
                }

            if command_result is not None:
                if (
                    not isinstance(command_result, dict)
                    or type(command_result.get("error")) is not bool
                ):
                    return {
                        "error": True,
                        "message": "INVALID_TELEGRAM_COMMAND_RESULT",
                    }
                return command_result

        return call_with_legacy_arity(
            self.adapter.handle_text,
            (text, user_id),
            (text,),
        )

    def on_callback(self, user_id, callback=None):
        if callback is None:
            callback = user_id
            user_id = None

        return self._with_tenant(
            user_id,
            lambda: call_with_legacy_arity(
                self.adapter.handle_button,
                (callback, user_id),
                (callback,),
            ),
        )

    def _with_tenant(self, user_id, function):
        token = set_current_tenant_user_id(user_id)
        store_token = set_current_tenant_store_id(None)
        try:
            resolver = getattr(self, "store_resolver", None)
            if callable(resolver) and user_id is not None:
                reset_current_tenant_store_id(store_token)
                store_token = set_current_tenant_store_id(resolver(user_id))
            return function()
        finally:
            reset_current_tenant_store_id(store_token)
            reset_current_tenant_user_id(token)
