import re

from services.seller_confirmed_product_identity_repository import (
    SellerConfirmedProductIdentityRepository,
)


class PeriodProfitIdentityConfirmationRuntimeService:
    """Persist an explicit seller statement that two SKU identities are one item.

    The seller must name exactly two SKU values and explicitly state equivalence.
    Exactly one of those SKU values must identify one current tenant-local cost row;
    that row becomes the current identity target and the other SKU becomes the
    historical finance alias. No cost value is copied and Ozon is never modified.
    """

    SOURCE = "SELLER_CONFIRMED_BOT_TEXT"

    def __init__(self, cost_service, repository=None):
        self.cost_service = cost_service
        self.repository = repository or SellerConfirmedProductIdentityRepository(
            cost_service
        )

    def handle_text(self, text):
        value = " ".join(str(text or "").strip().lower().split())
        if self._is_identity_revocation(value):
            return self._revoke(value)
        if not self._is_identity_confirmation(value):
            return None

        skus = self._sku_mentions(value)
        if len(skus) != 2:
            return self._error(
                "PERIOD_PROFIT_IDENTITY_CONFIRMATION_INPUT_INVALID",
                "Укажите ровно два SKU, например: «SKU 111 и SKU 222 — один товар».",
            )

        getter = getattr(self.cost_service, "get_all_costs", None)
        recorder = getattr(self.repository, "record_mapping", None)
        if not callable(getter) or not callable(recorder):
            return self._error(
                "PERIOD_PROFIT_IDENTITY_CONFIRMATION_SERVICE_UNAVAILABLE",
                "Сервис подтверждения связи SKU недоступен.",
            )

        try:
            rows = getter()
        except Exception:
            return self._error(
                "PERIOD_PROFIT_IDENTITY_CONFIRMATION_STORAGE_UNAVAILABLE",
                "Не удалось прочитать текущую identity товара.",
            )
        if not isinstance(rows, (list, tuple)):
            return self._error(
                "PERIOD_PROFIT_IDENTITY_CONFIRMATION_STORAGE_INVALID",
                "Некорректные текущие данные товара.",
            )

        candidates = []
        for row in rows:
            normalized = self._row(row)
            if normalized is None:
                continue
            if normalized["sku"] in skus:
                candidates.append(normalized)

        unique_targets = {
            (
                candidate["product_id"],
                candidate["sku"],
                candidate["offer_id"],
            )
            for candidate in candidates
        }
        if not unique_targets:
            return self._error(
                "PERIOD_PROFIT_IDENTITY_CONFIRMATION_CURRENT_IDENTITY_MISSING",
                "Ни один из указанных SKU не найден в текущей seller identity. Связь не сохранена.",
            )
        if len(unique_targets) != 1:
            return self._error(
                "PERIOD_PROFIT_IDENTITY_CONFIRMATION_AMBIGUOUS",
                "Оба SKU уже соответствуют текущим seller identity. Связь неоднозначна и не сохранена.",
            )

        target = candidates[0]
        finance_sku = next((sku for sku in skus if sku != target["sku"]), None)
        if not finance_sku:
            return self._error(
                "PERIOD_PROFIT_IDENTITY_CONFIRMATION_INPUT_INVALID",
                "Не удалось определить старый SKU из финансов Ozon.",
            )

        try:
            result = recorder(
                finance_sku=finance_sku,
                current_product_id=target["product_id"],
                current_sku=target["sku"],
                current_offer_id=target["offer_id"],
                source=self.SOURCE,
            )
        except Exception:
            return self._error(
                "PERIOD_PROFIT_IDENTITY_CONFIRMATION_STORAGE_UNAVAILABLE",
                "Не удалось сохранить подтверждённую связь SKU.",
            )

        if not isinstance(result, dict) or result.get("error") is True:
            code = (
                result.get("code")
                if isinstance(result, dict)
                else "PERIOD_PROFIT_IDENTITY_CONFIRMATION_RESPONSE_INVALID"
            )
            message = (
                "Для старого SKU уже сохранена другая подтверждённая связь. Новая связь не создана."
                if code == "SELLER_PRODUCT_IDENTITY_MAPPING_CONFLICT"
                else "Подтверждённая связь SKU не сохранена."
            )
            return self._error(
                str(code or "PERIOD_PROFIT_IDENTITY_CONFIRMATION_RECORD_FAILED"),
                message,
            )

        already = result.get("status") == "SELLER_PRODUCT_IDENTITY_MAPPING_ALREADY_RECORDED"
        return {
            "error": False,
            "code": (
                "PERIOD_PROFIT_IDENTITY_CONFIRMATION_ALREADY_RECORDED"
                if already
                else "PERIOD_PROFIT_IDENTITY_CONFIRMATION_RECORDED"
            ),
            "status": "PERIOD_PROFIT_IDENTITY_CONFIRMATION_READY",
            "message": (
                ("Уже подтверждено" if already else "Сохранено")
                + f": SKU {finance_sku} и SKU {target['sku']} — один товар. "
                "Связь используется только как seller-confirmed identity; себестоимость по датам не изменена."
            ),
            "seller_confirmed": True,
            "read_only_ozon": True,
            "executed": not already,
        }

    def _revoke(self, value):
        skus = self._sku_mentions(value)
        if len(skus) != 2:
            return self._error(
                "PERIOD_PROFIT_IDENTITY_REVOCATION_INPUT_INVALID",
                "Укажите ровно два SKU, например: «Отменить связь SKU 111 и SKU 222».",
            )
        getter = getattr(self.repository, "get_mapping", None)
        revoker = getattr(self.repository, "revoke_mapping", None)
        if not callable(getter) or not callable(revoker):
            return self._error(
                "PERIOD_PROFIT_IDENTITY_REVOCATION_SERVICE_UNAVAILABLE",
                "Сервис отмены связи SKU недоступен.",
            )

        matches = []
        for finance_sku, current_sku in ((skus[0], skus[1]), (skus[1], skus[0])):
            try:
                mapping = getter(finance_sku)
            except Exception:
                mapping = None
            if (
                isinstance(mapping, dict)
                and mapping.get("error") is False
                and mapping.get("mapping_confirmed") is True
                and self._text(mapping.get("current_sku")) == current_sku
            ):
                matches.append((finance_sku, current_sku))
        if len(matches) != 1:
            return self._error(
                "PERIOD_PROFIT_IDENTITY_REVOCATION_NOT_FOUND",
                "Точная активная связь этих двух SKU не найдена. Ничего не изменено.",
            )

        finance_sku, current_sku = matches[0]
        try:
            result = revoker(
                finance_sku=finance_sku,
                current_sku=current_sku,
                source="SELLER_REVOKED_BOT_TEXT",
            )
        except Exception:
            result = None
        if not isinstance(result, dict) or result.get("error") is True:
            return self._error(
                "PERIOD_PROFIT_IDENTITY_REVOCATION_FAILED",
                "Не удалось отменить связь SKU. Ничего не изменено.",
            )
        return {
            "error": False,
            "code": "PERIOD_PROFIT_IDENTITY_REVOCATION_RECORDED",
            "status": "PERIOD_PROFIT_IDENTITY_CONFIRMATION_READY",
            "message": (
                f"Связь SKU {finance_sku} и SKU {current_sku} отменена. "
                "Она больше не используется в расчётах. Ранее полученные отчёты "
                "по этой связи следует считать недействительными."
            ),
            "seller_confirmed": False,
            "read_only_ozon": True,
            "executed": True,
        }

    @staticmethod
    def _is_identity_revocation(value):
        return "sku" in value and any(
            phrase in value
            for phrase in (
                "отменить связь", "удалить связь", "отозвать связь",
                "не один товар", "не тот же товар",
            )
        )

    @staticmethod
    def _is_identity_confirmation(value):
        if "sku" not in value:
            return False
        return any(
            phrase in value
            for phrase in (
                "один товар",
                "тот же товар",
                "это один товар",
                "это тот же товар",
                "same product",
                "same item",
            )
        )

    @staticmethod
    def _sku_mentions(value):
        matches = re.findall(r"\bsku\s*[:№#-]?\s*(\d+)\b", value, flags=re.IGNORECASE)
        ordered = []
        for match in matches:
            sku = str(match).strip()
            if sku and sku not in ordered:
                ordered.append(sku)
        return ordered

    @staticmethod
    def _row(row):
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            return None
        product_id = str(row[0] or "").strip()
        sku = str(row[1] or "").strip()
        offer_id = str(row[2] or "").strip()
        if not product_id or not sku:
            return None
        return {
            "product_id": product_id,
            "sku": sku,
            "offer_id": offer_id or None,
        }

    @staticmethod
    def _text(value):
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _error(code, message):
        return {
            "error": True,
            "code": str(code),
            "status": "PERIOD_PROFIT_IDENTITY_CONFIRMATION_UNAVAILABLE",
            "message": str(message),
            "seller_confirmed": False,
            "read_only_ozon": True,
            "executed": False,
        }
