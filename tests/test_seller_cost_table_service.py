from services.seller_cost_table_service import SellerCostTableService


class Products:
    def load_products(self):
        return [("p1", "ART-1", "101"), ("p2", "ART-2", "202")]


class Costs:
    def __init__(self, existing=None):
        self.existing = existing or []
        self.calls = []

    def get_all_costs(self):
        return self.existing

    def record_cost_switch(self, **kwargs):
        self.calls.append(kwargs)
        return {"error": False}


def test_export_csv_contains_catalog_and_blank_costs():
    service = SellerCostTableService(Products(), Costs())
    result = service.export_csv()
    assert result["error"] is False
    assert result["filename"] == "sebestoymost.csv"
    assert "Артикул;Ozon SKU;Себестоимость, ₽" in result["file_content"]
    assert "ART-1;101;" in result["file_content"]


def test_import_csv_records_first_cost_for_all_history():
    costs = Costs()
    service = SellerCostTableService(Products(), costs)
    result = service.import_csv("Артикул;Ozon SKU;Себестоимость, ₽\nART-1;101;430\nART-2;202;510,5\n")
    assert result["error"] is False
    assert result["imported"] == 2
    assert [call["cost_price"] for call in costs.calls] == [430.0, 510.5]
    assert all(call["effective_from"] == "0001-01-01" for call in costs.calls)
    assert all(call["source"] == "SELLER_CONFIRMED_INITIAL_HISTORY_TABLE" for call in costs.calls)


def test_import_validates_all_rows_before_writing():
    costs = Costs()
    service = SellerCostTableService(Products(), costs)
    result = service.import_csv("Артикул;Ozon SKU;Себестоимость, ₽\nART-1;101;430\nOTHER;202;510\n")
    assert result["error"] is True
    assert result["code"] == "SELLER_COST_TABLE_VALIDATION_FAILED"
    assert costs.calls == []


def test_import_rejects_existing_cost_without_effective_date():
    costs = Costs(existing=[("p1", "101", "ART-1", 400.0, "RUB", "now")])
    service = SellerCostTableService(Products(), costs)
    result = service.import_csv("Артикул;Ozon SKU;Себестоимость, ₽\nART-1;101;430\n")
    assert result["error"] is True
    assert result["code"] == "SELLER_COST_TABLE_EXISTING_COST_REQUIRES_DATE"
    assert costs.calls == []
