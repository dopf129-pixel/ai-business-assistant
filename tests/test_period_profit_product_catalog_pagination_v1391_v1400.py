import services.product_service as product_module
from period_profit_factory import _load_period_profit_products
from services.product_service import ProductService


class OzonPages:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def _post(self, endpoint, payload):
        self.calls.append((endpoint, dict(payload)))
        return self.pages[len(self.calls) - 1]


def _page(items, last_id=""):
    return {
        "result": {
            "items": list(items),
            "last_id": last_id,
        }
    }


def test_v1391_product_catalog_refresh_reads_all_cursor_pages(monkeypatch):
    saved = []
    monkeypatch.setattr(product_module, "save_product", lambda product: saved.append(dict(product)))

    service = ProductService.__new__(ProductService)
    service.ozon = OzonPages([
        _page(
            [{"product_id": index, "offer_id": f"o-{index}", "sku": f"sku-{index}"} for index in range(100)],
            last_id="cursor-2",
        ),
        _page(
            [{"product_id": 100, "offer_id": "o-100", "sku": "sku-100"}],
            last_id="",
        ),
    ])

    result = service.refresh_products_for_period_profit(limit=100)

    assert result["error"] is False
    assert result["complete"] is True
    assert result["count"] == 101
    assert result["pages_loaded"] == 2
    assert len(saved) == 101
    assert service.ozon.calls[0][1] == {"filter": {}, "limit": 100}
    assert service.ozon.calls[1][1]["last_id"] == "cursor-2"


def test_v1392_repeated_cursor_fails_closed(monkeypatch):
    monkeypatch.setattr(product_module, "save_product", lambda product: None)
    service = ProductService.__new__(ProductService)
    service.ozon = OzonPages([
        _page([{"product_id": index} for index in range(100)], last_id="same"),
        _page([{"product_id": index + 100} for index in range(100)], last_id="same"),
    ])

    result = service.refresh_products_for_period_profit(limit=100)

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_PRODUCT_CATALOG_CURSOR_INVALID"
    assert result["complete"] is False


def test_v1393_period_profit_provider_refreshes_before_loading_products():
    events = []

    class Products:
        def refresh_products_for_period_profit(self):
            events.append("refresh")
            return {"error": False, "complete": True}

        def load_products(self):
            events.append("load")
            return [("1", "offer", "sku")]

    result = _load_period_profit_products(Products())

    assert result == [("1", "offer", "sku")]
    assert events == ["refresh", "load"]


def test_v1394_incomplete_catalog_never_uses_stale_local_subset():
    class Products:
        def refresh_products_for_period_profit(self):
            return {"error": True, "complete": False}

        def load_products(self):
            raise AssertionError("stale local subset must not be used")

    assert _load_period_profit_products(Products()) == []


def test_v1395_legacy_product_provider_without_refresh_remains_compatible():
    class Products:
        def load_products(self):
            return [("1", "offer", "sku")]

    assert _load_period_profit_products(Products()) == [("1", "offer", "sku")]


def test_v1396_refresh_is_read_only_toward_ozon(monkeypatch):
    monkeypatch.setattr(product_module, "save_product", lambda product: None)
    service = ProductService.__new__(ProductService)
    service.ozon = OzonPages([_page([{"product_id": 1}], last_id="")])

    result = service.refresh_products_for_period_profit(limit=100)

    assert result["error"] is False
    assert result["read_only"] is True
    assert result["executed"] is False
    assert service.ozon.calls[0][0] == "/v3/product/list"


def test_v1397_malformed_page_fails_closed(monkeypatch):
    monkeypatch.setattr(product_module, "save_product", lambda product: None)
    service = ProductService.__new__(ProductService)
    service.ozon = OzonPages([{"result": {"items": None}}])

    result = service.refresh_products_for_period_profit()

    assert result["error"] is True
    assert result["count"] is None


def test_v1398_storage_failure_fails_closed(monkeypatch):
    def fail(_product):
        raise RuntimeError("db")

    monkeypatch.setattr(product_module, "save_product", fail)
    service = ProductService.__new__(ProductService)
    service.ozon = OzonPages([_page([{"product_id": 1}])])

    result = service.refresh_products_for_period_profit()

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_PRODUCT_CATALOG_STORAGE_UNAVAILABLE"


def test_v1399_page_limit_fails_closed(monkeypatch):
    monkeypatch.setattr(product_module, "save_product", lambda product: None)
    service = ProductService.__new__(ProductService)
    service.ozon = OzonPages([
        _page([{"product_id": index} for index in range(100)], last_id="next")
    ])

    result = service.refresh_products_for_period_profit(limit=100, max_pages=1)

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_PRODUCT_CATALOG_PAGE_LIMIT_REACHED"


def test_v1400_update_products_keeps_integer_compatibility(monkeypatch):
    service = ProductService.__new__(ProductService)
    monkeypatch.setattr(
        service,
        "refresh_products_for_period_profit",
        lambda: {"error": False, "count": 123, "complete": True},
    )

    assert service.update_products() == 123
