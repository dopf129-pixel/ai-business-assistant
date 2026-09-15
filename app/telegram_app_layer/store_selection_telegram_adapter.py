from telegram_app_layer.return_inventory_telegram_adapter import ReturnInventoryTelegramAdapter


class StoreSelectionTelegramAdapter(ReturnInventoryTelegramAdapter):
    """Select one seller account before entering existing store-local workflows."""

    def __init__(self, *args, account_service=None, **kwargs):
        if account_service is None and len(args) == 9:
            args = list(args)
            account_service = args.pop()
            args = tuple(args)
        super().__init__(*args, **kwargs)
        self.account_service = account_service
        self._pending_store_add = set()

    def handle_button(self, callback, user_id=None):
        value = str(callback or "")
        if value == "stores":
            self._pending_store_add.discard(str(user_id))
            result = self.account_service.list_accounts(user_id)
            buttons = [{"text": ("✅ " if row["active"] else "") + "Магазин " + str(index + 1) + " — " + row["client_id_masked"],
                        "callback": "store_select:" + row["client_id"]}
                       for index, row in enumerate(result.get("accounts", []))]
            buttons.append({"text": "➕ Добавить магазин", "callback": "store_add"})
            return {"error": False, "message": "Выберите магазин. Данные и себестоимость каждого магазина хранятся отдельно.",
                    "keyboard": {"error": False, "type": "inline_keyboard", "buttons": buttons}, "read_only_ozon": True}
        if value == "store_add":
            self._pending_store_add.add(str(user_id))
            return {"error": False, "message": "Отправьте CLIENT_ID и READ-ONLY API_KEY нового магазина одной строкой через пробел.", "read_only_ozon": True}
        if value.startswith("store_select:"):
            return self.account_service.select(user_id, value.split(":", 1)[1])
        return super().handle_button(callback, user_id)

    def handle_text(self, text, user_id=None):
        user_key = str(user_id)
        if user_key in self._pending_store_add:
            parts = str(text or "").strip().split(maxsplit=1)
            if len(parts) != 2:
                return {"error": False, "handled": True, "message": "Отправьте CLIENT_ID и API_KEY через пробел."}
            result = self.account_service.connect(user_id, parts[0], parts[1])
            if result.get("status") == "OZON_ACCOUNT_CONNECTED":
                self._pending_store_add.discard(user_key)
            result["handled"] = True
            return result
        return super().handle_text(text, user_id)
