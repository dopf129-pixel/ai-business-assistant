"""Pure, bounded serializers for owner-requested analytics snapshots."""

import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import io
import json
import re


class AnalyticsExportSerializer:
    SCHEMA_VERSION = 1
    MAX_BYTES = 2 * 1024 * 1024
    MAX_ROWS = 5000
    MAX_COLUMNS = 64
    EXPORT_KINDS = {
        "period_profit": "Прибыль за период",
        "product_overview": "Обзор товаров",
        "unit_price_batch": "Пакетный план цен",
        "unit_price_sensitivity": "Чувствительность цены",
        "plan_fact_comparison": "Сравнение плана с фактом",
        "saved_plan": "Сохранённый план",
        "advertising_cap": "Предел рекламных расходов",
        "sales_mix": "Экономика объёма продаж",
        "plan_comparison": "Сравнение вариантов плана",
    }
    VALUE_TYPES = {"text", "status", "money", "decimal", "integer", "boolean", "json"}
    FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

    def __init__(self, clock=None):
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def serialize(self, export_kind, file_format, columns, rows, metadata=None):
        if not isinstance(export_kind, str) or export_kind not in self.EXPORT_KINDS:
            return self._error("ANALYTICS_EXPORT_KIND_UNSUPPORTED")
        if not isinstance(file_format, str) or file_format not in {"csv", "json"}:
            return self._error("ANALYTICS_EXPORT_FORMAT_UNSUPPORTED")
        schema = self._normalize_columns(columns)
        if isinstance(schema, dict) and schema.get("error") is True:
            return schema
        normalized_rows = self._normalize_rows(schema, rows)
        if isinstance(normalized_rows, dict) and normalized_rows.get("error") is True:
            return normalized_rows
        normalized_metadata = self._normalize_metadata(metadata or {})
        if isinstance(normalized_metadata, dict) and normalized_metadata.get("error") is True:
            return normalized_metadata
        try:
            metadata_size = len(json.dumps(
                normalized_metadata, ensure_ascii=False, allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8"))
        except (TypeError, ValueError, OverflowError):
            return self._error("ANALYTICS_EXPORT_METADATA_INVALID")
        if metadata_size > self.MAX_BYTES:
            return self._error("ANALYTICS_EXPORT_SIZE_LIMIT_EXCEEDED")
        exported_at = self._exported_at()
        try:
            if file_format == "csv":
                payload = self._csv(
                    export_kind, schema, normalized_rows, normalized_metadata
                )
                mime_type = "text/csv"
            else:
                payload = self._json(
                    export_kind, schema, normalized_rows,
                    normalized_metadata, exported_at,
                )
                mime_type = "application/json"
        except (TypeError, ValueError, OverflowError):
            return self._error("ANALYTICS_EXPORT_VALUE_INVALID")
        if len(payload) > self.MAX_BYTES:
            return self._error("ANALYTICS_EXPORT_SIZE_LIMIT_EXCEEDED")
        extension = ".csv" if file_format == "csv" else ".json"
        return {
            "error": False,
            "status": "ANALYTICS_EXPORT_READY",
            "message": f"Файл «{self.EXPORT_KINDS[export_kind]}» сформирован ({len(normalized_rows)} строк).",
            "document_kind": "analytics_export",
            "export_kind": export_kind,
            "schema_version": self.SCHEMA_VERSION,
            "filename": f"ozon_{export_kind}_export{extension}",
            "mime_type": mime_type,
            "file_content": payload,
            "size_bytes": len(payload),
            "row_count": len(normalized_rows),
            "read_only": True,
            "executed": False,
        }

    def _normalize_columns(self, columns):
        if not isinstance(columns, (list, tuple)) or not 1 <= len(columns) <= self.MAX_COLUMNS:
            return self._error("ANALYTICS_EXPORT_SCHEMA_INVALID")
        output = []
        seen = set()
        for column in columns:
            if not isinstance(column, dict):
                return self._error("ANALYTICS_EXPORT_SCHEMA_INVALID")
            key = column.get("key")
            label = column.get("label")
            value_type = column.get("type")
            if (
                not isinstance(key, str) or not self.FIELD_RE.fullmatch(key)
                or key in seen or not isinstance(label, str) or not label
                or value_type not in self.VALUE_TYPES
            ):
                return self._error("ANALYTICS_EXPORT_SCHEMA_INVALID")
            seen.add(key)
            item = {"key": key, "label": label, "type": value_type}
            if column.get("unit") is not None:
                if not isinstance(column["unit"], str):
                    return self._error("ANALYTICS_EXPORT_SCHEMA_INVALID")
                item["unit"] = column["unit"]
            if column.get("semantic") is not None:
                if not isinstance(column["semantic"], str):
                    return self._error("ANALYTICS_EXPORT_SCHEMA_INVALID")
                item["semantic"] = column["semantic"]
            output.append(item)
        return output

    def _normalize_rows(self, columns, rows):
        if not isinstance(rows, (list, tuple)) or len(rows) > self.MAX_ROWS:
            return self._error("ANALYTICS_EXPORT_ROW_LIMIT_EXCEEDED")
        by_key = {column["key"]: column for column in columns}
        normalized = []
        value_bytes = 0
        for row in rows:
            if not isinstance(row, dict) or set(row) - set(by_key):
                return self._error("ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH")
            target = {}
            for column in columns:
                key = column["key"]
                value = row.get(key)
                normalized_value = self._normalize_value(value, column["type"])
                if isinstance(normalized_value, dict) and normalized_value.get("error") is True:
                    return normalized_value
                target[key] = normalized_value
                if normalized_value is not None:
                    try:
                        encoded_value = (
                            json.dumps(normalized_value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                            if by_key[key]["type"] == "json"
                            else str(normalized_value)
                        )
                        value_bytes += len(encoded_value.encode("utf-8"))
                    except (TypeError, ValueError, OverflowError):
                        return self._error("ANALYTICS_EXPORT_VALUE_INVALID")
                    if value_bytes > self.MAX_BYTES:
                        return self._error("ANALYTICS_EXPORT_SIZE_LIMIT_EXCEEDED")
            normalized.append(target)
        return normalized

    def _normalize_value(self, value, value_type):
        if value is None:
            return None
        if value_type in {"money", "decimal"}:
            if isinstance(value, bool):
                return self._error("ANALYTICS_EXPORT_VALUE_INVALID")
            try:
                number = Decimal(str(value).strip().replace(",", "."))
            except (InvalidOperation, TypeError, ValueError):
                return self._error("ANALYTICS_EXPORT_VALUE_INVALID")
            if not number.is_finite() or number.adjusted() > 1000 or number.adjusted() < -1000:
                return self._error("ANALYTICS_EXPORT_VALUE_INVALID")
            rendered = format(number, "f")
            if len(rendered) > self.MAX_BYTES:
                return self._error("ANALYTICS_EXPORT_SIZE_LIMIT_EXCEEDED")
            return rendered
        if value_type == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                return self._error("ANALYTICS_EXPORT_VALUE_INVALID")
            return value
        if value_type == "boolean":
            return value if isinstance(value, bool) else self._error("ANALYTICS_EXPORT_VALUE_INVALID")
        if value_type == "json":
            try:
                normalized = self._json_safe(value)
                json.dumps(normalized, ensure_ascii=False, allow_nan=False)
                return normalized
            except (TypeError, ValueError, OverflowError):
                return self._error("ANALYTICS_EXPORT_VALUE_INVALID")
        if value_type in {"text", "status"}:
            if not isinstance(value, str) or len(value.encode("utf-8")) > self.MAX_BYTES:
                return self._error("ANALYTICS_EXPORT_VALUE_INVALID")
            return value
        return self._error("ANALYTICS_EXPORT_VALUE_INVALID")

    def _normalize_metadata(self, metadata):
        if not isinstance(metadata, dict):
            return self._error("ANALYTICS_EXPORT_METADATA_INVALID")
        try:
            return self._json_safe(metadata)
        except (TypeError, ValueError, OverflowError):
            return self._error("ANALYTICS_EXPORT_METADATA_INVALID")

    def _json(self, export_kind, columns, rows, metadata, exported_at):
        document = {
            "document_kind": "owner_analytics_export",
            "export_kind": export_kind,
            "schema_version": self.SCHEMA_VERSION,
            "title": self.EXPORT_KINDS[export_kind],
            "exported_at_utc": exported_at,
            "metadata": metadata,
            "columns": columns,
            "rows": rows,
        }
        return json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")

    def _csv(self, export_kind, columns, rows, metadata):
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, delimiter=";", lineterminator="\r\n")
        writer.writerow(["document_kind", "owner_analytics_export"])
        writer.writerow(["export_kind", export_kind])
        writer.writerow(["schema_version", str(self.SCHEMA_VERSION)])
        writer.writerow(["metadata_json", json.dumps(metadata, ensure_ascii=False, allow_nan=False, separators=(",", ":"))])
        writer.writerow(["columns_json", json.dumps(columns, ensure_ascii=False, allow_nan=False, separators=(",", ":"))])
        writer.writerow([])
        writer.writerow([
            self._safe_text(
                column["label"] + (f" ({column['unit']})" if column.get("unit") else "")
            )
            for column in columns
        ])
        for row in rows:
            values = []
            for column in columns:
                value = row[column["key"]]
                if value is None:
                    values.append("")
                elif column["type"] == "money":
                    values.append(value.replace(".", ","))
                elif column["type"] == "decimal":
                    values.append(value.replace(".", ","))
                elif column["type"] == "boolean":
                    values.append("true" if value else "false")
                elif column["type"] == "json":
                    values.append(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
                else:
                    values.append(self._safe_text(str(value)))
            writer.writerow(values)
        return ("\ufeff" + stream.getvalue()).encode("utf-8")

    @staticmethod
    def _safe_text(value):
        text = str(value)
        stripped = text.lstrip(" \t\r\n\v\f\u00a0")
        if stripped.startswith(("=", "+", "-", "@")):
            return "'" + text
        return text

    def _exported_at(self):
        value = self.clock()
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, date):
            dt = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
        else:
            return "unknown"
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _json_safe(self, value, depth=0):
        if depth > 8:
            raise ValueError("metadata nesting is too deep")
        if value is None or isinstance(value, (str, bool, int)):
            if isinstance(value, str) and len(value.encode("utf-8")) > self.MAX_BYTES:
                raise ValueError("metadata string is too long")
            return value
        if isinstance(value, float):
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError("nonfinite metadata")
            return value
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise ValueError("nonfinite metadata")
            return format(value, "f")
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, dict):
            if not all(isinstance(key, str) for key in value):
                raise ValueError("metadata keys must be text")
            return {key: self._json_safe(item, depth + 1) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._json_safe(item, depth + 1) for item in value]
        raise ValueError("unsupported metadata value")

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True, "executed": False}
