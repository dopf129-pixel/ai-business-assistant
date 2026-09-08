from telegram_app_layer.assistant_telegram_adapter import AssistantTelegramAdapter


class SellerCostTelegramAdapter(AssistantTelegramAdapter):
    """Add the explicit seller-cost interaction without changing other routes."""

    def __init__(
        self,
        assistant,
        keyboard_service,
        button_handler,
        user_profile_service=None,
        memory_command_service=None,
        seller_cost_service=None,
    ):
        super().__init__(
            assistant,
            keyboard_service,
            button_handler,
            user_profile_service,
            memory_command_service,
        )
        self.seller_cost_service = seller_cost_service

    def handle_text(self, text, user_id=None):
        if self.seller_cost_service is not None:
            profile_failure = self._admit_user_profile(user_id)
            if profile_failure:
                return profile_failure
            try:
                result = self.seller_cost_service.handle_text(user_id, text)
            except Exception:
                return {
                    "error": True,
                    "message": "SELLER_COST_TEXT_FLOW_FAILED",
                    "read_only_ozon": True,
                }
            if not isinstance(result, dict) or type(result.get("error")) is not bool:
                return {
                    "error": True,
                    "message": "INVALID_SELLER_COST_TEXT_RESULT",
                    "read_only_ozon": True,
                }
            if result.get("handled") is True:
                return result
            if result.get("handled") is not False:
                return {
                    "error": True,
                    "message": "INVALID_SELLER_COST_TEXT_RESULT",
                    "read_only_ozon": True,
                }
        return super().handle_text(text, user_id)

    def handle_button(self, callback, user_id=None):
        if self.seller_cost_service is None:
            return super().handle_button(callback, user_id)

        profile_failure = self._admit_user_profile(user_id)
        if profile_failure:
            return profile_failure

        callback_text = str(callback or "")
        try:
            if callback_text == "seller_cost":
                self.seller_cost_service.clear_pending(user_id)
                return self.seller_cost_service.open_menu()
            if callback_text.startswith("seller_cost:"):
                sku = callback_text.split(":", 1)[1]
                return self.seller_cost_service.select_sku(user_id, sku)
            self.seller_cost_service.clear_pending(user_id)
        except Exception:
            return {
                "error": True,
                "message": "SELLER_COST_BUTTON_FLOW_FAILED",
                "read_only_ozon": True,
            }

        return super().handle_button(callback, user_id)
