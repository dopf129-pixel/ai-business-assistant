from telegram_app_layer.seller_cost_telegram_adapter import SellerCostTelegramAdapter


class ReturnInventoryTelegramAdapter(SellerCostTelegramAdapter):
    """Add explicit local return-inventory confirmation to Telegram."""

    def __init__(
        self,
        assistant,
        keyboard_service,
        button_handler,
        user_profile_service=None,
        memory_command_service=None,
        seller_cost_service=None,
        return_inventory_service=None,
    ):
        super().__init__(
            assistant,
            keyboard_service,
            button_handler,
            user_profile_service,
            memory_command_service,
            seller_cost_service,
        )
        self.return_inventory_service = return_inventory_service

    def handle_text(self, text, user_id=None):
        if self.return_inventory_service is not None:
            profile_failure = self._admit_user_profile(user_id)
            if profile_failure:
                return profile_failure
            try:
                result = self.return_inventory_service.handle_text(user_id, text)
            except Exception:
                return self._failure("RETURN_INVENTORY_TEXT_FLOW_FAILED")
            if not isinstance(result, dict) or type(result.get("error")) is not bool:
                return self._failure("INVALID_RETURN_INVENTORY_TEXT_RESULT")
            if result.get("handled") is True:
                return result
            if result.get("handled") is not False:
                return self._failure("INVALID_RETURN_INVENTORY_TEXT_RESULT")

        return super().handle_text(text, user_id)

    def handle_button(self, callback, user_id=None):
        service = self.return_inventory_service
        if service is None:
            return super().handle_button(callback, user_id)

        profile_failure = self._admit_user_profile(user_id)
        if profile_failure:
            return profile_failure

        callback_text = str(callback or "")
        try:
            if callback_text == "return_inventory":
                self._clear_seller_cost(user_id)
                return service.open_menu(user_id)
            if callback_text.startswith("return_inventory_state:"):
                state = callback_text.split(":", 1)[1]
                return service.select_state(user_id, state)
            if callback_text == "return_inventory_confirm":
                return service.confirm(user_id)
            if callback_text == "return_inventory_cancel":
                return service.cancel(user_id)

            service.clear_pending(user_id)
        except Exception:
            return self._failure("RETURN_INVENTORY_BUTTON_FLOW_FAILED")

        return super().handle_button(callback, user_id)

    def _clear_seller_cost(self, user_id):
        service = self.seller_cost_service
        clearer = getattr(service, "clear_pending", None)
        if callable(clearer):
            clearer(user_id)

    @staticmethod
    def _failure(code):
        return {
            "error": True,
            "message": "RETURN_INVENTORY_FLOW_FAILED",
            "code": code,
            "read_only_ozon": True,
            "executed": False,
        }
