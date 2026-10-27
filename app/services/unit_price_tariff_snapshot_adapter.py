"""Allowlisted immutable tariff snapshots for saved unit-price plans."""

from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import re

from services.unit_price_tariff_resolver import UnitPriceTariffResolver


class UnitPriceTariffSnapshotAdapter:
    VERSION = 1
    AVAILABLE_STATUSES = frozenset({
        "CONFIRMED_RANGE", "MANUAL_RANGE", "CURRENT_PRICE_POINT_ONLY",
    })
    UNKNOWN_STATUSES = frozenset({
        "UNKNOWN", "EXPIRED", "CONFLICT", "UNSUPPORTED_SCHEME",
        "SOURCE_UNAVAILABLE",
    })
    SNAPSHOT_FIELDS = frozenset({
        "snapshot_version", "status", "reason", "effective_date", "price_basis",
        "seller_price_cents", "commission_rate", "matched_band", "selected_profile", "profiles",
    })
    PROFILE_FIELDS = frozenset({
        "owner_id", "store_id", "identity",
        "profile_id", "revision", "state_revision", "origin", "source_ref",
        "recorded_at", "observed_at", "effective_from", "effective_to",
        "sale_schema", "price_basis", "currency", "confirmed_by_owner", "bands",
    })
    BAND_FIELDS = frozenset({"price_from_cents", "price_to_cents", "commission_rate"})
    _CODE = re.compile(r"[A-Z0-9_]{1,80}\Z")

    @classmethod
    def freeze(cls, resolution, selected_profile=None, *, candidate_profiles=None,
               effective_date=None):
        """Project a resolver result and its selected full band profile safely."""
        resolution = resolution if isinstance(resolution, dict) else {}
        available = resolution.get("available") is True
        status = resolution.get("status")
        reason = resolution.get("reason")
        if available and status not in cls.AVAILABLE_STATUSES:
            return None
        if not available and status not in cls.UNKNOWN_STATUSES:
            status = "UNKNOWN" if status == "CURRENT_PRICE_POINT_ONLY" else "SOURCE_UNAVAILABLE"
            reason = reason or "TARIFF_NOT_CONFIRMED"
        price = resolution.get("seller_price_cents")
        basis = resolution.get("price_basis", "SELLER_PRICE_RUB")
        day = effective_date or resolution.get("effective_date")
        if not cls._valid_date(day) or type(price) is not int or price < 1 or basis != "SELLER_PRICE_RUB":
            return None
        clean_reason = cls._code(reason) if reason is not None else None
        if reason is not None and clean_reason is None:
            return None
        result = {
            "snapshot_version": cls.VERSION,
            "status": status,
            "reason": clean_reason,
            "effective_date": day,
            "price_basis": basis,
            "seller_price_cents": price,
            "commission_rate": None,
            "matched_band": None,
            "selected_profile": None,
            "profiles": [],
        }
        raw_profiles = list(candidate_profiles or [])
        if selected_profile is not None and not any(
                isinstance(item, dict)
                and item.get("profile_id") == selected_profile.get("profile_id")
                and item.get("revision") == selected_profile.get("revision")
                and item.get("state_revision") == selected_profile.get("state_revision")
                for item in raw_profiles):
            raw_profiles.append(selected_profile)
        if len(raw_profiles) > UnitPriceTariffResolver.MAX_PROFILES:
            return None
        profiles = []
        for item in raw_profiles:
            projected = cls._profile_projection(item)
            if projected is None:
                return None
            profiles.append(projected)
        profiles.sort(key=lambda item: (item["profile_id"], item["revision"]))
        if len({(item["profile_id"], item["revision"]) for item in profiles}) != len(profiles):
            return None
        result["profiles"] = profiles
        if not available:
            return result
        if not isinstance(selected_profile, dict):
            return None
        profile = cls._profile_projection(selected_profile)
        matched = resolution.get("matched_band")
        if profile is None or not isinstance(matched, dict):
            return None
        rate = cls._rate(resolution.get("commission_rate"))
        lower = matched.get("price_from_cents")
        upper = matched.get("price_to_cents")
        if (rate is None or type(lower) is not int or type(upper) is not int
                or lower > price or upper < price):
            return None
        band = next((item for item in profile["bands"]
                     if item["price_from_cents"] == lower
                     and item["price_to_cents"] == upper
                     and Decimal(item["commission_rate"]) == rate), None)
        if band is None:
            return None
        result.update({
            "commission_rate": format(rate.normalize(), "f"),
            "matched_band": {"price_from_cents": lower, "price_to_cents": upper},
            "selected_profile": {
                "profile_id": profile["profile_id"],
                "revision": profile["revision"],
                "state_revision": profile["state_revision"],
            },
        })
        return result

    @classmethod
    def validate(cls, snapshot, identity, inputs):
        """Validate a saved snapshot by resolving its frozen profile again."""
        if (not isinstance(snapshot, dict) or set(snapshot) != cls.SNAPSHOT_FIELDS
                or snapshot.get("snapshot_version") != cls.VERSION
                or snapshot.get("price_basis") != "SELLER_PRICE_RUB"
                or not cls._valid_date(snapshot.get("effective_date"))
                or type(snapshot.get("seller_price_cents")) is not int
                or snapshot["seller_price_cents"] < 1
                or not isinstance(identity, dict) or not isinstance(inputs, dict)):
            return None
        price_cents = cls.price_to_cents(inputs.get("price"))
        if price_cents != snapshot["seller_price_cents"]:
            return None
        status = snapshot.get("status")
        reason = snapshot.get("reason")
        if reason is not None and cls._code(reason) is None:
            return None
        identity_for_resolver = {
            "owner_id": str(identity.get("owner_id") or ""),
            "store_id": str(identity.get("store_id") or ""),
            "product_id": str(identity.get("product_id") or ""),
            "offer_id": str(identity.get("offer_id") or ""),
            "sku": str(identity.get("sku") or ""),
        }
        raw_profiles = snapshot.get("profiles")
        if not isinstance(raw_profiles, list) or len(raw_profiles) > UnitPriceTariffResolver.MAX_PROFILES:
            return None
        profiles = []
        for projection in raw_profiles:
            profile = cls._profile_restore(projection, identity_for_resolver)
            if profile is None:
                return None
            profiles.append(profile)
        if status in cls.UNKNOWN_STATUSES:
            if (snapshot.get("commission_rate") is not None
                    or snapshot.get("matched_band") is not None
                    or snapshot.get("selected_profile") is not None
                    or inputs.get("commission_rate") is not None):
                return None
            if status == "SOURCE_UNAVAILABLE":
                return deepcopy(snapshot)
            resolver = UnitPriceTariffResolver()
            resolution = resolver.resolve(
                seller_price_cents=price_cents,
                identity=identity_for_resolver,
                sale_schema="FBO",
                effective_date=snapshot["effective_date"],
                profiles=profiles,
            )
            resolved_status = resolution.get("status")
            if (resolution.get("available") is not False
                    or (resolved_status != status and not (
                        status == "UNKNOWN" and resolved_status == "CURRENT_PRICE_POINT_ONLY"
                    ))
                    or resolution.get("reason") != reason):
                return None
            return deepcopy(snapshot)
        if status not in cls.AVAILABLE_STATUSES or not profiles:
            return None
        band = snapshot.get("matched_band")
        selected = snapshot.get("selected_profile")
        rate = cls._rate(snapshot.get("commission_rate"))
        if (not isinstance(band, dict)
                or set(band) != {"price_from_cents", "price_to_cents"}
                or type(band.get("price_from_cents")) is not int
                or type(band.get("price_to_cents")) is not int
                or band["price_from_cents"] > price_cents
                or band["price_to_cents"] < price_cents
                or not isinstance(selected, dict)
                or set(selected) != {"profile_id", "revision", "state_revision"}
                or not any(
                    item["profile_id"] == selected.get("profile_id")
                    and item["revision"] == selected.get("revision")
                    and item["state_revision"] == selected.get("state_revision")
                    for item in profiles
                )
                or rate is None or cls._rate(inputs.get("commission_rate")) != rate):
            return None
        resolver = UnitPriceTariffResolver()
        resolution = resolver.resolve(
            seller_price_cents=price_cents,
            identity={
                "owner_id": str(identity.get("owner_id") or ""),
                "store_id": str(identity.get("store_id") or ""),
                "product_id": str(identity.get("product_id") or ""),
                "offer_id": str(identity.get("offer_id") or ""),
                "sku": str(identity.get("sku") or ""),
            },
            sale_schema="FBO",
            effective_date=snapshot["effective_date"],
            profiles=profiles,
            selected_profile_id=selected["profile_id"],
            selected_revision=selected["revision"],
            selected_state_revision=selected["state_revision"],
        )
        if (resolution.get("available") is not True
                or resolution.get("status") != status
                or cls._rate(resolution.get("commission_rate")) != rate
                or resolution.get("matched_band") != band
                or resolution.get("profile", {}).get("profile_id") != selected["profile_id"]
                or resolution.get("profile", {}).get("revision") != selected["revision"]
                or resolution.get("profile", {}).get("state_revision") != selected["state_revision"]):
            return None
        return deepcopy(snapshot)

    @classmethod
    def resolve_frozen(cls, snapshot, identity, seller_price_cents):
        """Resolve a candidate from the saved profile set with no repository/API reads."""
        if (not isinstance(snapshot, dict) or snapshot.get("snapshot_version") != cls.VERSION
                or not isinstance(identity, dict)
                or type(seller_price_cents) is not int or seller_price_cents < 1
                or not cls._valid_date(snapshot.get("effective_date"))):
            return {"error": True, "code": "TARIFF_SNAPSHOT_INVALID"}
        identity_for_resolver = {
            "owner_id": str(identity.get("owner_id") or ""),
            "store_id": str(identity.get("store_id") or ""),
            "product_id": str(identity.get("product_id") or ""),
            "offer_id": str(identity.get("offer_id") or ""),
            "sku": str(identity.get("sku") or ""),
        }
        projections = snapshot.get("profiles")
        if not isinstance(projections, list) or len(projections) > UnitPriceTariffResolver.MAX_PROFILES:
            return {"error": True, "code": "TARIFF_SNAPSHOT_INVALID"}
        profiles = []
        for projection in projections:
            profile = cls._profile_restore(projection, identity_for_resolver)
            if profile is None:
                return {"error": True, "code": "TARIFF_SNAPSHOT_INVALID"}
            profiles.append(profile)
        if snapshot.get("status") == "SOURCE_UNAVAILABLE":
            return {
                "error": False, "available": False, "status": "SOURCE_UNAVAILABLE",
                "reason": snapshot.get("reason"), "seller_price_cents": seller_price_cents,
                "price_basis": "SELLER_PRICE_RUB", "effective_date": snapshot["effective_date"],
                "candidate_profiles": profiles, "selected_profile": None,
                "read_only": True, "executed": False,
            }
        if not profiles:
            return {
                "error": False, "available": False, "status": "UNKNOWN",
                "reason": "NO_APPLICABLE_PROFILE", "seller_price_cents": seller_price_cents,
                "price_basis": "SELLER_PRICE_RUB", "effective_date": snapshot["effective_date"],
                "candidate_profiles": [], "selected_profile": None,
            }
        selected_profile_id = None
        selected_revision = None
        selected_state_revision = None
        selected_meta = snapshot.get("selected_profile")
        if seller_price_cents == snapshot.get("seller_price_cents") and isinstance(selected_meta, dict):
            selected_profile = next((
                item for item in profiles
                if item.get("profile_id") == selected_meta.get("profile_id")
                and item.get("revision") == selected_meta.get("revision")
                and item.get("state_revision") == selected_meta.get("state_revision")
                and item.get("source_ref") == "MANUAL_SCENARIO_COMMISSION_OVERRIDE"
                and len(item.get("bands") or []) == 1
                and item["bands"][0]["price_from_cents"] == snapshot.get("seller_price_cents")
                and item["bands"][0]["price_to_cents"] == snapshot.get("seller_price_cents")
            ), None)
            if selected_profile is not None:
                # An explicit manual edit is a confirmed point override for
                # the captured price only. At that exact price it wins over
                # an overlapping stored range; at every other price the
                # complete frozen range set is resolved normally.
                selected_profile_id = selected_profile["profile_id"]
                selected_revision = selected_profile["revision"]
                selected_state_revision = selected_profile["state_revision"]
        resolution = UnitPriceTariffResolver().resolve(
            seller_price_cents=seller_price_cents,
            identity=identity_for_resolver,
            sale_schema="FBO",
            effective_date=snapshot["effective_date"],
            profiles=profiles,
            selected_profile_id=selected_profile_id,
            selected_revision=selected_revision,
            selected_state_revision=selected_state_revision,
        )
        selected = None
        if resolution.get("available") is True:
            selected_meta = resolution.get("profile") or {}
            selected = next((profile for profile in profiles
                             if profile.get("profile_id") == selected_meta.get("profile_id")
                             and profile.get("revision") == selected_meta.get("revision")
                             and profile.get("state_revision") == selected_meta.get("state_revision")), None)
        return {
            **resolution,
            "effective_date": snapshot["effective_date"],
            "candidate_profiles": profiles,
            "selected_profile": deepcopy(selected),
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _profile_projection(cls, profile):
        bands = profile.get("bands")
        if not isinstance(bands, list) or not 1 <= len(bands) <= 20:
            return None
        clean_bands = []
        for band in bands:
            if not isinstance(band, dict) or set(band) != cls.BAND_FIELDS:
                return None
            low = band.get("price_from_cents")
            high = band.get("price_to_cents")
            rate = cls._rate(band.get("commission_rate"))
            if type(low) is not int or type(high) is not int or not 1 <= low <= high:
                return None
            if rate is None:
                return None
            clean_bands.append({
                "price_from_cents": low, "price_to_cents": high,
                "commission_rate": format(rate.normalize(), "f"),
            })
        clean_bands.sort(key=lambda row: (row["price_from_cents"], row["price_to_cents"]))
        if any(a["price_to_cents"] >= b["price_from_cents"] for a, b in zip(clean_bands, clean_bands[1:])):
            return None
        origin = profile.get("origin")
        if origin not in UnitPriceTariffResolver.PROFILE_ORIGINS:
            return None
        identity = profile.get("identity")
        if not isinstance(identity, dict) or set(identity) != {"product_id", "offer_id", "sku"}:
            return None
        projection = {
            "owner_id": cls._safe_text(profile.get("owner_id"), 128),
            "store_id": cls._safe_text(profile.get("store_id"), 128),
            "identity": {
                key: cls._safe_text(identity.get(key), limit)
                for key, limit in (("product_id", 80), ("offer_id", 120), ("sku", 64))
            },
            "profile_id": cls._safe_text(profile.get("profile_id"), 128),
            "revision": profile.get("revision"),
            "state_revision": profile.get("state_revision"),
            "origin": origin,
            "source_ref": cls._safe_text(profile.get("source_ref"), 128, optional=True),
            "recorded_at": cls._safe_text(profile.get("recorded_at"), 40),
            "observed_at": cls._safe_text(profile.get("observed_at"), 40, optional=True),
            "effective_from": profile.get("effective_from"),
            "effective_to": profile.get("effective_to"),
            "sale_schema": "FBO",
            "price_basis": "SELLER_PRICE_RUB",
            "currency": "RUB",
            "confirmed_by_owner": (
                profile.get("confirmed_by_owner")
                if profile.get("origin") == "MANUAL_SELLER_ASSUMPTION" else None
            ),
            "bands": clean_bands,
        }
        if (projection["owner_id"] is None or projection["store_id"] is None
                or any(value is None for value in projection["identity"].values())
                or projection["profile_id"] is None
                or type(projection["revision"]) is not int or projection["revision"] < 1
                or type(projection["state_revision"]) is not int or projection["state_revision"] < 1
                or projection["recorded_at"] is None
                or (origin == "MANUAL_SELLER_ASSUMPTION"
                    and projection["confirmed_by_owner"] is not True)
                or (origin != "MANUAL_SELLER_ASSUMPTION"
                    and projection["confirmed_by_owner"] is not None)
                or (profile.get("source_ref") is not None and projection["source_ref"] is None)
                or (profile.get("observed_at") is not None and projection["observed_at"] is None)
                or not cls._valid_date(projection["effective_from"])
                or (projection["effective_to"] is not None and not cls._valid_date(projection["effective_to"]))):
            return None
        return projection

    @classmethod
    def _profile_restore(cls, projection, identity):
        if not isinstance(projection, dict) or set(projection) != cls.PROFILE_FIELDS:
            return None
        profile = cls._profile_projection(projection)
        if (profile is None or profile != projection
                or profile["owner_id"] != identity.get("owner_id")
                or profile["store_id"] != identity.get("store_id")
                or profile["identity"] != {
                    key: identity.get(key)
                    for key in ("product_id", "offer_id", "sku")
                }):
            return None
        result = dict(profile)
        if profile.get("confirmed_by_owner") is not None:
            result["confirmed_by_owner"] = profile["confirmed_by_owner"]
        return result

    @staticmethod
    def price_to_cents(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            price = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if not price.is_finite() or price <= 0 or price * 100 != (price * 100).to_integral_value():
            return None
        cents = int(price * 100)
        return cents if cents <= UnitPriceTariffResolver.MAX_PRICE_CENTS else None

    @staticmethod
    def _rate(value):
        if isinstance(value, bool) or value is None or isinstance(value, float):
            return None
        try:
            rate = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if not rate.is_finite() or not 0 <= rate <= 100:
            return None
        return rate

    @staticmethod
    def _safe_text(value, maximum, optional=False):
        if value is None and optional:
            return None
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            return None
        text = str(value).strip()
        if not text or len(text) > maximum or any(ord(char) < 32 for char in text):
            return None
        return text

    @classmethod
    def _code(cls, value):
        return value if isinstance(value, str) and cls._CODE.fullmatch(value) else None

    @staticmethod
    def _valid_date(value):
        if not isinstance(value, str) or len(value) != 10:
            return False
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return False
        return parsed.isoformat() == value
