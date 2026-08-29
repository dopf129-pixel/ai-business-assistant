from api.ozon_client import OzonClient
from config import TAX_RATE
from services.cost_service import ProductCostService
from services.finance_service import FinanceService
from services.period_profit_query_service import PeriodProfitQueryService
from services.period_profit_return_evidence_service import PeriodProfitReturnEvidenceService
from services.period_profit_summary_service import PeriodProfitSummaryService
from services.product_service import ProductService


def create_period_profit_query():
    product_service = ProductService()
    summary_service = PeriodProfitSummaryService(
        finance_service=FinanceService(),
        cost_service=ProductCostService(),
        tax_rate=TAX_RATE,
    )
    return PeriodProfitQueryService(
        summary_service=summary_service,
        product_provider=product_service.load_products,
        return_evidence_service=PeriodProfitReturnEvidenceService(OzonClient()),
    )
