import re
from datetime import date


class PeriodProfitCostConfirmationRuntimeService:
    """Record seller-confirmed historical cost switches without touching Ozon.

    The runtime accepts an explicit seller statement such as
    ``21р себестоимость была с начала 2026г``.  It only records a switch when the
    stated amount maps to exactly one current tenant-local cost row, or when an
    explicitly supplied product/sku/offer identifier narrows the candidates to one.
    Ambiguity and amount mismatches fail closed.
    """

    SOURCE = "SELLER_CONFIRMED_BOT_TEXT"

    def __init__(self, cost_service):
        self.cost_service = cost_service

    def handle_text(self, text):
        value = " ".join(str(text or "").strip().lower().split())
        if not self._is_cost_confirmation(value):
            return None

        amount = self._amount(value)
        effective_from = self._effective_from(value)
        if amount is None or effective_from is None:
            return self._error(
                "PERIOD_PROFIT_COST_CONFIRMATION_INPUT_INVALID",
                "Укажите себестоимость и дату начала действия, например: "
                "«21 ₽ себестоимость с 01.01.2026».",
            )

        getter = getattr(self.cost_service, "get_all_costs", None)
        recorder = getattr(self.cost_service, "record_cost_switch", None)
        if not callable(getter) or not callable(recorder):
            return self._error(
                "PERIOD_PROFIT_COST_CONFIRMATION_SERVICE_UNAVAILABLE",
                "Сервис себестоимости недоступен.",
            )

        try:
            rows = getter()
        except Exception:
            return self._error(
                "PERIOD_PROFIT_COST_CONFIRMATION_STORAGE_UNAVAILABLE",
                "Не удалось прочитать сохранённую себестоимость.",
            )
        if not isinstance(rows, (list, tuple)):
            return self._error(
                "PERIOD_PROFIT_COST_CONFIRMATION_STORAGE_INVALID",
                "Некорректные данные себестоимости.",
            )

        candidates = []
        for row in rows:
            normalized = self._row(row)
            if normalized is None:
                continue
            if abs(normalized["cost_price"] - amount) > 0.000001:
                continue
            candidates.append(normalized)

        if len(candidates) > 1:
            narrowed = [
                row for row in candidates
                if self._identity_mentioned(value, row)
            ]
            if len(narrowed) == 1:
                candidates = narrowed

        if not candidates:
            return self._error(
                "PERIOD_PROFIT_COST_CONFIRMATION_CURRENT_COST_MISMATCH",
                "В текущих данных нет товара с такой себестоимостью. "
                "Историческая запись не создана.",
            )
        if len(candidates) != 1:
            return self._error(
                "PERIOD_PROFIT_COST_CONFIRMATION_AMBIGUOUS",
                "Несколько товаров имеют такую себестоимость. Укажите артикул, SKU "
                "или product_id вместе с суммой и датой.",
            )

        row = candidates[0]
        existing = self._existing_evidence(row, effective_from)
        if existing is not None:
            if existing.get("ready") is True and abs(existing["cost_price"] - amount) <= 0.000001:
                return self._success(amount, effective_from, already_confirmed=True)
            if existing.get("ready") is True:
                return self._error(
                    "PERIOD_PROFIT_COST_CONFIRMATION_VERSION_CONFLICT",
                    "На эту дату уже подтверждена другая себестоимость. "
                    "Новая запись не создана.",
                )

        try:
            result = recorder(
                product_id=row["product_id"],
                sku=row["sku"],
                offer_id=row["offer_id"],
                cost_price=amount,
                effective_from=effective_from,
                currency=row["currency"],
                source=self.SOURCE,
            )
        except Exception:
            return self._error(
                "PERIOD_PROFIT_COST_CONFIRMATION_STORAGE_UNAVAILABLE",
                "Не удалось сохранить историческую себестоимость.",
            )

        if not isinstance(result, dict) or result.get("error") is True:
            code = (
                result.get("code")
                if isinstance(result, dict)
                else "PERIOD_PROFIT_COST_CONFIRMATION_RESPONSE_INVALID"
            )
            return self._error(
                str(code or "PERIOD_PROFIT_COST_CONFIRMATION_RECORD_FAILED"),
                "Историческая себестоимость не сохранена.",
            )
        return self._success(amount, effective_from, already_confirmed=False)

    def _existing_evidence(self, row, effective_from):
        getter = getattr(self.cost_service, "get_effective_cost_evidence", None)
        if not callable(getter):
            return None
        try:
            evidence = getter(
                effective_from,
                product_id=row["product_id"],
                sku=row["sku"],
                offer_id=row["offer_id"],
            )
        except Exception:
            return None
        if not isinstance(evidence, dict):
            return None
        cost = self._number(evidence.get("cost_price"))
        return {
            "ready": (
                evidence.get("error") is False
                and evidence.get("effective_cost_confirmed") is True
                and cost is not None
            ),
            "cost_price": cost,
        }

    @staticmethod
    def _row(row):
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            return None
        cost = PeriodProfitCostConfirmationRuntimeService._number(row[3])
        if cost is None:
            return None
        product_id = str(row[0] or "").strip()
        sku = str(row[1] or "").strip()
        offer_id = str(row[2] or "").strip()
        currency = str(row[4] or "RUB").strip() or "RUB"
        if not product_id or (not sku and not offer_id):
            return None
        return {
            "product_id": product_id,
            "sku": sku or None,
            "offer_id": offer_id or None,
            "cost_price": cost,
            "currency": currency,
        }

    @staticmethod
    def _is_cost_confirmation(value):
        return (
            ("себесто" in value or "cost" in value)
            and any(token in value for token in ("была", "был", "было", "с ", "с начала", "действ"))
        )

    @staticmethod
    def _amount(value):
        matches = re.findall(
            r"(?<!\d)(\d+(?:[\.,]\d{1,2})?)\s*(?:₽|р\.?|руб(?:\.|ля|лей)?)",
            value,
        )
        if matches:
            return PeriodProfitCostConfirmationRuntimeService._number(matches[0].replace(",", "."))
        match = re.search(
            r"себесто(?:имость|имости|имост[ьи])?\s*(?:была|был|было|=|:)?\s*(\d+(?:[\.,]\d{1,2})?)",
            value,
        )
        if match:
            return PeriodProfitCostConfirmationRuntimeService._number(match.group(1).replace(",", "."))
        return None

    @staticmethod
    def _effective_from(value):
        explicit = re.search(
            r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)",
            value,
        )
        if explicit:
            try:
                return date(
                    int(explicit.group(3)),
                    int(explicit.group(2)),
                    int(explicit.group(1)),
                ).isoformat()
            except ValueError:
                return None
        iso = re.search(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)", value)
        if iso:
            try:
                return date(
                    int(iso.group(1)),
                    int(iso.group(2)),
                    int(iso.group(3)),
                ).isoformat()
            except ValueError:
                return None
        start_year = re.search(
            r"(?:с\s+начала|с\s+начал[ао])\s+(20\d{2})(?:\s*г(?:ода|\.)?)?",
            value,
        )
        if start_year:
            return date(int(start_year.group(1)), 1, 1).isoformat()
        return None

    @staticmethod
    def _identity_mentioned(value, row):
        for key in ("product_id", "sku", "offer_id"):
            identity = str(row.get(key) or "").strip().lower()
            if identity and identity in value:
                return True
        return False

    @staticmethod
    def _number(value):
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if number < 0:
            return None
        return number

    @staticmethod
    def _success(amount, effective_from, already_confirmed):
        amount_text = ("%.2f" % amount).rstrip("0").rstrip(".")
        prefix = "Уже подтверждено" if already_confirmed else "Сохранено"
        return {
            "error": False,
            "code": (
                "PERIOD_PROFIT_COST_CONFIRMATION_ALREADY_RECORDED"
                if already_confirmed
                else "PERIOD_PROFIT_COST_CONFIRMATION_RECORDED"
            ),
            "status": "PERIOD_PROFIT_COST_CONFIRMATION_READY",
            "message": (
                f"{prefix}: себестоимость {amount_text} ₽ действует с "
                f"{effective_from}. Ozon не изменялся."
            ),
            "seller_confirmed": True,
            "read_only_ozon": True,
            "executed": not already_confirmed,
        }

    @staticmethod
    def _error(code, message):
        return {
            "error": True,
            "code": code,
            "status": "PERIOD_PROFIT_COST_CONFIRMATION_UNAVAILABLE",
            "message": message,
            "seller_confirmed": False,
            "read_only_ozon": True,
            "executed": False,
        }
