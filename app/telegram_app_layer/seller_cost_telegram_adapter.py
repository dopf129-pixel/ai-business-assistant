from telegram_app_layer.assistant_telegram_adapter import AssistantTelegramAdapter
from telegram_app_layer.telegram_call_compat import call_with_legacy_arity


class SellerCostTelegramAdapter(AssistantTelegramAdapter):
    """Add the explicit seller-cost interaction without changing other routes."""

    def __init__(self, assistant, keyboard_service, button_handler, user_profile_service=None, memory_command_service=None, seller_cost_service=None, onboarding_service=None, fifo_history_service=None, fifo_rate_entry_service=None, fifo_late_entry_service=None, fifo_anchor_entry_service=None):
        super().__init__(assistant, keyboard_service, button_handler, user_profile_service, memory_command_service, onboarding_service)
        self.seller_cost_service = seller_cost_service
        self.fifo_history_service = fifo_history_service
        self.fifo_rate_entry_service = fifo_rate_entry_service
        self.fifo_late_entry_service = fifo_late_entry_service
        self.fifo_anchor_entry_service = fifo_anchor_entry_service

    def handle_text(self, text, user_id=None):
        if self.fifo_anchor_entry_service is not None:
            profile_failure = self._admit_user_profile(user_id)
            if profile_failure:
                return profile_failure
            try:
                result = self.fifo_anchor_entry_service.handle_text(user_id, text)
            except Exception:
                return {"error": True, "message": "FIFO_ANCHOR_TEXT_FLOW_FAILED", "read_only_ozon": True}
            if not isinstance(result, dict) or type(result.get("error")) is not bool:
                return {"error": True, "message": "INVALID_FIFO_ANCHOR_TEXT_RESULT", "read_only_ozon": True}
            if result.get("handled") is True:
                return result
            if result.get("handled") is not False:
                return {"error": True, "message": "INVALID_FIFO_ANCHOR_TEXT_RESULT", "read_only_ozon": True}
        if self.fifo_late_entry_service is not None:
            profile_failure = self._admit_user_profile(user_id)
            if profile_failure:
                return profile_failure
            try:
                result = self.fifo_late_entry_service.handle_text(user_id, text)
            except Exception:
                return {"error": True, "message": "FIFO_LATE_COST_TEXT_FLOW_FAILED", "read_only_ozon": True}
            if not isinstance(result, dict) or type(result.get("error")) is not bool:
                return {"error": True, "message": "INVALID_FIFO_LATE_COST_TEXT_RESULT", "read_only_ozon": True}
            if result.get("handled") is True:
                return result
            if result.get("handled") is not False:
                return {"error": True, "message": "INVALID_FIFO_LATE_COST_TEXT_RESULT", "read_only_ozon": True}
        if self.fifo_rate_entry_service is not None:
            profile_failure = self._admit_user_profile(user_id)
            if profile_failure:
                return profile_failure
            try:
                result = self.fifo_rate_entry_service.handle_text(user_id, text)
            except Exception:
                return {"error": True, "message": "FIFO_COST_TEXT_FLOW_FAILED", "read_only_ozon": True}
            if not isinstance(result, dict) or type(result.get("error")) is not bool:
                return {"error": True, "message": "INVALID_FIFO_COST_TEXT_RESULT", "read_only_ozon": True}
            if result.get("handled") is True:
                return result
            if result.get("handled") is not False:
                return {"error": True, "message": "INVALID_FIFO_COST_TEXT_RESULT", "read_only_ozon": True}
        if self.seller_cost_service is not None:
            profile_failure = self._admit_user_profile(user_id)
            if profile_failure:
                return profile_failure
            try:
                result = self.seller_cost_service.handle_text(user_id, text)
            except Exception:
                return {"error": True, "message": "SELLER_COST_TEXT_FLOW_FAILED", "read_only_ozon": True}
            if not isinstance(result, dict) or type(result.get("error")) is not bool:
                return {"error": True, "message": "INVALID_SELLER_COST_TEXT_RESULT", "read_only_ozon": True}
            if result.get("handled") is True:
                return result
            if result.get("handled") is not False:
                return {"error": True, "message": "INVALID_SELLER_COST_TEXT_RESULT", "read_only_ozon": True}
        return super().handle_text(text, user_id)

    def handle_document(self, content, user_id=None, filename=None):
        if self.seller_cost_service is None:
            return {"error": True, "message": "Загрузка себестоимости недоступна.", "read_only_ozon": True}
        profile_failure = self._admit_user_profile(user_id)
        if profile_failure:
            return profile_failure
        if filename and not str(filename).lower().endswith(".csv"):
            return {"error": True, "message": "Отправьте CSV-файл, который выдал бот.", "code": "SELLER_COST_TABLE_FILE_TYPE_INVALID", "read_only_ozon": True}
        try:
            return self.seller_cost_service.import_table_for_user(
                user_id, content, filename=filename,
            )
        except Exception:
            return {"error": True, "message": "Не удалось импортировать таблицу. Изменений не применено.", "code": "SELLER_COST_TABLE_IMPORT_FAILED", "read_only_ozon": True}

    def handle_button(self, callback, user_id=None):
        self._clear_unit_price_calculator_for_navigation(callback, user_id)
        if (
            self.seller_cost_service is None
            and self.fifo_history_service is None
            and self.fifo_rate_entry_service is None
            and self.fifo_late_entry_service is None
            and self.fifo_anchor_entry_service is None
        ):
            return super().handle_button(callback, user_id)
        profile_failure = self._admit_user_profile(user_id)
        if profile_failure:
            return profile_failure
        callback_text = str(callback or "")
        try:
            if callback_text.startswith("fifo_anchor:") and self.fifo_anchor_entry_service is not None:
                return self.fifo_anchor_entry_service.handle_callback(
                    user_id, callback_text,
                )
            if callback_text == "seller_cost":
                self.seller_cost_service.clear_pending(user_id)
                if self.fifo_rate_entry_service is not None:
                    self.fifo_rate_entry_service.clear_pending(user_id)
                if self.fifo_late_entry_service is not None:
                    self.fifo_late_entry_service.clear_pending(user_id)
                if self.fifo_anchor_entry_service is not None:
                    self.fifo_anchor_entry_service.clear_pending(user_id)
                return call_with_legacy_arity(
                    self.seller_cost_service.open_menu,
                    (user_id,),
                    (),
                )
            if callback_text.startswith("seller_cost_fifo_page:"):
                page_text = callback_text.split(":", 1)[1]
                if (
                    not page_text.isascii()
                    or not page_text.isdecimal()
                    or str(int(page_text)) != page_text
                ):
                    return {
                        "error": True,
                        "message": "Страница списка FIFO устарела. Откройте себестоимость заново.",
                        "code": "SELLER_COST_FIFO_PAGE_INVALID",
                        "read_only_ozon": True,
                    }
                self.seller_cost_service.clear_pending(user_id)
                if self.fifo_rate_entry_service is not None:
                    self.fifo_rate_entry_service.clear_pending(user_id)
                if self.fifo_late_entry_service is not None:
                    self.fifo_late_entry_service.clear_pending(user_id)
                if self.fifo_anchor_entry_service is not None:
                    self.fifo_anchor_entry_service.clear_pending(user_id)
                return self.seller_cost_service.open_menu(
                    user_id,
                    fifo_page=int(page_text),
                )
            if callback_text == "seller_cost_table":
                self.seller_cost_service.clear_pending(user_id)
                if self.fifo_rate_entry_service is not None:
                    self.fifo_rate_entry_service.clear_pending(user_id)
                if self.fifo_late_entry_service is not None:
                    self.fifo_late_entry_service.clear_pending(user_id)
                if self.fifo_anchor_entry_service is not None:
                    self.fifo_anchor_entry_service.clear_pending(user_id)
                return self.seller_cost_service.export_table()
            if callback_text == "seller_cost_history_export":
                return self.seller_cost_service.export_history_table()
            if callback_text.startswith("seller_cost_return:"):
                token = callback_text.split(":", 1)[1]
                resolver = getattr(
                    self.button_handler,
                    "consume_seller_cost_return_callback",
                    None,
                )
                if not callable(resolver):
                    return {
                        "error": True,
                        "handled": True,
                        "code": "SELLER_COST_ENTRY_STALE",
                        "message": "Кнопка устарела. Откройте SKU заново.",
                        "read_only_ozon": True,
                    }
                resolved = resolver(user_id, token)
                if not isinstance(resolved, dict) or resolved.get("error") is not False:
                    return resolved if isinstance(resolved, dict) else {
                        "error": True,
                        "handled": True,
                        "code": "SELLER_COST_ENTRY_STALE",
                        "message": "Кнопка устарела. Откройте SKU заново.",
                        "read_only_ozon": True,
                    }
                sku = str(resolved.get("sku") or "")
                if not sku:
                    return {
                        "error": True,
                        "handled": True,
                        "code": "SELLER_COST_ENTRY_STALE",
                        "message": "Кнопка устарела. Откройте SKU заново.",
                        "read_only_ozon": True,
                    }
                return self.seller_cost_service.select_sku(
                    user_id, sku, return_to_unit_economics=True,
                )
            if callback_text.startswith("seller_cost_resume_unit:"):
                token = callback_text.split(":", 1)[1]
                resume = self.seller_cost_service.consume_unit_economics_return(
                    user_id, token,
                )
                if not isinstance(resume, dict) or resume.get("error") is not False:
                    return resume if isinstance(resume, dict) else {
                        "error": True,
                        "message": "Возврат к юнит-экономике устарел. Откройте SKU заново.",
                        "read_only_ozon": True,
                    }
                sku = str(resume.get("sku") or "")
                if not sku:
                    return {
                        "error": True,
                        "message": "SKU для возврата недоступен. Откройте карточку заново.",
                        "read_only_ozon": True,
                    }
                refresher = getattr(
                    self.button_handler, "refresh_unit_economics", None,
                )
                if callable(refresher):
                    return refresher(sku, user_id=user_id)
                return super().handle_button("unit_economics:" + sku, user_id)
            if callback_text.startswith("fifo_history:") and self.fifo_history_service is not None:
                result = self.fifo_history_service.handle_callback(user_id, callback_text)
                if not isinstance(result, dict) or type(result.get("error")) is not bool:
                    return {"error": True, "message": "INVALID_FIFO_HISTORY_RESULT", "read_only_ozon": True}
                if result.get("error") is not False or result.get("handled") is not True:
                    return result
                self.clear_unit_price_calculator_state(user_id)
                self._clear_seller_cost_and_fifo_pending(user_id)
                if result.get("action") == "start_new_rate" and self.fifo_rate_entry_service is not None:
                    return self.fifo_rate_entry_service.start(
                        user_id,
                        result.get("identity"),
                        result.get("display_name"),
                        result.get("expected_revision"),
                    )
                if result.get("action") == "start_initial_anchor" and self.fifo_anchor_entry_service is not None:
                    return self.fifo_anchor_entry_service.start(
                        user_id,
                        result.get("identity"),
                        result.get("display_name"),
                        result.get("expected_revision"),
                    )
                if result.get("action") == "start_initial_zero_rate" and self.fifo_rate_entry_service is not None:
                    return self.fifo_rate_entry_service.start_initial_zero_stock(
                        user_id,
                        result.get("identity"),
                        result.get("display_name"),
                        result.get("expected_revision"),
                    )
                if result.get("action") == "start_late_entry" and self.fifo_late_entry_service is not None:
                    return self.fifo_late_entry_service.start(
                        user_id,
                        result.get("identity"),
                        result.get("display_name"),
                        result.get("expected_revision"),
                    )
                return result
            if callback_text.startswith("fifo_late:") and self.fifo_late_entry_service is not None:
                return self.fifo_late_entry_service.handle_callback(user_id, callback_text)
            if callback_text.startswith("fifo_rate:") and self.fifo_rate_entry_service is not None:
                return self.fifo_rate_entry_service.handle_callback(user_id, callback_text)
            if callback_text.startswith("seller_cost:"):
                if self.fifo_rate_entry_service is not None:
                    self.fifo_rate_entry_service.clear_pending(user_id)
                if self.fifo_late_entry_service is not None:
                    self.fifo_late_entry_service.clear_pending(user_id)
                if self.fifo_anchor_entry_service is not None:
                    self.fifo_anchor_entry_service.clear_pending(user_id)
                sku = callback_text.split(":", 1)[1]
                return self.seller_cost_service.select_sku(user_id, sku)
            if self.seller_cost_service.is_confirmation_callback(callback_text):
                return self.seller_cost_service.handle_button(user_id, callback_text)
            self.seller_cost_service.clear_pending(user_id)
            if self.fifo_rate_entry_service is not None:
                self.fifo_rate_entry_service.clear_pending(user_id)
            if self.fifo_late_entry_service is not None:
                self.fifo_late_entry_service.clear_pending(user_id)
            if self.fifo_anchor_entry_service is not None:
                self.fifo_anchor_entry_service.clear_pending(user_id)
        except Exception:
            return {"error": True, "message": "SELLER_COST_BUTTON_FLOW_FAILED", "read_only_ozon": True}
        return super().handle_button(callback, user_id)

    def _clear_seller_cost_and_fifo_pending(self, user_id):
        for service in (
            self.seller_cost_service,
            self.fifo_rate_entry_service,
            self.fifo_late_entry_service,
            self.fifo_anchor_entry_service,
        ):
            clearer = getattr(service, "clear_pending", None)
            if callable(clearer):
                clearer(user_id)
