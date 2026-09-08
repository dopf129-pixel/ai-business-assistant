from datetime import date, datetime, timedelta
from math import isfinite


class TelegramSellerCostUpdateService:
    """Collect an explicit seller cost switch without mutating Ozon.

    Period Profit finance evidence is date-granular, so a price entered during a
    day becomes effective on the next calendar date. This prevents earlier
    accruals from the confirmation day from being re-costed retroactively.
    """

    def __init__(self, product_service, cost_service, date_provider=None):
        self.product_service = product_service
        self.cost_service = cost_service
        self.date_provider = date_provider or date.today
        self._pending = {}

    def open_menu(self):
        try:
            rows = self.product_service.load_products()
        except Exception:
            return self._error("SELLER_COST_PRODUCT_CATALOG_UNAVAILABLE")
        if not isinstance(rows, list):
            return self._error("SELLER_COST_PRODUCT_CATALOG_INVALID")

        products = []
        seen = set()
        for row in rows:
            if not isinstance(row, (tuple, list)) or len(row) < 3:
                return self._error("SELLER_COST_PRODUCT_CATALOG_INVALID")
            product_id = self._text(row[0])
            offer_id = self._text(row[1])
            sku = self._text(row[2])
            if not product_id or not sku:
                return self._error("SELLER_COST_PRODUCT_CATALOG_INVALID")
            if sku in seen:
                return self._error("SELLER_COST_SKU_AMBIGUOUS")
            seen.add(sku)
            display_name = offer_id or sku
            products.append((display_name, sku, product_id, offer_id))

        products.sort(key=lambda item: item[0])
        if not products:
            return self._error("SELLER_COST_PRODUCT_CATALOG_EMPTY")

        return {
            "error": False,
            "message": "Выберите артикул товара, для которого приехала новая партия:",
            "keyboard": {
                "error": False,
                "type": "inline_keyboard",
                "buttons": [
                    {
                        "text": display_name,
                        "callback": "seller_cost:" + sku,
                    }
                    for display_name, sku, _, _ in products
                ],
            },
            "read_only_ozon": True,
        }

    def select_sku(self, user_id, sku):
        user_key = self._user_key(user_id)
        sku_key = self._text(sku)
        if user_key is None or not sku_key:
            return self._error("SELLER_COST_SELECTION_INVALID")

        try:
            rows = self.product_service.load_products()
        except Exception:
            return self._error("SELLER_COST_PRODUCT_CATALOG_UNAVAILABLE")
        matches = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, (tuple, list)) or len(row) < 3:
                return self._error("SELLER_COST_PRODUCT_CATALOG_INVALID")
            if self._text(row[2]) == sku_key:
                matches.append(row)
        if len(matches) != 1:
            return self._error(
                "SELLER_COST_SKU_NOT_FOUND" if not matches else "SELLER_COST_SKU_AMBIGUOUS"
            )

        row = matches[0]
        product_id = self._text(row[0])
        offer_id = self._text(row[1])
        if not product_id:
            return self._error("SELLER_COST_PRODUCT_IDENTITY_INVALID")
        self._pending[user_key] = {
            "product_id": product_id,
            "sku": sku_key,
            "offer_id": offer_id,
        }
        display_name = offer_id or sku_key
        return {
            "error": False,
            "message": (
                "Артикул " + display_name + " выбран (SKU " + sku_key + ").\n"
                "Введите новую себестоимость в рублях, например: 24.70\n"
                "Новая цена начнёт действовать со следующей календарной даты, "
                "чтобы не пересчитывать уже прошедшие начисления сегодняшнего дня."
            ),
            "seller_cost_input_pending": True,
            "read_only_ozon": True,
        }

    def handle_text(self, user_id, text):
        user_key = self._user_key(user_id)
        if user_key is None or user_key not in self._pending:
            return {
                "error": False,
                "handled": False,
                "read_only_ozon": True,
            }

        cost = self._cost(text)
        if cost is None:
            return {
                "error": False,
                "handled": True,
                "message": (
                    "Не удалось распознать себестоимость. "
                    "Введите число в рублях, например: 24.70"
                ),
                "seller_cost_input_pending": True,
                "read_only_ozon": True,
            }

        today = self._today()
        if today is None:
            return {
                "error": True,
                "handled": True,
                "message": "Не удалось определить дату активации себестоимости.",
                "code": "SELLER_COST_EFFECTIVE_DATE_UNAVAILABLE",
                "read_only_ozon": True,
            }
        effective_from = today + timedelta(days=1)
        identity = dict(self._pending[user_key])
        recorder = getattr(self.cost_service, "record_cost_switch", None)
        if not callable(recorder):
            return {
                "error": True,
                "handled": True,
                "message": "Хранилище подтверждённой себестоимости недоступно.",
                "code": "SELLER_COST_SWITCH_RECORDER_UNAVAILABLE",
                "read_only_ozon": True,
            }
        try:
            result = recorder(
                product_id=identity["product_id"],
                sku=identity["sku"],
                offer_id=identity["offer_id"],
                cost_price=cost,
                effective_from=effective_from.isoformat(),
                source="SELLER_CONFIRMED_BOT",
            )
        except Exception:
            result = None
        if not isinstance(result, dict) or result.get("error") is not False:
            return {
                "error": True,
                "handled": True,
                "message": "Не удалось сохранить новую себестоимость. Изменений не применено.",
                "code": (
                    result.get("code")
                    if isinstance(result, dict)
                    else "SELLER_COST_SWITCH_RECORD_FAILED"
                ),
                "read_only_ozon": True,
            }

        self._pending.pop(user_key, None)
        amount = self._format_cost(cost)
        display_name = identity["offer_id"] or identity["sku"]
        return {
            "error": False,
            "handled": True,
            "message": (
                "✅ Себестоимость артикула " + display_name + " (SKU "
                + identity["sku"] + ") сохранена: " + amount + " ₽.\n"
                "Для Period Profit она действует с "
                + effective_from.isoformat()
                + " до следующего подтверждённого изменения.\n"
                "Прошлые периоды не переписываются."
            ),
            "sku": identity["sku"],
            "offer_id": identity["offer_id"],
            "cost_price": round(cost, 2),
            "effective_from": effective_from.isoformat(),
            "seller_confirmed": True,
            "read_only_ozon": True,
        }

    def clear_pending(self, user_id):
        user_key = self._user_key(user_id)
        if user_key is not None:
            self._pending.pop(user_key, None)

    @staticmethod
    def _text(value):
        if value is None:
            return ""
        return str(value).strip()

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
        if not isfinite(number) or number < 0:
            return None
        return number

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
        text = f"{value:.2f}"
        return text.rstrip("0").rstrip(".")

    @staticmethod
    def _error(code):
        return {
            "error": True,
            "message": "Себестоимость сейчас недоступна. Изменений не применено.",
            "code": code,
            "read_only_ozon": True,
        }
