from datetime import date, datetime, timedelta
from math import isfinite

from services.seller_cost_table_service import SellerCostTableService


class TelegramSellerCostUpdateService:
    """Guided seller-cost setup without mutating Ozon."""

    INITIAL_HISTORY_DATE = date.min

    def __init__(self, product_service, cost_service, date_provider=None, table_service=None):
        self.product_service = product_service
        self.cost_service = cost_service
        self.date_provider = date_provider or date.today
        self.table_service = table_service or SellerCostTableService(product_service, cost_service)
        self._pending = {}

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
                "Первую себестоимость применю ко всей доступной истории продаж; если раньше она отличалась, историю можно уточнить позже."
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
        return self.table_service.import_csv(content)

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
        self._pending[user_key] = {"product_id": product_id, "sku": sku_key, "offer_id": offer_id, "initial": is_initial}
        timing = "Это первая себестоимость товара — применю её ко всей доступной истории продаж. Если раньше цена отличалась, историю можно будет уточнить позже." if is_initial else "Это изменение существующей себестоимости; новая цена начнёт действовать с завтрашней даты, чтобы не переписывать уже рассчитанный сегодняшний день."
        return {"error": False, "message": f"{display_name}\nSKU: {sku_key}\n\nВведите себестоимость одной штуки в ₽. Например: 430\n\n{timing}", "seller_cost_input_pending": True, "read_only_ozon": True}

    def handle_text(self, user_id, text):
        user_key = self._user_key(user_id)
        if user_key is None or user_key not in self._pending:
            return {"error": False, "handled": False, "read_only_ozon": True}
        cost = self._cost(text)
        if cost is None:
            return {"error": False, "handled": True, "message": "Не удалось распознать сумму. Отправьте только число в рублях, например: 430 или 430.50", "seller_cost_input_pending": True, "read_only_ozon": True}
        today = self._today()
        if today is None:
            return {"error": True, "handled": True, "message": "Не удалось определить дату активации себестоимости.", "code": "SELLER_COST_EFFECTIVE_DATE_UNAVAILABLE", "read_only_ozon": True}
        identity = dict(self._pending[user_key])
        is_initial = bool(identity.get("initial"))
        effective_from = self.INITIAL_HISTORY_DATE if is_initial else today + timedelta(days=1)
        source = "SELLER_CONFIRMED_INITIAL_HISTORY" if is_initial else "SELLER_CONFIRMED_BOT"
        recorder = getattr(self.cost_service, "record_cost_switch", None)
        if not callable(recorder):
            return {"error": True, "handled": True, "message": "Хранилище подтверждённой себестоимости недоступно.", "code": "SELLER_COST_SWITCH_RECORDER_UNAVAILABLE", "read_only_ozon": True}
        try:
            result = recorder(product_id=identity["product_id"], sku=identity["sku"], offer_id=identity["offer_id"], cost_price=cost, effective_from=effective_from.isoformat(), source=source)
        except Exception:
            result = None
        if not isinstance(result, dict) or result.get("error") is not False:
            return {"error": True, "handled": True, "message": "Не удалось сохранить себестоимость. Изменений не применено.", "code": result.get("code") if isinstance(result, dict) else "SELLER_COST_SWITCH_RECORD_FAILED", "read_only_ozon": True}
        self._pending.pop(user_key, None)
        menu = self.open_menu()
        amount = self._format_cost(cost)
        display_name = identity["offer_id"] or identity["sku"]
        history_note = " Применено ко всей доступной истории продаж." if is_initial else ""
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
                message = f"✅ {display_name}: {amount} ₽ сохранено.{history_note}\n\n🎉 Готово: себестоимость заполнена для всего каталога. Теперь можно считать прибыль за прошлые периоды."
                keyboard = menu.get("keyboard")
            return {"error": False, "handled": True, "message": message, "keyboard": keyboard, "cost_coverage": coverage, "sku": identity["sku"], "offer_id": identity["offer_id"], "cost_price": round(cost, 2), "effective_from": effective_from.isoformat(), "historical_default": is_initial, "seller_confirmed": True, "read_only_ozon": True}
        return {"error": False, "handled": True, "message": f"✅ {display_name}: {amount} ₽ сохранено.{history_note}", "sku": identity["sku"], "cost_price": round(cost, 2), "effective_from": effective_from.isoformat(), "historical_default": is_initial, "seller_confirmed": True, "read_only_ozon": True}

    def clear_pending(self, user_id):
        user_key = self._user_key(user_id)
        if user_key is not None:
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
