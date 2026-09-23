from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

import pytest

from services.ozon_promotion_report_import import (
    PromotionReportError, parse_promotion_report, combine_reports,
)
from services.ozon_promotion_history_repository import PromotionHistoryRepository


def _xlsx(start, end, sku="3921245627", amount="12.345"):
    headers = ["SKU", "Название товара", "Инструмент", "Место размещения",
               "ID кампании", "Расход, ₽"]
    from xml.sax.saxutils import escape
    def cell(col, row, value):
        return '<c r="%s%s" t="inlineStr"><is><t>%s</t></is></c>' % (
            col, row, escape(str(value)))
    def row(n, values):
        return '<row r="%s">%s</row>' % (
            n, "".join(cell(chr(65 + i), n, v) for i, v in enumerate(values)))
    xml = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           '<sheetData>' + row(1, ["Период: %s - %s" % (start, end)])
           + row(2, headers)
           + row(3, [sku, "Test", "Оплата за клик", "Поиск", "123", amount])
           + '</sheetData></worksheet>')
    buf = BytesIO()
    with ZipFile(buf, "w") as archive:
        archive.writestr("xl/worksheets/sheet2.xml", xml)
    return buf.getvalue()


def test_import_reads_exact_sku_expenses():
    report = parse_promotion_report(_xlsx("03.05.2026", "31.07.2026"))
    assert report["date_from"] == "2026-05-03"
    assert report["rows"][0]["expense"] == Decimal("12.345")
    assert report["rows"][0]["sku"] == "3921245627"


def test_import_rejects_bad_and_duplicate_rows():
    with pytest.raises(PromotionReportError):
        parse_promotion_report(b"not a workbook")
    with pytest.raises(PromotionReportError):
        parse_promotion_report(_xlsx("03.05.2026", "31.07.2026", amount="-1"))


def test_coverage_must_be_exact_no_gaps_or_overlaps():
    a = parse_promotion_report(_xlsx("03.05.2026", "31.07.2026"))
    b = parse_promotion_report(_xlsx("01.08.2026", "23.09.2026", amount="2"))
    result = combine_reports([b, a], "2026-05-03", "2026-09-23", {"3921245627"})
    assert result["total_expense"] == Decimal("14.345")
    with pytest.raises(PromotionReportError):
        combine_reports([a], "2026-05-03", "2026-09-23", {"3921245627"})
    with pytest.raises(PromotionReportError):
        combine_reports([a, a], "2026-05-03", "2026-09-23", {"3921245627"})


def test_import_is_store_scoped_and_idempotent(tmp_path):
    repo = PromotionHistoryRepository(db_name=str(tmp_path / "db.sqlite"))
    a = parse_promotion_report(_xlsx("03.05.2026", "31.07.2026"))
    b = parse_promotion_report(_xlsx("01.08.2026", "23.09.2026", amount="2"))
    for _ in range(2):
        repo.import_reports("user::ozon::store-a", [a, b],
                            "2026-05-03", "2026-09-23", {"3921245627"})
    result = repo.load_exact("user::ozon::store-a",
                             "2026-05-03", "2026-09-23", {"3921245627"})
    assert result["expense"] == 14.35
    assert repo.load_exact("user::ozon::store-b",
                           "2026-05-03", "2026-09-23", {"3921245627"}) is None
    assert repo.load_exact("user::ozon::store-a",
                           "2026-05-04", "2026-09-23", {"3921245627"}) is None
