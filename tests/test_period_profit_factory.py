import period_profit_factory as factory


class Products:
    def load_products(self): return [{"sku": "1"}]


class Finance: pass
class Costs: pass
class Expenses: pass
class InventoryRecovery: pass
class Ozon: pass


class TaxConfig:
    def get_policy(self):
        return {
            "error": False,
            "configured": True,
            "policy": {
                "mode": "USN_INCOME",
                "tax_rate": 6.0,
                "minimum_tax_rate": 1.0,
            },
        }


class ReturnEvidence:
    def __init__(self, ozon_client): self.ozon_client = ozon_client


class SaleLineageEvidence:
    def __init__(self, finance_service):
        self.finance_service = finance_service


class ReturnCogsEvidence:
    def __init__(
        self,
        cost_service,
        sale_lineage_evidence_service=None,
        inventory_recovery_repository=None,
    ):
        self.cost_service = cost_service
        self.sale_lineage_evidence_service = (
            sale_lineage_evidence_service
        )
        self.inventory_recovery_repository = (
            inventory_recovery_repository
        )


class ExternalExpenseEvidence:
    def __init__(self, repository): self.repository = repository


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
        return_cogs_recovery_evidence_service=None,
        external_expense_evidence_service=None,
    ):
        self.summary_service = summary_service
        self.product_provider = product_provider
        self.return_evidence_service = return_evidence_service
        self.authorized_return_mapping = authorized_return_mapping
        self.authorized_advertising_mapping = authorized_advertising_mapping
        self.authorized_storage_mapping = authorized_storage_mapping
        self.mapping_observability_service = mapping_observability_service
        self.return_cogs_recovery_evidence_service = return_cogs_recovery_evidence_service
        self.external_expense_evidence_service = external_expense_evidence_service


def test_factory_wires_existing_production_dependencies(monkeypatch):
    monkeypatch.setattr(factory, "ProductService", Products)
    monkeypatch.setattr(factory, "FinanceService", Finance)
    monkeypatch.setattr(factory, "ProductCostService", Costs)
    monkeypatch.setattr(factory, "ExpenseRepository", Expenses)
    monkeypatch.setattr(
        factory,
        "ReturnInventoryRecoveryRepository",
        InventoryRecovery,
    )
    monkeypatch.setattr(factory, "OzonClient", Ozon)
    monkeypatch.setattr(factory, "PeriodProfitReturnEvidenceService", ReturnEvidence)
    monkeypatch.setattr(
        factory,
        "PeriodProfitReturnCogsRecoveryEvidenceService",
        ReturnCogsEvidence,
    )
    monkeypatch.setattr(
        factory,
        "PeriodProfitReturnSaleLineageEvidenceService",
        SaleLineageEvidence,
    )
    monkeypatch.setattr(
        factory,
        "PeriodProfitExternalExpenseEvidenceService",
        ExternalExpenseEvidence,
    )
    monkeypatch.setattr(factory, "PeriodProfitSummaryService", Summary)
    monkeypatch.setattr(factory, "PeriodProfitQueryService", Query)
    monkeypatch.setattr(factory, "TaxConfigurationService", TaxConfig)

    query = factory.create_period_profit_query()
    assert isinstance(query.summary_service.finance_service, Finance)
    assert isinstance(query.summary_service.cost_service, Costs)
    assert query.summary_service.tax_rate == 0.06
    assert query.product_provider() == [{"sku": "1"}]
    assert isinstance(query.return_evidence_service, ReturnEvidence)
    assert isinstance(query.return_evidence_service.ozon_client, Ozon)
    assert isinstance(query.return_cogs_recovery_evidence_service, ReturnCogsEvidence)
    assert query.return_cogs_recovery_evidence_service.cost_service is query.summary_service.cost_service
    assert isinstance(
        query.return_cogs_recovery_evidence_service.sale_lineage_evidence_service,
        SaleLineageEvidence,
    )
    assert (
        query.return_cogs_recovery_evidence_service.sale_lineage_evidence_service.finance_service
        is query.summary_service.finance_service
    )
    assert isinstance(
        query.return_cogs_recovery_evidence_service.inventory_recovery_repository,
        InventoryRecovery,
    )
    assert isinstance(query.external_expense_evidence_service, ExternalExpenseEvidence)
    assert isinstance(query.external_expense_evidence_service.repository, Expenses)
    assert query.authorized_return_mapping is None
    assert query.authorized_advertising_mapping is None
    assert query.authorized_storage_mapping is None
    assert query.mapping_observability_service is None
