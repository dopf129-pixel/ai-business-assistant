import period_profit_factory as factory


class Products:
    def load_products(self): return [{"sku": "1"}]


class Finance: pass
class Costs: pass
class Ozon: pass


class ReturnEvidence:
    def __init__(self, ozon_client): self.ozon_client = ozon_client


class Summary:
    def __init__(self, finance_service, cost_service, tax_rate):
        self.finance_service = finance_service
        self.cost_service = cost_service
        self.tax_rate = tax_rate


class Query:
    def __init__(
        self,
        summary_service,
        product_provider,
        return_evidence_service=None,
        authorized_return_mapping=None,
        authorized_advertising_mapping=None,
        authorized_storage_mapping=None,
        mapping_observability_service=None,
    ):
        self.summary_service = summary_service
        self.product_provider = product_provider
        self.return_evidence_service = return_evidence_service
        self.authorized_return_mapping = authorized_return_mapping
        self.authorized_advertising_mapping = authorized_advertising_mapping
        self.authorized_storage_mapping = authorized_storage_mapping
        self.mapping_observability_service = mapping_observability_service


def test_factory_wires_existing_production_dependencies(monkeypatch):
    monkeypatch.setattr(factory, "ProductService", Products)
    monkeypatch.setattr(factory, "FinanceService", Finance)
    monkeypatch.setattr(factory, "ProductCostService", Costs)
    monkeypatch.setattr(factory, "OzonClient", Ozon)
    monkeypatch.setattr(factory, "PeriodProfitReturnEvidenceService", ReturnEvidence)
    monkeypatch.setattr(factory, "PeriodProfitSummaryService", Summary)
    monkeypatch.setattr(factory, "PeriodProfitQueryService", Query)
    monkeypatch.setattr(factory, "TAX_RATE", 0.06)

    query = factory.create_period_profit_query()
    assert isinstance(query.summary_service.finance_service, Finance)
    assert isinstance(query.summary_service.cost_service, Costs)
    assert query.summary_service.tax_rate == 0.06
    assert query.product_provider() == [{"sku": "1"}]
    assert isinstance(query.return_evidence_service, ReturnEvidence)
    assert isinstance(query.return_evidence_service.ozon_client, Ozon)
    assert query.authorized_return_mapping is None
    assert query.authorized_advertising_mapping is None
    assert query.authorized_storage_mapping is None
    assert query.mapping_observability_service is None
