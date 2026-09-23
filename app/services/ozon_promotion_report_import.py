"""Strict reader for manually exported Ozon 'Аналитика продвижения' XLSX files.

Only the SKU-level primary table is financial evidence. The merged-card
table describes attributed sales, not additional advertising spend.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile

_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_PERIOD = re.compile(r"Период:\\s*(\\d{2}\\.\\d{2}\\.\\d{4})\\s*-\\s*(\\d{2}\\.\\d{2}\\.\\d{4})")
_HEADER = ("SKU", "Название товара", "Инструмент", "Место размещения",
           "ID кампании", "Расход, ₽")
_ALLOWED = {"Оплата за клик", "Оплата за заказ: выбранные товары"}
_MAX_BYTES = 15 * 1024 * 1024


class PromotionReportError(ValueError):
    pass


def _column(ref):
    letters = re.match(r"[A-Z]+", ref)
    if not letters:
        raise PromotionReportError("Invalid spreadsheet cell")
    number = 0
    for char in letters.group():
        number = number * 26 + ord(char) - 64
    return number - 1


def _sheet_rows(archive, path, strings):
    root = ET.fromstring(archive.read(path))
    rows = []
    for row in root.findall(".//x:sheetData/x:row", _NS):
        cells = {}
        for cell in row.findall("x:c", _NS):
            value = cell.find("x:v", _NS)
            inline = cell.find("x:is", _NS)
            if value is not None:
                text = value.text or ""
                if cell.get("t") == "s":
                    text = strings[int(text)]
            elif inline is not None:
                text = "".join(node.text or "" for node in inline.findall(".//x:t", _NS))
            else:
                text = ""
            cells[_column(cell.get("r", ""))] = text
        rows.append(cells)
    return rows


def parse_promotion_report(data):
    """Return period and unrounded SKU-level rows, or reject ambiguous exports."""
    if not isinstance(data, bytes) or len(data) > _MAX_BYTES:
        raise PromotionReportError("Invalid report size")
    try:
        with ZipFile(BytesIO(data)) as archive:
            if len(archive.namelist()) > 120 or sum(i.file_size for i in archive.infolist()) > 40 * 1024 * 1024:
                raise PromotionReportError("Report exceeds extraction limits")
            strings = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                strings = ["".join(t.text or "" for t in si.findall(".//x:t", _NS))
                           for si in root.findall("x:si", _NS)]
            candidates = []
            for path in archive.namelist():
                if not re.fullmatch(r"xl/worksheets/sheet\\d+\\.xml", path):
                    continue
                rows = _sheet_rows(archive, path, strings)
                if len(rows) < 2:
                    continue
                header = tuple(rows[1].get(i, "") for i in range(6))
                if header == _HEADER:
                    candidates.append(rows)
            if len(candidates) != 1:
                raise PromotionReportError("Expected exactly one SKU-level promotion table")
            rows = candidates[0]
            match = _PERIOD.fullmatch(rows[0].get(0, "").strip())
            if not match:
                raise PromotionReportError("Missing report date range")
            start, end = (datetime.strptime(x, "%d.%m.%Y").date() for x in match.groups())
            if start > end:
                raise PromotionReportError("Invalid report date range")
            output = []
            seen = set()
            for row in rows[2:]:
                if not any(str(v).strip() for v in row.values()):
                    continue
                sku = str(row.get(0, "")).strip()
                kind = str(row.get(2, "")).strip()
                campaign = str(row.get(4, "")).strip()
                if not sku.isdecimal() or kind not in _ALLOWED or not campaign.isdecimal():
                    raise PromotionReportError("Invalid SKU, campaign or promotion type")
                try:
                    amount = Decimal(str(row.get(5, "")).strip().replace(",", "."))
                except InvalidOperation as exc:
                    raise PromotionReportError("Invalid advertising expense") from exc
                if not amount.is_finite() or amount < 0:
                    raise PromotionReportError("Invalid advertising expense")
                key = (sku, kind, str(row.get(3, "")).strip(), campaign)
                if key in seen:
                    raise PromotionReportError("Duplicate campaign/SKU/type rows")
                seen.add(key)
                output.append({"sku": sku, "instrument": kind,
                               "campaign_id": campaign, "expense": amount})
            if not output:
                raise PromotionReportError("Empty promotion report")
            return {"date_from": start.isoformat(), "date_to": end.isoformat(),
                    "rows": output}
    except (BadZipFile, ET.ParseError, KeyError, IndexError, ValueError) as exc:
        if isinstance(exc, PromotionReportError):
            raise
        raise PromotionReportError("Invalid XLSX report") from exc


def combine_reports(reports, date_from, date_to, accepted_skus):
    """Only complete, non-overlapping coverage is accepted; never prorate totals."""
    start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    ordered = sorted(reports, key=lambda r: r["date_from"])
    current = start
    selected = {str(s) for s in accepted_skus}
    totals = {"Оплата за клик": Decimal("0"), "Оплата за заказ: выбранные товары": Decimal("0")}
    matched = 0
    for report in ordered:
        a, z = date.fromisoformat(report["date_from"]), date.fromisoformat(report["date_to"])
        if a != current or z > end:
            raise PromotionReportError("Reports must exactly cover the requested dates without overlaps")
        for row in report["rows"]:
            if row["sku"] in selected:
                totals[row["instrument"]] += row["expense"]
                matched += 1
        current = z + timedelta(days=1)
    if current != end + timedelta(days=1):
        raise PromotionReportError("Historical advertising report coverage is incomplete")
    return {"date_from": date_from, "date_to": date_to, "matched_row_count": matched,
            "cpc_expense": totals["Оплата за клик"],
            "order_expense": totals["Оплата за заказ: выбранные товары"],
            "total_expense": sum(totals.values())}
