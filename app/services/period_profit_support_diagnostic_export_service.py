"""Strict, allowlisted JSON export for a cached Period Profit diagnosis."""

import json
import re
from datetime import date, datetime, timezone
from uuid import uuid4

from services.period_profit_diagnostic_view_service import (
    PeriodProfitDiagnosticViewService,
)


class PeriodProfitSupportDiagnosticExportService:
    SCHEMA_VERSION = 1
    MAX_BYTES = 32 * 1024
    MAX_IDENTIFIERS = 64
    IDENTIFIER_FIELDS = {
        "finance_sku": ("SKU", "SKU_"),
        "catalog_sku": ("SKU", "SKU_"),
        "product_id": ("PRODUCT", "PRODUCT_"),
    }
    STATUS_CODES = frozenset({"PERIOD_PROFIT_DIAGNOSTICS_READY"})
    BUDGET_CODES = frozenset({
        "NONE",
        "OPERATION_CANCELLED",
        "TIME_BUDGET_EXHAUSTED",
        "HTTP_ATTEMPT_BUDGET_EXHAUSTED",
    })
    COMPLETENESS_KEYS = PeriodProfitDiagnosticViewService.STATUS_KEYS
    COMPLETENESS_CODES = PeriodProfitDiagnosticViewService.ALLOWED_STATUS_CODES
    REASON_CODES = frozenset(PeriodProfitDiagnosticViewService.REASON_LABELS)

    def __init__(self, utc_clock=None):
        self.utc_clock = utc_clock or (lambda: datetime.now(timezone.utc))

    def build_snapshot(self, diagnostic_view, support_context=None):
        if (
            not isinstance(diagnostic_view, dict)
            or diagnostic_view.get("status") != "PERIOD_PROFIT_DIAGNOSTICS_READY"
        ):
            return self._error("PERIOD_PROFIT_SUPPORT_DIAGNOSTIC_UNAVAILABLE")
        period = {
            "from": self._date(diagnostic_view.get("date_from")),
            "to": self._date(diagnostic_view.get("date_to")),
        }
        if (
            period["from"] is None
            or period["to"] is None
            or period["from"] > period["to"]
        ):
            return self._error("PERIOD_PROFIT_SUPPORT_DIAGNOSTIC_INVALID_PERIOD")

        operation = self._operation(diagnostic_view.get("operation"))
        context = support_context if isinstance(support_context, dict) else {}
        operation_id = self._operation_id(context.get("operation_id"))
        started_at = self._timestamp(context.get("started_at_utc"))
        if operation_id is not None:
            operation["id"] = operation_id
        if started_at is not None:
            operation["started_at_utc"] = started_at
        operation["type"] = "PERIOD_PROFIT"

        budget_reason = context.get("budget_reason_code")
        if not isinstance(budget_reason, str) or budget_reason not in self.BUDGET_CODES:
            budget_reason = operation.get("budget_reason_code", "NONE")
        if budget_reason not in self.BUDGET_CODES:
            budget_reason = "NONE"

        reasons = diagnostic_view.get("reason_codes")
        reason_codes = list(dict.fromkeys(
            code for code in reasons or []
            if isinstance(code, str) and code in self.REASON_CODES
        )) if isinstance(reasons, (list, tuple)) else []
        completeness = diagnostic_view.get("source_completeness")
        source_completeness = {}
        if isinstance(completeness, dict):
            source_completeness = {
                key: value
                for key, value in completeness.items()
                if isinstance(key, str)
                and key in self.COMPLETENESS_KEYS
                and isinstance(value, str)
                and value in self.COMPLETENESS_CODES
            }

        counts = {
            "events_total": self._count(operation.get("events_total")),
            "events_dropped": self._count(operation.get("events_dropped")),
            "http_attempts": self._count(operation.get("http_attempts")),
            "http_attempt_cap": self._count(operation.get("http_attempt_cap")),
            "rows_attempted": self._count(operation.get("rows_attempted")),
            "rows_completed": self._count(operation.get("rows_completed")),
            "rows_unknown": self._count(operation.get("rows_unknown")),
            "elapsed_seconds": self._count(operation.get("elapsed_seconds")),
        }
        identifiers = self._masked_identifier_references(
            context.get("_identifier_values")
        )
        generated_at = self._timestamp(self.utc_clock())
        if generated_at is None:
            return self._error("PERIOD_PROFIT_SUPPORT_DIAGNOSTIC_CLOCK_INVALID")

        return {
            "error": False,
            "status": "PERIOD_PROFIT_SUPPORT_DIAGNOSTIC_SNAPSHOT_READY",
            "snapshot": {
                "schema": "period_profit_support_diagnostic",
                "schema_version": self.SCHEMA_VERSION,
                "application": {
                    "revision": "UNAVAILABLE",
                    "started_at_utc": None,
                },
                "operation": {
                    "id": operation["id"],
                    "type": operation["type"],
                    "started_at_utc": operation.get("started_at_utc"),
                    "generated_at_utc": generated_at,
                },
                "period": period,
                "status_codes": {
                    "diagnostic": "PERIOD_PROFIT_DIAGNOSTICS_READY",
                    "budget_reason": budget_reason,
                },
                "reason_codes": reason_codes,
                "source_completeness": source_completeness,
                "counts": counts,
                "identifier_references": identifiers,
                "field_types": {
                    "schema_version": "integer",
                    "operation.id": "opaque_random_id",
                    "operation.type": "enum",
                    "operation.started_at_utc": "utc_datetime_or_null",
                    "operation.generated_at_utc": "utc_datetime",
                    "period.from": "date",
                    "period.to": "date",
                    "status_codes": "enum_map",
                    "reason_codes": "enum_list",
                    "source_completeness": "enum_map",
                    "counts": "bounded_integer_map",
                    "identifier_references": "masked_alias_map",
                },
            },
            "read_only": True,
            "executed": False,
        }

    def export(self, snapshot, application_metadata=None):
        if not self._valid_snapshot(snapshot):
            return self._error("PERIOD_PROFIT_SUPPORT_DIAGNOSTIC_SNAPSHOT_INVALID")
        normalized = self._normalize_snapshot(snapshot)
        if not normalized:
            return self._error("PERIOD_PROFIT_SUPPORT_DIAGNOSTIC_CLOCK_INVALID")
        metadata = application_metadata if isinstance(application_metadata, dict) else {}
        revision = self._revision(metadata.get("revision"))
        started_at = self._timestamp(metadata.get("started_at_utc"))
        normalized["application"] = {
            "revision": revision or "UNAVAILABLE",
            "started_at_utc": started_at,
        }
        try:
            payload = json.dumps(
                normalized,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError):
            return self._error("PERIOD_PROFIT_SUPPORT_DIAGNOSTIC_SERIALIZATION_FAILED")
        if len(payload) > self.MAX_BYTES:
            return self._error("PERIOD_PROFIT_SUPPORT_DIAGNOSTIC_SIZE_LIMIT_EXCEEDED")
        return {
            "error": False,
            "status": "PERIOD_PROFIT_SUPPORT_DIAGNOSTIC_READY",
            "document_kind": "support_diagnostic",
            "filename": "period_profit_support_diagnostic.json",
            "mime_type": "application/json",
            "file_content": payload,
            "size_bytes": len(payload),
            "read_only": True,
            "executed": False,
        }

    def _valid_snapshot(self, snapshot):
        if not isinstance(snapshot, dict):
            return False
        period = snapshot.get("period")
        operation = snapshot.get("operation")
        return (
            snapshot.get("schema") == "period_profit_support_diagnostic"
            and isinstance(snapshot.get("schema_version"), int)
            and not isinstance(snapshot.get("schema_version"), bool)
            and snapshot.get("schema_version") == self.SCHEMA_VERSION
            and isinstance(period, dict)
            and self._date(period.get("from")) is not None
            and self._date(period.get("to")) is not None
            and self._date(period.get("from")) <= self._date(period.get("to"))
            and isinstance(operation, dict)
            and isinstance(snapshot.get("counts"), dict)
            and isinstance(snapshot.get("status_codes"), dict)
        )

    def _normalize_snapshot(self, snapshot):
        period = snapshot.get("period") if isinstance(snapshot.get("period"), dict) else {}
        operation = snapshot.get("operation") if isinstance(snapshot.get("operation"), dict) else {}
        statuses = snapshot.get("status_codes") if isinstance(snapshot.get("status_codes"), dict) else {}
        completeness = snapshot.get("source_completeness")
        reasons = snapshot.get("reason_codes")
        counts = snapshot.get("counts")
        generated_at = self._timestamp(operation.get("generated_at_utc"))
        if generated_at is None:
            generated_at = self._timestamp(self.utc_clock())
        if generated_at is None:
            return {}
        normalized_completeness = {}
        if isinstance(completeness, dict):
            normalized_completeness = {
                key: value for key, value in completeness.items()
                if isinstance(key, str)
                and key in self.COMPLETENESS_KEYS
                and isinstance(value, str)
                and value in self.COMPLETENESS_CODES
            }
        normalized_reasons = list(dict.fromkeys(
            value for value in reasons
            if isinstance(value, str) and value in self.REASON_CODES
        )) if isinstance(reasons, (list, tuple)) else []
        allowed_count_keys = {
            "events_total", "events_dropped", "http_attempts",
            "http_attempt_cap", "rows_attempted", "rows_completed",
            "rows_unknown", "elapsed_seconds",
        }
        normalized_counts = {}
        if isinstance(counts, dict):
            normalized_counts = {
                key: self._count(value)
                for key, value in counts.items()
                if isinstance(key, str) and key in allowed_count_keys
            }
        budget_reason = statuses.get("budget_reason")
        if not isinstance(budget_reason, str) or budget_reason not in self.BUDGET_CODES:
            budget_reason = "NONE"
        return {
            "schema": "period_profit_support_diagnostic",
            "schema_version": self.SCHEMA_VERSION,
            "application": {"revision": "UNAVAILABLE", "started_at_utc": None},
            "operation": {
                "id": self._operation_id(operation.get("id")) or uuid4().hex,
                "type": "PERIOD_PROFIT",
                "started_at_utc": self._timestamp(operation.get("started_at_utc")),
                "generated_at_utc": generated_at,
            },
            "period": {
                "from": self._date(period.get("from")),
                "to": self._date(period.get("to")),
            },
            "status_codes": {
                "diagnostic": "PERIOD_PROFIT_DIAGNOSTICS_READY",
                "budget_reason": budget_reason,
            },
            "reason_codes": normalized_reasons,
            "source_completeness": normalized_completeness,
            "counts": normalized_counts,
            "identifier_references": self._normalize_aliases(
                snapshot.get("identifier_references")
            ),
            "field_types": {
                "schema_version": "integer",
                "operation.id": "opaque_random_id",
                "operation.type": "enum",
                "operation.started_at_utc": "utc_datetime_or_null",
                "operation.generated_at_utc": "utc_datetime",
                "period.from": "date",
                "period.to": "date",
                "status_codes": "enum_map",
                "reason_codes": "enum_list",
                "source_completeness": "enum_map",
                "counts": "bounded_integer_map",
                "identifier_references": "masked_alias_map",
            },
        }

    def _masked_identifier_references(self, raw_values):
        if not isinstance(raw_values, (list, tuple)):
            return {}
        aliases = {}
        counters = {"SKU": 0, "PRODUCT": 0}
        references = {}
        for item in raw_values[: self.MAX_IDENTIFIERS]:
            if not isinstance(item, dict):
                continue
            field = item.get("field")
            if not isinstance(field, str):
                continue
            kind_prefix = self.IDENTIFIER_FIELDS.get(field)
            value = item.get("value")
            if (
                kind_prefix is None
                or item.get("kind") != kind_prefix[0]
                or not isinstance(value, str)
                or not value
                or len(value) > 128
            ):
                continue
            kind, prefix = kind_prefix
            identity = (kind, value)
            alias = aliases.get(identity)
            if alias is None:
                counters[kind] += 1
                alias = prefix + f"{counters[kind]:04d}"
                aliases[identity] = alias
            references[field] = alias
        return references

    def _normalize_aliases(self, value):
        if not isinstance(value, dict):
            return {}
        output = {}
        for field, alias in value.items():
            if not isinstance(field, str):
                continue
            spec = self.IDENTIFIER_FIELDS.get(field)
            if spec is None or not isinstance(alias, str):
                continue
            prefix = spec[1]
            if re.fullmatch(re.escape(prefix) + r"\d{4}", alias):
                output[field] = alias
        return output

    def _operation(self, value):
        raw = value if isinstance(value, dict) else {}
        op_id = self._operation_id(raw.get("operation_id")) or uuid4().hex
        return {
            "id": op_id,
            "type": "PERIOD_PROFIT",
            "started_at_utc": self._timestamp(raw.get("started_at_utc")),
            "budget_reason_code": self._budget_reason(raw.get("budget_reason_code")),
            "events_total": self._count(raw.get("events_total")),
            "events_dropped": self._count(raw.get("events_dropped")),
            "http_attempts": self._count(raw.get("http_attempts")),
            "http_attempt_cap": self._count(raw.get("http_attempt_cap")),
            "rows_attempted": self._count(raw.get("rows_attempted")),
            "rows_completed": self._count(raw.get("rows_completed")),
            "rows_unknown": self._count(raw.get("rows_unknown")),
            "elapsed_seconds": self._count(raw.get("elapsed_seconds")),
        }

    @staticmethod
    def _count(value):
        if isinstance(value, bool) or not isinstance(value, int):
            return 0
        return min(max(value, 0), 1000000000)

    @staticmethod
    def _date(value):
        if not isinstance(value, str) or len(value) != 10:
            return None
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None

    @staticmethod
    def _timestamp(value):
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str) and len(value) <= 40:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _operation_id(value):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", value):
            return None
        return value.lower()

    @classmethod
    def _budget_reason(cls, value):
        return value if isinstance(value, str) and value in cls.BUDGET_CODES else "NONE"

    @staticmethod
    def _revision(value):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{7,40}", value):
            return None
        return value.lower()

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True, "executed": False}
