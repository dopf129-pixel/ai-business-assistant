"""Automated historical SKU spend via asynchronous Ozon Performance reports.

Reports are accepted only when the downloaded CSV exposes an unambiguous
SKU and expense column. Missing campaigns, failed jobs or unknown formats
must not be interpreted as zero advertising cost.
"""
import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO, TextIOWrapper
import re
import time
from zipfile import ZipFile, BadZipFile

import requests


class HistoricalReportError(Exception):
    def __init__(
        self, code, campaign_payment_type=None, campaign_id=None,
        report_format_stage=None,
    ):
        self.code = code
        self.campaign_payment_type = campaign_payment_type
        self.campaign_id = campaign_id
        self.report_format_stage = report_format_stage
        super().__init__(code)


def _number(value):
    text = str(value or "").replace("\u00a0", "").replace(" ", "").replace(",", ".").strip()
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise HistoricalReportError("OZON_HISTORICAL_EXPENSE_INVALID") from exc
    if not number.is_finite() or number < 0:
        raise HistoricalReportError("OZON_HISTORICAL_EXPENSE_INVALID")
    return number


def _decode(data):
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HistoricalReportError("OZON_HISTORICAL_REPORT_ENCODING")


def parse_report_csv(data, kind):
    """Parse the SKU-level table, not its 'Всего' or campaign summary rows."""
    text = _decode(data)
    lines = text.splitlines()
    aliases = {
        "sku": {"sku", "sku товара", "sku продвигаемого товара"},
        "expense": ({"расход, р, с ндс", "расход, ₽", "расход, р", "расход"}
                    if kind == "CPC" else {"расход, ₽", "расход, р", "расход"}),
    }
    for delimiter in (";", ",", "\t"):
        for i, line in enumerate(lines[:12]):
            header = [x.strip().strip("\ufeff").lower() for x in next(csv.reader([line], delimiter=delimiter))]
            sku_cols = [j for j, value in enumerate(header) if value in aliases["sku"]]
            expense_cols = [j for j, value in enumerate(header) if value in aliases["expense"]]
            if len(sku_cols) != 1 or len(expense_cols) != 1:
                continue
            sku_col, expense_col = sku_cols[0], expense_cols[0]
            output = []
            summary_expenses = []
            for row in csv.reader(lines[i + 1:], delimiter=delimiter):
                if not row or not any(x.strip() for x in row):
                    continue
                if len(row) <= max(sku_col, expense_col):
                    raise HistoricalReportError(
                        "OZON_HISTORICAL_REPORT_FORMAT",
                        report_format_stage="CSV_ROW_TOO_SHORT",
                    )
                sku = row[sku_col].strip()
                if sku.lower() in {"всего", "итого", "total", "bcero"}:
                    # Ozon's CPC CSV can label its total row "Bcero".
                    # Ignore it when product rows exist, but do not turn a
                    # positive or missing campaign-only total into zero SKU spend.
                    summary_expenses.append(row[expense_col].strip())
                    continue
                if not sku.isdecimal():
                    raise HistoricalReportError(
                        "OZON_HISTORICAL_REPORT_FORMAT",
                        report_format_stage="CSV_UNKNOWN_ROW_LABEL",
                    )
                output.append({"sku": sku, "expense": _number(row[expense_col]), "kind": kind})
            if not output and summary_expenses:
                for value in summary_expenses:
                    try:
                        expense = _number(value)
                    except HistoricalReportError as exc:
                        raise HistoricalReportError(
                            "OZON_HISTORICAL_REPORT_FORMAT",
                            report_format_stage="CSV_SUMMARY_WITHOUT_SKU",
                        ) from exc
                    if expense > 0:
                        raise HistoricalReportError(
                            "OZON_HISTORICAL_REPORT_FORMAT",
                            report_format_stage="CSV_SUMMARY_WITHOUT_SKU",
                        )
            return output
    raise HistoricalReportError(
        "OZON_HISTORICAL_REPORT_FORMAT",
        report_format_stage="CSV_HEADER_NOT_FOUND",
    )


class HistoricalPerformanceReports:
    WINDOW_DAYS = 62
    MAX_POLLS = 12
    POLL_SECONDS = 2
    MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024

    def __init__(self, client):
        self.client = client
        self.calls = 0

    @staticmethod
    def _safe_campaign_payment_type(value):
        text = str(value or "").strip().upper()
        if not text:
            return "MISSING"
        if (
            len(text) > 64
            or not text.isascii()
            or not all(character.isalnum() or character == "_" for character in text)
        ):
            return "UNRECOGNIZED_VALUE"
        return text

    def _json(self, method, endpoint, **kwargs):
        token = self.client._access_token()
        if token.get("error"):
            raise HistoricalReportError(token.get("code", "OZON_PERFORMANCE_AUTH_UNAVAILABLE"))
        for attempt in range(2):
            result = self.client._request(method, endpoint, token["access_token"], **kwargs)
            self.calls += 1
            if result.get("status_code") == 401 and attempt == 0:
                token = self.client._access_token(force=True)
                if token.get("error"):
                    raise HistoricalReportError("OZON_PERFORMANCE_AUTH_UNAVAILABLE")
                continue
            if result.get("error"):
                raise HistoricalReportError(result.get("code", "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE"))
            return result
        raise HistoricalReportError("OZON_PERFORMANCE_AUTH_UNAVAILABLE")

    def _campaign_ids(self):
        ids = []
        for page in range(1, 101):
            result = self._json("get", "/api/client/campaign",
                                params={"advObjectType": "SKU", "page": page, "pageSize": 100})
            items = result.get("list")
            if not isinstance(items, list):
                raise HistoricalReportError("OZON_HISTORICAL_CAMPAIGNS_INVALID")
            for item in items:
                if not isinstance(item, dict) or not str(item.get("id", "")).isdecimal():
                    raise HistoricalReportError("OZON_HISTORICAL_CAMPAIGNS_INVALID")
                # Only CPC campaigns are part of this report. The API also
                # exposes CPM as a valid paymentType; it is outside the
                # CPC+CPO SKU scope and must not abort the whole report.
                payment_type = item.get("paymentType")
                missing_payment_type = not str(payment_type or "").strip()
                # This endpoint is explicitly filtered to advObjectType=SKU,
                # which Ozon defines as pay-per-click. Some campaign records
                # omit paymentType; use the filter as the CPC fallback only
                # when the response does not contradict that scope.
                sku_campaign = item.get("advObjectType") in (None, "", "SKU")
                if payment_type == "CPC" or (missing_payment_type and sku_campaign):
                    ids.append(str(item["id"]))
                elif payment_type not in ("CPO", "CPM"):
                    raise HistoricalReportError(
                        "OZON_HISTORICAL_CAMPAIGN_TYPE_UNKNOWN",
                        campaign_payment_type=self._safe_campaign_payment_type(
                            payment_type
                        ),
                        campaign_id=str(item["id"]),
                    )
            if len(items) < 100:
                return list(dict.fromkeys(ids))
        raise HistoricalReportError("OZON_HISTORICAL_CAMPAIGNS_INCOMPLETE")

    def _download(self, uuid):
        token = self.client._access_token()
        if token.get("error"):
            raise HistoricalReportError("OZON_PERFORMANCE_AUTH_UNAVAILABLE")
        for attempt in range(2):
            try:
                response = self.client.session.get(
                    self.client.BASE_URL + "/api/client/statistics/report",
                    headers={"Authorization": "Bearer " + token["access_token"]},
                    params={"UUID": uuid}, timeout=30)
                self.calls += 1
            except requests.exceptions.RequestException as exc:
                raise HistoricalReportError("OZON_HISTORICAL_DOWNLOAD_FAILED") from exc
            if response.status_code == 401 and attempt == 0:
                token = self.client._access_token(force=True)
                if token.get("error"):
                    raise HistoricalReportError("OZON_PERFORMANCE_AUTH_UNAVAILABLE")
                continue
            if response.status_code != 200 or len(response.content) > self.MAX_DOWNLOAD_BYTES:
                raise HistoricalReportError("OZON_HISTORICAL_DOWNLOAD_FAILED")
            return response.content
        raise HistoricalReportError("OZON_HISTORICAL_DOWNLOAD_FAILED")

    def _generate(self, endpoint, payload, kind):
        created = self._json("post", endpoint, json=payload)
        uuid = str(created.get("UUID") or "")
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", uuid):
            raise HistoricalReportError("OZON_HISTORICAL_REPORT_ID_INVALID")
        for attempt in range(self.MAX_POLLS):
            status = self._json("get", "/api/client/statistics/" + uuid)
            if status.get("state") == "OK":
                if not status.get("link"):
                    raise HistoricalReportError("OZON_HISTORICAL_REPORT_LINK_MISSING")
                break
            if status.get("state") not in ("NOT_STARTED", "IN_PROGRESS"):
                raise HistoricalReportError("OZON_HISTORICAL_REPORT_FAILED")
            if attempt < self.MAX_POLLS - 1:
                time.sleep(self.POLL_SECONDS)
        else:
            raise HistoricalReportError("OZON_HISTORICAL_REPORT_TIMEOUT")
        data = self._download(uuid)
        if data[:2] == b"PK":
            try:
                with ZipFile(BytesIO(data)) as archive:
                    members = archive.infolist()
                    if not members or len(members) > 100 or sum(m.file_size for m in members) > self.MAX_DOWNLOAD_BYTES:
                        raise HistoricalReportError(
                            "OZON_HISTORICAL_REPORT_FORMAT",
                            report_format_stage="ZIP_LIMITS_EXCEEDED",
                        )
                    if any(not m.filename.lower().endswith(".csv") for m in members):
                        raise HistoricalReportError(
                            "OZON_HISTORICAL_REPORT_FORMAT",
                            report_format_stage="ZIP_MEMBER_NOT_CSV",
                        )
                    return [row for m in members for row in parse_report_csv(archive.read(m), kind)]
            except BadZipFile as exc:
                raise HistoricalReportError(
                    "OZON_HISTORICAL_REPORT_FORMAT",
                    report_format_stage="ZIP_INVALID",
                ) from exc
        return parse_report_csv(data, kind)

    def load(self, date_from, date_to):
        try:
            start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
            if start > end:
                raise ValueError()
        except ValueError:
            return {"error": True, "code": "OZON_PERFORMANCE_PERIOD_INVALID"}
        try:
            campaigns = self._campaign_ids()
            rows = []
            current = start
            while current <= end:
                finish = min(end, current + timedelta(days=self.WINDOW_DAYS - 1))
                # CPC reports require explicit campaign IDs; split into batches.
                for offset in range(0, len(campaigns), 10):
                    batch = campaigns[offset:offset + 10]
                    rows.extend(self._generate(
                        "/api/client/statistics",
                        {"campaigns": batch, "dateFrom": current.isoformat(),
                         "dateTo": finish.isoformat()},
                        "CPC"))
                # CPO selected products are a distinct cost, never the
                # "Расход (Оплата за клик)" comparison field in this report.
                rows.extend(self._generate(
                    "/api/client/statistic/products/generate",
                    {"from": current.isoformat() + "T00:00:00Z",
                     "to": finish.isoformat() + "T23:59:59Z"}, "CPO"))
                current = finish + timedelta(days=1)
            return {"rows": rows, "external_call_count": self.calls}
        except HistoricalReportError as exc:
            result = {
                "error": True,
                "code": exc.code,
                "external_call_count": self.calls,
            }
            if exc.campaign_payment_type is not None:
                result["campaign_payment_type"] = exc.campaign_payment_type
            if exc.campaign_id is not None:
                result["campaign_id"] = exc.campaign_id
            if exc.report_format_stage is not None:
                result["report_format_stage"] = exc.report_format_stage
            return result
