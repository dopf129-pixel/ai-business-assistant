from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook
import pytest

from services.fifo_cost_report_import_service import FifoCostReportImportService
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    PeriodProvenance,
    ScopeIdentity,
)


_HEADERS = {
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

_TARGET_SKU = "3921245627"
_SCOPE = ScopeIdentity(
    owner_id="owner-1", store_id="store-1", sku=_TARGET_SKU,
    product_id="product-1",
)


def _turnover_payload(*, mutate=None, second_sku=True, hidden_extra_sheet=False):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Оборотная ведомость"
    for cell_ref, value in _HEADERS.items():
        sheet[cell_ref] = value
    row_values = [0] * 40
    row_values[0] = int(_TARGET_SKU)
    row_values[3:11] = [2740, 0, 2, 1, 1, 1, 75, 1672]
    row_values[11:18] = [0, 0, 0, 0, 0, 0, 0]
    row_values[18] = 9  # Excluded compensation does not enter receipts total.
    row_values[19:26] = [775, 0, 5, 0, 0, 0, 0]
    row_values[26] = 4  # Excluded compensation does not enter expenses total.
    row_values[27:35] = [1988, 0, 2, 6, 0, 0, 70, 1646]
    row_values[35:39] = [4492, 0, 780, 3712]
    row_values[39] = 0
    for column, value in enumerate(row_values, start=1):
        sheet.cell(row=4, column=column, value=value)
    if second_sku:
        sheet["A5"] = 1234567890
        sheet["D5"] = 17
    if hidden_extra_sheet:
        hidden = workbook.create_sheet("Hidden extra")
        hidden.sheet_state = "hidden"
    if mutate:
        mutate(sheet)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _parse(payload=None, *, filename="turnover_04112026-05112026.xlsx", **kwargs):
    return FifoCostReportImportService().parse_turnover_workbook(
        payload=payload if payload is not None else _turnover_payload(),
        filename=filename,
        scope=_SCOPE,
        **kwargs,
    )


def test_turnover_import_normalizes_exact_sku_and_separates_sales_from_expenses():
    result = _parse()

    assert result.status == "COMPLETE"
    assert result.read_only is True
    assert result.executed is False
    report = result.report_evidence
    assert report is not None
    assert report.period_from == "2026-11-04"
    assert report.period_to == "2026-11-05"
    assert report.period_provenance is PeriodProvenance.FILENAME_CANDIDATE
    assert report.metadata.completeness is EvidenceCompleteness.COMPLETE
    assert report.normalized_fields["source_row"] == 4
    assert report.normalized_fields["opening_total"] == 4492
    assert report.normalized_fields["receipts_total"] == 0
    assert report.normalized_fields["redeemed_units"] == 775
    assert report.normalized_fields["withdrawal_units"] == 5
    assert report.normalized_fields["non_sale_expense_units"] == 5
    assert report.normalized_fields["closing_total"] == 3712
    assert report.normalized_fields["closing_buckets"]["buyer_delivery"] == 1646
    assert report.normalized_fields["closing_buckets"]["buyer_return_transit"] == 70
    assert report.normalized_fields["computed_balance_difference"] == 0
    assert report.normalized_fields["excluded_compensation_receipt"] == 9
    assert report.normalized_fields["excluded_compensation_expense"] == 4
    assert report.normalized_fields["component_controls_match"] is True
    assert "3921245627" not in report.normalized_fields.values()


def test_owner_confirmed_period_overrides_filename_candidate():
    result = _parse(owner_confirmed_period=("2026-11-01", "2026-11-05"))

    assert result.status == "COMPLETE"
    assert result.report_evidence.period_from == "2026-11-01"
    assert result.report_evidence.period_provenance is PeriodProvenance.OWNER_CONFIRMED


def test_invalid_owner_period_returns_safe_error_instead_of_raising():
    result = _parse(owner_confirmed_period=("not-a-date", "2026-11-05"))

    assert result.status == "INVALID"
    assert result.report_evidence is None
    assert result.issue_codes == ("FIFO_REPORT_PERIOD_INVALID",)


def test_duplicate_target_sku_is_rejected():
    payload = _turnover_payload(mutate=lambda sheet: setattr(sheet["A5"], "value", int(_TARGET_SKU)))

    result = _parse(payload)

    assert result.status == "INVALID"
    assert result.issue_codes == ("FIFO_REPORT_TARGET_SKU_DUPLICATED",)


def test_missing_required_quantity_is_not_treated_as_zero():
    payload = _turnover_payload(mutate=lambda sheet: setattr(sheet["D4"], "value", None))

    result = _parse(payload)

    assert result.status == "INVALID"
    assert result.issue_codes == ("FIFO_REPORT_REQUIRED_QUANTITY_MISSING",)


def test_formula_quantity_is_rejected_without_evaluating_formula():
    payload = _turnover_payload(mutate=lambda sheet: setattr(sheet["D4"], "value", "=2000+740"))

    result = _parse(payload)

    assert result.status == "INVALID"
    assert result.issue_codes == ("FIFO_REPORT_FORMULA_VALUE_UNSUPPORTED",)


def test_header_formula_is_rejected_instead_of_trusting_cached_text():
    payload = _turnover_payload(
        mutate=lambda sheet: setattr(sheet["D1"], "value", '="Остаток на начало"'),
    )

    result = _parse(payload)

    assert result.status == "INVALID"
    assert result.issue_codes == ("FIFO_REPORT_HEADER_FORMULA_UNSUPPORTED",)


def test_excel_error_and_fractional_quantity_are_not_coerced():
    error_payload = _turnover_payload(mutate=lambda sheet: _set_excel_error(sheet["D4"]))
    fractional_payload = _turnover_payload(
        mutate=lambda sheet: setattr(sheet["D4"], "value", 2740.5),
    )

    error_result = _parse(error_payload)
    fractional_result = _parse(fractional_payload)

    assert error_result.status == "INVALID"
    assert error_result.issue_codes == ("FIFO_REPORT_EXCEL_ERROR_CELL",)
    assert fractional_result.status == "INVALID"
    assert fractional_result.issue_codes == ("FIFO_REPORT_QUANTITY_INVALID",)


def test_balance_discrepancy_is_partial_evidence_not_a_zero_stock_claim():
    payload = _turnover_payload(mutate=lambda sheet: setattr(sheet["AM4"], "value", 3711))

    result = _parse(payload)

    assert result.status == "PARTIAL"
    assert result.report_evidence.metadata.completeness is EvidenceCompleteness.PARTIAL
    assert "FIFO_TURNOVER_BALANCE_CONTROL_FAILED" in result.issue_codes
    assert result.report_evidence.normalized_fields["closing_total"] == 3711


@pytest.mark.parametrize(
    ("cell", "value", "issue_code"),
    [
        ("AJ4", 4491, "FIFO_TURNOVER_OPENING_TOTAL_MISMATCH"),
        ("AK4", 1, "FIFO_TURNOVER_RECEIPTS_TOTAL_MISMATCH"),
        ("AL4", 779, "FIFO_TURNOVER_EXPENSES_TOTAL_MISMATCH"),
        ("AM4", 3711, "FIFO_TURNOVER_CLOSING_TOTAL_MISMATCH"),
        ("AN4", 1, "FIFO_TURNOVER_REPORTED_BALANCE_MISMATCH"),
    ],
)
def test_each_report_total_has_an_independent_control(cell, value, issue_code):
    payload = _turnover_payload(mutate=lambda sheet: setattr(sheet[cell], "value", value))

    result = _parse(payload)

    assert result.status == "PARTIAL"
    assert issue_code in result.issue_codes
    assert result.report_evidence.metadata.completeness is EvidenceCompleteness.PARTIAL


def test_changed_header_and_unknown_extra_column_are_rejected():
    changed_header = _parse(_turnover_payload(
        mutate=lambda sheet: setattr(sheet["T2"], "value", "Заказано товаров"),
    ))
    extra_column = _parse(_turnover_payload(
        mutate=lambda sheet: setattr(sheet["AO1"], "value", "Unknown"),
    ))

    assert changed_header.status == "INVALID"
    assert changed_header.issue_codes == ("FIFO_REPORT_FORMAT_UNSUPPORTED",)
    assert extra_column.status == "INVALID"
    assert extra_column.issue_codes == ("FIFO_REPORT_FORMAT_UNSUPPORTED",)


def test_whitespace_and_nonbreaking_spaces_in_headers_are_normalized():
    payload = _turnover_payload(mutate=lambda sheet: setattr(
        sheet["D1"], "value", "Остаток\u00a0 на   начало",
    ))

    assert _parse(payload).status == "COMPLETE"


def test_header_case_is_not_normalized():
    payload = _turnover_payload(mutate=lambda sheet: setattr(
        sheet["D1"], "value", "остаток на начало",
    ))

    result = _parse(payload)

    assert result.status == "INVALID"
    assert result.issue_codes == ("FIFO_REPORT_FORMAT_UNSUPPORTED",)


def test_hidden_extra_sheet_is_rejected_before_parsing():
    result = _parse(_turnover_payload(hidden_extra_sheet=True))

    assert result.status == "INVALID"
    assert result.issue_codes == ("FIFO_REPORT_WORKBOOK_RELATIONSHIP_INVALID",)


def test_filename_period_is_candidate_and_missing_period_stays_unknown():
    result = _parse(filename="turnover.xlsx")

    assert result.status == "PARTIAL"
    assert result.report_evidence.period_from is None
    assert result.report_evidence.period_provenance is PeriodProvenance.UNKNOWN
    assert "FIFO_REPORT_FILENAME_PERIOD_UNAVAILABLE" in result.issue_codes


def test_target_sku_larger_than_quantity_limit_is_not_parsed_as_a_quantity():
    result = _parse()

    assert result.status == "COMPLETE"
    assert result.report_evidence.normalized_fields["redeemed_units"] == 775


def test_zip_path_traversal_and_external_relationships_are_rejected():
    payload = _turnover_payload()
    traversal_output = BytesIO()
    with ZipFile(BytesIO(payload), "r") as source, ZipFile(
        traversal_output, "w", compression=ZIP_DEFLATED,
    ) as destination:
        for name in source.namelist():
            destination.writestr(name, source.read(name))
        destination.writestr("../unexpected.xml", "<root />")
    traversal = _parse(traversal_output.getvalue())

    external_output = BytesIO()
    with ZipFile(BytesIO(payload), "r") as source, ZipFile(
        external_output, "w", compression=ZIP_DEFLATED,
    ) as destination:
        for name in source.namelist():
            content = source.read(name)
            if name == "xl/_rels/workbook.xml.rels":
                content = content.replace(
                    b"</Relationships>",
                    b'<Relationship Id="external" Type="https://example.invalid/external" Target="https://example.invalid/file" TargetMode="External"/></Relationships>',
                )
            destination.writestr(name, content)
    external = _parse(external_output.getvalue())

    relationship_path_output = BytesIO()
    with ZipFile(BytesIO(payload), "r") as source, ZipFile(
        relationship_path_output, "w", compression=ZIP_DEFLATED,
    ) as destination:
        for name in source.namelist():
            content = source.read(name)
            if name == "xl/_rels/workbook.xml.rels":
                content = content.replace(
                    b"Target=\"/xl/worksheets/sheet1.xml\"",
                    b"Target=\"/../xl/worksheets/sheet1.xml\"",
                )
            destination.writestr(name, content)
    relationship_path = _parse(relationship_path_output.getvalue())

    assert traversal.status == "INVALID"
    assert traversal.issue_codes == ("FIFO_REPORT_ZIP_PATH_INVALID",)
    assert external.status == "INVALID"
    assert external.issue_codes == ("FIFO_REPORT_EXTERNAL_RELATIONSHIP_UNSUPPORTED",)
    assert relationship_path.status == "INVALID"
    assert relationship_path.issue_codes == ("FIFO_REPORT_RELATIONSHIP_INVALID",)


def test_zip_preflight_enforces_entry_and_compression_limits(monkeypatch):
    monkeypatch.setattr(FifoCostReportImportService, "MAX_ZIP_ENTRIES", 1)
    entry_result = _parse()
    monkeypatch.setattr(FifoCostReportImportService, "MAX_ZIP_ENTRIES", 2048)
    monkeypatch.setattr(FifoCostReportImportService, "MAX_COMPRESSION_RATIO", 1)
    ratio_result = _parse()

    assert entry_result.status == "INVALID"
    assert entry_result.issue_codes == ("FIFO_REPORT_ZIP_ENTRY_LIMIT",)
    assert ratio_result.status == "INVALID"
    assert ratio_result.issue_codes == ("FIFO_REPORT_COMPRESSION_RATIO_LIMIT",)


def _set_excel_error(cell):
    cell.value = "#VALUE!"
    cell.data_type = "e"
