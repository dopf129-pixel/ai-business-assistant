from api.ozon_client import OzonClient
from config import TAX_RATE
from period_profit_mapping_registry_factory import (
    load_active_period_profit_mappings,
)
from services.cost_service import ProductCostService
from services.finance_service import FinanceService
from services.period_profit_mapping_observability_service import (
    PeriodProfitMappingObservabilityService,
)
from services.period_profit_query_service import PeriodProfitQueryService
from services.period_profit_return_evidence_service import PeriodProfitReturnEvidenceService
from services.period_profit_summary_service import PeriodProfitSummaryService
from services.product_service import ProductService


def create_period_profit_query(mapping_registry=None):
    product_service = ProductService()
    summary_service = PeriodProfitSummaryService(
        finance_service=FinanceService(),
        cost_service=ProductCostService(),
        tax_rate=TAX_RATE,
    )
    mappings = load_active_period_profit_mappings(mapping_registry)
    observability = (
        PeriodProfitMappingObservabilityService(mapping_registry)
        if mapping_registry is not None
        else None
    )
    return PeriodProfitQueryService(
        summary_service=summary_service,
        product_provider=product_service.load_products,
        return_evidence_service=PeriodProfitReturnEvidenceService(OzonClient()),
        authorized_return_mapping=mappings.get("RETURN"),
        authorized_advertising_mapping=mappings.get("ADVERTISING"),
        authorized_storage_mapping=mappings.get("STORAGE"),
        mapping_observability_service=observability,
    )
