from datetime import date

from services.seller_cost_table_service import SellerCostTableService


class Products:
    def load_products(self):
        return [("p1", "ART-1", "101"), ("p2", "ART-2", "202")]


class Costs:
    def __init__(self, existing=None):
        self.existing = existing or []
        self.calls = []
        self.batch_calls = []

    def get_all_costs(self):
        return self.existing

    def record_cost_switch(self, **kwargs):
        self.calls.append(kwargs)
        return {"error": False}

    def record_cost_switches(self, rows, *, expected_revision=None):
        self.batch_calls.append(rows)
        return {"error": False, "inserted": len(rows), "unchanged": 0}


def test_export_csv_contains_catalog_and_blank_costs():
    service = SellerCostTableService(Products(), Costs())
    result = service.export_csv()
    assert result["error"] is False
    assert result["filename"] == "sebestoymost.csv"
    assert result["mime_type"] == "text/csv"
    assert result["document_kind"] == "seller_cost_import_template"
    assert "Артикул;Ozon SKU;Себестоимость, ₽;Действует с" in result["file_content"]
    assert "ART-1;101;;" in result["file_content"]


def test_import_csv_previews_first_cost_and_commits_only_after_confirmation():
    costs = Costs()
    service = SellerCostTableService(Products(), costs, date_provider=lambda: date(2026, 9, 15))
    result = service.import_csv("Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\nART-1;101;430;\nART-2;202;510,5;\n")
    assert result["error"] is False
    assert result["imported"] == 2
    assert result["all_history_allowed"] is True
    assert all(row["effective_from"] == "2026-09-15" for row in result["rows"])
    assert costs.batch_calls == []
    saved = service.commit_import(result["rows"], whole_history=False)
    assert saved["error"] is False
    assert [row["cost_price"] for row in costs.batch_calls[0]] == [430.0, 510.5]
    assert all(row["effective_from"] == "2026-09-15" for row in costs.batch_calls[0])


def test_import_whole_history_requires_explicit_commit_and_only_new_costs():
    costs = Costs()
    service = SellerCostTableService(Products(), costs, date_provider=lambda: date(2026, 9, 15))
    preview = service.import_csv("Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\nART-1;101;430;\n")
    saved = service.commit_import(preview["rows"], whole_history=True)
    assert saved["error"] is False
    assert costs.batch_calls[0][0]["effective_from"] == "0001-01-01"
    assert costs.batch_calls[0][0]["source"] == "SELLER_CONFIRMED_INITIAL_HISTORY_TABLE"


def test_import_validates_all_rows_before_writing():
    costs = Costs()
    service = SellerCostTableService(Products(), costs)
    result = service.import_csv("Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\nART-1;101;430;\nOTHER;202;510;\n")
    assert result["error"] is True
    assert result["code"] == "SELLER_COST_TABLE_VALIDATION_FAILED"
    assert costs.batch_calls == []


def test_import_rejects_existing_cost_without_effective_date():
    costs = Costs(existing=[("p1", "101", "ART-1", 400.0, "RUB", "now")])
    service = SellerCostTableService(Products(), costs)
    result = service.import_csv("Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\nART-1;101;430;\n")
    assert result["error"] is True
    assert result["code"] == "SELLER_COST_TABLE_VALIDATION_FAILED"
    assert costs.batch_calls == []


def test_import_existing_cost_requires_explicit_date_and_does_not_apply_whole_history():
    costs = Costs(existing=[("p1", "101", "ART-1", 400.0, "RUB", "now")])
    service = SellerCostTableService(Products(), costs, date_provider=lambda: date(2026, 9, 15))
    preview = service.import_csv("Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\nART-1;101;430;2026-10-01\n")
    assert preview["error"] is False
    assert preview["all_history_allowed"] is False
    assert service.commit_import(preview["rows"], whole_history=True)["error"] is True
    assert costs.batch_calls == []
    saved = service.commit_import(preview["rows"], whole_history=False)
    assert saved["error"] is False
    assert costs.batch_calls[0][0]["effective_from"] == "2026-10-01"


def test_import_captures_source_reference_and_cost_revision_and_rejects_stale_commit():
    costs = Costs()
    service = SellerCostTableService(Products(), costs)
    preview = service.import_csv(
        "Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\n"
        "ART-1;101;430;2026-10-01\n"
    )
    assert preview["error"] is False
    assert preview["source_reference"].startswith("seller-cost-file-")
    assert preview["source_revision"].startswith("seller-cost-rev-")

    costs.existing = [("p1", "101", "ART-1", 410.0, "RUB", "2026-10-01")]
    result = service.commit_import(
        preview["rows"], expected_source_revision=preview["source_revision"],
    )
    assert result["error"] is True
    assert result["code"] == "SELLER_COST_TABLE_PREVIEW_STALE"
    assert costs.batch_calls == []


def test_import_supports_multiple_distinct_dated_rates_for_one_legacy_sku():
    costs = Costs()
    service = SellerCostTableService(Products(), costs)
    preview = service.import_csv(
        "Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\n"
        "ART-1;101;430;2026-01-01\n"
        "ART-1;101;450;2026-03-01\n"
    )
    assert preview["error"] is False
    assert preview["imported"] == 2
    assert preview["all_history_allowed"] is False
    saved = service.commit_import(preview["rows"])
    assert saved["error"] is False
    assert [row["effective_from"] for row in costs.batch_calls[0]] == [
        "2026-01-01", "2026-03-01",
    ]


def test_existing_future_legacy_rate_requires_date_for_imported_older_value():
    class FutureHistoryCosts(Costs):
        def get_seller_cost_identities(self):
            return {
                "error": False,
                "records": [{"product_id": "p1", "sku": "101", "offer_id": "ART-1"}],
            }

    service = SellerCostTableService(Products(), FutureHistoryCosts())
    no_date = service.import_csv(
        "Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\n"
        "ART-1;101;430;\n"
    )
    assert no_date["error"] is True
    assert no_date["code"] == "SELLER_COST_TABLE_VALIDATION_FAILED"
    older = service.import_csv(
        "Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\n"
        "ART-1;101;430;2026-01-01\n"
    )
    assert older["error"] is False
    assert older["rows"][0]["initial"] is False


def test_import_bounds_bytes_rows_and_cell_size():
    service = SellerCostTableService(Products(), Costs())
    too_large = service.import_csv(b"x" * (service.MAX_UPLOAD_BYTES + 1))
    assert too_large["code"] == "SELLER_COST_TABLE_TOO_LARGE"

    header = "Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\n"
    many_rows = header + ("ART-1;101;430;2026-10-01\n" * (service.MAX_ROWS + 1))
    result = service.import_csv(many_rows)
    assert result["code"] == "SELLER_COST_TABLE_TOO_MANY_ROWS"

    long_cell = header + ("x" * (service.MAX_CELL_CHARS + 1)) + ";101;430;2026-10-01\n"
    result = service.import_csv(long_cell)
    assert result["code"] == "SELLER_COST_TABLE_CELL_TOO_LARGE"


def test_import_rejects_invalid_encoding_and_csv_rows_with_extra_columns():
    service = SellerCostTableService(Products(), Costs())
    invalid = service.import_csv(b"\xff\xfe\x00\x00")
    assert invalid["code"] == "SELLER_COST_TABLE_ENCODING_INVALID"
    extra = service.import_csv(
        "Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\n"
        "ART-1;101;430;2026-10-01;лишняя колонка\n"
    )
    assert extra["code"] == "SELLER_COST_TABLE_VALIDATION_FAILED"


def test_catalog_duplicate_sku_is_rejected_as_ambiguous():
    class AmbiguousProducts:
        def load_products(self):
            return [("p1", "ART-1", "101"), ("p2", "ART-2", "101")]

    service = SellerCostTableService(AmbiguousProducts(), Costs())
    result = service.import_csv(
        "Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\n"
        "ART-1;101;430;2026-10-01\n"
    )
    assert result["error"] is True
    assert result["code"] == "SELLER_COST_PRODUCT_CATALOG_AMBIGUOUS"


def test_template_formula_escapes_catalog_identifiers_and_import_roundtrips_them():
    class FormulaProducts:
        def load_products(self):
            return [("p1", "=1+1", "@sku")]

    service = SellerCostTableService(FormulaProducts(), Costs())
    exported = service.export_csv()
    assert "'=1+1;'@sku;;" in exported["file_content"]
    imported = service.import_csv(
        "Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\n"
        "'=1+1;'@sku;430;2026-10-01\n"
    )
    assert imported["error"] is False
    assert imported["rows"][0]["sku"] == "@sku"


def test_legacy_import_rejects_fifo_history_file_with_clear_mode_reason():
    service = SellerCostTableService(Products(), Costs())
    result = service.import_csv(
        "Режим;SKU;Тип записи\nFIFO;101;FINITE_LAYER\n"
    )
    assert result["error"] is True
    assert result["code"] == "SELLER_COST_TABLE_FIFO_MODE_CONFLICT"
    assert "подтверждённый сценарий FIFO" in result["message"]


def test_fifo_cost_mode_conflict_is_checked_before_legacy_import():
    class FifoRepository:
        def read_cost_mode_status(self, **_kwargs):
            return {"error": False, "active": True, "stream_state": "READY"}

    costs = Costs()
    service = SellerCostTableService(
        Products(), costs, fifo_cost_repository=FifoRepository(),
    )
    result = service.import_csv(
        "Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\n"
        "ART-1;101;430;2026-10-01\n",
        store_id="store-1",
    )
    assert result["error"] is True
    assert result["code"] == "SELLER_COST_TABLE_FIFO_MODE_CONFLICT"
    assert costs.batch_calls == []


def test_legacy_history_export_is_read_only_and_contains_date_source_revision():
    class HistoryCosts(Costs):
        def get_cost_history_snapshot(self):
            return {
                "error": False,
                "revision": "legacy-cost-" + "a" * 24,
                "records": [{
                    "record_type": "product_cost_switch_history",
                    "sku": "101", "offer_id": "ART-1", "cost_price": "430.00",
                    "effective_from": "2026-10-01", "effective_through": None,
                    "source": "SELLER_CONFIRMED_COST_TABLE",
                }],
            }

    result = SellerCostTableService(Products(), HistoryCosts()).export_history_csv()
    assert result["error"] is False
    assert result["document_kind"] == "analytics_export"
    assert "2026-10-01" in result["file_content"]
    assert "SELLER_CONFIRMED_COST_TABLE" in result["file_content"]
    assert "legacy-cost-" + "a" * 24 in result["file_content"]
    assert "не является шаблоном импорта" in result["message"]
