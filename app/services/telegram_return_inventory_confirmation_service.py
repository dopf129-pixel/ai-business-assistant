from datetime import date, datetime


class TelegramReturnInventoryConfirmationService:
    """Collect explicit local seller inventory evidence for one exact return.

    This service never writes to Ozon. It records only the seller's explicit
    local fact about whether the exact returned quantity is saleable again.
    The evidence is intentionally insufficient by itself to change Period
    Profit: all accounting, recognition, authorization, and commit gates remain
    independent.
    """

    STATES = {
        "SALEABLE_RESTORED",
        "NON_SALEABLE",
    }

    def __init__(self, repository, date_provider=None):
        self.repository = repository
        self.date_provider = date_provider or date.today
        self._pending = {}

    def open_menu(self, user_id):
        user_key = self._user_key(user_id)
        if user_key is None:
            return self._error("RETURN_INVENTORY_USER_INVALID")

        self._pending[user_key] = {
            "stage": "IDENTITY",
        }
        return {
            "error": False,
            "message": (
                "Укажите возврат одной строкой:\n"
                "return_id | posting_number | SKU | количество\n\n"
                "Пример:\n"
                "1001736969 | 0239984545-0031-1 | 3921245627 | 1\n\n"
                "Это локальное подтверждение фактического состояния товара. "
                "Статус Ozon ReturnedToOzon сам по себе не означает, что товар "
                "снова пригоден к продаже."
            ),
            "return_inventory_input_pending": True,
            "read_only_ozon": True,
            "executed": False,
        }

    def handle_text(self, user_id, text):
        user_key = self._user_key(user_id)
        pending = self._pending.get(user_key) if user_key is not None else None
        if not isinstance(pending, dict) or pending.get("stage") != "IDENTITY":
            return {
                "error": False,
                "handled": False,
                "read_only_ozon": True,
                "executed": False,
            }

        identity = self._identity(text)
        if identity is None:
            return {
                "error": False,
                "handled": True,
                "message": (
                    "Не удалось распознать возврат. Используйте формат:\n"
                    "return_id | posting_number | SKU | количество"
                ),
                "return_inventory_input_pending": True,
                "read_only_ozon": True,
                "executed": False,
            }

        self._pending[user_key] = {
            "stage": "STATE",
            **identity,
        }
        return {
            "error": False,
            "handled": True,
            "message": (
                "Проверьте возврат:\n"
                + self._identity_text(identity)
                + "\n\nКаково фактическое состояние этого количества?"
            ),
            "keyboard": {
                "error": False,
                "type": "inline_keyboard",
                "buttons": [
                    {
                        "text": "✅ Снова пригоден к продаже",
                        "callback": "return_inventory_state:SALEABLE_RESTORED",
                    },
                    {
                        "text": "🚫 Не пригоден к продаже",
                        "callback": "return_inventory_state:NON_SALEABLE",
                    },
                    {
                        "text": "Отмена",
                        "callback": "return_inventory_cancel",
                    },
                ],
            },
            "read_only_ozon": True,
            "executed": False,
        }

    def select_state(self, user_id, recovery_state):
        user_key = self._user_key(user_id)
        pending = self._pending.get(user_key) if user_key is not None else None
        state = self._text(recovery_state).upper()
        if (
            not isinstance(pending, dict)
            or pending.get("stage") != "STATE"
            or state not in self.STATES
        ):
            return self._error("RETURN_INVENTORY_STATE_SELECTION_INVALID")

        updated = dict(pending)
        updated["stage"] = "CONFIRM"
        updated["recovery_state"] = state
        self._pending[user_key] = updated

        state_text = (
            "СНОВА ПРИГОДЕН К ПРОДАЖЕ"
            if state == "SALEABLE_RESTORED"
            else "НЕ ПРИГОДЕН К ПРОДАЖЕ"
        )
        return {
            "error": False,
            "message": (
                "Подтвердите локальный факт:\n"
                + self._identity_text(updated)
                + "\nСостояние: "
                + state_text
                + "\n\nПосле подтверждения запись будет добавлена в локальную "
                "историю. Ozon не изменяется. Остальные Return COGS gates "
                "останутся обязательными."
            ),
            "keyboard": {
                "error": False,
                "type": "inline_keyboard",
                "buttons": [
                    {
                        "text": "Подтвердить",
                        "callback": "return_inventory_confirm",
                    },
                    {
                        "text": "Отмена",
                        "callback": "return_inventory_cancel",
                    },
                ],
            },
            "read_only_ozon": True,
            "executed": False,
        }

    def confirm(self, user_id):
        user_key = self._user_key(user_id)
        pending = self._pending.get(user_key) if user_key is not None else None
        if not isinstance(pending, dict) or pending.get("stage") != "CONFIRM":
            return self._error("RETURN_INVENTORY_CONFIRMATION_INVALID")

        confirmed_on = self._today()
        if confirmed_on is None:
            return self._error("RETURN_INVENTORY_CONFIRMATION_DATE_UNAVAILABLE")

        recorder = getattr(self.repository, "record_recovery", None)
        if not callable(recorder):
            return self._error("RETURN_INVENTORY_RECORDER_UNAVAILABLE")

        try:
            result = recorder(
                return_id=pending["return_id"],
                posting_number=pending["posting_number"],
                sku=pending["sku"],
                quantity=pending["quantity"],
                recovery_state=pending["recovery_state"],
                confirmed_on=confirmed_on.isoformat(),
                source="SELLER_CONFIRMED_BOT",
            )
        except Exception:
            result = None

        if not isinstance(result, dict) or result.get("error") is not False:
            return {
                "error": True,
                "message": (
                    "Не удалось сохранить подтверждение состояния возврата. "
                    "Никаких изменений в Ozon не выполнено."
                ),
                "code": (
                    result.get("code")
                    if isinstance(result, dict)
                    else "RETURN_INVENTORY_RECORD_FAILED"
                ),
                "read_only_ozon": True,
                "executed": False,
            }

        self._pending.pop(user_key, None)
        state_text = (
            "снова пригоден к продаже"
            if pending["recovery_state"] == "SALEABLE_RESTORED"
            else "не пригоден к продаже"
        )
        return {
            "error": False,
            "message": (
                "✅ Локальное подтверждение сохранено: товар "
                + state_text
                + ".\n"
                + self._identity_text(pending)
                + "\n"
                "Это только inventory evidence. Оно не обходит проверку "
                "количества, периода, компенсации, accounting recognition, "
                "authorization и commit и само по себе не меняет прибыль."
            ),
            "return_id": pending["return_id"],
            "posting_number": pending["posting_number"],
            "sku": pending["sku"],
            "quantity": pending["quantity"],
            "recovery_state": pending["recovery_state"],
            "confirmed_on": confirmed_on.isoformat(),
            "seller_confirmed": True,
            "read_only_ozon": True,
            "executed": False,
        }

    def cancel(self, user_id):
        self.clear_pending(user_id)
        return {
            "error": False,
            "message": "Подтверждение состояния возврата отменено. Изменений нет.",
            "read_only_ozon": True,
            "executed": False,
        }

    def clear_pending(self, user_id):
        user_key = self._user_key(user_id)
        if user_key is not None:
            self._pending.pop(user_key, None)

    @classmethod
    def _identity(cls, value):
        parts = [part.strip() for part in str(value or "").split("|")]
        if len(parts) != 4:
            return None
        return_id, posting_number, sku, quantity_text = parts
        quantity = cls._quantity(quantity_text)
        if not return_id or not posting_number or not sku or quantity is None:
            return None
        return {
            "return_id": return_id,
            "posting_number": posting_number,
            "sku": sku,
            "quantity": quantity,
        }

    @staticmethod
    def _identity_text(identity):
        return (
            "Return ID: " + str(identity.get("return_id"))
            + "\nPosting: " + str(identity.get("posting_number"))
            + "\nSKU: " + str(identity.get("sku"))
            + "\nКоличество: " + str(identity.get("quantity"))
        )

    @staticmethod
    def _quantity(value):
        if isinstance(value, bool):
            return None
        try:
            number = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if number > 0 else None

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
    def _error(code):
        return {
            "error": True,
            "message": (
                "Подтверждение состояния возврата сейчас недоступно. "
                "Никаких изменений в Ozon не выполнено."
            ),
            "code": code,
            "read_only_ozon": True,
            "executed": False,
        }
