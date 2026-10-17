import csv
import io
import json
from datetime import datetime, timezone

from services.analytics_export_serializer import AnalyticsExportSerializer


def _serializer():
    return AnalyticsExportSerializer(
        clock=lambda: datetime(2026, 10, 17, 10, 30, tzinfo=timezone.utc)
    )


def _columns():
    return [
        {"key": "sku", "label": "SKU", "type": "text"},
        {"key": "profit", "label": "Прибыль", "type": "money", "unit": "RUB"},
        {"key": "margin", "label": "Маржа", "type": "decimal", "unit": "%"},
        {"key": "status", "label": "Статус", "type": "status"},
        {"key": "units", "label": "Штук", "type": "integer", "unit": "шт."},
    ]


def test_csv_is_utf8_bom_semicolon_and_spreadsheet_safe_for_text_only():
    result = _serializer().serialize(
        "product_overview", "csv", _columns(),
        [{
            "sku": "\t=HYPERLINK(\"https://invalid\")\nSKU-1",
            "profit": "-1234.56", "margin": "0", "status": "READY", "units": 0,
        }],
        metadata={"filter": "all", "sort": "profit"},
    )

    assert result["error"] is False
    payload = result["file_content"]
    assert payload.startswith(b"\xef\xbb\xbf")
    text = payload.decode("utf-8-sig")
    assert "metadata_json;" in text
    assert "=HYPERLINK" in text
    assert "'\t=HYPERLINK" in text
    assert "-1234,56" in text  # numeric negatives are not apostrophe-prefixed
    assert "\"" in text  # CSV writer quotes the cell with quotes/newlines.
    assert result["filename"] == "ozon_product_overview_export.csv"
    assert result["document_kind"] == "analytics_export"


def test_json_is_versioned_preserves_null_zero_and_decimal_strings():
    result = _serializer().serialize(
        "period_profit", "json", _columns(),
        [
            {"sku": "SKU-1", "profit": "0", "margin": None, "status": "UNKNOWN", "units": 0},
            {"sku": "SKU-2", "profit": None, "margin": "12.345", "status": "READY", "units": 3},
        ],
        metadata={"coverage": {"selected": 2, "reported": 1}},
    )

    payload = json.loads(result["file_content"].decode("utf-8"))
    assert payload["document_kind"] == "owner_analytics_export"
    assert payload["schema_version"] == 1
    assert payload["export_kind"] == "period_profit"
    assert payload["exported_at_utc"] == "2026-10-17T10:30:00Z"
    assert payload["rows"][0]["profit"] == "0"
    assert payload["rows"][0]["margin"] is None
    assert payload["rows"][1]["profit"] is None
    assert payload["rows"][1]["margin"] == "12.345"
    assert payload["rows"][0]["units"] == 0
    assert payload["columns"][1]["unit"] == "RUB"


def test_csv_empty_unknown_and_zero_are_distinguishable():
    result = _serializer().serialize(
        "unit_price_batch", "csv", _columns(),
        [
            {"sku": "A", "profit": None, "margin": None, "status": "UNKNOWN", "units": None},
            {"sku": "B", "profit": 0, "margin": 0, "status": "READY", "units": 0},
        ],
    )
    rows = list(csv.reader(io.StringIO(result["file_content"].decode("utf-8-sig"), newline=""), delimiter=";"))
    header_index = rows.index(["SKU", "Прибыль (RUB)", "Маржа (%)", "Статус", "Штук (шт.)"])
    assert rows[header_index + 1][1] == ""
    assert rows[header_index + 2][1] == "0"
    assert rows[header_index + 1][4] == ""
    assert rows[header_index + 2][4] == "0"


def test_serializer_rejects_nonfinite_values_extra_fields_and_oversize_without_truncating():
    serializer = _serializer()
    columns = _columns()
    base_row = {"sku": "SKU", "profit": 1, "margin": 2, "status": "READY", "units": 1}
    assert serializer.serialize("unit_price_batch", "json", columns, [{**base_row, "extra": 1}])["code"] == "ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH"
    assert serializer.serialize("unit_price_batch", "json", columns, [{**base_row, "profit": float("nan")}])["code"] == "ANALYTICS_EXPORT_VALUE_INVALID"
    too_large = {**base_row, "sku": "x" * serializer.MAX_BYTES}
    assert serializer.serialize("unit_price_batch", "csv", columns, [too_large])["code"] == "ANALYTICS_EXPORT_SIZE_LIMIT_EXCEEDED"


def test_serializer_rejects_invalid_schema_and_never_silently_truncates_rows():
    serializer = _serializer()
    assert serializer.serialize("unknown", "csv", _columns(), [])["error"] is True
    assert serializer.serialize("unit_price_batch", "xlsx", _columns(), [])["error"] is True
    too_many = [{}] * (serializer.MAX_ROWS + 1)
    assert serializer.serialize("unit_price_batch", "json", _columns(), too_many)["code"] == "ANALYTICS_EXPORT_ROW_LIMIT_EXCEEDED"
