"""Bounded, read-only parsers for the supported Ozon FIFO evidence reports.

FL12 implements only the turnover statement profile. The service returns
normalized evidence and never stores the workbook or changes a transition case.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
from pathlib import PureWindowsPath
import posixpath
import re
from time import monotonic
from urllib.parse import unquote
from zipfile import ZipFile

from defusedxml import ElementTree as DefusedET
from defusedxml.common import DefusedXmlException
from openpyxl import load_workbook

from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
    TransitionMetadata,
)


@dataclass(frozen=True, slots=True)
class FifoCostReportImportResult:
    status: str
    read_only: bool
    executed: bool
    report_evidence: ReportEvidence | None
    file_sha256: str | None
    issue_codes: tuple[str, ...]


class FifoCostReportImportService:
    """Parse the allowlisted Ozon turnover workbook into safe evidence."""

    PARSER_VERSION = "fifo-turnover-v1"
    SHEET_NAME = "Оборотная ведомость"
    MAX_FILE_BYTES = 10 * 1024 * 1024
    MAX_FILENAME_CHARS = 255
    MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
    MAX_ZIP_ENTRIES = 2048
    MAX_COMPRESSION_RATIO = 100
    MAX_ROWS_PER_SHEET = 50_000
    MAX_COLUMNS_PER_SHEET = 100
    MAX_QUANTITY = 1_000_000
    MAX_PARSE_SECONDS = 15.0

    _CELL_RE = re.compile(r"^([A-Z]{1,3})([1-9][0-9]{0,6})$")
    _FILENAME_PERIOD_RE = re.compile(r"(?<![0-9])([0-9]{8})[-_]([0-9]{8})(?![0-9])")
    _MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    _OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    _PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

    # This profile is intentionally strict. Whitespace/NBSP differences are
    # normalized, while changed labels require a deliberate parser version.
    _EXPECTED_HEADERS = {
        "A1": "SKU",
        "D1": "Остаток на начало",
        "D2": "Остатки на складах Ozon",
        "D3": "Доступно к продаже на складах Ozon",
        "E2": "Истекает срок годности",
        "E3": "Товары с истекающим сроком годности",
        "F2": "Брак, доступный к вывозу со стока",
        "F3": "Нельзя уценить из-за сильных повреждений",
        "G2": "Проходят проверку",
        "G3": "Отправили на проверку после обнаружения брака, истекшего срока годности или пересорта",
        "H2": "В перемещении",
        "H3": "Перемещаем между складами Ozon по вашей заявке",
        "I2": "Возвращаются к продавцу",
        "I3": "В процессе вывоза по вашей заявке или по автозаявке",
        "J2": "Возвращаются от покупателей",
        "J3": "Возвращаются на склады Ozon от покупателей",
        "K2": "Доставляем покупателям",
        "K3": "Доставляем по заказам от покупателей",
        "L1": "Приход",
        "L2": "Приняли на склады Ozon",
        "L3": "Вы отгрузили на склады Ozon",
        "M2": "Возврат покупателя",
        "M3": "Покупатели вернули после доставки",
        "N2": "Товар в отмененных заявках на вывоз",
        "N3": "Товар в отмененных заявках на вывоз, которы й не успел поступить на остаток",
        "O2": "Перенесли с карточкой товара",
        "O3": "Остатки, которые вы перенесли из другого личного кабинета",
        "P2": "Излишки",
        "P3": "Нашли во время инвентаризации",
        "Q2": "Уценка",
        "Q3": "Продаём с уценкой",
        "R2": "Пересорт",
        "R3": "Исправили неточность учёта товара и разместили в правильной ячейке",
        "S2": "Декомпенсировали",
        "S3": "Удержали ранее начисленную компенсации после обнаружения товара. В расчете Итого не используется",
        "T1": "Реализовано",
        "T2": "Выкуплено товаров",
        "T3": "Товары, которые выкупили",
        "U2": "Перенесли с карточкой товара",
        "U3": "Остатки, которые вы перенесли в другой личный кабинет",
        "V2": "Вывезли по заявке",
        "V3": "Доставили в точку вывоза по вашей заявке или автозаявке",
        "W2": "Утилизировали",
        "W3": "Утилизировали по вашей заявке или автозаявке",
        "X2": "Списали",
        "X3": "Утилизировали по инициативе Ozon — из-за повреждений или по другим причинам",
        "Y2": "Уценка",
        "Y3": "Продаём с уценкой",
        "Z2": "Пересорт",
        "Z3": "Исправили неточность учёта товара и разместили в правильной ячейке",
        "AA2": "Компенсировали",
        "AA3": "Компенсировали из-за брака, потери или по результатам спора. В расчете Итого не используется",
        "AB1": "Остаток на конец",
        "AB2": "Остатки на складах Ozon",
        "AB3": "Доступно к продаже на складах Ozon",
        "AC2": "Истекает срок годности",
        "AC3": "Товары с истекающим сроком годности",
        "AD2": "Брак, доступный к вывозу со стока",
        "AD3": "Нельзя уценить из-за сильных повреждений",
        "AE2": "Проходят проверку",
        "AE3": "Отправили на проверку после обнаружения брака, истекшего срока годности или пересорта",
        "AF2": "В перемещении",
        "AG2": "Возвращаются к продавцу",
        "AG3": "В процессе вывоза по вашей заявке или по автозаявке",
        "AH2": "Возвращаются от покупателей",
        "AH3": "Возвращаются на склады Ozon от покупателей",
        "AI2": "Доставляем покупателям",
        "AI3": "Доставляем по заказам от покупателей",
        "AJ1": "Итого Остаток на начало",
        "AK1": "Итого Приход",
        "AL1": "Итого Расход",
        "AM1": "Итого Остаток на конец",
        "AN1": "Итого",
        "AN3": "Рассчитывается по формуле: Остаток на начало + Приход - Расход - Остаток на конец",
    }

    _OPENING_BUCKETS = {
        "available": "D",
        "expiring": "E",
        "defective": "F",
        "checking": "G",
        "internal_transfer": "H",
        "seller_withdrawal": "I",
        "buyer_return_transit": "J",
        "buyer_delivery": "K",
    }
    _RECEIPT_COLUMNS = tuple("LMNOPQR")
    _EXPENSE_COLUMNS = tuple("TUVWXYZ")
    _CLOSING_BUCKETS = {
        "available": "AB",
        "expiring": "AC",
        "defective": "AD",
        "checking": "AE",
        "internal_transfer": "AF",
        "seller_withdrawal": "AG",
        "buyer_return_transit": "AH",
        "buyer_delivery": "AI",
    }
    _FIELD_CELLS = {
        "opening_total": "AJ",
        "receipts_total": "AK",
        "expenses_total": "AL",
        "closing_total": "AM",
        "reported_balance_difference": "AN",
        "excluded_compensation_receipt": "S",
        "excluded_compensation_expense": "AA",
    }

    def __init__(self, *, utc_clock=None, monotonic_clock=monotonic):
        self.utc_clock = utc_clock or (lambda: datetime.now(timezone.utc))
        self.monotonic_clock = monotonic_clock

    def parse_turnover_workbook(
        self,
        *,
        payload,
        filename,
        scope,
        owner_confirmed_period=None,
        captured_at=None,
    ) -> FifoCostReportImportResult:
        """Parse one exact Ozon turnover report into redacted report evidence."""
        started = self.monotonic_clock()
        if not isinstance(scope, ScopeIdentity):
            return self._error("FIFO_REPORT_SCOPE_INVALID")
        if (
            not isinstance(filename, str)
            or not filename.strip()
            or len(filename) > self.MAX_FILENAME_CHARS
        ):
            return self._error("FIFO_REPORT_FILENAME_INVALID")
        if not filename.lower().endswith(".xlsx"):
            return self._error("FIFO_REPORT_FORMAT_UNSUPPORTED")
        if isinstance(payload, memoryview):
            if payload.nbytes > self.MAX_FILE_BYTES:
                return self._error("FIFO_REPORT_FILE_SIZE_INVALID")
            payload = payload.tobytes()
        if not isinstance(payload, (bytes, bytearray)):
            return self._error("FIFO_REPORT_PAYLOAD_INVALID")
        if not payload or len(payload) > self.MAX_FILE_BYTES:
            return self._error("FIFO_REPORT_FILE_SIZE_INVALID")
        payload = bytes(payload)
        file_digest = sha256(payload).hexdigest()

        try:
            period, period_provenance, period_issues = self._period_from_filename(
                filename, owner_confirmed_period,
            )
        except _ReportInputError as error:
            return self._error(error.code, file_sha256=file_digest)
        captured = captured_at if captured_at is not None else self.utc_clock()
        try:
            header_values, target_row, formula_cells = self._read_profile(
                payload, target_sku=scope.sku, started=started,
            )
        except _ReportInputError as error:
            return self._error(error.code, file_sha256=file_digest)
        if self.monotonic_clock() - started > 15.0:
            return self._error("FIFO_REPORT_PARSE_TIME_BUDGET_EXCEEDED", file_sha256=file_digest)

        header_issue = self._validate_headers(header_values, formula_cells)
        if header_issue:
            return self._error(header_issue, file_sha256=file_digest)

        if target_row is None:
            return self._error("FIFO_REPORT_TARGET_SKU_NOT_FOUND", file_sha256=file_digest)
        row_number, row = target_row
        cells_to_read = self._required_data_cells(row_number)
        if any(f"{column}{row_number}" in formula_cells for column in cells_to_read):
            return self._error("FIFO_REPORT_FORMULA_VALUE_UNSUPPORTED", file_sha256=file_digest)

        try:
            values = {
                column: self._quantity(row.get(column), f"{column}{row_number}")
                for column in cells_to_read
            }
        except _ReportInputError as error:
            return self._error(error.code, file_sha256=file_digest)

        opening_buckets = {
            bucket: values[column]
            for bucket, column in self._OPENING_BUCKETS.items()
        }
        receipt_components = {
            column: values[column] for column in self._RECEIPT_COLUMNS
        }
        expense_components = {
            column: values[column] for column in self._EXPENSE_COLUMNS
        }
        closing_buckets = {
            bucket: values[column]
            for bucket, column in self._CLOSING_BUCKETS.items()
        }
        opening_total = values["AJ"]
        receipts_total = values["AK"]
        expenses_total = values["AL"]
        closing_total = values["AM"]
        reported_difference = values["AN"]
        opening_component_total = sum(opening_buckets.values())
        receipt_component_total = sum(receipt_components.values())
        expense_component_total = sum(expense_components.values())
        closing_component_total = sum(closing_buckets.values())
        computed_difference = opening_total + receipts_total - expenses_total - closing_total
        redeemed_units = values["T"]
        non_sale_expense_units = expenses_total - redeemed_units

        issues = list(period_issues)
        controls = (
            (opening_component_total == opening_total, "FIFO_TURNOVER_OPENING_TOTAL_MISMATCH"),
            (receipt_component_total == receipts_total, "FIFO_TURNOVER_RECEIPTS_TOTAL_MISMATCH"),
            (expense_component_total == expenses_total, "FIFO_TURNOVER_EXPENSES_TOTAL_MISMATCH"),
            (closing_component_total == closing_total, "FIFO_TURNOVER_CLOSING_TOTAL_MISMATCH"),
            (reported_difference == computed_difference, "FIFO_TURNOVER_REPORTED_BALANCE_MISMATCH"),
            (computed_difference == 0, "FIFO_TURNOVER_BALANCE_CONTROL_FAILED"),
            (non_sale_expense_units >= 0, "FIFO_TURNOVER_REDEEMED_EXCEEDS_EXPENSES"),
        )
        issues.extend(code for passed, code in controls if not passed)
        completeness = (
            EvidenceCompleteness.COMPLETE
            if not issues else EvidenceCompleteness.PARTIAL
        )
        source_fingerprint = self._source_fingerprint(file_digest, scope)
        cell_references = tuple(dict.fromkeys(
            [cell for cell in self._EXPECTED_HEADERS]
            + [f"{column}{row_number}" for column in cells_to_read]
            + [f"A{row_number}"]
        ))
        normalized_fields = {
            "source_sheet": self.SHEET_NAME,
            "source_row": row_number,
            "opening_buckets": opening_buckets,
            "opening_component_total": opening_component_total,
            "opening_total": opening_total,
            "receipt_components_by_column": receipt_components,
            "excluded_compensation_receipt": values["S"],
            "receipt_component_total": receipt_component_total,
            "receipts_total": receipts_total,
            "redeemed_units": redeemed_units,
            "non_sale_expense_components_by_column": {
                column: value for column, value in expense_components.items()
                if column != "T"
            },
            "non_sale_expense_units": non_sale_expense_units,
            "withdrawal_units": values["V"],
            "excluded_compensation_expense": values["AA"],
            "expense_component_total": expense_component_total,
            "expenses_total": expenses_total,
            "closing_buckets": closing_buckets,
            "closing_component_total": closing_component_total,
            "closing_total": closing_total,
            "reported_balance_difference": reported_difference,
            "computed_balance_difference": computed_difference,
            "balance_status": "BALANCED" if computed_difference == 0 else "DISCREPANCY",
            "component_controls_match": all(passed for passed, _ in controls[:5]),
        }
        try:
            metadata = TransitionMetadata(
                scope=scope,
                source_kind=EvidenceSourceKind.OWNER_IMPORTED,
                completeness=completeness,
                source_fingerprint=source_fingerprint,
            )
            report = ReportEvidence(
                metadata=metadata,
                report_type=ReportType.TURNOVER,
                period_from=period[0] if period else None,
                period_to=period[1] if period else None,
                period_provenance=period_provenance,
                captured_at=captured,
                file_sha256=file_digest,
                parser_version=self.PARSER_VERSION,
                cell_references=cell_references,
                normalized_fields=normalized_fields,
            )
        except (TypeError, ValueError):
            return self._error("FIFO_REPORT_EVIDENCE_INVALID", file_sha256=file_digest)
        return FifoCostReportImportResult(
            status="COMPLETE" if completeness is EvidenceCompleteness.COMPLETE else "PARTIAL",
            read_only=True,
            executed=False,
            report_evidence=report,
            file_sha256=file_digest,
            issue_codes=tuple(dict.fromkeys(issues)),
        )

    def _read_profile(self, payload, *, target_sku, started):
        try:
            with ZipFile(BytesIO(payload), "r") as archive:
                infos = archive.infolist()
                if len(infos) > self.MAX_ZIP_ENTRIES:
                    raise _ReportInputError("FIFO_REPORT_ZIP_ENTRY_LIMIT")
                names = [info.filename for info in infos]
                if len(set(names)) != len(names):
                    raise _ReportInputError("FIFO_REPORT_ZIP_DUPLICATE_ENTRY")
                total_uncompressed = 0
                for info in infos:
                    self._check_parse_time(started)
                    self._validate_zip_path(info.filename)
                    if info.flag_bits & 0x1:
                        raise _ReportInputError("FIFO_REPORT_ZIP_ENCRYPTED_ENTRY")
                    total_uncompressed += info.file_size
                    if total_uncompressed > self.MAX_UNCOMPRESSED_BYTES:
                        raise _ReportInputError("FIFO_REPORT_UNCOMPRESSED_SIZE_LIMIT")
                    if info.file_size and (
                        info.compress_size <= 0
                        or info.file_size / info.compress_size > self.MAX_COMPRESSION_RATIO
                    ):
                        raise _ReportInputError("FIFO_REPORT_COMPRESSION_RATIO_LIMIT")
                    if "vbaproject.bin" in info.filename.casefold() or "externallinks" in info.filename.casefold():
                        raise _ReportInputError("FIFO_REPORT_MACRO_OR_EXTERNAL_LINK_UNSUPPORTED")
                if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                    raise _ReportInputError("FIFO_REPORT_XLSX_PACKAGE_INVALID")
                content_types = archive.read("[Content_Types].xml").lower()
                if any(marker in content_types for marker in (b"macroenabled", b"vbaproject", b"externallink")):
                    raise _ReportInputError("FIFO_REPORT_MACRO_OR_EXTERNAL_LINK_UNSUPPORTED")
                self._validate_relationships(archive, names)
                sheet_paths = self._worksheet_paths(archive, names)
                if self.SHEET_NAME not in sheet_paths:
                    raise _ReportInputError("FIFO_REPORT_TURNOVER_SHEET_MISSING")
                sheet_dimensions = {}
                header_formula_cells = set()
                for sheet_name, path in sheet_paths.items():
                    max_row, max_column, formulas = self._inspect_sheet_xml(
                        archive,
                        path,
                        is_turnover_sheet=sheet_name == self.SHEET_NAME,
                        started=started,
                    )
                    if max_row > self.MAX_ROWS_PER_SHEET:
                        raise _ReportInputError("FIFO_REPORT_ROW_LIMIT")
                    if max_column > self.MAX_COLUMNS_PER_SHEET:
                        raise _ReportInputError("FIFO_REPORT_COLUMN_LIMIT")
                    if sheet_name == self.SHEET_NAME and max_column > 40:
                        raise _ReportInputError("FIFO_REPORT_FORMAT_UNSUPPORTED")
                    sheet_dimensions[sheet_name] = (max_row, max_column)
                    if sheet_name == self.SHEET_NAME:
                        header_formula_cells = formulas
                workbook = load_workbook(
                    BytesIO(payload), read_only=True, data_only=True,
                    keep_links=False,
                )
                try:
                    if self.SHEET_NAME not in workbook.sheetnames:
                        raise _ReportInputError("FIFO_REPORT_TURNOVER_SHEET_MISSING")
                    worksheet = workbook[self.SHEET_NAME]
                    max_row, _ = sheet_dimensions[self.SHEET_NAME]
                    headers = {}
                    for row_number, row in enumerate(
                        worksheet.iter_rows(
                            min_row=1, max_row=min(3, max_row),
                            min_col=1, max_col=40,
                        ),
                        start=1,
                    ):
                        for column_index, cell in enumerate(row, start=1):
                            headers[
                                f"{self._column_name(column_index)}{row_number}"
                            ] = cell.value
                    target_row_numbers = []
                    for row_number, row in enumerate(
                        worksheet.iter_rows(
                            min_row=4, max_row=max_row, min_col=1, max_col=1,
                        ),
                        start=4,
                    ):
                        self._check_parse_time(started)
                        if self._normalize_sku(row[0].value) == target_sku:
                            target_row_numbers.append(row_number)
                    if len(target_row_numbers) > 1:
                        raise _ReportInputError("FIFO_REPORT_TARGET_SKU_DUPLICATED")
                    if not target_row_numbers:
                        return headers, None, header_formula_cells
                    target_row_number = target_row_numbers[0]
                    target_row = next(worksheet.iter_rows(
                        min_row=target_row_number,
                        max_row=target_row_number,
                        min_col=1,
                        max_col=40,
                    ))
                    target_values = {
                        self._column_name(column_index): cell.value
                        for column_index, cell in enumerate(target_row, start=1)
                    }
                    required_columns = self._required_data_columns()
                    if any(
                        getattr(cell, "data_type", None) == "e"
                        and self._column_name(column_index) in required_columns
                        for column_index, cell in enumerate(target_row, start=1)
                    ):
                        raise _ReportInputError("FIFO_REPORT_EXCEL_ERROR_CELL")
                    target_formula_cells = self._formula_cells_for_row(
                        archive,
                        sheet_paths[self.SHEET_NAME],
                        target_row_number,
                        required_columns,
                        started=started,
                    )
                    return (
                        headers,
                        (target_row_number, target_values),
                        header_formula_cells | target_formula_cells,
                    )
                finally:
                    workbook.close()
        except _ReportInputError:
            raise
        except MemoryError:
            raise
        except Exception:
            raise _ReportInputError("FIFO_REPORT_XLSX_PACKAGE_INVALID") from None

    def _validate_relationships(self, archive, names):
        for name in names:
            if not name.casefold().endswith(".rels"):
                continue
            try:
                root = DefusedET.fromstring(archive.read(name))
            except (DefusedXmlException, DefusedET.ParseError, KeyError):
                raise _ReportInputError("FIFO_REPORT_RELATIONSHIP_INVALID") from None
            for relationship in root.iter():
                if relationship.tag != f"{{{self._PACKAGE_REL_NS}}}Relationship":
                    continue
                if relationship.attrib.get("TargetMode", "").casefold() == "external":
                    raise _ReportInputError("FIFO_REPORT_EXTERNAL_RELATIONSHIP_UNSUPPORTED")
                target = relationship.attrib.get("Target")
                if not isinstance(target, str) or not target:
                    raise _ReportInputError("FIFO_REPORT_RELATIONSHIP_INVALID")
                decoded_target = unquote(target)
                if (
                    "\\" in decoded_target
                    or ":" in decoded_target
                    or "?" in decoded_target
                    or "#" in decoded_target
                    or decoded_target.startswith("//")
                ):
                    raise _ReportInputError("FIFO_REPORT_RELATIONSHIP_INVALID")
                target_parts = decoded_target.lstrip("/").split("/")
                if any(part in {"", ".", ".."} for part in target_parts):
                    raise _ReportInputError("FIFO_REPORT_RELATIONSHIP_INVALID")
                if decoded_target.startswith("/"):
                    resolved_target = posixpath.normpath(decoded_target.lstrip("/"))
                else:
                    rel_parent = posixpath.dirname(name)
                    if rel_parent == "_rels":
                        source_parent = ""
                    elif rel_parent.endswith("/_rels"):
                        source_parent = posixpath.dirname(rel_parent)
                    else:
                        raise _ReportInputError("FIFO_REPORT_RELATIONSHIP_INVALID")
                    resolved_target = posixpath.normpath(
                        posixpath.join(source_parent, decoded_target),
                    )
                if resolved_target not in names:
                    raise _ReportInputError("FIFO_REPORT_RELATIONSHIP_INVALID")

    def _worksheet_paths(self, archive, names):
        try:
            workbook = DefusedET.fromstring(archive.read("xl/workbook.xml"))
            rels = DefusedET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        except (DefusedXmlException, DefusedET.ParseError, KeyError):
            raise _ReportInputError("FIFO_REPORT_WORKBOOK_XML_INVALID") from None
        relationships = {}
        for item in rels.findall(f"{{{self._PACKAGE_REL_NS}}}Relationship"):
            relationship_id = item.attrib.get("Id")
            if not isinstance(relationship_id, str) or relationship_id in relationships:
                raise _ReportInputError("FIFO_REPORT_WORKBOOK_RELATIONSHIP_INVALID")
            relationships[relationship_id] = item.attrib.get("Target")
        result = {}
        sheets = workbook.find(f"{{{self._MAIN_NS}}}sheets")
        if sheets is None:
            raise _ReportInputError("FIFO_REPORT_WORKBOOK_XML_INVALID")
        for sheet in sheets.findall(f"{{{self._MAIN_NS}}}sheet"):
            name = sheet.attrib.get("name")
            relation_id = sheet.attrib.get(f"{{{self._OFFICE_REL_NS}}}id")
            target = relationships.get(relation_id)
            if not isinstance(name, str) or not isinstance(target, str) or not target:
                raise _ReportInputError("FIFO_REPORT_WORKBOOK_RELATIONSHIP_INVALID")
            if name in result:
                raise _ReportInputError("FIFO_REPORT_WORKBOOK_RELATIONSHIP_INVALID")
            raw_target = target
            if (
                "\\" in raw_target
                or ":" in raw_target
                or "?" in raw_target
                or "#" in raw_target
                or raw_target.startswith("//")
            ):
                raise _ReportInputError("FIFO_REPORT_WORKBOOK_RELATIONSHIP_INVALID")
            target_parts = raw_target.lstrip("/").split("/")
            if any(part in {"", ".", ".."} for part in target_parts):
                raise _ReportInputError("FIFO_REPORT_WORKBOOK_RELATIONSHIP_INVALID")
            normalized_path = (
                posixpath.normpath(raw_target.lstrip("/"))
                if raw_target.startswith("/")
                else posixpath.normpath(posixpath.join("xl", raw_target))
            )
            if normalized_path.startswith("../") or normalized_path not in names:
                raise _ReportInputError("FIFO_REPORT_WORKBOOK_RELATIONSHIP_INVALID")
            result[name] = normalized_path
        return result

    def _inspect_sheet_xml(self, archive, path, *, is_turnover_sheet, started):
        try:
            stream = archive.open(path, "r")
            row_count = 0
            max_row = 0
            max_column = 0
            previous_row = 0
            formulas = set()
            for _event, element in DefusedET.iterparse(stream, events=("end",)):
                if element.tag != f"{{{self._MAIN_NS}}}row":
                    continue
                self._check_parse_time(started)
                row_count += 1
                try:
                    row_number = int(element.attrib.get("r", "0"))
                except (TypeError, ValueError):
                    raise _ReportInputError("FIFO_REPORT_ROW_REFERENCE_INVALID") from None
                if row_number <= previous_row:
                    raise _ReportInputError("FIFO_REPORT_ROW_REFERENCE_INVALID")
                previous_row = row_number
                max_row = max(max_row, row_number)
                if (
                    row_count > self.MAX_ROWS_PER_SHEET
                    or row_number < 1
                    or row_number > self.MAX_ROWS_PER_SHEET
                ):
                    raise _ReportInputError("FIFO_REPORT_ROW_LIMIT")
                for cell in element.findall(f"{{{self._MAIN_NS}}}c"):
                    reference = cell.attrib.get("r", "")
                    parsed = self._parse_cell_ref(reference)
                    if parsed is None:
                        raise _ReportInputError("FIFO_REPORT_CELL_REFERENCE_INVALID")
                    column, cell_row = parsed
                    max_column = max(max_column, column)
                    max_row = max(max_row, cell_row)
                    if cell_row != row_number:
                        raise _ReportInputError("FIFO_REPORT_CELL_ROW_MISMATCH")
                    if column > self.MAX_COLUMNS_PER_SHEET:
                        raise _ReportInputError("FIFO_REPORT_COLUMN_LIMIT")
                    if cell.find(f"{{{self._MAIN_NS}}}f") is not None:
                        if is_turnover_sheet and reference in self._EXPECTED_HEADERS:
                            formulas.add(reference)
                        elif is_turnover_sheet and column == 1 and row_number >= 4:
                            raise _ReportInputError("FIFO_REPORT_SKU_FORMULA_UNSUPPORTED")
                element.clear()
            stream.close()
            return max_row, max_column, formulas
        except _ReportInputError:
            raise
        except (DefusedXmlException, DefusedET.ParseError, OSError, KeyError):
            raise _ReportInputError("FIFO_REPORT_SHEET_XML_INVALID") from None

    def _formula_cells_for_row(
        self, archive, path, row_number, required_columns, *, started,
    ):
        try:
            formulas = set()
            stream = archive.open(path, "r")
            for _event, element in DefusedET.iterparse(stream, events=("end",)):
                if element.tag != f"{{{self._MAIN_NS}}}row":
                    continue
                self._check_parse_time(started)
                try:
                    current_row = int(element.attrib.get("r", "0"))
                except (TypeError, ValueError):
                    raise _ReportInputError("FIFO_REPORT_ROW_REFERENCE_INVALID") from None
                if current_row == row_number:
                    for cell in element.findall(f"{{{self._MAIN_NS}}}c"):
                        reference = cell.attrib.get("r", "")
                        parsed = self._parse_cell_ref(reference)
                        if parsed is None:
                            raise _ReportInputError("FIFO_REPORT_CELL_REFERENCE_INVALID")
                        column_index, cell_row = parsed
                        column = self._column_name(column_index)
                        if (
                            cell_row == row_number
                            and column in required_columns
                            and cell.find(f"{{{self._MAIN_NS}}}f") is not None
                        ):
                            formulas.add(reference)
                    break
                element.clear()
            stream.close()
            return formulas
        except _ReportInputError:
            raise
        except (DefusedXmlException, DefusedET.ParseError, OSError, KeyError):
            raise _ReportInputError("FIFO_REPORT_SHEET_XML_INVALID") from None

    @classmethod
    def _validate_zip_path(cls, name):
        if not isinstance(name, str) or not name or "\\" in name:
            raise _ReportInputError("FIFO_REPORT_ZIP_PATH_INVALID")
        raw_path = name[:-1] if name.endswith("/") else name
        if (
            not raw_path
            or raw_path.startswith("/")
            or "\x00" in raw_path
            or any(part in {"", ".", ".."} for part in raw_path.split("/"))
        ):
            raise _ReportInputError("FIFO_REPORT_ZIP_PATH_INVALID")
        if PureWindowsPath(name).drive:
            raise _ReportInputError("FIFO_REPORT_ZIP_PATH_INVALID")

    @classmethod
    def _parse_cell_ref(cls, value):
        match = cls._CELL_RE.fullmatch(value) if isinstance(value, str) else None
        if match is None:
            return None
        column = 0
        for char in match.group(1):
            column = column * 26 + ord(char) - ord("A") + 1
        row = int(match.group(2))
        return column, row

    @classmethod
    def _validate_headers(cls, values, formula_cells):
        for cell, expected in cls._EXPECTED_HEADERS.items():
            if cell in formula_cells:
                return "FIFO_REPORT_HEADER_FORMULA_UNSUPPORTED"
            actual = values.get(cell)
            if cls._normalize_header(actual) != cls._normalize_header(expected):
                return "FIFO_REPORT_FORMAT_UNSUPPORTED"
        return None

    @classmethod
    def _required_data_columns(cls):
        return set(
            list(cls._OPENING_BUCKETS.values())
            + list(cls._RECEIPT_COLUMNS)
            + list(cls._EXPENSE_COLUMNS)
            + list(cls._CLOSING_BUCKETS.values())
            + ["AJ", "AK", "AL", "AM", "AN", "A", "S", "AA"]
        )

    @staticmethod
    def _column_name(column_index):
        result = ""
        while column_index:
            column_index, remainder = divmod(column_index - 1, 26)
            result = chr(ord("A") + remainder) + result
        return result

    @classmethod
    def _required_data_cells(cls, row_number):
        return tuple(sorted(
            cls._required_data_columns() - {"A"},
            key=lambda column: cls._parse_cell_ref(f"{column}{row_number}")[0],
        ))

    def _check_parse_time(self, started):
        if self.monotonic_clock() - started > self.MAX_PARSE_SECONDS:
            raise _ReportInputError("FIFO_REPORT_PARSE_TIME_BUDGET_EXCEEDED")

    @staticmethod
    def _quantity(value, cell_ref):
        if isinstance(value, bool) or value is None:
            raise _ReportInputError("FIFO_REPORT_REQUIRED_QUANTITY_MISSING")
        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise _ReportInputError("FIFO_REPORT_QUANTITY_INVALID") from None
        if (
            not decimal_value.is_finite()
            or decimal_value != decimal_value.to_integral_value()
            or decimal_value < 0
            or decimal_value > FifoCostReportImportService.MAX_QUANTITY
        ):
            raise _ReportInputError("FIFO_REPORT_QUANTITY_INVALID")
        return int(decimal_value)

    @classmethod
    def _normalize_header(cls, value):
        if not isinstance(value, str):
            return None
        return " ".join(value.replace("\u00a0", " ").split())

    @staticmethod
    def _normalize_sku(value):
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, int):
            return str(value) if value > 0 else None
        if isinstance(value, float) and value.is_integer() and value > 0:
            return str(int(value))
        if isinstance(value, str):
            normalized = value.strip()
            return normalized if normalized.isascii() and normalized.isdigit() else None
        return None

    @classmethod
    def _period_from_filename(cls, filename, owner_confirmed_period):
        if owner_confirmed_period is not None:
            if (
                not isinstance(owner_confirmed_period, (tuple, list))
                or len(owner_confirmed_period) != 2
            ):
                raise _ReportInputError("FIFO_REPORT_PERIOD_INVALID")
            start = cls._parse_iso_date(owner_confirmed_period[0])
            end = cls._parse_iso_date(owner_confirmed_period[1])
            if start is None or end is None or end < start:
                raise _ReportInputError("FIFO_REPORT_PERIOD_INVALID")
            return (start.isoformat(), end.isoformat()), PeriodProvenance.OWNER_CONFIRMED, ()
        basename = PureWindowsPath(filename).name
        match = cls._FILENAME_PERIOD_RE.search(basename)
        if match is None:
            return None, PeriodProvenance.UNKNOWN, ("FIFO_REPORT_FILENAME_PERIOD_UNAVAILABLE",)
        try:
            start = datetime.strptime(match.group(1), "%d%m%Y").date()
            end = datetime.strptime(match.group(2), "%d%m%Y").date()
        except ValueError:
            return None, PeriodProvenance.UNKNOWN, ("FIFO_REPORT_FILENAME_PERIOD_INVALID",)
        if end < start:
            return None, PeriodProvenance.UNKNOWN, ("FIFO_REPORT_FILENAME_PERIOD_INVALID",)
        return (start.isoformat(), end.isoformat()), PeriodProvenance.FILENAME_CANDIDATE, ()

    @staticmethod
    def _parse_iso_date(value):
        if not isinstance(value, str):
            return None
        try:
            parsed = date.fromisoformat(value.strip())
        except ValueError:
            return None
        return parsed if parsed.isoformat() == value.strip() else None

    @classmethod
    def _source_fingerprint(cls, file_digest, scope):
        material = "\0".join((
            cls.PARSER_VERSION,
            file_digest,
            scope.owner_id,
            scope.store_id,
            scope.product_id or "",
            scope.offer_id or "",
            scope.sku,
        ))
        return sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _error(code, *, file_sha256=None):
        return FifoCostReportImportResult(
            status="INVALID",
            read_only=True,
            executed=False,
            report_evidence=None,
            file_sha256=file_sha256,
            issue_codes=(code,),
        )


class _ReportInputError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)
