"""Pure, fail-closed tariff resolution for seller-price scenarios."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re


class UnitPriceTariffResolver:
    """Resolve one commission rate without performing I/O or inferring bands."""

    VERSION = 1
    MAX_PROFILES = 20
    MAX_BANDS_PER_PROFILE = 20
    # Match the current forward calculator's maximum supported 13-digit price.
    MAX_PRICE_CENTS = 999_999_999_999_999
    MAX_TEXT_LENGTH = 128
    MAX_RATE_DIGITS = 28
    MIN_RATE_ADJUSTED_EXPONENT = -12
    REQUIRED_IDENTITY_FIELDS = (
        "owner_id", "store_id", "product_id", "offer_id", "sku",
    )
    PROFILE_ORIGINS = {
        "CONFIRMED_OFFICIAL_SOURCE",
        "MANUAL_SELLER_ASSUMPTION",
        "CURRENT_PRICE_POINT",
    }
    _SOURCE_REF_PATTERN = re.compile(r"[A-Za-z0-9_.:/-]{1,128}\Z")

    def resolve(
        self,
        *,
        seller_price_cents,
        identity,
        sale_schema,
        effective_date,
        profiles,
        selected_profile_id=None,
        selected_revision=None,
        selected_state_revision=None,
    ):
        """Resolve an exact seller-price point from explicitly scoped profiles.

        A profile is selected only when its complete identity, scheme, date and
        inclusive cents range match. Multiple applicable profiles fail closed
        unless a caller supplies an exact profile/revision selection.
        """
        request = self._normalize_request(
            seller_price_cents, identity, sale_schema, effective_date, profiles,
            selected_profile_id, selected_revision, selected_state_revision,
        )
        if request.get("error") is True:
            return request
        if request["sale_schema"] != "FBO":
            return self._unavailable(
                "UNSUPPORTED_SCHEME", "FBO_ONLY_SCENARIO_SUPPORTED",
                request["seller_price_cents"],
            )

        scoped = []
        expired = False
        not_yet_effective = False
        current_points = []
        for candidate in request["profiles"]:
            scope_status = self._profile_scope_status(candidate, request["identity"])
            if scope_status == "OUT_OF_SCOPE":
                continue
            if scope_status == "INVALID":
                return self._error("TARIFF_PROFILE_INVALID", "PROFILE_SCOPE_INVALID")
            normalized = self._normalize_profile(candidate)
            if normalized.get("error") is True:
                return normalized
            if normalized["sale_schema"] != request["sale_schema"]:
                continue
            if not self._same_identity(normalized["identity"], request["identity"]):
                continue
            if request["selected_profile_id"] is not None and (
                normalized["profile_id"] != request["selected_profile_id"]
                or normalized["revision"] != request["selected_revision"]
            ):
                continue
            state_revision = request["selected_state_revision"]
            if state_revision is not None and normalized["state_revision"] != state_revision:
                return self._unavailable(
                    "CONFLICT", "SELECTED_PROFILE_STATE_STALE",
                    request["seller_price_cents"], normalized,
                )

            day = request["effective_date"]
            if normalized["effective_to"] is not None and day > normalized["effective_to"]:
                expired = True
                continue
            if day < normalized["effective_from"]:
                not_yet_effective = True
                continue
            if normalized["origin"] == "CURRENT_PRICE_POINT":
                if request["seller_price_cents"] != normalized["bands"][0]["price_from_cents"]:
                    current_points.append(normalized)
                    continue
            scoped.append(normalized)

        if request["selected_profile_id"] is not None and not scoped:
            if expired:
                return self._unavailable(
                    "EXPIRED", "PROFILE_EXPIRED", request["seller_price_cents"]
                )
            return self._unavailable(
                "UNKNOWN", "SELECTED_PROFILE_NOT_APPLICABLE",
                request["seller_price_cents"],
            )

        matches = []
        profiles_with_gap = []
        for profile in scoped:
            band = next(
                (
                    item for item in profile["bands"]
                    if item["price_from_cents"] <= request["seller_price_cents"]
                    <= item["price_to_cents"]
                ),
                None,
            )
            if band is None:
                profiles_with_gap.append(profile)
            else:
                matches.append((profile, band))

        if len(matches) > 1:
            return self._unavailable(
                "CONFLICT", "MULTIPLE_APPLICABLE_PROFILES",
                request["seller_price_cents"],
            )
        if len(matches) == 1:
            profile, band = matches[0]
            status = {
                "CONFIRMED_OFFICIAL_SOURCE": "CONFIRMED_RANGE",
                "MANUAL_SELLER_ASSUMPTION": "MANUAL_RANGE",
                "CURRENT_PRICE_POINT": "CURRENT_PRICE_POINT_ONLY",
            }[profile["origin"]]
            return {
                "error": False,
                "available": True,
                "status": status,
                "reason": None,
                "commission_rate": band["commission_rate"],
                "price_basis": "SELLER_PRICE_RUB",
                "seller_price_cents": request["seller_price_cents"],
                "matched_band": {
                    "price_from_cents": band["price_from_cents"],
                    "price_to_cents": band["price_to_cents"],
                },
                "profile": self._profile_projection(profile),
                "read_only": True,
                "executed": False,
            }
        if current_points and not scoped:
            selected = current_points[0] if len(current_points) == 1 else None
            if selected is not None:
                return self._unavailable(
                    "CURRENT_PRICE_POINT_ONLY", "CURRENT_PRICE_DOES_NOT_CONFIRM_CANDIDATE",
                    request["seller_price_cents"], selected,
                )
            return self._unavailable(
                "CONFLICT", "MULTIPLE_CURRENT_PRICE_POINTS",
                request["seller_price_cents"],
            )
        if expired and not scoped:
            return self._unavailable("EXPIRED", "PROFILE_EXPIRED", request["seller_price_cents"])
        if not_yet_effective and not scoped:
            return self._unavailable(
                "UNKNOWN", "PROFILE_NOT_YET_EFFECTIVE", request["seller_price_cents"]
            )
        reason = "PRICE_OUTSIDE_PROFILE_BANDS" if profiles_with_gap else "NO_APPLICABLE_PROFILE"
        return self._unavailable("UNKNOWN", reason, request["seller_price_cents"])

    def _normalize_request(
        self, price_cents, identity, sale_schema, effective_date, profiles,
        selected_profile_id, selected_revision, selected_state_revision,
    ):
        if type(price_cents) is not int or not 1 <= price_cents <= self.MAX_PRICE_CENTS:
            return self._error("TARIFF_REQUEST_INVALID", "SELLER_PRICE_CENTS_INVALID")
        normalized_identity = self._normalize_identity(identity)
        if normalized_identity is None:
            return self._error("TARIFF_REQUEST_INVALID", "IDENTITY_INCOMPLETE")
        if not isinstance(sale_schema, str) or not sale_schema.strip():
            return self._error("TARIFF_REQUEST_INVALID", "SALE_SCHEMA_INVALID")
        normalized_schema = sale_schema.strip().upper()
        if len(normalized_schema) > 16 or not normalized_schema.isascii():
            return self._error("TARIFF_REQUEST_INVALID", "SALE_SCHEMA_INVALID")
        day = self._date(effective_date)
        if day is None:
            return self._error("TARIFF_REQUEST_INVALID", "EFFECTIVE_DATE_INVALID")
        if not isinstance(profiles, (list, tuple)) or len(profiles) > self.MAX_PROFILES:
            return self._error("TARIFF_REQUEST_INVALID", "PROFILE_COUNT_LIMIT")
        selection = (selected_profile_id, selected_revision, selected_state_revision)
        if any(value is not None for value in selection):
            profile_id = self._safe_text(selected_profile_id)
            if (
                profile_id is None
                or type(selected_revision) is not int or selected_revision < 1
                or (selected_state_revision is not None and (
                    type(selected_state_revision) is not int or selected_state_revision < 1
                ))
            ):
                return self._error("TARIFF_REQUEST_INVALID", "PROFILE_SELECTION_INVALID")
        else:
            profile_id = None
        return {
            "error": False,
            "seller_price_cents": price_cents,
            "identity": normalized_identity,
            "sale_schema": normalized_schema,
            "effective_date": day,
            "profiles": list(profiles),
            "selected_profile_id": profile_id,
            "selected_revision": selected_revision,
            "selected_state_revision": selected_state_revision,
        }

    def _normalize_profile(self, profile):
        if not isinstance(profile, dict):
            return self._error("TARIFF_PROFILE_INVALID", "PROFILE_NOT_OBJECT")
        profile_id = self._safe_text(profile.get("profile_id"))
        owner_id = self._safe_text(profile.get("owner_id"))
        store_id = self._safe_text(profile.get("store_id"))
        profile_identity = self._normalize_identity({
            "owner_id": owner_id,
            "store_id": store_id,
            **(profile.get("identity") if isinstance(profile.get("identity"), dict) else {}),
        })
        schema = profile.get("sale_schema")
        schema = schema.strip().upper() if isinstance(schema, str) else ""
        if (
            profile_id is None
            or profile_identity is None
            or type(profile.get("revision")) is not int or profile["revision"] < 1
            or type(profile.get("state_revision")) is not int or profile["state_revision"] < 1
            or schema != "FBO"
            or profile.get("price_basis") != "SELLER_PRICE_RUB"
            or profile.get("currency") != "RUB"
            or profile.get("origin") not in self.PROFILE_ORIGINS
        ):
            return self._error("TARIFF_PROFILE_INVALID", "PROFILE_METADATA_INVALID")
        start = self._date(profile.get("effective_from"))
        end = self._date(profile.get("effective_to")) if profile.get("effective_to") is not None else None
        if start is None or (profile.get("effective_to") is not None and end is None) or (end and end < start):
            return self._error("TARIFF_PROFILE_INVALID", "PROFILE_EFFECTIVE_DATES_INVALID")

        origin = profile["origin"]
        source_ref = self._safe_source_ref(profile.get("source_ref"))
        recorded_at = self._safe_timestamp(profile.get("recorded_at"))
        if origin == "MANUAL_SELLER_ASSUMPTION":
            if profile.get("confirmed_by_owner") is not True or recorded_at is None:
                return self._error("TARIFF_PROFILE_INVALID", "MANUAL_CONFIRMATION_REQUIRED")
        elif source_ref is None or recorded_at is None:
            return self._error("TARIFF_PROFILE_INVALID", "SOURCE_PROVENANCE_REQUIRED")

        raw_bands = profile.get("bands")
        if (
            not isinstance(raw_bands, (list, tuple))
            or not 1 <= len(raw_bands) <= self.MAX_BANDS_PER_PROFILE
        ):
            return self._error("TARIFF_PROFILE_INVALID", "BAND_COUNT_LIMIT")
        bands = []
        for item in raw_bands:
            if not isinstance(item, dict):
                return self._error("TARIFF_PROFILE_INVALID", "BAND_NOT_OBJECT")
            lower = item.get("price_from_cents")
            upper = item.get("price_to_cents")
            rate = self._rate(item.get("commission_rate"))
            if (
                type(lower) is not int or type(upper) is not int
                or not 1 <= lower <= upper <= self.MAX_PRICE_CENTS
                or rate is None
            ):
                return self._error("TARIFF_PROFILE_INVALID", "BAND_VALUES_INVALID")
            bands.append({
                "price_from_cents": lower,
                "price_to_cents": upper,
                "commission_rate": format(rate.normalize(), "f"),
            })
        bands.sort(key=lambda item: (item["price_from_cents"], item["price_to_cents"]))
        if any(
            previous["price_to_cents"] >= current["price_from_cents"]
            for previous, current in zip(bands, bands[1:])
        ):
            return self._error("TARIFF_PROFILE_INVALID", "BAND_OVERLAP")
        if origin == "CURRENT_PRICE_POINT" and (
            len(bands) != 1 or bands[0]["price_from_cents"] != bands[0]["price_to_cents"]
        ):
            return self._error("TARIFF_PROFILE_INVALID", "CURRENT_SOURCE_MUST_BE_A_POINT")
        if origin == "CURRENT_PRICE_POINT":
            observed = self._safe_timestamp(profile.get("observed_at"))
            if observed is None or observed.date() != start or end != start:
                return self._error("TARIFF_PROFILE_INVALID", "CURRENT_POINT_DATE_INVALID")
        return {
            "error": False,
            "profile_id": profile_id,
            "revision": profile["revision"],
            "state_revision": profile["state_revision"],
            "owner_id": owner_id,
            "store_id": store_id,
            "identity": profile_identity,
            "sale_schema": schema,
            "origin": origin,
            "source_ref": source_ref,
            "recorded_at": recorded_at.isoformat() if recorded_at else None,
            "effective_from": start,
            "effective_to": end,
            "bands": bands,
        }

    def _profile_scope_status(self, profile, identity):
        if not isinstance(profile, dict):
            return "INVALID"
        owner = self._safe_text(profile.get("owner_id"))
        store = self._safe_text(profile.get("store_id"))
        if owner is None or store is None:
            return "INVALID"
        if owner != identity["owner_id"] or store != identity["store_id"]:
            return "OUT_OF_SCOPE"
        raw_identity = profile.get("identity")
        if not isinstance(raw_identity, dict):
            return "INVALID"
        normalized = self._normalize_identity({
            "owner_id": owner,
            "store_id": store,
            **raw_identity,
        })
        if normalized is None:
            return "INVALID"
        return "IN_SCOPE" if self._same_identity(normalized, identity) else "OUT_OF_SCOPE"

    def _normalize_identity(self, identity):
        if not isinstance(identity, dict):
            return None
        normalized = {}
        for field in self.REQUIRED_IDENTITY_FIELDS:
            value = self._safe_text(identity.get(field))
            if value is None:
                return None
            normalized[field] = value
        return normalized

    def _same_identity(self, left, right):
        return all(left.get(field) == right.get(field) for field in self.REQUIRED_IDENTITY_FIELDS)

    def _rate(self, value):
        if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
            return None
        try:
            rate = Decimal(str(value).strip())
        except (InvalidOperation, TypeError, ValueError):
            return None
        if (
            not rate.is_finite()
            or rate < 0 or rate > 100
            or len(rate.as_tuple().digits) > self.MAX_RATE_DIGITS
            or (not rate.is_zero() and rate.adjusted() < self.MIN_RATE_ADJUSTED_EXPONENT)
        ):
            return None
        return rate

    def _date(self, value):
        if isinstance(value, datetime):
            return None
        if isinstance(value, date):
            return value
        if not isinstance(value, str) or len(value) != 10:
            return None
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.isoformat() == value else None

    def _safe_timestamp(self, value):
        if not isinstance(value, str) or len(value) > 40 or any(ord(char) < 32 for char in value):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None

    def _safe_text(self, value):
        if isinstance(value, bool) or value is None or not isinstance(value, (str, int)):
            return None
        text = str(value).strip()
        if not text or len(text) > self.MAX_TEXT_LENGTH or any(ord(char) < 32 or ord(char) == 127 for char in text):
            return None
        return text

    def _safe_source_ref(self, value):
        text = self._safe_text(value)
        if text is None or not self._SOURCE_REF_PATTERN.fullmatch(text):
            return None
        return text

    def _profile_projection(self, profile):
        return {
            "profile_id": profile["profile_id"],
            "revision": profile["revision"],
            "state_revision": profile["state_revision"],
            "origin": profile["origin"],
            "source_ref": profile["source_ref"],
            "recorded_at": profile["recorded_at"],
            "effective_from": profile["effective_from"].isoformat(),
            "effective_to": profile["effective_to"].isoformat() if profile["effective_to"] else None,
        }

    def _unavailable(self, status, reason, price_cents, profile=None):
        result = {
            "error": False,
            "available": False,
            "status": status,
            "reason": reason,
            "commission_rate": None,
            "price_basis": "SELLER_PRICE_RUB",
            "seller_price_cents": price_cents,
            "matched_band": None,
            "read_only": True,
            "executed": False,
        }
        if profile:
            result["profile"] = self._profile_projection(profile)
        return result

    def _error(self, code, reason):
        return {
            "error": True,
            "code": code,
            "reason": reason,
            "read_only": True,
            "executed": False,
        }
