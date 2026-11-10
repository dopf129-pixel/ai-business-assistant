"""Read-only parser for the allowlisted Ozon stock-management workbook."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from io import BytesIO
import re
from pathlib import PureWindowsPath
from zipfile import ZipFile

from openpyxl import load_workbook

from services.fifo_cost_report_import_service import (
    FifoCostReportImportResult,
    FifoCostReportImportService,
    _ReportInputError,
)
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
    TransitionMetadata,
)


class FifoCostStockManagementImportService(FifoCostReportImportService):
    """Parse the exact Ozon stock report without combining overlapping views."""

    PARSER_VERSION = "fifo-stock-management-v1"
    STOCK_SHEET = "Товары"
    WAREHOUSE_SHEET = "Товар-склад"
    CLUSTER_PRODUCT_SHEET = "Товар-кластер"
    CLUSTER_SHEET = "Кластеры"
    REMOVED_SHEET = "Товар-склад снято с продажи"
    EXPECTED_SHEETS = frozenset({
        STOCK_SHEET,
        WAREHOUSE_SHEET,
        CLUSTER_PRODUCT_SHEET,
        CLUSTER_SHEET,
        REMOVED_SHEET,
    })
    MAX_NORMALIZED_ROWS = 10_000
    _SNAPSHOT_DATE_RE = re.compile(r"(?<![0-9])([0-3][0-9]\.[01][0-9]\.[0-9]{4})(?![0-9])")

    _STOCK_HEADERS = {
        "A1": "Артикул",
        "B1": "Название товара",
        "C1": "SKU",
        "D1": "Признак товара",
        "E1": "Зона размещения",
        "F1": "Ликвидность",
        "L1": "Всего товаров",
        "M1": "Доступно к продаже",
        "N1": "Недоступно к продаже",
        "V1": "Товары в пути",
        "AA1": "Вывоз со склада Ozon",
        "F2": "Статус",
        "G2": "Дней до конца остатка",
        "H2": "Среднесуточные продажи за 28 дней Штук",
        "I2": "Дней без продаж",
        "N2": "Готовим к продаже",
        "O2": "Маркируемые товары, ожидающие вывоз",
        "P2": "Маркируемые товары, ожидающие УПД",
        "Q2": "Истекает срок годности",
        "R2": "Брак, доступный к вывозу с поставки",
        "S2": "Брак, доступный к вывозу со стока",
        "T2": "Излишки с поставки, готовые к вывозу",
        "U2": "Проходят проверку",
        "V2": "В заявках на поставку",
        "W2": "В поставках в пути",
        "X2": "Доставляем покупателям",
        "Y2": "Возвращаются от покупателей",
        "Z2": "В перемещении",
        "AA2": "Готовим к вывозу",
        "AB2": "Готово к вывозу",
        "AC2": "Возвращается к продавцу",
    }
    _WAREHOUSE_HEADERS = {
        "A1": "Артикул",
        "B1": "Название товара",
        "C1": "SKU",
        "D1": "Признак товара",
        "E1": "Зона размещения",
        "F1": "Кластер",
        "G1": "Склад",
        "J1": "Всего товаров",
        "K1": "Доступно к продаже",
        "L1": "Недоступно к продаже",
        "T1": "Товары в пути",
        "Y1": "Вывоз со склада Ozon",
        "L2": "Готовим к продаже",
        "M2": "Маркируемые товары, ожидающие вывоз",
        "N2": "Маркируемые товары, ожидающие УПД",
        "O2": "Истекает срок годности",
        "P2": "Брак, доступный к вывозу с поставки",
        "Q2": "Брак, доступный к вывозу со стока",
        "R2": "Излишки с поставки, готовые к вывозу",
        "S2": "Проходят проверку",
        "T2": "В заявках на поставку",
        "U2": "В поставках в пути",
        "V2": "Доставляем покупателям",
        "W2": "Возвращаются от покупателей",
        "X2": "В перемещении",
        "Y2": "Готовим к вывозу",
        "Z2": "Готово к вывозу",
        "AA2": "Возвращается к продавцу",
    }
    _REMOVED_HEADERS = {
        "A1": "Артикул",
        "B1": "Название товара",
        "C1": "SKU",
        "D1": "Признак товара",
        "E1": "Зона размещения",
        "F1": "Кластер",
        "G1": "Склад",
        "H1": "Снято с продажи",
    }

    # Master-sheet quantities. L is an Ozon diagnostic total, not a stock
    # bucket. M is available; N:AC are independent displayed status buckets.
    _MASTER_BUCKET_COLUMNS = {
        "available": "M",
        "preparing": "N",
        "marking_pending_withdrawal": "O",
        "marking_pending_documents": "P",
        "expiring": "Q",
        "defective_supply": "R",
        "defective_stock": "S",
        "unidentified_supply_surplus": "T",
        "checking": "U",
        "supplier_planned": "V",
        "supplier_transit": "W",
        "buyer_delivery": "X",
        "buyer_return_transit": "Y",
        "internal_transfer": "Z",
        "seller_withdrawal_preparing": "AA",
        "seller_withdrawal_ready": "AB",
        "seller_return_transit": "AC",
    }
    _MASTER_CONTROL_COLUMNS = {
        "total_goods": "L",
        **_MASTER_BUCKET_COLUMNS,
    }
    _WAREHOUSE_CONTROL_COLUMNS = {
        "total_goods": "J",
        "available": "K",
        "preparing": "L",
        "marking_pending_withdrawal": "M",
        "marking_pending_documents": "N",
        "expiring": "O",
        "defective_supply": "P",
        "defective_stock": "Q",
        "unidentified_supply_surplus": "R",
        "checking": "S",
        "supplier_planned": "T",
        "supplier_transit": "U",
        "buyer_delivery": "V",
        "buyer_return_transit": "W",
        "internal_transfer": "X",
        "seller_withdrawal_preparing": "Y",
        "seller_withdrawal_ready": "Z",
        "seller_return_transit": "AA",
    }
    _MASTER_REQUIRED_COLUMNS = frozenset({"C", "D", *tuple("LMNOPQRSTUVWXYZ"), "AA", "AB", "AC"})
    _WAREHOUSE_KEY_COLUMNS = frozenset({"C", "D", "E", "F", "G"})
    _WAREHOUSE_REQUIRED_COLUMNS = frozenset({
        *_WAREHOUSE_KEY_COLUMNS, *tuple("JKLMNOPQRSTUVWXYZ"), "AA",
    })
    _REMOVED_KEY_COLUMNS = _WAREHOUSE_KEY_COLUMNS
    _REMOVED_REQUIRED_COLUMNS = frozenset({*_REMOVED_KEY_COLUMNS, "H"})
    _MAX_COLUMNS_BY_SHEET = {
        STOCK_SHEET: 29,
        WAREHOUSE_SHEET: 27,
        CLUSTER_PRODUCT_SHEET: 30,
        CLUSTER_SHEET: 23,
        REMOVED_SHEET: 8,
    }

    def parse_stock_management_workbook(
        self,
        *,
        payload,
        filename,
        scope,
        owner_confirmed_period=None,
        captured_at=None,
    ) -> FifoCostReportImportResult:
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
            period, provenance, period_issues = self._snapshot_period(
                filename, owner_confirmed_period,
            )
            captured = captured_at if captured_at is not None else self.utc_clock()
            parsed = self._read_stock_profile(
                payload, target_sku=scope.sku, started=started,
            )
        except _ReportInputError as error:
            return self._error(error.code, file_sha256=file_digest)
        if self.monotonic_clock() - started > self.MAX_PARSE_SECONDS:
            return self._error(
                "FIFO_REPORT_PARSE_TIME_BUDGET_EXCEEDED", file_sha256=file_digest,
            )

        try:
            master = parsed["master_rows"]
            warehouse = parsed["warehouse_rows"]
            removed = parsed["removed_rows"]
            if not master:
                return self._error(
                    "FIFO_REPORT_TARGET_SKU_NOT_FOUND", file_sha256=file_digest,
                )
            if any(len(rows) > self.MAX_NORMALIZED_ROWS for rows in (master, warehouse, removed)):
                return self._error(
                    "FIFO_STOCK_TARGET_DETAIL_LIMIT", file_sha256=file_digest,
                )

            master_totals, feature_rows, fbs_return_available, unknown_feature_count = (
                self._aggregate_master_rows(master, scope)
            )
            warehouse_totals, warehouse_groups = self._aggregate_warehouse_rows(
                warehouse, scope,
            )
            removed_total, removed_groups = self._aggregate_removed_rows(
                removed, scope,
            )
            issues = list(period_issues)
            if unknown_feature_count:
                issues.append("FIFO_STOCK_PRODUCT_FEATURE_UNKNOWN")
            if not warehouse:
                issues.append("FIFO_STOCK_WAREHOUSE_ROWS_MISSING")
                warehouse_status = "MISSING"
                mismatched_fields = []
            else:
                mismatched_fields = [
                    field for field in self._MASTER_CONTROL_COLUMNS
                    if master_totals[field] != warehouse_totals[field]
                ]
                warehouse_status = "MATCH" if not mismatched_fields else "MISMATCH"
                if mismatched_fields:
                    issues.append("FIFO_STOCK_WAREHOUSE_CONTROL_MISMATCH")
            if not removed:
                issues.append("FIFO_STOCK_REMOVED_FROM_SALE_UNKNOWN")

            stock_buckets = dict(master_totals)
            stock_buckets.pop("total_goods", None)
            stock_buckets["removed_from_sale"] = removed_total
            stock_buckets["reserved"] = None
            stock_buckets["supplier_receiving"] = stock_buckets.get(
                "supplier_receiving",
            )
            stock_buckets["defective"] = self._sum_known_buckets(
                stock_buckets, ("defective_supply", "defective_stock"),
            )
            stock_buckets["seller_withdrawal"] = self._sum_known_buckets(
                stock_buckets, (
                    "seller_withdrawal_preparing", "seller_withdrawal_ready",
                    "seller_return_transit",
                ),
            )
            cell_references, source_rows = self._source_provenance(parsed)
            if len(cell_references) > 100_000:
                return self._error(
                    "FIFO_STOCK_CELL_REFERENCE_LIMIT", file_sha256=file_digest,
                )

            completeness = (
                EvidenceCompleteness.COMPLETE
                if not issues else EvidenceCompleteness.PARTIAL
            )
            normalized_fields = {
                "source_sheets": [
                    self.STOCK_SHEET, self.WAREHOUSE_SHEET, self.REMOVED_SHEET,
                ],
                "source_rows_by_sheet": source_rows,
                "product_feature_rows": feature_rows,
                "stock_buckets": stock_buckets,
                "available_units": master_totals["available"],
                "fbs_return_available_units": fbs_return_available,
                "fbs_return_is_subset_of_available": True,
                "total_goods_units": master_totals["total_goods"],
                "total_goods_units_is_diagnostic": True,
                "reserved_units": None,
                "reserved_unknown_reason": "NO_INDEPENDENT_NUMERIC_FIELD",
                "removed_from_sale_units": removed_total,
                "removed_from_sale_rows": removed_groups,
                "warehouse_control": {
                    "status": warehouse_status,
                    "is_additive_to_stock_buckets": False,
                    "mismatched_fields": mismatched_fields,
                    "totals_by_warehouse": warehouse_groups,
                },
                "cluster_views_not_added": [
                    self.CLUSTER_PRODUCT_SHEET, self.CLUSTER_SHEET,
                ],
                "all_views_are_not_additive": True,
                "bucket_sum_is_not_physical_stock": True,
            }
            metadata = TransitionMetadata(
                scope=scope,
                source_kind=EvidenceSourceKind.OWNER_IMPORTED,
                completeness=completeness,
                source_fingerprint=self._source_fingerprint(file_digest, scope),
            )
            report = ReportEvidence(
                metadata=metadata,
                report_type=ReportType.STOCK_MANAGEMENT,
                period_from=period,
                period_to=period,
                period_provenance=provenance,
                captured_at=captured,
                file_sha256=file_digest,
                parser_version=self.PARSER_VERSION,
                cell_references=cell_references,
                normalized_fields=normalized_fields,
            )
        except _ReportInputError as error:
            return self._error(error.code, file_sha256=file_digest)
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

    def _read_stock_profile(self, payload, *, target_sku, started):
        header_cells_by_sheet = {
            self.STOCK_SHEET: set(self._STOCK_HEADERS),
            self.WAREHOUSE_SHEET: set(self._WAREHOUSE_HEADERS),
            self.REMOVED_SHEET: set(self._REMOVED_HEADERS),
        }
        inspection = self._preflight_xlsx_package(
            payload,
            started=started,
            expected_sheets=self.EXPECTED_SHEETS,
            header_cells_by_sheet=header_cells_by_sheet,
            sku_columns_by_sheet={
                self.STOCK_SHEET: "C",
                self.WAREHOUSE_SHEET: "C",
                self.REMOVED_SHEET: "C",
            },
            max_columns_by_sheet=self._MAX_COLUMNS_BY_SHEET,
        )
        try:
            workbook = load_workbook(
                BytesIO(payload), read_only=True, data_only=True,
                keep_links=False,
            )
            try:
                if set(workbook.sheetnames) != set(self.EXPECTED_SHEETS):
                    raise _ReportInputError("FIFO_REPORT_SHEET_SET_UNSUPPORTED")
                expected_headers = {
                    self.STOCK_SHEET: self._STOCK_HEADERS,
                    self.WAREHOUSE_SHEET: self._WAREHOUSE_HEADERS,
                    self.REMOVED_SHEET: self._REMOVED_HEADERS,
                }
                header_values = {}
                for sheet_name, expected in expected_headers.items():
                    sheet = workbook[sheet_name]
                    max_row, _ = inspection.sheet_dimensions[sheet_name]
                    headers = self._read_header_cells(sheet, max_row, expected)
                    header_values[sheet_name] = headers
                    issue = self._validate_profile_headers(
                        headers,
                        expected,
                        inspection.header_formula_cells[sheet_name],
                    )
                    if issue:
                        raise _ReportInputError(issue)

                selected_rows = {}
                for sheet_name in (self.STOCK_SHEET, self.WAREHOUSE_SHEET, self.REMOVED_SHEET):
                    worksheet = workbook[sheet_name]
                    max_row, max_column = inspection.sheet_dimensions[sheet_name]
                    selected_rows[sheet_name] = self._read_rows_for_sku(
                        worksheet,
                        max_row=max_row,
                        max_column=max_column,
                        target_sku=target_sku,
                        started=started,
                    )
                with ZipFile(BytesIO(payload), "r") as archive:
                    for sheet_name, rows in selected_rows.items():
                        required_columns = self._required_columns_by_sheet(sheet_name)
                        sheet_path = inspection.sheet_paths[sheet_name]
                        for row_number, values in rows:
                            if any(
                                value.data_type == "e"
                                and self._column_name(column_index) in required_columns
                                for column_index, value in enumerate(values["_cells"], start=1)
                            ):
                                raise _ReportInputError("FIFO_REPORT_EXCEL_ERROR_CELL")
                            formula_cells = self._formula_cells_for_row(
                                archive,
                                sheet_path,
                                row_number,
                                required_columns,
                                started=started,
                            )
                            if formula_cells:
                                raise _ReportInputError("FIFO_REPORT_FORMULA_VALUE_UNSUPPORTED")
                return {
                    "master_rows": selected_rows[self.STOCK_SHEET],
                    "warehouse_rows": selected_rows[self.WAREHOUSE_SHEET],
                    "removed_rows": selected_rows[self.REMOVED_SHEET],
                    "header_values": header_values,
                }
            finally:
                workbook.close()
        except _ReportInputError:
            raise
        except MemoryError:
            raise
        except Exception:
            raise _ReportInputError("FIFO_REPORT_XLSX_PACKAGE_INVALID") from None

    def _read_rows_for_sku(
        self, worksheet, *, max_row, max_column, target_sku, started,
    ):
        target_row_numbers = []
        if max_row < 5:
            return target_row_numbers
        for row_number, row in enumerate(
            worksheet.iter_rows(
                min_row=5, max_row=max_row, min_col=3, max_col=3,
            ),
            start=5,
        ):
            self._check_parse_time(started)
            if getattr(row[0], "data_type", None) == "e":
                raise _ReportInputError("FIFO_REPORT_EXCEL_ERROR_CELL")
            if self._normalize_sku(row[0].value) == target_sku:
                target_row_numbers.append(row_number)
                if len(target_row_numbers) > self.MAX_NORMALIZED_ROWS:
                    raise _ReportInputError("FIFO_STOCK_TARGET_DETAIL_LIMIT")
        selected = []
        for row_number in target_row_numbers:
            cells = next(worksheet.iter_rows(
                min_row=row_number,
                max_row=row_number,
                min_col=1,
                max_col=max_column,
            ))
            values = {
                self._column_name(column_index): cell.value
                for column_index, cell in enumerate(cells, start=1)
            }
            values["_cells"] = cells
            selected.append((row_number, values))
        return selected

    def _aggregate_master_rows(self, rows, scope):
        totals = {field: 0 for field in self._MASTER_CONTROL_COLUMNS}
        feature_rows = []
        seen_feature_refs = set()
        fbs_return_available = 0
        unknown_feature_count = 0
        for row_number, values in rows:
            feature_kind, feature_ref, unknown = self._feature_reference(
                values.get("D"), scope,
            )
            if feature_ref in seen_feature_refs:
                raise _ReportInputError("FIFO_STOCK_SKU_FEATURE_DUPLICATED")
            seen_feature_refs.add(feature_ref)
            row_totals = {}
            for field, column in self._MASTER_CONTROL_COLUMNS.items():
                value = self._quantity(values.get(column), f"{column}{row_number}")
                row_totals[field] = value
                totals[field] = self._bounded_sum(totals[field], value)
            if feature_kind == "FBS_RETURN":
                fbs_return_available = self._bounded_sum(
                    fbs_return_available, row_totals["available"],
                )
            unknown_feature_count += int(unknown)
            feature_rows.append({
                "source_row": row_number,
                "feature_kind": feature_kind,
                "feature_reference": feature_ref,
                "buckets": row_totals,
            })
        return totals, feature_rows, fbs_return_available, unknown_feature_count

    def _aggregate_warehouse_rows(self, rows, scope):
        totals = {field: 0 for field in self._WAREHOUSE_CONTROL_COLUMNS}
        groups_by_warehouse = {}
        seen_keys = set()
        for row_number, values in rows:
            dimensions = self._dimensions(values, scope, self.WAREHOUSE_SHEET)
            if dimensions in seen_keys:
                raise _ReportInputError("FIFO_STOCK_WAREHOUSE_KEY_DUPLICATED")
            seen_keys.add(dimensions)
            warehouse_reference = self._warehouse_reference(scope, dimensions[3])
            row_totals = {}
            for field, column in self._WAREHOUSE_CONTROL_COLUMNS.items():
                value = self._quantity(values.get(column), f"{column}{row_number}")
                row_totals[field] = value
                totals[field] = self._bounded_sum(totals[field], value)
            group = groups_by_warehouse.setdefault(
                warehouse_reference,
                {
                    "row_count": 0,
                    "source_rows": [],
                    "totals": {field: 0 for field in self._WAREHOUSE_CONTROL_COLUMNS},
                },
            )
            group["row_count"] += 1
            group["source_rows"].append(row_number)
            for field, value in row_totals.items():
                group["totals"][field] = self._bounded_sum(
                    group["totals"][field], value,
                )
        return totals, [
            {"warehouse_reference": key, **groups_by_warehouse[key]}
            for key in sorted(groups_by_warehouse)
        ]

    @staticmethod
    def _sum_known_buckets(buckets, names):
        values = tuple(buckets.get(name) for name in names)
        if any(type(value) is not int or value < 0 for value in values):
            return None
        return sum(values)

    def _aggregate_removed_rows(self, rows, scope):
        seen_keys = set()
        groups = []
        total = 0
        for row_number, values in rows:
            dimensions = self._dimensions(values, scope, self.REMOVED_SHEET)
            if dimensions in seen_keys:
                raise _ReportInputError("FIFO_STOCK_REMOVED_KEY_DUPLICATED")
            seen_keys.add(dimensions)
            value = self._quantity(values.get("H"), f"H{row_number}")
            total = self._bounded_sum(total, value)
            groups.append({
                "dimension_reference": self._opaque_dimension_reference(scope, dimensions),
                "source_row": row_number,
                "units": value,
            })
        return (total if rows else None), groups

    def _dimensions(self, values, scope, sheet_name):
        product_feature = values.get("D")
        if product_feature is None:
            normalized_feature = ""
        elif isinstance(product_feature, str):
            normalized_feature = self._normalize_header(product_feature)
        else:
            raise _ReportInputError("FIFO_STOCK_DIMENSION_INVALID")
        dimension_values = [normalized_feature or ""]
        for column in ("E", "F", "G"):
            value = values.get(column)
            if not isinstance(value, str) or not value.strip():
                raise _ReportInputError("FIFO_STOCK_DIMENSION_INVALID")
            dimension_values.append(self._normalize_header(value))
        return tuple(dimension_values)

    @classmethod
    def _feature_reference(cls, value, scope):
        if value is None:
            normalized = ""
        elif isinstance(value, str):
            normalized = cls._normalize_header(value)
        else:
            raise _ReportInputError("FIFO_STOCK_DIMENSION_INVALID")
        if normalized == "":
            feature_kind = "BASE"
            unknown = False
        elif normalized == "Возврат FBS":
            feature_kind = "FBS_RETURN"
            unknown = False
        else:
            feature_kind = "OTHER"
            unknown = True
        material = "\0".join((
            "fifo-stock-feature:v1",
            scope.owner_id,
            scope.store_id,
            scope.sku,
            str(normalized),
        ))
        return feature_kind, sha256(material.encode("utf-8")).hexdigest(), unknown

    @staticmethod
    def _opaque_dimension_reference(scope, dimensions):
        material = "\0".join((
            "fifo-stock-dimension:v1",
            scope.owner_id,
            scope.store_id,
            scope.sku,
            *dimensions,
        ))
        return sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _warehouse_reference(scope, warehouse_name):
        material = "\0".join((
            "fifo-stock-warehouse:v1",
            scope.owner_id,
            scope.store_id,
            scope.sku,
            warehouse_name,
        ))
        return sha256(material.encode("utf-8")).hexdigest()

    def _source_provenance(self, parsed):
        header_maps = {
            self.STOCK_SHEET: self._STOCK_HEADERS,
            self.WAREHOUSE_SHEET: self._WAREHOUSE_HEADERS,
            self.REMOVED_SHEET: self._REMOVED_HEADERS,
        }
        selected = {
            self.STOCK_SHEET: parsed["master_rows"],
            self.WAREHOUSE_SHEET: parsed["warehouse_rows"],
            self.REMOVED_SHEET: parsed["removed_rows"],
        }
        references = []
        source_rows = {}
        for sheet_name, headers in header_maps.items():
            references.extend(headers)
            rows = selected[sheet_name]
            source_rows[sheet_name] = [row_number for row_number, _ in rows]
            if sheet_name == self.STOCK_SHEET:
                columns = {"C", "D", *self._MASTER_CONTROL_COLUMNS.values()}
            elif sheet_name == self.WAREHOUSE_SHEET:
                columns = {*self._WAREHOUSE_KEY_COLUMNS, *self._WAREHOUSE_CONTROL_COLUMNS.values()}
            else:
                columns = {*self._REMOVED_KEY_COLUMNS, "H"}
            for row_number, _ in rows:
                references.extend(f"{column}{row_number}" for column in columns)
        return tuple(dict.fromkeys(references)), source_rows

    @staticmethod
    def _bounded_sum(current, value):
        total = current + value
        if total > FifoCostStockManagementImportService.MAX_QUANTITY:
            raise _ReportInputError("FIFO_REPORT_QUANTITY_INVALID")
        return total

    @staticmethod
    def _required_columns_by_sheet(sheet_name):
        if sheet_name == FifoCostStockManagementImportService.STOCK_SHEET:
            return FifoCostStockManagementImportService._MASTER_REQUIRED_COLUMNS
        if sheet_name == FifoCostStockManagementImportService.WAREHOUSE_SHEET:
            return FifoCostStockManagementImportService._WAREHOUSE_REQUIRED_COLUMNS
        return FifoCostStockManagementImportService._REMOVED_REQUIRED_COLUMNS

    @classmethod
    def _validate_profile_headers(cls, values, expected, formula_cells):
        for cell, expected_value in expected.items():
            if cell in formula_cells:
                return "FIFO_REPORT_HEADER_FORMULA_UNSUPPORTED"
            if cls._normalize_header(values.get(cell)) != cls._normalize_header(expected_value):
                return "FIFO_REPORT_FORMAT_UNSUPPORTED"
        return None

    @classmethod
    def _read_header_cells(cls, worksheet, max_row, expected):
        values = {}
        max_header_row = min(max_row, max(int(re.search(r"[0-9]+$", ref).group()) for ref in expected))
        max_header_column = max(
            cls._parse_cell_ref(ref)[0] for ref in expected
        )
        for row_number, row in enumerate(
            worksheet.iter_rows(
                min_row=1,
                max_row=max_header_row,
                min_col=1,
                max_col=max_header_column,
            ),
            start=1,
        ):
            for column_index, cell in enumerate(row, start=1):
                values[f"{cls._column_name(column_index)}{row_number}"] = cell.value
        return values

    def _snapshot_period(self, filename, owner_confirmed_period):
        if owner_confirmed_period is not None:
            period, provenance, issues = self._period_from_filename(
                filename, owner_confirmed_period,
            )
            return period[0], provenance, issues
        basename = PureWindowsPath(filename).name
        matches = list(self._SNAPSHOT_DATE_RE.finditer(basename))
        if len(matches) != 1:
            return None, PeriodProvenance.UNKNOWN, (
                "FIFO_REPORT_FILENAME_PERIOD_UNAVAILABLE",
            )
        try:
            day = datetime.strptime(matches[0].group(1), "%d.%m.%Y").date()
        except ValueError:
            return None, PeriodProvenance.UNKNOWN, (
                "FIFO_REPORT_FILENAME_PERIOD_INVALID",
            )
        return day.isoformat(), PeriodProvenance.FILENAME_CANDIDATE, ()
