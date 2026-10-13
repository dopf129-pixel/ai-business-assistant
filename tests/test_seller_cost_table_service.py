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

    def record_cost_switches(self, rows):
        self.batch_calls.append(rows)
        return {"error": False, "inserted": len(rows), "unchanged": 0}


def test_export_csv_contains_catalog_and_blank_costs():
    service = SellerCostTableService(Products(), Costs())
    result = service.export_csv()
    assert result["error"] is False
    assert result["filename"] == "sebestoymost.csv"
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
