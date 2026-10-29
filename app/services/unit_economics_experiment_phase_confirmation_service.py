"""Pure owner-confirmation rules for an experiment price phase."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class UnitEconomicsExperimentPhaseConfirmationService:
    """Validate the exact seller price and clock before a phase is activated."""

    SCHEMA_VERSION = 1
    CONFIRMED_PRICE_EVIDENCE = "OWNER_DECLARED"

    @classmethod
    def preview(
        cls, phase_config, experiment_status, phase_status, actual_price_cents,
        effective_from, now, *, owner_confirmed=False, candidate_prices_cents=None,
    ):
        context = cls._context(
            phase_config, experiment_status, phase_status, actual_price_cents,
            effective_from, now, candidate_prices_cents,
        )
        if context.get("error"):
            return context
        if owner_confirmed is not True:
            return {
                "error": False, "status": "PREVIEW_ONLY",
                "seller_price_cents": actual_price_cents,
                "effective_from": context["effective_from"],
                "timezone": context["timezone"],
                "first_full_local_day": context["first_full_local_day"],
                "price_evidence_kind": cls.CONFIRMED_PRICE_EVIDENCE,
                "price_history_verified": False,
                "read_only": True, "executed": False,
                "limitations": ["OWNER_CONFIRMATION_IS_NOT_API_PRICE_HISTORY"],
            }
        confirmation = cls._confirmation(context, actual_price_cents, now)
        return {
            "error": False, "status": "READY_TO_CONFIRM",
            "confirmation": confirmation,
            "read_only": True, "executed": False,
            "limitations": ["OWNER_CONFIRMATION_IS_NOT_API_PRICE_HISTORY"],
        }

    @classmethod
    def normalize_confirmation(cls, value, phase_config):
        fields = {
            "schema_version", "seller_price_cents", "effective_from", "confirmed_at",
            "timezone", "first_full_local_day", "owner_confirmed",
            "price_evidence_kind", "price_history_verified",
        }
        if not isinstance(value, dict) or set(value) != fields:
            return None
        if (type(value.get("schema_version")) is not int
                or value["schema_version"] != cls.SCHEMA_VERSION
                or value.get("owner_confirmed") is not True
                or value.get("price_evidence_kind") != cls.CONFIRMED_PRICE_EVIDENCE
                or value.get("price_history_verified") is not False
                or type(value.get("seller_price_cents")) is not int
                or not isinstance(phase_config, dict)
                or value["seller_price_cents"] != phase_config.get("planned_price_cents")
                or value.get("timezone") != phase_config.get("timezone")):
            return None
        try:
            ZoneInfo(value["timezone"])
        except (ZoneInfoNotFoundError, TypeError, ValueError, OSError):
            return None
        effective = cls._aware(value.get("effective_from"))
        confirmed = cls._aware(value.get("confirmed_at"))
        first_day = cls._date(value.get("first_full_local_day"))
        if effective is None or confirmed is None or first_day is None or effective > confirmed:
            return None
        local_effective = effective.astimezone(ZoneInfo(value["timezone"]))
        expected_first_day = local_effective.date()
        if (local_effective.time().replace(tzinfo=None) != time.min
                or local_effective.fold != 0):
            expected_first_day += timedelta(days=1)
        if first_day != expected_first_day:
            return None
        planned_start = cls._date(phase_config.get("planned_from_date"))
        planned_end = cls._date(phase_config.get("planned_to_date"))
        if (planned_start is None or planned_end is None
                or planned_start < first_day or first_day > planned_end):
            return None
        return {
            "schema_version": cls.SCHEMA_VERSION,
            "seller_price_cents": value["seller_price_cents"],
            "effective_from": effective.isoformat(),
            "confirmed_at": confirmed.astimezone(timezone.utc).isoformat().replace(
                "+00:00", "Z",
            ),
            "timezone": value["timezone"],
            "first_full_local_day": first_day.isoformat(),
            "owner_confirmed": True,
            "price_evidence_kind": cls.CONFIRMED_PRICE_EVIDENCE,
            "price_history_verified": False,
        }

    @classmethod
    def _context(
        cls, phase_config, experiment_status, phase_status, actual_price_cents,
        effective_from, now, candidate_prices_cents,
    ):
        if not isinstance(phase_config, dict):
            return cls._error("EXPERIMENT_PHASE_CONFIG_INVALID")
        if phase_status != "PLANNED":
            return cls._error("EXPERIMENT_PHASE_NOT_PLANNED")
        kind = phase_config.get("kind")
        expected_status = {
            "BASELINE": "READY", "CANDIDATE": "CANDIDATE_READY",
        }.get(kind)
        if expected_status is None or experiment_status != expected_status:
            return cls._error("EXPERIMENT_PHASE_CONFIRMATION_STATE_INVALID")
        if (type(actual_price_cents) is not int or actual_price_cents < 1
                or actual_price_cents != phase_config.get("planned_price_cents")):
            return cls._error("EXPERIMENT_CONFIRMED_PRICE_MISMATCH")
        if kind == "CANDIDATE" and (
            not isinstance(candidate_prices_cents, list)
            or actual_price_cents not in candidate_prices_cents
        ):
            return cls._error("EXPERIMENT_CANDIDATE_NOT_SELECTED")
        timezone_name = phase_config.get("timezone")
        try:
            zone = ZoneInfo(timezone_name)
            planned_start = cls._date(phase_config.get("planned_from_date"))
            planned_end = cls._date(phase_config.get("planned_to_date"))
            effective = cls._aware(effective_from)
            current = cls._aware(now)
        except (ZoneInfoNotFoundError, TypeError, ValueError, OSError):
            return cls._error("EXPERIMENT_PHASE_CONFIRMATION_TIME_INVALID")
        if (planned_start is None or planned_end is None or effective is None
                or current is None or planned_end < planned_start):
            return cls._error("EXPERIMENT_PHASE_CONFIRMATION_TIME_INVALID")
        if effective > current:
            return cls._error("EXPERIMENT_PHASE_CONFIRMATION_TIME_FUTURE")
        normalized_effective = effective.isoformat()
        local_effective = effective.astimezone(zone)
        first_full_day = local_effective.date()
        if (local_effective.time().replace(tzinfo=None) != time.min
                or local_effective.fold != 0):
            first_full_day += timedelta(days=1)
        if planned_start < first_full_day or first_full_day > planned_end:
            return cls._error("EXPERIMENT_PHASE_WINDOW_BEFORE_NEXT_FULL_DAY")
        return {
            "error": False, "effective_from": normalized_effective,
            "timezone": timezone_name,
            "first_full_local_day": first_full_day.isoformat(),
        }

    @classmethod
    def _confirmation(cls, context, seller_price_cents, now):
        current = cls._aware(now)
        return {
            "schema_version": cls.SCHEMA_VERSION,
            "seller_price_cents": seller_price_cents,
            "effective_from": context["effective_from"],
            "confirmed_at": current.astimezone(timezone.utc).isoformat().replace(
                "+00:00", "Z",
            ),
            "timezone": context["timezone"],
            "first_full_local_day": context["first_full_local_day"],
            "owner_confirmed": True,
            "price_evidence_kind": cls.CONFIRMED_PRICE_EVIDENCE,
            "price_history_verified": False,
        }

    @staticmethod
    def _aware(value):
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str) and len(value) <= 40:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None

    @staticmethod
    def _date(value):
        if not isinstance(value, str):
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}
