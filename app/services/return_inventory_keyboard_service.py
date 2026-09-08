from services.assistant_keyboard_service import AssistantKeyboardService


class ReturnInventoryKeyboardService(AssistantKeyboardService):
    """Expose the local return-inventory evidence flow on the main keyboard."""

    def build_main_keyboard(self):
        result = super().build_main_keyboard()
        if not isinstance(result, dict) or result.get("error") is not False:
            return result

        buttons = result.get("buttons")
        if not isinstance(buttons, list):
            return {
                "error": True,
                "type": "inline_keyboard",
                "buttons": [],
            }

        output = dict(result)
        output["buttons"] = list(buttons) + [
            {
                "text": "↩️ Состояние возврата",
                "callback": "return_inventory",
            }
        ]
        return output
