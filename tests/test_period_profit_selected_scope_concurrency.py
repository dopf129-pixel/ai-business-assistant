from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from services.period_profit_sku_runtime_service import PeriodProfitSkuRuntimeService


class _ConcurrentQuery:
    def __init__(self):
        self.product_provider = lambda: [
            {"product_id": "p-a", "offer_id": "offer-a", "sku": "sku-a"},
            {"product_id": "p-b", "offer_id": "offer-b", "sku": "sku-b"},
        ]
        self.barrier = Barrier(2)

    def query(self, **_kwargs):
        self.barrier.wait(timeout=2)
        return self.product_provider()[0]


def test_selected_product_provider_scope_is_request_local_under_concurrency():
    query = _ConcurrentQuery()
    runtime = PeriodProfitSkuRuntimeService(query)
    identities = [
        {"product_id": "p-a", "offer_id": "offer-a", "sku": "sku-a"},
        {"product_id": "p-b", "offer_id": "offer-b", "sku": "sku-b"},
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(runtime._query_selected_product, identities))

    assert {result["sku"] for result in results} == {"sku-a", "sku-b"}
    assert len(query.product_provider()) == 2
