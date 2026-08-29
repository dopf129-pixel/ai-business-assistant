import period_profit_factory as factory


class Products:
    def load_products(self): return [{"sku": "1"}]


class Finance: pass
class Costs: pass


class Summary:
    def __init__(self, finance_service, cost_service, tax_rate):
        self.finance_service = finance_service
        self.cost_service = cost_service
        self.tax_rate = tax_rate


class Query:
    def __init__(self, summary_service, product_provider):
        self.summary_service = summary_service
        self.product_provider = product_provider


def test_factory_wires_existing_production_dependencies(monkeypatch):
    monkeypatch.setattr(factory, "ProductService", Products)
    monkeypatch.setattr(factory, "FinanceService", Finance)
    monkeypatch.setattr(factory, "ProductCostService", Costs)
    monkeypatch.setattr(factory, "PeriodProfitSummaryService", Summary)
    monkeypatch.setattr(factory, "PeriodProfitQueryService", Query)
    monkeypatch.setattr(factory, "TAX_RATE", 0.06)

    query = factory.create_period_profit_query()
    assert isinstance(query.summary_service.finance_service, Finance)
    assert isinstance(query.summary_service.cost_service, Costs)
    assert query.summary_service.tax_rate == 0.06
    assert query.product_provider() == [{"sku": "1"}]
