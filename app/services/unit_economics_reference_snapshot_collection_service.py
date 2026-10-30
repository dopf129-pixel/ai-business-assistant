"""Collect and persist one complete, reconciliation-only 56-day SKU snapshot."""

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.unit_economics_readiness_view_service import UnitEconomicsReadinessViewService
from services.unit_economics_window_snapshot_service import UnitEconomicsWindowSnapshotService


class UnitEconomicsReferenceSnapshotCollectionService:
    """Explicitly collect finance + FBO denominator evidence for one saved SKU."""

    COMPONENTS = (
        "FINANCE_ACQUIRING", "FINANCE_COMMISSION", "FINANCE_LOGISTICS",
        "FINANCE_OTHER_FEES",
    )
    _SOURCE_COMPONENT_FIELDS = {
        "FINANCE_ACQUIRING": "acquiring",
        "FINANCE_COMMISSION": "commission",
        "FINANCE_LOGISTICS": "logistics",
        "FINANCE_OTHER_FEES": "other_fees",
    }
    _REASONS = {
        "NONE", "SOURCE_UNAVAILABLE", "FINANCE_PARTIAL", "RETURNS_PARTIAL",
        "UNSUPPORTED_FINANCE_TYPES", "EXPENSE_CREDIT_REQUIRES_REVIEW",
        "ZERO_UNIT_DENOMINATOR", "SNAPSHOT_INCOMPLETE",
    }

    def __init__(self, repository, evidence_collection_service, *, clock=None):
        self.repository = repository
        self.evidence_collection_service = evidence_collection_service
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def collect(self, identity, *, owner_id, store_id, timezone_name):
        if (not isinstance(identity, dict)
                or set(identity) != {"owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema"}
                or identity.get("owner_id") != owner_id
                or identity.get("store_id") != store_id
                or identity.get("sale_schema") != "FBO"
                or any(not isinstance(value, str) or not value.strip() for value in identity.values())):
            return self._error("UNIT_ECONOMICS_REFERENCE_IDENTITY_INVALID")
        try:
            now = self.clock()
            if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
                raise ValueError("aware clock required")
            local_today = now.astimezone(ZoneInfo(timezone_name)).date()
        except (TypeError, ValueError, ZoneInfoNotFoundError, OSError):
            return self._error("UNIT_ECONOMICS_REFERENCE_CLOCK_OR_TIMEZONE_INVALID")
        spec = UnitEconomicsWindowSnapshotService.reference_window(
            local_today.isoformat(), timezone_name,
        )
        if spec.get("error"):
            return self._error("UNIT_ECONOMICS_REFERENCE_WINDOW_INVALID")

        evidence = self.evidence_collection_service.collect_reference_window(
            identity, date_from=spec["window"]["from_date"],
            date_to=spec["window"]["to_date"], timezone_name=timezone_name,
        )
        if not isinstance(evidence, dict) or evidence.get("error") is not False:
            code = evidence.get("code") if isinstance(evidence, dict) else None
            safe_code = code if isinstance(code, str) and code.isascii() and code.replace("_", "").isalnum() else "SOURCE_UNAVAILABLE"
            return {"error": False, "status": "UNAVAILABLE", "reason_code": safe_code,
                    "read_only": True, "source_io": True}
        result = self._build_snapshot(spec, identity, evidence)
        if result.get("error"):
            return result
        if result.get("status") != "COMPLETE":
            return {
                "error": False, "status": result.get("status", "PARTIAL"),
                "reason_code": self._reason(result["reason_code"]),
                "window": result["window"], "read_only": True, "source_io": True,
            }
        saved = self.repository.create_unit_economics_expense_snapshot(
            {"schema_version": 1, "identity": identity, "readiness": result["readiness"]},
            owner_id=owner_id, store_id=store_id,
        )
        if not isinstance(saved, dict) or saved.get("error") is True:
            return self._error("UNIT_ECONOMICS_REFERENCE_SNAPSHOT_SAVE_FAILED")
        return {
            "error": False, "status": "COMPLETE", "snapshot_id": saved["snapshot_id"],
            "created": saved.get("created") is True, "window": result["window"],
            "read_only": True, "source_io": True,
        }

    @classmethod
    def _build_snapshot(cls, spec, identity, evidence):
        sources = evidence.get("sources")
        sources = sources if isinstance(sources, list) else []
        by_name = {item.get("name"): item for item in sources if isinstance(item, dict)}
        finance = by_name.get("FINANCE", {})
        returns = by_name.get("RETURNS", {})
        metrics = evidence.get("metrics")
        metrics = metrics if isinstance(metrics, dict) else {}
        unsupported = finance.get("unsupported_types")
        unsupported = unsupported if isinstance(unsupported, list) else []
        finance_complete = finance.get("status") == "COMPLETE" and not unsupported
        returns_complete = returns.get("status") == "COMPLETE"
        source_complete = finance_complete and returns_complete

        component_values = {}
        for key, field in cls._SOURCE_COMPONENT_FIELDS.items():
            if not finance_complete:
                component_values[key] = {"status": "UNAVAILABLE", "amount_rub": None}
                continue
            try:
                amount = Decimal(str(metrics[field]))
            except (InvalidOperation, TypeError, ValueError, KeyError):
                amount = None
            if amount is None or not amount.is_finite():
                component_values[key] = {"status": "REVIEW_REQUIRED", "amount_rub": "0.00"}
            elif amount > 0:
                # A positive net fee category can contain refund credits. Do not
                # reinterpret it as zero expense or silently invert its sign.
                component_values[key] = {
                    "status": "REVIEW_REQUIRED", "amount_rub": cls._money(amount),
                }
            elif amount == 0:
                component_values[key] = {"status": "CONFIRMED_ZERO", "amount_rub": "0.00"}
            else:
                component_values[key] = {"status": "PRESENT", "amount_rub": cls._money(-amount)}

        unit_count = metrics.get("ordered_units") if returns_complete else None
        if type(unit_count) is not int or unit_count < 0:
            unit_count = None
            returns_complete = False
            source_complete = False
        elapsed = 0
        diagnostics = evidence.get("diagnostics")
        if isinstance(diagnostics, dict) and type(diagnostics.get("elapsed_seconds")) is int:
            elapsed = max(0, min(60, diagnostics["elapsed_seconds"]))
        attempts = diagnostics.get("collection_http_attempts", 0) if isinstance(diagnostics, dict) else 0
        if type(attempts) is not int or not 0 <= attempts <= 64:
            attempts = 64
            source_complete = False
        trace_reason = diagnostics.get("budget_reason_code", "NONE") if isinstance(diagnostics, dict) else "NONE"
        stop_reason = {
            "NONE": "NONE",
            "HTTP_ATTEMPT_BUDGET_EXHAUSTED": "REQUEST_BUDGET_EXHAUSTED",
            "TIME_BUDGET_EXHAUSTED": "TIME_BUDGET_EXHAUSTED",
            "HTTP_429": "HTTP_429",
        }.get(trace_reason, "SOURCE_READ_FAILED")
        budget = {
            "remaining_seconds": float(max(0, 60 - elapsed)),
            "requests_reserved": attempts, "request_limit": 64,
            "total_requests_reserved": attempts, "total_request_limit": 64,
            "stop_reason": stop_reason, "http_429_count": 1 if stop_reason == "HTTP_429" else 0,
        }
        count_status = "COMPLETE" if returns_complete else "PARTIAL"
        revision_payload = {
            "window": spec["window"], "identity": identity,
            "source_statuses": {"finance": finance.get("status"), "returns": returns.get("status")},
            "metrics": {key: metrics.get(key) for key in sorted(cls._SOURCE_COMPONENT_FIELDS.values())},
            "ordered_units": unit_count, "unsupported_type_count": len(unsupported),
        }
        revision = hashlib.sha256(json.dumps(
            revision_payload, sort_keys=True, separators=(",", ":"), default=str,
        ).encode("utf-8")).hexdigest()
        segment = {
            "identity": identity,
            "from_date": spec["window"]["from_date"],
            "to_date": spec["window"]["to_date"],
            "components": component_values,
            "quantity": {
                "status": count_status, "units": unit_count,
                "denominator_kind": "ORDERED_UNITS_WINDOW" if returns_complete else None,
            },
            "coverage": {
                "complete": source_complete, "page_count": 56,
                "stop_reason": "END_OF_WINDOW" if source_complete else "SOURCE_INCOMPLETE",
            },
            "source_revisions": [revision],
        }
        snapshot = UnitEconomicsWindowSnapshotService.build_snapshot(
            spec, identity, [segment], list(cls.COMPONENTS), budget,
        )
        if snapshot.get("error"):
            return {"error": True, "code": "UNIT_ECONOMICS_REFERENCE_SNAPSHOT_INVALID"}

        if unit_count == 0:
            reason = "ZERO_UNIT_DENOMINATOR"
        elif unsupported:
            reason = "UNSUPPORTED_FINANCE_TYPES"
        elif not finance_complete:
            reason = "FINANCE_PARTIAL"
        elif not returns_complete:
            reason = "RETURNS_PARTIAL"
        elif any(value.get("status") == "REVIEW_REQUIRED"
                 for value in component_values.values()):
            reason = "EXPENSE_CREDIT_REQUIRES_REVIEW"
        elif snapshot.get("coverage", {}).get("status") != "COMPLETE":
            reason = "SNAPSHOT_INCOMPLETE"
        else:
            reason = "NONE"

        # Partial evidence is useful for explaining what is missing, but must
        # not be forced through the COMPLETE readiness contract or persisted.
        if reason != "NONE":
            return {
                "error": False, "status": "PARTIAL", "reason_code": reason,
                "window": snapshot["window"],
            }

        readiness = UnitEconomicsReadinessViewService.build(
            snapshot,
            {key: {"source": "OZON_SELLER_FINANCE", "applicability": "RECONCILIATION_ONLY"}
             for key in cls.COMPONENTS},
        )
        if readiness.get("error"):
            return {"error": True, "code": "UNIT_ECONOMICS_REFERENCE_READINESS_INVALID"}
        readiness["window"] = {
            **readiness["window"], "date_basis": "LOCAL_CALENDAR_DAY",
        }
        if readiness.get("status") != "COMPLETE":
            return {
                "error": False, "status": "PARTIAL", "reason_code": "SNAPSHOT_INCOMPLETE",
                "window": snapshot["window"],
            }
        return {
            "error": False, "status": "COMPLETE", "readiness": readiness,
            "window": snapshot["window"], "reason_code": "NONE",
        }

    @staticmethod
    def _money(value):
        return format(value.quantize(Decimal("0.01")), ".2f")

    @classmethod
    def _reason(cls, value):
        return value if value in cls._REASONS else "SOURCE_UNAVAILABLE"

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True, "source_io": False}
