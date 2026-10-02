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


CPO_REPORT_ENDPOINTS = frozenset({
    "/api/client/statistic/orders/generate",
    "/api/client/statistics/all_sku_promo/orders/generate",
})


class HistoricalReportError(Exception):
    def __init__(
        self, code, campaign_payment_type=None, campaign_id=None,
        campaign_diagnostics=None, campaign_unknown_count=None,
        report_format_stage=None, report_format_columns=None,
        report_format_row_label=None, report_format_kind=None, dependency_stage=None,
        dependency_error_type=None, report_format_endpoint=None,
        report_format_order_sku_present=None,
    ):
        self.code = code
        self.campaign_payment_type = campaign_payment_type
        self.campaign_id = campaign_id
        self.campaign_diagnostics = campaign_diagnostics
        self.campaign_unknown_count = campaign_unknown_count
        self.report_format_stage = report_format_stage
        self.report_format_columns = report_format_columns
        self.report_format_row_label = report_format_row_label
        self.report_format_kind = report_format_kind
        self.report_format_endpoint = report_format_endpoint
        self.report_format_order_sku_present = report_format_order_sku_present
        self.dependency_stage = dependency_stage
        self.dependency_error_type = dependency_error_type
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


def _report_header_columns(lines):
    hints = (
        "sku", "артикул", "товар", "расход", "expense", "spend",
        "стоим", "оплат", "заказ", "кампан", "клик", "показ",
        "выруч", "сумма", "дата",
    )
    candidates = []
    for delimiter_index, delimiter in enumerate((";", ",", "\t")):
        for line_index, line in enumerate(lines[:12]):
            try:
                cells = next(csv.reader([line], delimiter=delimiter))
            except csv.Error:
                continue
            cells = [
                " ".join(cell.replace("\ufeff", "").replace("\u00a0", " ").split())
                for cell in cells
            ]
            cells = [cell for cell in cells if cell]
            if not 2 <= len(cells) <= 24:
                continue
            if any(len(cell) > 64 or any(char.isdigit() for char in cell) for cell in cells):
                continue
            hint_count = sum(
                any(hint in cell.casefold() for hint in hints)
                for cell in cells
            )
            if hint_count < 2:
                continue
            candidates.append((len(cells), line_index, -delimiter_index, cells))
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate[:3])[3]


def parse_report_csv(
    data, kind, *, allow_order_sku_fallback=False, report_endpoint=None,
):
    """Parse the SKU-level table, not its 'Всего' or campaign summary rows."""
    text = _decode(data)
    lines = text.splitlines()
    aliases = {
        # For pay-per-order order reports, the cost belongs to the promoted
        # product. The separate order SKU can be different and must not receive
        # the advertising expense.
        "sku": ({"sku", "sku товара", "sku продвигаемого товара"}
                if kind == "CPC" else {"sku продвигаемого товара"}),
        "expense": ({"расход, р, с ндс", "расход, ₽, с ндс", "расход, ₽", "расход, р", "расход"}
                    if kind == "CPC" else {"расход, ₽", "расход, р", "расход"}),
    }
    for delimiter in (";", ",", "\t"):
        for i, line in enumerate(lines[:12]):
            header_cells = next(csv.reader([line], delimiter=delimiter))
            header = [x.strip().strip("\ufeff").lower() for x in header_cells]
            sku_cols = [j for j, value in enumerate(header) if value in aliases["sku"]]
            expense_cols = [j for j, value in enumerate(header) if value in aliases["expense"]]
            if len(sku_cols) != 1 or len(expense_cols) != 1:
                continue
            sku_col, expense_col = sku_cols[0], expense_cols[0]
            order_sku_cols = [
                j for j, value in enumerate(header)
                if value in {"sku", "sku товара"}
            ]
            order_sku_col = (
                order_sku_cols[0]
                if kind == "CPO" and len(order_sku_cols) == 1
                else None
            )
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
                normalized_row = [
                    cell.strip().strip("\ufeff").lower() for cell in row
                ]
                if len(normalized_row) == len(header) and normalized_row == header:
                    # Some exported reports repeat the table header between
                    # sections. It is unambiguous because every cell matches;
                    # arbitrary non-numeric SKU labels still fail closed.
                    continue
                sku = row[sku_col].strip()
                if sku.lower() in {"всего", "итого", "total", "bcero"}:
                    # Ozon's CPC CSV can label its total row "Bcero".
                    # Ignore it when product rows exist, but do not turn a
                    # positive or missing campaign-only total into zero SKU spend.
                    summary_expenses.append(row[expense_col].strip())
                    continue
                if not sku.isdecimal():
                    if not sku:
                        try:
                            if _number(row[expense_col]) == 0:
                                # A row with no promoted SKU and no spend cannot
                                # change SKU profit; ignore it safely.
                                continue
                        except HistoricalReportError:
                            pass
                        if (
                            allow_order_sku_fallback
                            and order_sku_col is not None
                            and len(row) > order_sku_col
                            and row[order_sku_col].strip().isdecimal()
                        ):
                            # In the all-products CPO report, order SKU is the
                            # only available product identity when promoted SKU
                            # is omitted.
                            sku = row[order_sku_col].strip()
                    if not sku.isdecimal():
                        raise HistoricalReportError(
                            "OZON_HISTORICAL_REPORT_FORMAT",
                            report_format_stage="CSV_UNKNOWN_ROW_LABEL",
                            report_format_columns=header_cells,
                            # Avoid exposing row contents: a malformed SKU cell
                            # can contain order or product data.
                            report_format_row_label="EMPTY" if not sku else "NON_NUMERIC",
                            report_format_kind=kind,
                            report_format_endpoint=(
                                report_endpoint if kind == "CPO"
                                and report_endpoint in CPO_REPORT_ENDPOINTS else None
                            ),
                            report_format_order_sku_present=(
                                bool(
                                    order_sku_col is not None
                                    and len(row) > order_sku_col
                                    and row[order_sku_col].strip()
                                )
                                if kind == "CPO" else None
                            ),
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
        report_format_columns=_report_header_columns(lines),
        report_format_kind=kind,
    )


class HistoricalPerformanceReports:
    WINDOW_DAYS = 62
    MAX_POLLS = 30
    POLL_SECONDS = 5
    MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
    CAMPAIGN_LOOKUP_BATCH_SIZE = 50
    MAX_CAMPAIGN_LOOKUP_IDS = 100
    MAX_CAMPAIGN_DIAGNOSTICS = 10
    RATE_LIMIT_DEFAULT_RETRY_SECONDS = 5
    RATE_LIMIT_MAX_RETRY_SECONDS = 60
    DEPENDENCY_ERROR_TYPES = frozenset({
        "TIMEOUT", "CONNECTION_ERROR", "TLS_ERROR", "REQUEST_ERROR",
    })

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

    @staticmethod
    def _safe_campaign_enum(value):
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

    @staticmethod
    def _campaign_date(value):
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            try:
                # Campaign dates are date-only values; createdAt is an ISO
                # timestamp. Its calendar day is enough for the conservative
                # outside-period check.
                return datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                ).date()
            except ValueError:
                # Unparseable optional dates cannot justify excluding a
                # campaign. A missing/unknown payment type will still fail
                # closed below.
                return None

    @classmethod
    def _campaign_outside_period(cls, item, date_from, date_to):
        starts = cls._campaign_date(item.get("fromDate"))
        ends = cls._campaign_date(item.get("toDate"))
        created = cls._campaign_date(item.get("createdAt"))
        # A future start, a past end, or creation after the requested window
        # proves that the campaign could not have incurred spend in that
        # period. Keep unknown-type campaigns that overlap or lack dates
        # fail-closed so no potentially relevant expense is silently omitted.
        return (
            (starts is not None and starts > date_to)
            or (ends is not None and ends < date_from)
            or (created is not None and created > date_to)
        )

    @classmethod
    def _campaign_diagnostic(cls, item, lookup_status):
        def safe_date(key):
            raw = item.get(key)
            parsed = cls._campaign_date(raw)
            if parsed is not None:
                return parsed.isoformat()
            return "MISSING" if raw in (None, "") else "UNPARSEABLE"

        return {
            "campaign_id": str(item.get("id", "")),
            "payment_type": cls._safe_campaign_payment_type(item.get("paymentType")),
            "adv_object_type": cls._safe_campaign_enum(item.get("advObjectType")),
            "state": cls._safe_campaign_enum(item.get("state")),
            "from_date": safe_date("fromDate"),
            "to_date": safe_date("toDate"),
            "created_at": safe_date("createdAt"),
            "lookup_status": lookup_status,
        }

    @classmethod
    def _campaign_lookup_failure_status(cls, exc):
        if exc.code == "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE":
            error_type = exc.dependency_error_type
            if error_type in cls.DEPENDENCY_ERROR_TYPES:
                return "DEPENDENCY_" + error_type
            return "DEPENDENCY_UNAVAILABLE"
        match = re.fullmatch(r"OZON_PERFORMANCE_HTTP_(\d{3})", str(exc.code))
        if match:
            status_code = int(match.group(1))
            if 400 <= status_code <= 599:
                return "HTTP_" + str(status_code)
        if exc.code == "OZON_PERFORMANCE_RESPONSE_INVALID":
            return "RESPONSE_INVALID"
        return "LOOKUP_FAILED"

    def _lookup_campaigns(self, campaigns):
        """Recheck ambiguous campaign IDs without the initial object-type filter."""
        refreshed = {}
        lookup_status = {}
        campaign_ids = list(dict.fromkeys(str(item["id"]) for item in campaigns))
        lookup_ids = campaign_ids[:self.MAX_CAMPAIGN_LOOKUP_IDS]
        lookup_status.update({
            campaign_id: "LOOKUP_LIMIT_REACHED"
            for campaign_id in campaign_ids[self.MAX_CAMPAIGN_LOOKUP_IDS:]
        })
        for offset in range(0, len(lookup_ids), self.CAMPAIGN_LOOKUP_BATCH_SIZE):
            batch = lookup_ids[offset:offset + self.CAMPAIGN_LOOKUP_BATCH_SIZE]
            try:
                result = self._json(
                    "get", "/api/client/campaign",
                    params={"campaignIds": batch, "page": 1, "pageSize": len(batch)},
                    dependency_stage="CAMPAIGN_LOOKUP",
                )
            except HistoricalReportError as exc:
                if exc.code == "OZON_PERFORMANCE_AUTH_UNAVAILABLE":
                    raise
                failure_status = self._campaign_lookup_failure_status(exc)
                lookup_status.update({
                    campaign_id: failure_status for campaign_id in batch
                })
                continue
            items = result.get("list")
            if not isinstance(items, list):
                lookup_status.update({campaign_id: "INVALID_RESPONSE" for campaign_id in batch})
                continue
            batch_set = set(batch)
            for item in items:
                if not isinstance(item, dict):
                    continue
                campaign_id = str(item.get("id", ""))
                if campaign_id in batch_set and campaign_id.isdecimal():
                    refreshed[campaign_id] = item
                    lookup_status[campaign_id] = "FOUND"
            for campaign_id in batch:
                lookup_status.setdefault(campaign_id, "NOT_FOUND")
        return refreshed, lookup_status

    def _json(self, method, endpoint, *, dependency_stage=None, **kwargs):
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
            if (
                result.get("status_code") == 429
                and attempt == 0
                and str(method or "").lower() == "get"
                and dependency_stage in self.RETRYABLE_DEPENDENCY_STAGES
            ):
                retry_after = result.get("retry_after_seconds")
                if retry_after is None:
                    retry_seconds = self.RATE_LIMIT_DEFAULT_RETRY_SECONDS
                elif (
                    isinstance(retry_after, (int, float))
                    and not isinstance(retry_after, bool)
                    and 0 <= retry_after <= self.RATE_LIMIT_MAX_RETRY_SECONDS
                ):
                    retry_seconds = retry_after
                else:
                    # Keep the error visible when the provider's cooldown is
                    # longer than this worker may wait.
                    retry_seconds = None
                if retry_seconds is not None:
                    time.sleep(retry_seconds)
                    continue
            if result.get("error"):
                code = result.get("code", "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE")
                safe_stage = (
                    dependency_stage
                    if code == "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE"
                    and dependency_stage in self.DEPENDENCY_STAGES
                    else None
                )
                if code == "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE":
                    error_type = result.get("dependency_error_type")
                    safe_error_type = (
                        error_type
                        if isinstance(error_type, str)
                        and error_type in self.DEPENDENCY_ERROR_TYPES
                        else None
                    )
                    # Only known read operations are safe to repeat. All-
                    # products report creation uses GET too, so the HTTP verb
                    # alone cannot determine retry safety.
                    if (
                        dependency_stage in self.RETRYABLE_DEPENDENCY_STAGES
                        and str(method or "").lower() == "get"
                        and attempt == 0
                    ):
                        time.sleep(1)
                        continue
                    raise HistoricalReportError(
                        code,
                        dependency_stage=safe_stage,
                        dependency_error_type=safe_error_type,
                    )
                raise HistoricalReportError(code)
            return result
        raise HistoricalReportError("OZON_PERFORMANCE_AUTH_UNAVAILABLE")

    def _campaign_ids(self, date_from=None, date_to=None):
        ids = []
        unknown_campaigns = []
        for page in range(1, 101):
            result = self._json("get", "/api/client/campaign",
                                params={"advObjectType": "SKU", "page": page, "pageSize": 100},
                                dependency_stage="CAMPAIGN_LIST")
            items = result.get("list")
            if not isinstance(items, list):
                raise HistoricalReportError("OZON_HISTORICAL_CAMPAIGNS_INVALID")
            for item in items:
                if not isinstance(item, dict) or not str(item.get("id", "")).isdecimal():
                    raise HistoricalReportError("OZON_HISTORICAL_CAMPAIGNS_INVALID")
                if (
                    date_from is not None
                    and date_to is not None
                    and self._campaign_outside_period(item, date_from, date_to)
                ):
                    continue
                # Ozon documents SKU as "Оплата за клик" and
                # SEARCH_PROMO as "Оплата за заказ". Legacy campaign records
                # may omit paymentType; use the documented SKU type only for
                # a missing/invalid placeholder. An explicit paymentType wins.
                payment_type = item.get("paymentType")
                missing_payment_type = (
                    not str(payment_type or "").strip()
                    or str(payment_type).strip().upper() == "CAMPAIGN_TYPE_INVALID"
                )
                if payment_type == "CPC" or (
                    missing_payment_type and item.get("advObjectType") == "SKU"
                ):
                    ids.append(str(item["id"]))
                elif payment_type not in ("CPO", "CPM"):
                    unknown_campaigns.append(dict(item))
            if len(items) < 100:
                break
        else:
            raise HistoricalReportError("OZON_HISTORICAL_CAMPAIGNS_INCOMPLETE")

        if unknown_campaigns:
            refreshed, lookup_status = self._lookup_campaigns(unknown_campaigns)
            unresolved = []
            for listed_item in unknown_campaigns:
                campaign_id = str(listed_item["id"])
                item = dict(listed_item)
                detailed_item = refreshed.get(campaign_id)
                if detailed_item:
                    # Prefer non-empty values from the unfiltered lookup while
                    # retaining useful fields from the paginated listing.
                    item.update({
                        key: value for key, value in detailed_item.items()
                        if value not in (None, "")
                    })
                if (
                    date_from is not None
                    and date_to is not None
                    and self._campaign_outside_period(item, date_from, date_to)
                ):
                    continue
                payment_type = item.get("paymentType")
                missing_payment_type = (
                    not str(payment_type or "").strip()
                    or str(payment_type).strip().upper() == "CAMPAIGN_TYPE_INVALID"
                )
                if payment_type == "CPC" or (
                    missing_payment_type and item.get("advObjectType") == "SKU"
                ):
                    ids.append(campaign_id)
                elif payment_type not in ("CPO", "CPM"):
                    # Keep explicit unknown payment values fail-closed. The
                    # objects response cannot override the declared payment
                    # model, and is unnecessary when Ozon documents SKU as CPC.
                    diagnostic = self._campaign_diagnostic(
                        item, lookup_status.get(campaign_id, "UNAVAILABLE")
                    )
                    diagnostic["objects_lookup_status"] = "NOT_APPLICABLE"
                    unresolved.append(diagnostic)
            if unresolved:
                first = unresolved[0]
                raise HistoricalReportError(
                    "OZON_HISTORICAL_CAMPAIGN_TYPE_UNKNOWN",
                    campaign_payment_type=first["payment_type"],
                    campaign_id=first["campaign_id"],
                    campaign_diagnostics=unresolved[:self.MAX_CAMPAIGN_DIAGNOSTICS],
                    campaign_unknown_count=len(unresolved),
                )

        return list(dict.fromkeys(ids))

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

    DEPENDENCY_STAGES = frozenset({
        "CAMPAIGN_LIST",
        "CAMPAIGN_OBJECTS",
        "CAMPAIGN_LOOKUP",
        "CPC_REPORT_CREATE",
        "CPC_REPORT_STATUS",
        "CPO_SELECTED_ORDERS_REPORT_CREATE",
        "CPO_SELECTED_ORDERS_REPORT_STATUS",
        "CPO_ALL_SKU_ORDERS_REPORT_CREATE",
        "CPO_ALL_SKU_ORDERS_REPORT_STATUS",
    })
    RETRYABLE_DEPENDENCY_STAGES = frozenset({
        "CAMPAIGN_LIST",
        "CAMPAIGN_OBJECTS",
        "CAMPAIGN_LOOKUP",
        "CPC_REPORT_STATUS",
        "CPO_SELECTED_ORDERS_REPORT_STATUS",
        "CPO_ALL_SKU_ORDERS_REPORT_STATUS",
    })

    REPORT_DEPENDENCY_PREFIXES = {
        "/api/client/statistics": "CPC_REPORT",
        "/api/client/statistic/orders/generate": "CPO_SELECTED_ORDERS_REPORT",
        "/api/client/statistics/all_sku_promo/orders/generate": "CPO_ALL_SKU_ORDERS_REPORT",
    }

    def _generate(
        self, endpoint, payload, kind, *, method="post", query_params=False,
        allow_order_sku_fallback=False,
    ):
        dependency_prefix = self.REPORT_DEPENDENCY_PREFIXES.get(
            endpoint, "HISTORICAL_REPORT"
        )
        request_payload = {"params" if query_params else "json": payload}
        created = self._json(
            method, endpoint,
            dependency_stage=dependency_prefix + "_CREATE",
            **request_payload,
        )
        uuid = str(created.get("UUID") or "")
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", uuid):
            raise HistoricalReportError("OZON_HISTORICAL_REPORT_ID_INVALID")
        for attempt in range(self.MAX_POLLS):
            status = self._json(
                "get", "/api/client/statistics/" + uuid,
                dependency_stage=dependency_prefix + "_STATUS",
            )
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
                    return [
                        row for m in members
                        for row in parse_report_csv(
                            archive.read(m), kind,
                            allow_order_sku_fallback=allow_order_sku_fallback,
                            report_endpoint=endpoint,
                        )
                    ]
            except BadZipFile as exc:
                raise HistoricalReportError(
                    "OZON_HISTORICAL_REPORT_FORMAT",
                    report_format_stage="ZIP_INVALID",
                ) from exc
        return parse_report_csv(
            data, kind, allow_order_sku_fallback=allow_order_sku_fallback,
            report_endpoint=endpoint,
        )

    def load(self, date_from, date_to):
        try:
            start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
            if start > end:
                raise ValueError()
        except ValueError:
            return {"error": True, "code": "OZON_PERFORMANCE_PERIOD_INVALID"}
        try:
            campaigns = self._campaign_ids(start, end)
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
                # CPO spend comes from order-level reports so the charge can be
                # assigned to the promoted SKU. Selected products and the
                # account-wide all-products promotion use separate reports.
                rows.extend(self._generate(
                    "/api/client/statistic/orders/generate",
                    {"from": current.isoformat() + "T00:00:00Z",
                     "to": finish.isoformat() + "T23:59:59Z"}, "CPO"))
                rows.extend(self._generate(
                    "/api/client/statistics/all_sku_promo/orders/generate",
                    {"timeBounds.from": current.isoformat() + "T00:00:00Z",
                     "timeBounds.to": finish.isoformat() + "T23:59:59Z"}, "CPO",
                    method="get", query_params=True,
                    allow_order_sku_fallback=True))
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
            if exc.campaign_diagnostics:
                result["campaign_diagnostics"] = exc.campaign_diagnostics
            if exc.campaign_unknown_count is not None:
                result["campaign_unknown_count"] = exc.campaign_unknown_count
            if exc.report_format_stage is not None:
                result["report_format_stage"] = exc.report_format_stage
            if exc.report_format_columns:
                result["report_format_columns"] = exc.report_format_columns
            if exc.report_format_row_label is not None:
                result["report_format_row_label"] = exc.report_format_row_label
            if exc.report_format_kind in {"CPC", "CPO"}:
                result["report_format_kind"] = exc.report_format_kind
            if exc.report_format_endpoint in CPO_REPORT_ENDPOINTS:
                result["report_format_endpoint"] = exc.report_format_endpoint
            if isinstance(exc.report_format_order_sku_present, bool):
                result["report_format_order_sku_present"] = (
                    exc.report_format_order_sku_present
                )
            if exc.dependency_stage in self.DEPENDENCY_STAGES:
                result["dependency_stage"] = exc.dependency_stage
            if (
                isinstance(exc.dependency_error_type, str)
                and exc.dependency_error_type in self.DEPENDENCY_ERROR_TYPES
            ):
                result["dependency_error_type"] = exc.dependency_error_type
            return result
