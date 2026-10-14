from datetime import date, datetime, timedelta
from math import isfinite
from threading import RLock
from uuid import uuid4

from services.seller_cost_table_service import SellerCostTableService


class TelegramSellerCostUpdateService:
    """Guided seller-cost setup without mutating Ozon."""

    INITIAL_HISTORY_DATE = date.min
    CONFIRM_DATE_CALLBACK = "seller_cost_confirm_date"
    SELECT_ALL_HISTORY_CALLBACK = "seller_cost_select_all_history"
    CONFIRM_ALL_HISTORY_CALLBACK = "seller_cost_confirm_all_history"
    CANCEL_CALLBACK = "seller_cost_cancel"
    TABLE_CONFIRM_CALLBACK = "seller_cost_table_confirm"
    TABLE_SELECT_ALL_HISTORY_CALLBACK = "seller_cost_table_select_all_history"
    TABLE_CONFIRM_ALL_HISTORY_CALLBACK = "seller_cost_table_confirm_all_history"

    def __init__(self, product_service, cost_service, date_provider=None, table_service=None, store_name_provider=None):
        self.product_service = product_service
        self.cost_service = cost_service
        self.date_provider = date_provider or date.today
        self.table_service = table_service or SellerCostTableService(
            product_service, cost_service, date_provider=self.date_provider
        )
        self.store_name_provider = store_name_provider
        self._pending = {}
        self._pending_lock = RLock()

    def open_menu(self):
        products = self._products()
        if isinstance(products, dict):
            return products
        costs = self._current_costs()
        missing = [item for item in products if item[1] not in costs]
        configured = len(products) - len(missing)
        if missing:
            shown = missing[:19]
            message = (
                "💰 Себестоимость товаров\n\n"
                f"Себестоимость указана для {configured} из {len(products)} товаров.\n\n"
                "Заполнять весь каталог не обязательно. Выберите только те SKU, по которым хотите считать прибыль. "
                "После сохранения можно сразу открыть прибыль по этому товару. "
                "Для массового заполнения можно скачать таблицу. "
                "Для первого ввода бот предложит дату действия; применение ко всей истории потребует отдельного подтверждения."
            )
            buttons = [{"text": "📥 Заполнить таблицей", "callback": "seller_cost_table"}]
            buttons += [{"text": name, "callback": "seller_cost:" + sku} for name, sku, _, _ in shown]
            if len(missing) > len(shown):
                message += f"\n\nПоказаны первые {len(shown)} позиций."
        else:
            message = (
                "✅ Себестоимость заполнена для всех товаров каталога.\n\n"
                "Теперь Period Profit сможет использовать подтверждённые значения. "
                "Если придёт новая партия по другой цене — выберите товар ниже и обновите стоимость."
            )
            buttons = [{"text": name, "callback": "seller_cost:" + sku} for name, sku, _, _ in products[:20]]
        return {"error": False, "message": message, "cost_coverage": {"configured": configured, "total": len(products), "missing": len(missing)}, "keyboard": {"error": False, "type": "inline_keyboard", "buttons": buttons}, "read_only_ozon": True}

    def export_table(self):
        return self.table_service.export_csv()

    def import_table(self, content):
        return self.import_table_for_user(None, content)

    def import_table_for_user(self, user_id, content):
        user_key = self._user_key(user_id)
        if user_key is None:
            return self._error("SELLER_COST_TABLE_USER_REQUIRED")
        prepared = self.table_service.import_csv(content)
        if not isinstance(prepared, dict) or prepared.get("error") is not False:
            return prepared if isinstance(prepared, dict) else self._error("SELLER_COST_TABLE_INVALID")
        pending = {
            "draft_id": uuid4().hex[:16],
            "step": "confirm_table",
            "table_rows": prepared["rows"],
            "tenant_scope": self._tenant_scope(),
            "store_label": self._active_store_label(),
            "initial_count": prepared["initial_count"],
            "existing_count": prepared["existing_count"],
            "all_history_allowed": prepared["all_history_allowed"],
        }
        with self._pending_lock:
            self._pending[user_key] = pending
        return {
            "error": False,
            "message": self._table_confirmation_message(pending),
            "keyboard": self._table_confirmation_keyboard(pending),
            "seller_cost_confirmation_pending": True,
            "imported": len(pending["table_rows"]),
            "read_only_ozon": True,
        }

    def select_sku(self, user_id, sku):
        user_key = self._user_key(user_id)
        sku_key = self._text(sku)
        if user_key is None or not sku_key:
            return self._error("SELLER_COST_SELECTION_INVALID")
        products = self._products()
        if isinstance(products, dict):
            return products
        matches = [item for item in products if item[1] == sku_key]
        if len(matches) != 1:
            return self._error("SELLER_COST_SKU_NOT_FOUND" if not matches else "SELLER_COST_SKU_AMBIGUOUS")
        display_name, _, product_id, offer_id = matches[0]
        is_initial = sku_key not in self._current_costs()
        pending = {
            "draft_id": uuid4().hex[:16],
            "product_id": product_id,
            "sku": sku_key,
            "offer_id": offer_id,
            "display_name": display_name,
            "initial": is_initial,
            "step": "awaiting_cost",
            "tenant_scope": self._tenant_scope(),
            "store_label": self._active_store_label(),
        }
        with self._pending_lock:
            self._pending[user_key] = pending
        timing = (
            "Это первая себестоимость товара. После ввода суммы я предложу дату начала действия. "
            "Старые периоды останутся без подтверждённой себестоимости, пока вы отдельно не выберете всю историю."
            if is_initial
            else "Новая цена будет предложена со следующего дня, чтобы не менять уже рассчитанный сегодняшний день."
        )
        return {
            "error": False,
            "message": (
                f"{display_name}\nSKU: {sku_key}\n\n"
                "Введите себестоимость одной штуки в ₽. Например: 430\n\n"
                f"{timing}"
            ),
            "seller_cost_input_pending": True,
            "read_only_ozon": True,
        }

    def handle_text(self, user_id, text):
        with self._pending_lock:
            return self._handle_text_locked(user_id, text)

    def _handle_text_locked(self, user_id, text):
        user_key = self._user_key(user_id)
        if user_key is None or user_key not in self._pending:
            return {"error": False, "handled": False, "read_only_ozon": True}
        pending = self._pending[user_key]
        if not self._pending_store_is_current(pending):
            self._pending.pop(user_key, None)
            return self._stale_store_result()
        if pending.get("step") != "awaiting_cost":
            if pending.get("step", "").startswith("confirm_table"):
                if pending.get("step") == "confirm_table_all_history":
                    message = self._table_all_history_confirmation_message(pending)
                    keyboard = {
                        "error": False,
                        "type": "inline_keyboard",
                        "buttons": [
                            {"text": "Подтвердить для всей истории", "callback": self.TABLE_CONFIRM_ALL_HISTORY_CALLBACK},
                            {"text": "Отмена", "callback": self.CANCEL_CALLBACK},
                        ],
                    }
                else:
                    message = "Таблица пока не сохранена. Проверьте строки и подтвердите действие кнопкой либо отмените импорт."
                    keyboard = self._table_confirmation_keyboard(pending)
                return {
                    "error": False,
                    "handled": True,
                    "message": message,
                    "keyboard": keyboard,
                    "read_only_ozon": True,
                }
            confirmation = self._date_confirmation(pending)
            return {
                "error": False,
                "handled": True,
                "message": "Проверьте выбранный период и подтвердите действие кнопкой.",
                "keyboard": confirmation["keyboard"],
                "read_only_ozon": True,
            }
        cost = self._cost(text)
        if cost is None:
            return {"error": False, "handled": True, "message": "Не удалось распознать сумму. Отправьте только число в рублях, например: 430 или 430.50", "seller_cost_input_pending": True, "read_only_ozon": True}
        today = self._today()
        if today is None:
            return {"error": True, "handled": True, "message": "Не удалось определить дату активации себестоимости.", "code": "SELLER_COST_EFFECTIVE_DATE_UNAVAILABLE", "read_only_ozon": True}
        identity = dict(pending)
        effective_from = today if identity.get("initial") else today + timedelta(days=1)
        identity.update(
            {
                "cost_price": cost,
                "effective_from": effective_from.isoformat(),
                "step": "confirm_date",
            }
        )
        self._pending[user_key] = identity
        confirmation = self._date_confirmation(identity)
        return {
            "error": False,
            "handled": True,
            "message": self._date_confirmation_message(identity),
            "keyboard": confirmation["keyboard"],
            "sku": identity["sku"],
            "offer_id": identity["offer_id"],
            "cost_price": round(cost, 2),
            "effective_from": identity["effective_from"],
            "seller_cost_confirmation_pending": True,
            "read_only_ozon": True,
        }

    def handle_button(self, user_id, callback):
        with self._pending_lock:
            return self._handle_button_locked(user_id, callback)

    def _handle_button_locked(self, user_id, callback):
        user_key = self._user_key(user_id)
        callback_text = self._text(callback)
        action, separator, draft_id = callback_text.rpartition(":")
        if not separator:
            action = callback_text
            draft_id = ""
        callbacks = {
            self.CONFIRM_DATE_CALLBACK,
            self.SELECT_ALL_HISTORY_CALLBACK,
            self.CONFIRM_ALL_HISTORY_CALLBACK,
            self.CANCEL_CALLBACK,
            self.TABLE_CONFIRM_CALLBACK,
            self.TABLE_SELECT_ALL_HISTORY_CALLBACK,
            self.TABLE_CONFIRM_ALL_HISTORY_CALLBACK,
        }
        if action not in callbacks:
            return {"error": False, "handled": False, "read_only_ozon": True}
        if user_key is None or user_key not in self._pending:
            return self._pending_action_unavailable()
        pending = self._pending[user_key]
        if not draft_id or draft_id != pending.get("draft_id"):
            return self._pending_action_unavailable()
        if not self._pending_store_is_current(pending):
            self._pending.pop(user_key, None)
            return self._stale_store_result()
        if action == self.CANCEL_CALLBACK:
            self._pending.pop(user_key, None)
            return {
                "error": False,
                "handled": True,
                "message": "Изменение себестоимости отменено. Данные не записаны.",
                "read_only_ozon": True,
            }
        if action == self.TABLE_SELECT_ALL_HISTORY_CALLBACK:
            if (
                pending.get("step") != "confirm_table"
                or pending.get("all_history_allowed") is not True
            ):
                return self._pending_action_unavailable()
            pending["step"] = "confirm_table_all_history"
            self._pending[user_key] = pending
            return {
                "error": False,
                "handled": True,
                "message": self._table_all_history_confirmation_message(pending),
                "keyboard": {
                    "error": False,
                    "type": "inline_keyboard",
                    "buttons": [
                        {"text": "Подтвердить для всей истории", "callback": self._draft_callback(self.TABLE_CONFIRM_ALL_HISTORY_CALLBACK, pending)},
                        {"text": "Отмена", "callback": self._draft_callback(self.CANCEL_CALLBACK, pending)},
                    ],
                },
                "read_only_ozon": True,
            }
        if action == self.TABLE_CONFIRM_CALLBACK:
            if pending.get("step") != "confirm_table":
                return self._pending_action_unavailable()
            return self._save_pending_table(user_key, pending, whole_history=False)
        if action == self.TABLE_CONFIRM_ALL_HISTORY_CALLBACK:
            if pending.get("step") != "confirm_table_all_history":
                return self._pending_action_unavailable()
            return self._save_pending_table(user_key, pending, whole_history=True)
        if action == self.SELECT_ALL_HISTORY_CALLBACK:
            if pending.get("initial") is not True or pending.get("step") != "confirm_date":
                return self._pending_action_unavailable()
            pending["step"] = "confirm_all_history"
            self._pending[user_key] = pending
            return {
                "error": False,
                "handled": True,
                "message": self._all_history_confirmation_message(pending),
                "keyboard": {
                    "error": False,
                    "type": "inline_keyboard",
                    "buttons": [
                        {"text": "Подтвердить для всей истории", "callback": self._draft_callback(self.CONFIRM_ALL_HISTORY_CALLBACK, pending)},
                        {"text": "Отмена", "callback": self._draft_callback(self.CANCEL_CALLBACK, pending)},
                    ],
                },
                "read_only_ozon": True,
            }
        if action == self.CONFIRM_DATE_CALLBACK:
            if pending.get("step") != "confirm_date":
                return self._pending_action_unavailable()
            return self._save_pending_cost(user_key, pending, whole_history=False)
        if action == self.CONFIRM_ALL_HISTORY_CALLBACK:
            if pending.get("step") != "confirm_all_history":
                return self._pending_action_unavailable()
            return self._save_pending_cost(user_key, pending, whole_history=True)
        return self._pending_action_unavailable()

    def _save_pending_table(self, user_key, pending, whole_history):
        result = self.table_service.commit_import(
            pending.get("table_rows"), whole_history=whole_history
        )
        if not isinstance(result, dict) or result.get("error") is not False:
            return {
                "error": True,
                "handled": True,
                "message": result.get("message") if isinstance(result, dict) else "Таблица не сохранена; изменений не применено.",
                "code": result.get("code") if isinstance(result, dict) else "SELLER_COST_TABLE_IMPORT_FAILED",
                "read_only_ozon": True,
            }
        self._pending.pop(user_key, None)
        menu = self.open_menu()
        response = dict(result)
        response["handled"] = True
        response["message"] = (
            f"Магазин: {pending['store_label']}\n{result.get('message', '')}"
        )
        if isinstance(menu, dict) and menu.get("error") is False:
            response["cost_coverage"] = menu.get("cost_coverage")
            response["keyboard"] = menu.get("keyboard")
        return response

    @classmethod
    def _table_confirmation_message(cls, pending):
        rows = pending.get("table_rows") or []
        lines = [
            "Проверьте CSV перед сохранением:",
            f"Магазин: {pending['store_label']}",
            f"Позиций: {len(rows)}; новых: {pending['initial_count']}; с изменением цены: {pending['existing_count']}",
        ]
        for row in rows[:12]:
            lines.append(
                f"• SKU {row['sku']} ({row['offer_id'] or 'без артикула'}): "
                f"{cls._format_cost(row['cost_price'])} ₽, с {row['effective_from']}"
            )
        if len(rows) > 12:
            lines.append(f"… и ещё {len(rows) - 12} поз.")
        lines.append("До нажатия кнопки изменения не записаны. Даты для существующих цен взяты из CSV.")
        return "\n".join(lines)

    @classmethod
    def _table_all_history_confirmation_message(cls, pending):
        rows = pending.get("table_rows") or []
        lines = [
            "Подтвердите применение первоначальной себестоимости ко всей истории продаж:",
            f"Магазин: {pending['store_label']}",
            f"Позиций: {len(rows)}",
        ]
        for row in rows[:12]:
            lines.append(
                f"• SKU {row['sku']}: {cls._format_cost(row['cost_price'])} ₽ за штуку"
            )
        if len(rows) > 12:
            lines.append(f"… и ещё {len(rows) - 12} поз.")
        lines.append("Ранние периоды будут пересчитаны. Запись произойдёт только после отдельного подтверждения ниже.")
        return "\n".join(lines)

    @staticmethod
    def _table_confirmation_keyboard(pending):
        buttons = [
            {"text": "Сохранить с датами из таблицы", "callback": TelegramSellerCostUpdateService._draft_callback(TelegramSellerCostUpdateService.TABLE_CONFIRM_CALLBACK, pending)}
        ]
        if pending.get("all_history_allowed") is True:
            buttons.append(
                {"text": "Применить первоначальные цены ко всей истории", "callback": TelegramSellerCostUpdateService._draft_callback(TelegramSellerCostUpdateService.TABLE_SELECT_ALL_HISTORY_CALLBACK, pending)}
            )
        buttons.append({"text": "Отмена", "callback": TelegramSellerCostUpdateService._draft_callback(TelegramSellerCostUpdateService.CANCEL_CALLBACK, pending)})
        return {"error": False, "type": "inline_keyboard", "buttons": buttons}

    @staticmethod
    def _draft_callback(action, pending):
        return str(action) + ":" + str(pending.get("draft_id") or "")

    @classmethod
    def is_confirmation_callback(cls, callback):
        value = cls._text(callback)
        actions = {
            cls.CONFIRM_DATE_CALLBACK,
            cls.SELECT_ALL_HISTORY_CALLBACK,
            cls.CONFIRM_ALL_HISTORY_CALLBACK,
            cls.CANCEL_CALLBACK,
            cls.TABLE_CONFIRM_CALLBACK,
            cls.TABLE_SELECT_ALL_HISTORY_CALLBACK,
            cls.TABLE_CONFIRM_ALL_HISTORY_CALLBACK,
        }
        action = value.rpartition(":")[0] if ":" in value else value
        return action in actions

    def _save_pending_cost(self, user_key, identity, whole_history):
        effective_from = (
            self.INITIAL_HISTORY_DATE.isoformat()
            if whole_history
            else identity.get("effective_from")
        )
        source = (
            "SELLER_CONFIRMED_INITIAL_HISTORY"
            if whole_history
            else "SELLER_CONFIRMED_FIRST_EFFECTIVE_DATE"
            if identity.get("initial")
            else "SELLER_CONFIRMED_BOT"
        )
        recorder = getattr(self.cost_service, "record_cost_switch", None)
        if not callable(recorder):
            return {"error": True, "handled": True, "message": "Хранилище подтверждённой себестоимости недоступно.", "code": "SELLER_COST_SWITCH_RECORDER_UNAVAILABLE", "read_only_ozon": True}
        try:
            result = recorder(
                product_id=identity["product_id"],
                sku=identity["sku"],
                offer_id=identity["offer_id"],
                cost_price=identity["cost_price"],
                effective_from=effective_from,
                source=source,
            )
        except Exception:
            result = None
        if not isinstance(result, dict) or result.get("error") is not False:
            return {"error": True, "handled": True, "message": "Не удалось сохранить себестоимость. Изменений не применено.", "code": result.get("code") if isinstance(result, dict) else "SELLER_COST_SWITCH_RECORD_FAILED", "read_only_ozon": True}
        self._pending.pop(user_key, None)
        menu = self.open_menu()
        amount = self._format_cost(identity["cost_price"])
        display_name = identity["offer_id"] or identity["sku"]
        if whole_history:
            history_note = " Применено ко всей доступной истории по вашему отдельному подтверждению."
        elif identity.get("initial"):
            history_note = f" Действует с {effective_from}; более ранние периоды остались без этой себестоимости."
        else:
            history_note = f" Действует с {effective_from}."
        if isinstance(menu, dict) and menu.get("error") is False:
            coverage = menu.get("cost_coverage") or {}
            remaining = int(coverage.get("missing") or 0)
            if remaining:
                message = f"✅ {display_name}: {amount} ₽ сохранено.{history_note}\n\nМожно сразу посмотреть прибыль по этому товару или указать себестоимость для другого SKU."
                keyboard = dict(menu.get("keyboard") or {})
                buttons = list(keyboard.get("buttons") or [])
                buttons.insert(0, {"text": "📊 Прибыль по этому товару", "callback": "period_profit_sku:" + identity["sku"]})
                keyboard["buttons"] = buttons
            else:
                message = f"✅ {display_name}: {amount} ₽ сохранено.{history_note}\n\n🎉 Себестоимость заполнена для всего каталога."
                keyboard = menu.get("keyboard")
            return {"error": False, "handled": True, "message": message, "keyboard": keyboard, "cost_coverage": coverage, "sku": identity["sku"], "offer_id": identity["offer_id"], "cost_price": round(identity["cost_price"], 2), "effective_from": effective_from, "historical_default": whole_history, "seller_confirmed": True, "read_only_ozon": True}
        return {"error": False, "handled": True, "message": f"✅ {display_name}: {amount} ₽ сохранено.{history_note}", "sku": identity["sku"], "offer_id": identity["offer_id"], "cost_price": round(identity["cost_price"], 2), "effective_from": effective_from, "historical_default": whole_history, "seller_confirmed": True, "read_only_ozon": True}

    def _date_confirmation(self, pending):
        buttons = [
            {"text": f"Сохранить с {pending['effective_from']}", "callback": self._draft_callback(self.CONFIRM_DATE_CALLBACK, pending)},
        ]
        if pending.get("initial") is True:
            buttons.append(
                {"text": "Применить ко всей истории", "callback": self._draft_callback(self.SELECT_ALL_HISTORY_CALLBACK, pending)}
            )
        buttons.append({"text": "Отмена", "callback": self._draft_callback(self.CANCEL_CALLBACK, pending)})
        return {
            "keyboard": {
                "error": False,
                "type": "inline_keyboard",
                "buttons": buttons,
            }
        }

    @staticmethod
    def _date_confirmation_message(pending):
        return (
            "Проверьте перед сохранением:\n"
            f"Магазин: {pending['store_label']}\n"
            f"Товар: {pending['display_name']} (SKU {pending['sku']})\n"
            f"Себестоимость: {TelegramSellerCostUpdateService._format_cost(pending['cost_price'])} ₽ за штуку\n"
            f"Период действия: с {pending['effective_from']}\n\n"
            "Подтвердите запись кнопкой. До подтверждения себестоимость не сохранена."
        )

    @staticmethod
    def _all_history_confirmation_message(pending):
        return (
            "Подтвердите применение ко всей доступной истории:\n"
            f"Магазин: {pending['store_label']}\n"
            f"Товар: {pending['display_name']} (SKU {pending['sku']})\n"
            f"Себестоимость: {TelegramSellerCostUpdateService._format_cost(pending['cost_price'])} ₽ за штуку\n"
            "Период действия: вся доступная история продаж.\n\n"
            "Ранние расчёты будут пересчитаны с этой себестоимостью. Подтверждение действия требуется отдельно."
        )

    def _pending_store_is_current(self, pending):
        return (
            pending.get("tenant_scope") == self._tenant_scope()
            and pending.get("store_label") == self._active_store_label()
        )

    def _active_store_label(self):
        if callable(self.store_name_provider):
            try:
                value = self.store_name_provider()
                if self._text(value):
                    return self._text(value)
            except Exception:
                pass
        try:
            from services.ozon_account_repository import OzonAccountRepository, split_store_tenant_scope
            tenant_user_id = self._tenant_scope()
            user_key, client_id = split_store_tenant_scope(tenant_user_id)
            if user_key and client_id:
                accounts = OzonAccountRepository().list_accounts(user_key)
                account = next((row for row in accounts if row.get("client_id") == client_id), None)
                if isinstance(account, dict):
                    return self._text(account.get("display_name") or account.get("client_id_masked")) or "активный магазин"
        except Exception:
            pass
        return "активный магазин"

    @staticmethod
    def _tenant_scope():
        try:
            from services.tenant_context import get_current_tenant_user_id
            return str(get_current_tenant_user_id() or "")
        except Exception:
            return ""

    @staticmethod
    def _stale_store_result():
        return {
            "error": True,
            "handled": True,
            "message": "Активный магазин изменился. Старое подтверждение отменено; выберите товар заново в нужном магазине.",
            "code": "SELLER_COST_PENDING_STORE_STALE",
            "read_only_ozon": True,
        }

    @staticmethod
    def _pending_action_unavailable():
        return {
            "error": True,
            "handled": True,
            "message": "Подтверждение себестоимости устарело. Выберите товар и отправьте сумму заново.",
            "code": "SELLER_COST_CONFIRMATION_UNAVAILABLE",
            "read_only_ozon": True,
        }

    def clear_pending(self, user_id):
        user_key = self._user_key(user_id)
        if user_key is not None:
            with self._pending_lock:
                self._pending.pop(user_key, None)

    def _products(self):
        try:
            rows = self.product_service.load_products()
        except Exception:
            return self._error("SELLER_COST_PRODUCT_CATALOG_UNAVAILABLE")
        if not isinstance(rows, list):
            return self._error("SELLER_COST_PRODUCT_CATALOG_INVALID")
        if not rows:
            refresher = getattr(self.product_service, "refresh_products_for_period_profit", None)
            if not callable(refresher):
                return self._catalog_error("SELLER_COST_PRODUCT_CATALOG_EMPTY")
            try:
                refreshed = refresher()
            except Exception:
                refreshed = None
            if not isinstance(refreshed, dict) or refreshed.get("error") is not False:
                code = refreshed.get("code") if isinstance(refreshed, dict) else None
                return self._catalog_error(code or "SELLER_COST_PRODUCT_CATALOG_REFRESH_FAILED")
            try:
                rows = self.product_service.load_products()
            except Exception:
                return self._catalog_error("SELLER_COST_PRODUCT_CATALOG_UNAVAILABLE")
            if not isinstance(rows, list):
                return self._catalog_error("SELLER_COST_PRODUCT_CATALOG_INVALID")
        products, seen = [], set()
        for row in rows:
            if not isinstance(row, (tuple, list)) or len(row) < 3:
                return self._error("SELLER_COST_PRODUCT_CATALOG_INVALID")
            product_id, offer_id, sku = self._text(row[0]), self._text(row[1]), self._text(row[2])
            if not product_id or not sku:
                return self._error("SELLER_COST_PRODUCT_CATALOG_INVALID")
            if sku in seen:
                return self._error("SELLER_COST_SKU_AMBIGUOUS")
            seen.add(sku)
            products.append((offer_id or sku, sku, product_id, offer_id))
        products.sort(key=lambda item: item[0])
        return products if products else self._catalog_error("SELLER_COST_PRODUCT_CATALOG_EMPTY")

    def _current_costs(self):
        getter = getattr(self.cost_service, "get_all_costs", None)
        if not callable(getter):
            return set()
        try:
            rows = getter()
        except Exception:
            return set()
        result = set()
        for row in rows if isinstance(rows, list) else []:
            sku = self._text(row.get("sku")) if isinstance(row, dict) else self._text(row[1]) if isinstance(row, (tuple, list)) and len(row) >= 2 else ""
            if sku:
                result.add(sku)
        return result

    @staticmethod
    def _text(value):
        return "" if value is None else str(value).strip()

    @staticmethod
    def _user_key(value):
        if value is None or isinstance(value, bool):
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _cost(value):
        if isinstance(value, bool):
            return None
        text = str(value or "").strip().replace(",", ".")
        try:
            number = float(text)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if isfinite(number) and number >= 0 else None

    def _today(self):
        try:
            value = self.date_provider()
        except Exception:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _format_cost(value):
        return f"{value:.2f}".rstrip("0").rstrip(".")

    @staticmethod
    def _catalog_error(code):
        return {"error": True, "message": "Не удалось загрузить товары из Ozon. Проверьте подключение магазина и попробуйте ещё раз.", "code": code, "read_only_ozon": True}

    @staticmethod
    def _error(code):
        return {"error": True, "message": "Себестоимость сейчас недоступна. Изменений не применено.", "code": code, "read_only_ozon": True}
