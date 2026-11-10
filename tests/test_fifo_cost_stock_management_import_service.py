from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook

from services.fifo_cost_stock_management_import_service import (
    FifoCostStockManagementImportService,
)
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    PeriodProvenance,
    ScopeIdentity,
)


_SKU = "3921245627"
_SCOPE = ScopeIdentity(
    owner_id="owner-1", store_id="store-1", sku=_SKU,
    product_id="product-1",
)
_MASTER_HEADERS = {
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
    "H2": "Среднесуточные продажи за 28 дней\n\nШтук",
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
_BUCKETS = {
    "available": 1182,
    "preparing": 17,
    "marking_pending_withdrawal": 0,
    "marking_pending_documents": 0,
    "expiring": 0,
    "defective_supply": 0,
    "defective_stock": 0,
    "unidentified_supply_surplus": 0,
    "checking": 5,
    "supplier_planned": 600,
    "supplier_transit": 6234,
    "buyer_delivery": 1689,
    "buyer_return_transit": 43,
    "internal_transfer": 0,
    "seller_withdrawal_preparing": 1,
    "seller_withdrawal_ready": 0,
    "seller_return_transit": 0,
}
_MASTER_COLUMNS = {
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
_DETAIL_COLUMNS = {
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


def _set_headers(sheet, headers):
    for cell, value in headers.items():
        sheet[cell] = value


def _set_bucket_row(sheet, row_number, *, total, available, buckets, feature=None):
    sheet[f"C{row_number}"] = int(_SKU)
    sheet[f"D{row_number}"] = feature
    sheet[f"L{row_number}"] = total
    for bucket, column in _MASTER_COLUMNS.items():
        sheet[f"{column}{row_number}"] = buckets[bucket]


def _set_detail_row(sheet, row_number, *, total, available, buckets, feature=None, warehouse):
    sheet[f"C{row_number}"] = int(_SKU)
    sheet[f"D{row_number}"] = feature
    sheet[f"E{row_number}"] = "Zone A"
    sheet[f"F{row_number}"] = "Cluster A"
    sheet[f"G{row_number}"] = warehouse
    sheet[f"J{row_number}"] = total
    for bucket, column in _DETAIL_COLUMNS.items():
        sheet[f"{column}{row_number}"] = buckets[bucket]


def _stock_payload(*, mutate=None, include_removed=True, hidden_extra=False):
    workbook = Workbook()
    stock = workbook.active
    stock.title = "Товары"
    warehouse = workbook.create_sheet("Товар-склад")
    product_cluster = workbook.create_sheet("Товар-кластер")
    clusters = workbook.create_sheet("Кластеры")
    removed = workbook.create_sheet("Товар-склад снято с продажи")
    _set_headers(stock, _MASTER_HEADERS)
    _set_headers(warehouse, _WAREHOUSE_HEADERS)
    _set_headers(removed, _REMOVED_HEADERS)
    product_cluster["AD1"] = "Synthetic extra view, never aggregated"
    clusters["W1"] = "Synthetic cluster view, never aggregated"

    _set_bucket_row(stock, 5, total=7522, available=1182, buckets=_BUCKETS)
    fbs_buckets = {bucket: 0 for bucket in _BUCKETS}
    fbs_buckets["available"] = 9
    fbs_buckets["preparing"] = 1
    _set_bucket_row(
        stock, 6, total=10, available=9, buckets=fbs_buckets,
        feature="Возврат FBS",
    )
    _set_detail_row(
        warehouse, 5, total=7522, available=1182, buckets=_BUCKETS,
        warehouse="Warehouse A",
    )
    _set_detail_row(
        warehouse, 6, total=10, available=9, buckets=fbs_buckets,
        feature="Возврат FBS", warehouse="Warehouse B",
    )
    if include_removed:
        removed["C5"] = int(_SKU)
        removed["D5"] = None
        removed["E5"] = "Zone A"
        removed["F5"] = "Cluster A"
        removed["G5"] = "Warehouse A"
        removed["H5"] = 41
    if hidden_extra:
        hidden = workbook.create_sheet("Hidden extra")
        hidden.sheet_state = "hidden"
    if mutate:
        mutate(workbook)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _parse(payload=None, *, filename="stock_07.11.2026_21-16.xlsx", **kwargs):
    return FifoCostStockManagementImportService().parse_stock_management_workbook(
        payload=payload if payload is not None else _stock_payload(),
        filename=filename,
        scope=_SCOPE,
        **kwargs,
    )


def test_stock_import_preserves_fbs_return_and_independent_status_buckets():
    result = _parse()

    assert result.status == "COMPLETE"
    assert result.read_only is True
    assert result.executed is False
    report = result.report_evidence
    fields = report.normalized_fields
    assert report.period_from == "2026-11-07"
    assert report.period_to == "2026-11-07"
    assert report.period_provenance is PeriodProvenance.FILENAME_CANDIDATE
    assert report.metadata.completeness is EvidenceCompleteness.COMPLETE
    assert fields["available_units"] == 1191
    assert fields["fbs_return_available_units"] == 9
    assert fields["fbs_return_is_subset_of_available"] is True
    assert fields["stock_buckets"]["preparing"] == 18
    assert fields["stock_buckets"]["checking"] == 5
    assert fields["stock_buckets"]["supplier_planned"] == 600
    assert fields["stock_buckets"]["supplier_transit"] == 6234
    assert fields["stock_buckets"]["buyer_delivery"] == 1689
    assert fields["stock_buckets"]["buyer_return_transit"] == 43
    assert fields["stock_buckets"]["removed_from_sale"] == 41
    assert fields["stock_buckets"]["defective"] == 0
    assert fields["stock_buckets"]["seller_withdrawal"] == 1
    assert fields["stock_buckets"]["supplier_receiving"] is None
    assert fields["total_goods_units"] == 7532
    assert fields["total_goods_units_is_diagnostic"] is True
    assert fields["reserved_units"] is None
    assert fields["reserved_unknown_reason"] == "NO_INDEPENDENT_NUMERIC_FIELD"
    assert fields["warehouse_control"]["status"] == "MATCH"
    assert fields["warehouse_control"]["is_additive_to_stock_buckets"] is False
    warehouse_totals = fields["warehouse_control"]["totals_by_warehouse"]
    assert len(warehouse_totals) == 2
    assert sum(group["totals"]["available"] for group in warehouse_totals) == 1191
    assert fields["cluster_views_not_added"] == ("Товар-кластер", "Кластеры")
    assert fields["all_views_are_not_additive"] is True
    assert fields["bucket_sum_is_not_physical_stock"] is True
    assert len(fields["product_feature_rows"]) == 2
    assert [row["feature_kind"] for row in fields["product_feature_rows"]] == [
        "BASE", "FBS_RETURN",
    ]


def test_owner_confirmed_snapshot_date_takes_precedence_over_filename_candidate():
    result = _parse(owner_confirmed_period=("2026-11-06", "2026-11-07"))

    assert result.status == "COMPLETE"
    assert result.report_evidence.period_from == "2026-11-06"
    assert result.report_evidence.period_to == "2026-11-06"
    assert result.report_evidence.period_provenance is PeriodProvenance.OWNER_CONFIRMED


def test_snapshot_without_filename_date_keeps_period_unknown():
    result = _parse(filename="stock.xlsx")

    assert result.status == "PARTIAL"
    assert result.report_evidence.period_from is None
    assert result.report_evidence.period_provenance is PeriodProvenance.UNKNOWN
    assert "FIFO_REPORT_FILENAME_PERIOD_UNAVAILABLE" in result.issue_codes


def test_missing_removed_row_is_unknown_not_zero():
    result = _parse(_stock_payload(include_removed=False))

    assert result.status == "PARTIAL"
    assert result.report_evidence.normalized_fields["removed_from_sale_units"] is None
    assert result.report_evidence.normalized_fields["stock_buckets"]["removed_from_sale"] is None
    assert "FIFO_STOCK_REMOVED_FROM_SALE_UNKNOWN" in result.issue_codes


def test_warehouse_total_mismatch_keeps_partial_evidence_and_lists_fields():
    payload = _stock_payload(mutate=lambda workbook: setattr(
        workbook["Товар-склад"]["K5"], "value", 1181,
    ))

    result = _parse(payload)

    assert result.status == "PARTIAL"
    control = result.report_evidence.normalized_fields["warehouse_control"]
    assert control["status"] == "MISMATCH"
    assert control["mismatched_fields"] == ("available",)
    assert "FIFO_STOCK_WAREHOUSE_CONTROL_MISMATCH" in result.issue_codes


def test_duplicate_warehouse_dimension_key_is_rejected():
    def duplicate(workbook):
        source = workbook["Товар-склад"]
        for column in range(1, 28):
            source.cell(row=7, column=column, value=source.cell(row=5, column=column).value)

    result = _parse(_stock_payload(mutate=duplicate))

    assert result.status == "INVALID"
    assert result.issue_codes == ("FIFO_STOCK_WAREHOUSE_KEY_DUPLICATED",)


def test_missing_selected_sku_is_rejected_and_cluster_views_are_not_a_fallback():
    payload = _stock_payload(mutate=lambda workbook: [
        setattr(workbook["Товары"][f"C{row}"], "value", 987654321)
        for row in (5, 6)
    ])

    result = _parse(payload)

    assert result.status == "INVALID"
    assert result.issue_codes == ("FIFO_REPORT_TARGET_SKU_NOT_FOUND",)


def test_hidden_or_extra_sheet_is_rejected():
    result = _parse(_stock_payload(hidden_extra=True))

    assert result.status == "INVALID"
    assert result.issue_codes == ("FIFO_REPORT_WORKBOOK_RELATIONSHIP_INVALID",)


def test_unsupported_header_case_is_rejected_without_changing_case_scope():
    payload = _stock_payload(mutate=lambda workbook: setattr(
        workbook["Товары"]["M1"], "value", "доступно к продаже",
    ))

    result = _parse(payload)

    assert result.status == "INVALID"
    assert result.issue_codes == ("FIFO_REPORT_FORMAT_UNSUPPORTED",)


def test_formula_quantity_and_blank_quantity_are_not_zero():
    formula = _parse(_stock_payload(mutate=lambda workbook: setattr(
        workbook["Товары"]["M5"], "value", "=1000+182",
    )))
    blank = _parse(_stock_payload(mutate=lambda workbook: setattr(
        workbook["Товары"]["M5"], "value", None,
    )))

    assert formula.status == "INVALID"
    assert formula.issue_codes == ("FIFO_REPORT_FORMULA_VALUE_UNSUPPORTED",)
    assert blank.status == "INVALID"
    assert blank.issue_codes == ("FIFO_REPORT_REQUIRED_QUANTITY_MISSING",)


def test_error_in_sku_selection_column_blocks_ambiguous_row_selection():
    def set_error(workbook):
        cell = workbook["Товары"]["C7"]
        cell.value = "#VALUE!"
        cell.data_type = "e"

    result = _parse(_stock_payload(mutate=set_error))

    assert result.status == "INVALID"
    assert result.issue_codes == ("FIFO_REPORT_EXCEL_ERROR_CELL",)


def test_non_text_product_feature_is_rejected_instead_of_collapsing_to_unknown():
    result = _parse(_stock_payload(mutate=lambda workbook: setattr(
        workbook["Товары"]["D5"], "value", 123,
    )))

    assert result.status == "INVALID"
    assert result.issue_codes == ("FIFO_STOCK_DIMENSION_INVALID",)


def test_raw_labels_names_and_sku_are_not_repeated_in_normalized_fields():
    result = _parse()
    fields_text = repr(result.report_evidence.normalized_fields)

    assert _SKU not in fields_text
    assert "Warehouse A" not in fields_text
    assert "Cluster A" not in fields_text
    assert "Название товара" not in fields_text
