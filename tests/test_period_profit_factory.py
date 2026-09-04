import period_profit_factory as factory


class Products:
    def load_products(self): return [{"sku": "1"}]


class Finance: pass
class Costs: pass
class Expenses: pass
class InventoryRecovery: pass
class AccountingAttribution: pass
class AccountingRecognition: pass
class ApplicationAuthorization: pass
class ApplicationCommit: pass
class Ozon: pass


class TaxConfig:
    def get_policy(self):
        return {
            "error": False,
            "configured": True,
            "policy": {"mode": "USN_INCOME", "tax_rate": 6.0, "minimum_tax_rate": 1.0},
        }


class ReturnEvidence:
    def __init__(self, ozon_client): self.ozon_client = ozon_client


class SaleLineageEvidence:
    def __init__(self, finance_service): self.finance_service = finance_service


class SaleQuantityEvidence:
    def __init__(self, ozon_client): self.ozon_client = ozon_client


class ReturnCogsEvidence:
    def __init__(self, cost_service, sale_lineage_evidence_service=None, inventory_recovery_repository=None):
        self.cost_service = cost_service
        self.sale_lineage_evidence_service = sale_lineage_evidence_service
        self.inventory_recovery_repository = inventory_recovery_repository


class ReturnCogsQuantityEvidence:
    def __init__(self, base_service, sale_quantity_evidence_service):
        self.base_service = base_service
        self.sale_quantity_evidence_service = sale_quantity_evidence_service


class ReturnCogsAccountingEvidence:
    def __init__(self, base_service, accounting_attribution_repository):
        self.base_service = base_service
        self.accounting_attribution_repository = accounting_attribution_repository


class ReturnCogsAccountingReadiness:
    def __init__(self, base_service): self.base_service = base_service


class ReturnCogsRecoveryAmountEvidence:
    def __init__(self, base_service): self.base_service = base_service


class ReturnCogsRecognitionEligibility:
    def __init__(self, base_service): self.base_service = base_service


class ReturnCogsAccountingRecognition:
    def __init__(self, base_service, accounting_recognition_repository):
        self.base_service = base_service
        self.accounting_recognition_repository = accounting_recognition_repository


class ReturnCogsApplicationEligibility:
    def __init__(self, base_service, application_authorization_repository):
        self.base_service = base_service
        self.application_authorization_repository = application_authorization_repository


class ReturnCogsApplicationCommitReadiness:
    def __init__(self, base_service, application_commit_repository):
        self.base_service = base_service
        self.application_commit_repository = application_commit_repository


class ExternalExpenseEvidence:
    def __init__(self, repository): self.repository = repository


class Summary:
    def __init__(self, finance_service, cost_service, tax_rate):
        self.finance_service = finance_service
        self.cost_service = cost_service
        self.tax_rate = tax_rate


class Query:
    def __init__(self, summary_service, product_provider, return_evidence_service=None,
                 authorized_return_mapping=None, authorized_advertising_mapping=None,
                 authorized_storage_mapping=None, mapping_observability_service=None,
                 return_cogs_recovery_evidence_service=None,
                 external_expense_evidence_service=None):
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
    monkeypatch.setattr(factory, "ReturnInventoryRecoveryRepository", InventoryRecovery)
    monkeypatch.setattr(factory, "ReturnCogsAccountingAttributionRepository", AccountingAttribution)
    monkeypatch.setattr(factory, "ReturnCogsAccountingRecognitionRepository", AccountingRecognition)
    monkeypatch.setattr(factory, "ReturnCogsProfitApplicationAuthorizationRepository", ApplicationAuthorization)
    monkeypatch.setattr(factory, "ReturnCogsProfitApplicationCommitRepository", ApplicationCommit)
    monkeypatch.setattr(factory, "OzonClient", Ozon)
    monkeypatch.setattr(factory, "PeriodProfitReturnEvidenceService", ReturnEvidence)
    monkeypatch.setattr(factory, "PeriodProfitReturnCogsRecoveryEvidenceService", ReturnCogsEvidence)
    monkeypatch.setattr(factory, "PeriodProfitReturnCogsQuantityEvidenceService", ReturnCogsQuantityEvidence)
    monkeypatch.setattr(factory, "PeriodProfitReturnCogsAccountingEvidenceService", ReturnCogsAccountingEvidence)
    monkeypatch.setattr(factory, "PeriodProfitReturnCogsAccountingReadinessService", ReturnCogsAccountingReadiness)
    monkeypatch.setattr(factory, "PeriodProfitReturnCogsRecoveryAmountEvidenceService", ReturnCogsRecoveryAmountEvidence)
    monkeypatch.setattr(factory, "PeriodProfitReturnCogsRecognitionEligibilityService", ReturnCogsRecognitionEligibility)
    monkeypatch.setattr(factory, "PeriodProfitReturnCogsAccountingRecognitionService", ReturnCogsAccountingRecognition)
    monkeypatch.setattr(factory, "PeriodProfitReturnCogsApplicationEligibilityService", ReturnCogsApplicationEligibility)
    monkeypatch.setattr(factory, "PeriodProfitReturnCogsApplicationCommitReadinessService", ReturnCogsApplicationCommitReadiness)
    monkeypatch.setattr(factory, "PeriodProfitReturnSaleLineageEvidenceService", SaleLineageEvidence)
    monkeypatch.setattr(factory, "PeriodProfitReturnSaleQuantityEvidenceService", SaleQuantityEvidence)
    monkeypatch.setattr(factory, "PeriodProfitExternalExpenseEvidenceService", ExternalExpenseEvidence)
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

    commit_readiness = query.return_cogs_recovery_evidence_service
    assert isinstance(commit_readiness, ReturnCogsApplicationCommitReadiness)
    assert isinstance(commit_readiness.application_commit_repository, ApplicationCommit)
    application = commit_readiness.base_service
    assert isinstance(application, ReturnCogsApplicationEligibility)
    assert isinstance(application.application_authorization_repository, ApplicationAuthorization)
    recognition = application.base_service
    assert isinstance(recognition, ReturnCogsAccountingRecognition)
    assert isinstance(recognition.accounting_recognition_repository, AccountingRecognition)
    eligibility = recognition.base_service
    assert isinstance(eligibility, ReturnCogsRecognitionEligibility)
    amount = eligibility.base_service
    assert isinstance(amount, ReturnCogsRecoveryAmountEvidence)
    readiness = amount.base_service
    assert isinstance(readiness, ReturnCogsAccountingReadiness)
    accounting = readiness.base_service
    assert isinstance(accounting, ReturnCogsAccountingEvidence)
    quantity_wrapper = accounting.base_service
    assert isinstance(quantity_wrapper, ReturnCogsQuantityEvidence)
    base = quantity_wrapper.base_service
    assert isinstance(base, ReturnCogsEvidence)
    assert base.cost_service is query.summary_service.cost_service
    assert isinstance(base.sale_lineage_evidence_service, SaleLineageEvidence)
    assert base.sale_lineage_evidence_service.finance_service is query.summary_service.finance_service
    assert isinstance(base.inventory_recovery_repository, InventoryRecovery)
    quantity = quantity_wrapper.sale_quantity_evidence_service
    assert isinstance(quantity, SaleQuantityEvidence)
    assert quantity.ozon_client is query.return_evidence_service.ozon_client
    assert isinstance(accounting.accounting_attribution_repository, AccountingAttribution)
    assert isinstance(query.external_expense_evidence_service, ExternalExpenseEvidence)
    assert isinstance(query.external_expense_evidence_service.repository, Expenses)
    assert query.authorized_return_mapping is None
    assert query.authorized_advertising_mapping is None
    assert query.authorized_storage_mapping is None
    assert query.mapping_observability_service is None
