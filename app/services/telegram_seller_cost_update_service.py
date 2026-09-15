from datetime import date, datetime, timedelta
from math import isfinite


class TelegramSellerCostUpdateService:
    """Guided seller-cost setup without mutating Ozon."""

    def __init__(self, product_service, cost_service, date_provider=None):
        self.product_service = product_service
        self.cost_service = cost_service
        self.date_provider = date_provider or date.today
        self._pending = {}

    def open_menu(self):
        products = self._products()
        if isinstance(products, dict):
            return products
        costs = self._current_costs()
        missing = [item for item in products if item[1] not in costs]
        configured = len(products) - len(missing)
        if missing:
            shown = missing[:20]
            message = (
                "💰 Себестоимость товаров\n\n"
                f"Заполнено: {configured} из {len(products)}\n"
                f"Без себестоимости: {len(missing)}\n\n"
                "Нажмите товар и отправьте только сумму в рублях. "
                "После сохранения я предложу следующий товар."
            )
            buttons = [
                {"text": display_name, "callback": "seller_cost:" + sku}
                for display_name, sku, _, _ in shown
            ]
            if len(missing) > len(shown):
                message += f"\n\nПоказаны первые {len(shown)} позиций."
        else:
            message = (
                "✅ Себестоимость заполнена для всех товаров каталога.\n\n"
                "Теперь Period Profit сможет использовать подтверждённые значения. "
                "Если придёт новая партия по другой цене — выберите товар ниже и обновите стоимость."
            )
            buttons = [
                {"text": display_name, "callback": "seller_cost:" + sku}
                for display_name, sku, _, _ in products[:20]
            ]
        return {
            "error": False,
            "message": message,
            "cost_coverage": {"configured": configured, "total": len(products), "missing": len(missing)},
            "keyboard": {"error": False, "type": "inline_keyboard", "buttons": buttons},
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
        self._pending[user_key] = {
            "product_id": product_id,
            "sku": sku_key,
            "offer_id": offer_id,
            "initial": is_initial,
        }
        timing = (
            "Это первая себестоимость товара, поэтому она начнёт действовать с сегодняшней даты."
            if is_initial
            else "Это изменение существующей себестоимости; новая цена начнёт действовать с завтрашней даты, чтобы не переписывать уже рассчитанный сегодняшний день."
        )
        return {
            "error": False,
            "message": (
                f"{display_name}\nSKU: {sku_key}\n\n"
                "Введите себестоимость одной штуки в ₽. Например: 430\n\n" + timing
            ),
            "seller_cost_input_pending": True,
            "read_only_ozon": True,
        }

    def handle_text(self, user_id, text):
        user_key = self._user_key(user_id)
        if user_key is None or user_key not in self._pending:
            return {"error": False, "handled": False, "read_only_ozon": True}
        cost = self._cost(text)
        if cost is None:
            return {
                "error": False,
                "handled": True,
                "message": "Не удалось распознать сумму. Отправьте только число в рублях, например: 430 или 430.50",
                "seller_cost_input_pending": True,
                "read_only_ozon": True,
            }
        today = self._today()
        if today is None:
            return {"error": True, "handled": True, "message": "Не удалось определить дату активации себестоимости.", "code": "SELLER_COST_EFFECTIVE_DATE_UNAVAILABLE", "read_only_ozon": True}
        identity = dict(self._pending[user_key])
        effective_from = today if identity.get("initial") else today + timedelta(days=1)
        recorder = getattr(self.cost_service, "record_cost_switch", None)
        if not callable(recorder):
            return {"error": True, "handled": True, "message": "Хранилище подтверждённой себестоимости недоступно.", "code": "SELLER_COST_SWITCH_RECORDER_UNAVAILABLE", "read_only_ozon": True}
        try:
            result = recorder(
                product_id=identity["product_id"], sku=identity["sku"], offer_id=identity["offer_id"],
                cost_price=cost, effective_from=effective_from.isoformat(), source="SELLER_CONFIRMED_BOT",
            )
        except Exception:
            result = None
        if not isinstance(result, dict) or result.get("error") is not False:
            return {"error": True, "handled": True, "message": "Не удалось сохранить себестоимость. Изменений не применено.", "code": result.get("code") if isinstance(result, dict) else "SELLER_COST_SWITCH_RECORD_FAILED", "read_only_ozon": True}
        self._pending.pop(user_key, None)
        menu = self.open_menu()
        amount = self._format_cost(cost)
        display_name = identity["offer_id"] or identity["sku"]
        if isinstance(menu, dict) and menu.get("error") is False:
            coverage = menu.get("cost_coverage") or {}
            remaining = int(coverage.get("missing") or 0)
            if remaining:
                message = f"✅ {display_name}: {amount} ₽ сохранено.\n\nОсталось заполнить: {remaining}. Выберите следующий товар:"
            else:
                message = f"✅ {display_name}: {amount} ₽ сохранено.\n\n🎉 Готово: себестоимость заполнена для всего каталога. Теперь можно считать прибыль."
            return {
                "error": False, "handled": True, "message": message,
                "keyboard": menu.get("keyboard"), "cost_coverage": coverage,
                "sku": identity["sku"], "offer_id": identity["offer_id"], "cost_price": round(cost, 2),
                "effective_from": effective_from.isoformat(), "seller_confirmed": True, "read_only_ozon": True,
            }
        return {"error": False, "handled": True, "message": f"✅ {display_name}: {amount} ₽ сохранено.", "sku": identity["sku"], "cost_price": round(cost, 2), "effective_from": effective_from.isoformat(), "seller_confirmed": True, "read_only_ozon": True}

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
        return products if products else self._error("SELLER_COST_PRODUCT_CATALOG_EMPTY")

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
            if isinstance(row, dict):
                sku = self._text(row.get("sku"))
            elif isinstance(row, (tuple, list)) and len(row) >= 3:
                sku = self._text(row[2])
            else:
                sku = ""
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
    def _error(code):
        return {"error": True, "message": "Себестоимость сейчас недоступна. Изменений не применено.", "code": code, "read_only_ozon": True}
