"""Expose confirmed current-price commission evidence without extrapolating it."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

from services.ozon_account_repository import split_store_tenant_scope
from services.unit_price_tariff_resolver import UnitPriceTariffResolver


class UnitPriceTariffSource:
    """Map one existing scenario snapshot to a current-price point only.

    This adapter performs no network or storage access. Ozon's current price
    response does not provide a confirmed tariff grid for hypothetical prices,
    so callers must combine this point with an explicitly selected manual
    profile when they need a rate at another price.
    """

    RANGE_STATUS = "RANGE_SOURCE_UNAVAILABLE"
    RANGE_REASON = "HYPOTHETICAL_PRICE_RANGE_NOT_CONFIRMED"
    SOURCE_REF = "OZON_PRODUCT_INFO_PRICES_CURRENT_POINT"
    MAX_TEXT_LENGTH = 128
    _SNAPSHOT_ID = re.compile(r"[a-f0-9]{16}\Z")

    def from_scenario_snapshot(self, snapshot):
        """Return an ephemeral profile for the exact current price, if proven."""
        unavailable = self._unavailable()
        if not isinstance(snapshot, dict) or snapshot.get("error") is not False:
            unavailable["reason"] = "CURRENT_SOURCE_UNAVAILABLE"
            return unavailable

        identity = snapshot.get("identity")
        suggested = snapshot.get("suggested_inputs")
        provenance = snapshot.get("input_provenance")
        completeness = snapshot.get("source_completeness")
        periods = snapshot.get("source_periods")
        product = snapshot.get("product")
        if not all(isinstance(value, dict) for value in
                   (identity, suggested, provenance, completeness, periods, product)):
            unavailable["reason"] = "CURRENT_SOURCE_SNAPSHOT_INCOMPLETE"
            return unavailable

        owner_id = self._text(identity.get("user_id"))
        store_id = self._text(identity.get("store_id"))
        tenant_scope = self._text(identity.get("tenant_scope"))
        scoped_user, _ = split_store_tenant_scope(tenant_scope)
        product_id = self._text(identity.get("product_id"))
        offer_id = self._text(identity.get("offer_id"))
        sku = self._text(identity.get("sku"))
        if (not owner_id or not store_id or not tenant_scope
                or scoped_user != owner_id or not product_id or not offer_id or not sku):
            unavailable["reason"] = "CURRENT_SOURCE_IDENTITY_INCOMPLETE"
            return unavailable
        if str(product.get("scheme") or "").strip().upper() != "FBO":
            unavailable["reason"] = "UNSUPPORTED_SCHEME"
            return unavailable

        price_completeness = completeness.get("seller_price")
        commission_completeness = completeness.get("commission_rate")
        if (not isinstance(price_completeness, dict)
                or not isinstance(commission_completeness, dict)
                or price_completeness.get("complete") is not True
                or commission_completeness.get("complete") is not True
                or provenance.get("price") != "ozon_current_seller_price"
                or provenance.get("commission_rate") != "ozon_current_fbo_rate"):
            unavailable["reason"] = "CURRENT_PRICE_COMMISSION_NOT_CONFIRMED"
            return unavailable

        price_cents = self._price_cents(suggested.get("price"))
        rate = self._rate(suggested.get("commission_rate"))
        source_periods = (
            periods.get("seller_price_as_of"),
            periods.get("commission_rate_as_of"),
        )
        observed_at = self._timestamp(source_periods[0])
        commission_as_of = self._timestamp(source_periods[1])
        snapshot_id = snapshot.get("snapshot_id")
        if price_cents is None or rate is None:
            unavailable["reason"] = "CURRENT_PRICE_COMMISSION_INVALID"
            return unavailable
        if (observed_at is None or commission_as_of is None
                or source_periods[0] != source_periods[1]):
            unavailable["reason"] = "CURRENT_SOURCE_TIMESTAMP_MISMATCH"
            return unavailable
        if not isinstance(snapshot_id, str) or not self._SNAPSHOT_ID.fullmatch(snapshot_id):
            unavailable["reason"] = "CURRENT_SOURCE_SNAPSHOT_ID_INVALID"
            return unavailable

        effective_day = observed_at.date().isoformat()
        point_profile = {
            "profile_id": "current-" + snapshot_id,
            "revision": 1,
            "state_revision": 1,
            "owner_id": owner_id,
            "store_id": store_id,
            "identity": {
                "product_id": product_id,
                "offer_id": offer_id,
                "sku": sku,
            },
            "sale_schema": "FBO",
            "price_basis": "SELLER_PRICE_RUB",
            "currency": "RUB",
            "origin": "CURRENT_PRICE_POINT",
            "source_ref": self.SOURCE_REF,
            "recorded_at": observed_at.isoformat(),
            "observed_at": observed_at.isoformat(),
            "effective_from": effective_day,
            "effective_to": effective_day,
            "bands": [{
                "price_from_cents": price_cents,
                "price_to_cents": price_cents,
                "commission_rate": format(rate, "f"),
            }],
        }
        return {
            "error": False,
            "status": "CURRENT_PRICE_POINT_AVAILABLE",
            "range_status": self.RANGE_STATUS,
            "reason": self.RANGE_REASON,
            "current_point_available": True,
            "current_price_cents": price_cents,
            "current_rate": format(rate, "f"),
            "observed_at": observed_at.isoformat(),
            "profiles": [point_profile],
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _unavailable(cls):
        return {
            "error": False,
            "status": "CURRENT_PRICE_POINT_UNAVAILABLE",
            "range_status": cls.RANGE_STATUS,
            "reason": cls.RANGE_REASON,
            "current_point_available": False,
            "current_price_cents": None,
            "current_rate": None,
            "observed_at": None,
            "profiles": [],
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _text(cls, value):
        if isinstance(value, bool) or value is None or not isinstance(value, (str, int)):
            return None
        text = str(value).strip()
        if (not text or len(text) > cls.MAX_TEXT_LENGTH
                or any(ord(char) < 32 or ord(char) == 127 for char in text)):
            return None
        return text

    @classmethod
    def _decimal(cls, value):
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            return None
        text = str(value).strip()
        if not text or len(text) > cls.MAX_TEXT_LENGTH:
            return None
        try:
            result = Decimal(text)
        except (InvalidOperation, ValueError):
            return None
        return result if result.is_finite() else None

    @classmethod
    def _price_cents(cls, value):
        amount = cls._decimal(value)
        if amount is None or amount <= 0:
            return None
        max_cents = UnitPriceTariffResolver.MAX_PRICE_CENTS
        if amount < Decimal("0.01") or amount > Decimal(max_cents) / 100:
            return None
        sign, digits, exponent = amount.as_tuple()
        if sign:
            return None
        coefficient_text = "".join(str(digit) for digit in digits) or "0"
        coefficient = int(coefficient_text)
        cents_exponent = exponent + 2
        if cents_exponent < 0:
            places = -cents_exponent
            if places > len(coefficient_text):
                return None
            divisor = 10 ** places
            if coefficient % divisor:
                return None
            cents = coefficient // divisor
        else:
            if len(coefficient_text) + cents_exponent > len(str(max_cents)):
                return None
            cents = coefficient * (10 ** cents_exponent)
        return cents if 1 <= cents <= max_cents else None    @classmethod
    def _rate(cls, value):
        rate = cls._decimal(value)
        if (rate is None or not Decimal("0") <= rate <= Decimal("100")
                or len(rate.as_tuple().digits) > UnitPriceTariffResolver.MAX_RATE_DIGITS
                or (not rate.is_zero()
                    and rate.adjusted() < UnitPriceTariffResolver.MIN_RATE_ADJUSTED_EXPONENT)):
            return None
        return rate

    @staticmethod
    def _timestamp(value):
        if not isinstance(value, str) or len(value) > 40:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed