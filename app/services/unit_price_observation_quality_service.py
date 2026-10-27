"""Conservative quality/comparability gate for saved unit-price observations."""

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation


class UnitPriceObservationQualityService:
    """Assess evidence quality without claiming price causality or confidence."""

    MIN_WINDOW_DAYS = 3
    MAX_WINDOW_DAYS = 56
    DEFAULT_RECOMMENDED_WINDOW_DAYS = 7
    DEFAULT_SMALL_SAMPLE_UNITS = 30
    DEFAULT_MAX_EVIDENCE_AGE_DAYS = 14
    MAX_CANDIDATES = 10
    MAX_SUCCESSFUL_UNITS = 10_000
    _FACT_COMPLETENESS = (
        "price_history", "successful_units", "finance", "advertising", "tariff",
        "tax", "unit_cost", "returns", "analytics", "window", "deduplication",
    )

    def assess(
        self, candidates, *, now=None, recommended_window_days=DEFAULT_RECOMMENDED_WINDOW_DAYS,
        small_sample_units=DEFAULT_SMALL_SAMPLE_UNITS,
        max_evidence_age_days=DEFAULT_MAX_EVIDENCE_AGE_DAYS,
    ):
        """Return safe assessment payload for two or more candidate results.

        Each candidate has `result` and may include an immutable, canonical
        `assumption_signature` for a model-only comparison. No identifiers are
        copied into the assessment payload.
        """
        now = now or datetime.now(timezone.utc)
        if not self._valid_configuration(
            now, recommended_window_days, small_sample_units, max_evidence_age_days,
        ):
            return self._error("UNIT_PRICE_QUALITY_CONFIGURATION_INVALID")
        if not isinstance(candidates, list) or len(candidates) > self.MAX_CANDIDATES:
            return self._error("UNIT_PRICE_QUALITY_CANDIDATES_INVALID")

        assessed = [self._assess_candidate(
            candidate, now=now, recommended_window_days=recommended_window_days,
            small_sample_units=small_sample_units,
            max_evidence_age_days=max_evidence_age_days,
        ) for candidate in candidates]
        reasons = []
        if len(assessed) < 2:
            reasons.append("AT_LEAST_TWO_PRICE_VARIANTS_REQUIRED")
        if assessed and not all(item["identity"] == assessed[0]["identity"] for item in assessed):
            reasons.append("PRODUCT_STORE_OR_SCHEME_MISMATCH")
        if assessed and not all(item["scope"] == assessed[0]["scope"] for item in assessed):
            reasons.append("OWNER_OR_STORE_SCOPE_MISMATCH")
        if len({item["price_cents"] for item in assessed if item["price_cents"] is not None}) < 2:
            reasons.append("PRICE_VARIANTS_NOT_DISTINCT")
        bases = {item["evidence_basis"] for item in assessed}
        if len(bases) != 1 or None in bases:
            reasons.append("EVIDENCE_BASIS_MISMATCH")
        metric_signatures = {
            tuple(
                value if isinstance(value, str) else None
                for value in (item.get("revenue_basis"), item.get("advertising_status"))
            )
            for item in (self._result_metrics(candidate) for candidate in candidates)
        }
        if len(metric_signatures) > 1:
            reasons.append("REVENUE_OR_ADVERTISING_BASIS_MISMATCH")
        source_signatures = {item.get("source_date_bases") for item in assessed}
        if len(source_signatures) > 1:
            reasons.append("SOURCE_DATE_BASIS_MISMATCH")
        signatures = {
            candidate.get("assumption_signature")
            for candidate in candidates if isinstance(candidate, dict)
            and isinstance(candidate.get("result"), dict)
            and candidate["result"].get("evidence_basis") == "MODELLED_FROM_OBSERVED_INPUTS"
        }
        if len(signatures) > 1:
            reasons.append("MODEL_ASSUMPTIONS_MISMATCH")

        if assessed and all(item.get("window") for item in assessed):
            first = assessed[0]
            for item in assessed[1:]:
                if item["window"]["timezone"] != first["window"]["timezone"]:
                    reasons.append("WINDOW_TIMEZONE_MISMATCH")
                if item["window"]["date_basis"] != first["window"]["date_basis"]:
                    reasons.append("WINDOW_DATE_BASIS_MISMATCH")
                if item["window"]["days"] != first["window"]["days"]:
                    reasons.append("WINDOW_DURATION_MISMATCH")
                if item["window"]["weekday_counts"] != first["window"]["weekday_counts"]:
                    reasons.append("WEEKDAY_COMPOSITION_MISMATCH")
            for index, item in enumerate(assessed):
                for other in assessed[index + 1:]:
                    if item["window"]["start"] <= other["window"]["end"] and other["window"]["start"] <= item["window"]["end"]:
                        reasons.append("OBSERVATION_WINDOWS_OVERLAP")

        for item in assessed:
            reasons.extend(item["reasons"])
        reasons = self._unique(reasons)
        warnings = self._unique(
            [warning for item in assessed for warning in item["warnings"]]
            + [
                "SAMPLE_THRESHOLDS_ARE_OPERATIONAL_WARNINGS_NOT_STATISTICAL_CONFIDENCE.",
                "COMPARISON_DOES_NOT_ESTABLISH_PRICE_CHANGE_CAUSALITY.",
            ]
        )
        basis = next(iter(bases)) if len(bases) == 1 and None not in bases else None
        comparable = len(assessed) >= 2 and not reasons
        return {
            "error": False,
            "status": "COMPARABLE" if comparable else "NOT_READY" if len(assessed) < 2 else "INCOMPARABLE",
            "evidence_basis": basis,
            "verified": bool(comparable and basis == "CANONICAL_FACT_COMPARABLE"),
            "candidate_count": len(assessed),
            "candidates": [{
                "index": item["index"], "result_revision": item["result_revision"],
                "status": "READY" if not item["reasons"] else "INCOMPARABLE",
                "window_days": item["window"]["days"] if item.get("window") else None,
                "successful_units": item["successful_units"],
                "price_cents": item["price_cents"],
                "evidence_age_days": item["evidence_age_days"],
                "reasons": item["reasons"], "warnings": item["warnings"],
            } for item in assessed],
            "reasons": reasons[:64], "warnings": warnings[:64],
            "thresholds": {
                "recommended_window_days": recommended_window_days,
                "small_sample_units": small_sample_units,
                "max_evidence_age_days": max_evidence_age_days,
            },
            "read_only": True, "executed": False,
        }

    def _assess_candidate(
        self, candidate, *, now, recommended_window_days,
        small_sample_units, max_evidence_age_days,
    ):
        index = candidate.get("index") if isinstance(candidate, dict) else None
        index = index if type(index) is int and index >= 0 else 0
        revision = candidate.get("result_revision") if isinstance(candidate, dict) else None
        revision = revision if type(revision) is int and revision > 0 else None
        result = candidate.get("result") if isinstance(candidate, dict) else None
        reasons = []
        warnings = []
        if not isinstance(result, dict):
            return self._empty_candidate(index, revision, ["OBSERVATION_RESULT_INVALID"])

        identity = result.get("identity")
        expected = {"store_id", "product_id", "offer_id", "sku", "sale_schema"}
        if (not isinstance(identity, dict) or set(identity) != expected
                or any(not isinstance(identity.get(key), str) or not identity[key].strip() for key in expected)
                or identity.get("sale_schema") != "FBO"):
            reasons.append("OBSERVATION_IDENTITY_UNCONFIRMED")
            identity = None
        owner_id = candidate.get("owner_id") if isinstance(candidate, dict) else None
        store_id = candidate.get("store_id") if isinstance(candidate, dict) else None
        if (not isinstance(owner_id, str) or not owner_id.strip()
                or not isinstance(store_id, str) or not store_id.strip()
                or (identity is not None and identity.get("store_id") != store_id)):
            reasons.append("OBSERVATION_OWNER_STORE_SCOPE_UNCONFIRMED")
            scope = None
        else:
            scope = (owner_id, store_id)

        price_cents = result.get("seller_price_cents")
        if type(price_cents) is not int or not 1 <= price_cents <= 999_999_999_999_999:
            reasons.append("SELLER_PRICE_UNCONFIRMED")
            price_cents = None

        window = self._window(result.get("window"), now)
        if window is None:
            reasons.append("OBSERVATION_WINDOW_INVALID_OR_NOT_COMPLETED")

        metrics = result.get("metrics")
        metrics = metrics if isinstance(metrics, dict) else {}
        for field in ("revenue_basis", "advertising_status"):
            if not isinstance(metrics.get(field), str) or not metrics[field].strip():
                reasons.append(field.upper() + "_UNKNOWN")
        units = metrics.get("successful_sale_units")
        denominator = metrics.get("successful_unit_denominator")
        if (type(units) is not int or not 1 <= units <= self.MAX_SUCCESSFUL_UNITS
                or type(denominator) is not int or denominator != units):
            reasons.append("SUCCESSFUL_UNIT_DENOMINATOR_UNCONFIRMED")
            units = None

        completeness = result.get("completeness")
        completeness = completeness if isinstance(completeness, dict) else {}
        sources = result.get("sources")
        sources = sources if isinstance(sources, list) else []
        basis = result.get("evidence_basis")
        if result.get("status") != "AVAILABLE":
            reasons.append("OBSERVATION_RESULT_NOT_AVAILABLE")
        warnings.extend(self._safe_result_reasons(result.get("reasons")))
        warnings.extend(self._safe_result_reasons(result.get("warnings")))

        if basis == "CANONICAL_FACT_COMPARABLE":
            for key in self._FACT_COMPLETENESS:
                if completeness.get(key) != "CONFIRMED":
                    reasons.append("FACT_" + key.upper() + "_INCOMPLETE")
            observed_profit = self._decimal(metrics.get("observed_profit_per_unit"))
            if observed_profit is None:
                reasons.append("OBSERVED_PROFIT_PER_UNIT_UNAVAILABLE")
            required = (
                "FINANCE", "ANALYTICS", "PERFORMANCE", "RETURNS", "SELLER_PRICE",
                "TARIFF", "COST", "TAX",
            )
            self._check_sources(
                sources, result.get("window"), reasons,
                required=required,
                require_complete=required,
                basis_names=("FINANCE", "ANALYTICS", "PERFORMANCE", "RETURNS", "SELLER_PRICE"),
            )
            freshness_names = required
            source_basis_names = ("FINANCE", "ANALYTICS", "PERFORMANCE", "RETURNS", "SELLER_PRICE")
        elif basis == "MODELLED_FROM_OBSERVED_INPUTS":
            if self._decimal(metrics.get("profit_per_unit")) is None:
                reasons.append("MODELLED_PROFIT_PER_UNIT_UNAVAILABLE")
            if completeness.get("successful_units") != "CONFIRMED":
                reasons.append("SUCCESSFUL_UNIT_COMPLETENESS_UNCONFIRMED")
            if completeness.get("tariff") != "MANUAL_ASSUMPTION":
                reasons.append("MODEL_TARIFF_BASIS_UNCONFIRMED")
            if completeness.get("tax") != "MANUAL_ASSUMPTION":
                reasons.append("MODEL_TAX_BASIS_UNCONFIRMED")
            if completeness.get("unit_cost") != "MANUAL_ASSUMPTION":
                reasons.append("MODEL_UNIT_COST_BASIS_UNCONFIRMED")
            if completeness.get("price_history") != "CONFIRMED":
                warnings.append("OWNER_DECLARED_PRICE_DOES_NOT_VERIFY_PER_SALE_PRICE_HISTORY.")
            if completeness.get("returns") != "CONFIRMED":
                warnings.append("RETURN_COHORT_IS_NOT_CONFIRMED.")
            if metrics.get("advertising_status") == "CPC_ONLY_MODEL":
                warnings.append("CPC_ONLY_MODEL_OMITS_OTHER_ADVERTISING_TYPES.")
            elif completeness.get("advertising") != "CONFIRMED":
                reasons.append("MODEL_ADVERTISING_SCOPE_UNCONFIRMED")
            units_source_name = next((
                name for name in ("RETURNS", "ANALYTICS", "FINANCE")
                if (self._find_source(sources, name) or {}).get("complete") is True
            ), "ANALYTICS" if self._find_source(sources, "ANALYTICS") is not None else "FINANCE")
            if units_source_name == "RETURNS" and completeness.get("returns") != "CONFIRMED":
                reasons.append("MODEL_BUYOUT_EVIDENCE_INCOMPLETE")
            self._check_sources(
                sources, result.get("window"), reasons,
                required=("PERFORMANCE", units_source_name),
                require_complete=("PERFORMANCE", units_source_name),
                basis_names=() if units_source_name == "RETURNS" else ("PERFORMANCE", units_source_name),
            )
            units_source = self._find_source(sources, units_source_name)
            if units_source is None or units_source.get("complete") is not True:
                reasons.append("SUCCESSFUL_UNIT_SOURCE_UNAVAILABLE")
            freshness_names = ("PERFORMANCE", units_source_name)
            source_basis_names = freshness_names
            signature = candidate.get("assumption_signature") if isinstance(candidate, dict) else None
            if not isinstance(signature, str) or not signature.strip() or len(signature) > 160:
                reasons.append("MODEL_ASSUMPTIONS_NOT_IDENTIFIED")
        else:
            reasons.append("EVIDENCE_BASIS_UNSUPPORTED")
            freshness_names = ("FINANCE", "PERFORMANCE")
            source_basis_names = freshness_names

        window_days = window["days"] if window else None
        if window_days is not None and window_days < recommended_window_days:
            warnings.append("OBSERVATION_WINDOW_SHORTER_THAN_RECOMMENDED.")
        if units is not None and units < small_sample_units:
            warnings.append("SMALL_SUCCESSFUL_UNIT_SAMPLE.")

        latest_received, freshness_error = self._freshness(
            sources, now, max_evidence_age_days, required_names=freshness_names,
        )
        if freshness_error:
            reasons.append(freshness_error)
        age_days = None
        if latest_received is not None:
            age_days = max(0, int((now.astimezone(timezone.utc) - latest_received).total_seconds() // 86400))
        if basis == "MODELLED_FROM_OBSERVED_INPUTS":
            warnings.extend(self._known_model_confounders(result))

        return {
            "index": index, "result_revision": revision, "identity": identity,
            "scope": scope,
            "price_cents": price_cents, "evidence_basis": basis,
            "window": window, "successful_units": units,
            "source_date_bases": self._source_basis_signature(sources, source_basis_names),
            "evidence_age_days": age_days,
            "reasons": self._unique(reasons), "warnings": self._unique(warnings),
        }

    def _check_sources(self, sources, raw_window, reasons, *, required, require_complete=(), basis_names=()):
        if not isinstance(raw_window, dict):
            return
        required_date_basis = None
        for name in required:
            source = self._find_source(sources, name)
            if source is None:
                reasons.append("SOURCE_" + name + "_MISSING")
                continue
            status = source.get("status")
            if not isinstance(status, str):
                reasons.append("SOURCE_" + name + "_STATUS_UNKNOWN")
            elif status in {"SOURCE_UNAVAILABLE", "RATE_LIMITED", "CONFLICT", "STALE"}:
                reasons.append("SOURCE_" + name + "_" + status)
            if name in require_complete and source.get("complete") is not True:
                reasons.append("SOURCE_" + name + "_INCOMPLETE")
            if name in require_complete and status != "COMPLETE":
                reasons.append("SOURCE_" + name + "_STATUS_NOT_COMPLETE")
            if source.get("source_window_start") != raw_window.get("from") or source.get("source_window_end") != raw_window.get("to"):
                reasons.append("SOURCE_" + name + "_WINDOW_MISMATCH")
            if source.get("timezone") != raw_window.get("timezone"):
                reasons.append("SOURCE_" + name + "_TIMEZONE_MISMATCH")
            date_basis = source.get("source_date_basis")
            if not isinstance(date_basis, str) or not date_basis:
                reasons.append("SOURCE_" + name + "_DATE_BASIS_UNKNOWN")
            elif name in basis_names:
                if required_date_basis is None:
                    required_date_basis = date_basis
                elif date_basis != required_date_basis:
                    reasons.append("SOURCE_DATE_BASIS_MISMATCH")

    @staticmethod
    def _find_source(sources, name):
        return next((item for item in sources if isinstance(item, dict) and item.get("name") == name), None)

    @classmethod
    def _source_basis_signature(cls, sources, names):
        signature = []
        for name in names:
            value = (cls._find_source(sources, name) or {}).get("source_date_basis")
            signature.append((name, value if isinstance(value, str) else None))
        return tuple(signature)

    def _window(self, value, now):
        if not isinstance(value, dict):
            return None
        try:
            start = date.fromisoformat(value["from"])
            end = date.fromisoformat(value["to"])
            timezone_name = value["timezone"]
            zone = self._zone(timezone_name)
            local_today = now.astimezone(zone).date()
            date_basis = value["date_basis"]
            if not isinstance(date_basis, str) or not date_basis:
                return None
        except (KeyError, TypeError, ValueError):
            return None
        days = (end - start).days + 1
        if not self.MIN_WINDOW_DAYS <= days <= self.MAX_WINDOW_DAYS or end >= local_today:
            return None
        weekdays = [0] * 7
        current = start
        while current <= end:
            weekdays[current.weekday()] += 1
            current = date.fromordinal(current.toordinal() + 1)
        return {
            "start": start, "end": end, "days": days,
            "timezone": timezone_name, "date_basis": date_basis,
            "weekday_counts": tuple(weekdays),
        }

    @staticmethod
    def _zone(name):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            return ZoneInfo(name)
        except (TypeError, ValueError, ZoneInfoNotFoundError):
            raise ValueError("invalid timezone")

    def _freshness(self, sources, now, max_age_days, *, required_names):
        received = []
        for name in required_names:
            source = self._find_source(sources, name)
            if source is None:
                continue
            value = self._aware_timestamp(source.get("received_at"))
            if value is None:
                return None, "SOURCE_FRESHNESS_TIMESTAMP_UNAVAILABLE"
            if value > now.astimezone(timezone.utc):
                return None, "SOURCE_FRESHNESS_TIMESTAMP_IN_FUTURE"
            received.append(value)
        if not received:
            return None, "SOURCE_FRESHNESS_UNAVAILABLE"
        oldest = min(received)
        age = (now.astimezone(timezone.utc) - oldest).total_seconds()
        if age > max_age_days * 86400:
            return oldest, "OBSERVATION_EVIDENCE_STALE"
        return oldest, None

    @staticmethod
    def _aware_timestamp(value):
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None and parsed.utcoffset() is not None else None

    @staticmethod
    def _decimal(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return amount if amount.is_finite() else None

    @classmethod
    def _valid_configuration(cls, now, recommended_days, small_units, max_age_days):
        return bool(
            isinstance(now, datetime) and now.tzinfo is not None and now.utcoffset() is not None
            and type(recommended_days) is int and cls.MIN_WINDOW_DAYS <= recommended_days <= cls.MAX_WINDOW_DAYS
            and type(small_units) is int and 1 <= small_units <= cls.MAX_SUCCESSFUL_UNITS
            and type(max_age_days) is int and 1 <= max_age_days <= 90
        )

    @staticmethod
    def _known_model_confounders(result):
        warnings = []
        for warning in result.get("warnings", []) if isinstance(result.get("warnings"), list) else []:
            if not isinstance(warning, str):
                continue
            if "OTHER_ADVERTISING_TYPES_ARE_UNKNOWN" in warning:
                warnings.append("OTHER_ADVERTISING_TYPES_ARE_UNKNOWN.")
            if "OWNER_DECLARED_PRICE_DOES_NOT_PROVE" in warning:
                warnings.append("OWNER_DECLARED_PRICE_DOES_NOT_PROVE_PER_SALE_HISTORY.")
            if "NO_CAUSAL_CLAIM" in warning:
                warnings.append("NO_CAUSAL_CLAIM_IS_MADE.")
        if not warnings:
            warnings.append("MODEL_CONFOUNDERS_MUST_BE_REVIEWED_BEFORE_DECISION.")
        return warnings

    @staticmethod
    def _safe_result_reasons(values):
        if not isinstance(values, list):
            return []
        return [
            "SOURCE_RESULT_NOTE: " + value
            for value in values[:32]
            if isinstance(value, str) and 0 < len(value) <= 300
            and all(character.isalnum() or character in "_:. -" for character in value)
        ]

    @staticmethod
    def _result_metrics(candidate):
        result = candidate.get("result") if isinstance(candidate, dict) else None
        metrics = result.get("metrics") if isinstance(result, dict) else None
        return metrics if isinstance(metrics, dict) else {}

    @staticmethod
    def _unique(items):
        return list(dict.fromkeys(item for item in items if isinstance(item, str)))

    @staticmethod
    def _empty_candidate(index, revision, reasons):
        return {
            "index": index, "result_revision": revision, "identity": None, "scope": None,
            "price_cents": None, "evidence_basis": None, "window": None,
            "successful_units": None, "source_date_bases": None, "evidence_age_days": None,
            "reasons": reasons, "warnings": [],
        }

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True, "executed": False}
