"""Parse owner-entered seller-price commission points and inclusive ranges."""

from datetime import date
from decimal import Decimal, InvalidOperation
import re


class UnitPriceTariffInputParser:
    MAX_TEXT_LENGTH = 4096
    MAX_LINES = 20
    _PRICE = r"[0-9][0-9 \u00a0\u202f]*(?:[.,][0-9]{1,2})?"
    _RATE = r"[0-9]+(?:[.,][0-9]{1,12})?"
    _POINT = re.compile(rf"^\s*({_PRICE})\s*(?:₽)?\s*(?:=|:)\s*({_RATE})\s*%?\s*$", re.IGNORECASE)
    _RANGE = re.compile(rf"^\s*({_PRICE})\s*(?:-|–|—|\.\.)\s*({_PRICE})\s*(?:₽)?\s*(?:=|:)\s*({_RATE})\s*%?\s*$", re.IGNORECASE)
    _RANGE_WORDS = re.compile(rf"^\s*от\s*({_PRICE})\s*до\s*({_PRICE})\s*(?:₽)?\s*(?:=|:)\s*({_RATE})\s*%?\s*$", re.IGNORECASE)
    _DATE = re.compile(r"^\s*(?:дата|действует\s+с)\s*:\s*(\d{4}-\d{2}-\d{2})\s*$", re.IGNORECASE)

    @classmethod
    def parse(cls, text, *, default_date):
        if not isinstance(text, str) or not text.strip() or len(text) > cls.MAX_TEXT_LENGTH:
            return {"error": True, "code": "TARIFF_INPUT_EMPTY_OR_TOO_LONG"}
        if isinstance(default_date, date):
            effective_from = default_date
        elif isinstance(default_date, str):
            try:
                effective_from = date.fromisoformat(default_date)
            except ValueError:
                return {"error": True, "code": "TARIFF_DEFAULT_DATE_INVALID"}
        else:
            return {"error": True, "code": "TARIFF_DEFAULT_DATE_INVALID"}

        lines = [line.strip() for line in re.split(r"[\r\n;]+", text) if line.strip()]
        if not lines or len(lines) > cls.MAX_LINES + 1:
            return {"error": True, "code": "TARIFF_BAND_COUNT_LIMIT"}
        first_date = cls._DATE.fullmatch(lines[0])
        if first_date:
            try:
                effective_from = date.fromisoformat(first_date.group(1))
            except ValueError:
                return {"error": True, "code": "TARIFF_EFFECTIVE_DATE_INVALID"}
            lines = lines[1:]
        if not lines or len(lines) > cls.MAX_LINES:
            return {"error": True, "code": "TARIFF_BAND_COUNT_LIMIT"}

        bands = []
        for line in lines:
            point = cls._POINT.fullmatch(line)
            if point:
                lower_value, rate_value = point.groups()
                upper_value = lower_value
            else:
                matched = cls._RANGE.fullmatch(line) or cls._RANGE_WORDS.fullmatch(line)
                if not matched:
                    return {"error": True, "code": "TARIFF_LINE_FORMAT_INVALID"}
                lower_value, upper_value, rate_value = matched.groups()
            lower = cls._price_cents(lower_value)
            upper = cls._price_cents(upper_value)
            rate = cls._rate(rate_value)
            if lower is None or upper is None or lower > upper or rate is None:
                return {"error": True, "code": "TARIFF_LINE_VALUE_INVALID"}
            bands.append({
                "price_from_cents": lower,
                "price_to_cents": upper,
                "commission_rate": "0" if rate.is_zero() else format(rate.normalize(), "f"),
            })
        bands.sort(key=lambda band: (band["price_from_cents"], band["price_to_cents"]))
        if any(left["price_to_cents"] >= right["price_from_cents"] for left, right in zip(bands, bands[1:])):
            return {"error": True, "code": "TARIFF_BANDS_OVERLAP"}
        return {
            "error": False,
            "effective_from": effective_from.isoformat(),
            "bands": bands,
        }

    @classmethod
    def _price_cents(cls, value):
        try:
            amount = Decimal(re.sub(r"[ \u00a0\u202f]", "", value).replace(",", "."))
            cents = amount * 100
        except (InvalidOperation, ValueError, TypeError):
            return None
        if (not amount.is_finite() or amount <= 0 or cents != cents.to_integral_value()
                or cents > Decimal("999999999999999")):
            return None
        return int(cents)

    @staticmethod
    def _rate(value):
        try:
            rate = Decimal(value.replace(",", "."))
        except (InvalidOperation, ValueError, TypeError):
            return None
        if (not rate.is_finite() or rate < 0 or rate > 100
                or len(rate.as_tuple().digits) > 28
                or (not rate.is_zero() and rate.adjusted() < -12)):
            return None
        return rate
