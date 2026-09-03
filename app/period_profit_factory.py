from math import isfinite

from api.ozon_client import OzonClient
from period_profit_mapping_registry_factory import (
    load_active_period_profit_mappings,
)
from services.cost_service import ProductCostService
from services.expense_repository import ExpenseRepository
from services.finance_service import FinanceService
from services.period_profit_mapping_observability_service import (
    PeriodProfitMappingObservabilityService,
)
from services.period_profit_external_expense_evidence_service import (
    PeriodProfitExternalExpenseEvidenceService,
)
from services.period_profit_query_service import PeriodProfitQueryService
from services.period_profit_return_evidence_service import PeriodProfitReturnEvidenceService
from services.period_profit_return_cogs_recovery_evidence_service import (
    PeriodProfitReturnCogsRecoveryEvidenceService,
)
from services.period_profit_return_sale_lineage_evidence_service import (
    PeriodProfitReturnSaleLineageEvidenceService,
)
from services.period_profit_summary_service import PeriodProfitSummaryService
from services.product_service import ProductService
from services.tax_configuration_service import TaxConfigurationService


def create_period_profit_query(mapping_registry=None):
    product_service = ProductService()
    tax_policy = (
        TaxConfigurationService()
        .get_policy()
    )
    cost_service = ProductCostService()
    expense_repository = ExpenseRepository()
    finance_service = FinanceService()
    summary_service = PeriodProfitSummaryService(
        finance_service=finance_service,
        cost_service=cost_service,
        tax_rate=_period_profit_tax_fraction(
            tax_policy
        ),
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
        return_cogs_recovery_evidence_service=(
            PeriodProfitReturnCogsRecoveryEvidenceService(
                cost_service,
                PeriodProfitReturnSaleLineageEvidenceService(
                    finance_service
                ),
            )
        ),
        external_expense_evidence_service=(
            PeriodProfitExternalExpenseEvidenceService(
                expense_repository
            )
        ),
        authorized_return_mapping=mappings.get("RETURN"),
        authorized_advertising_mapping=mappings.get("ADVERTISING"),
        authorized_storage_mapping=mappings.get("STORAGE"),
        mapping_observability_service=observability,
    )



def _period_profit_tax_fraction(policy_result):
    if not isinstance(policy_result, dict):
        return None

    if (
        policy_result.get("error") is not False
        or policy_result.get("configured") is not True
    ):
        return None

    policy = policy_result.get("policy")
    if not isinstance(policy, dict):
        return None

    mode = str(
        policy.get("mode") or ""
    ).upper()

    if mode == "NONE":
        return 0.0

    if mode != "USN_INCOME":
        return None

    rate = policy.get("tax_rate")
    if isinstance(rate, bool):
        return None

    try:
        rate = float(rate)
    except (TypeError, ValueError):
        return None

    if (
        not isfinite(rate)
        or rate < 0.0
        or rate > 100.0
    ):
        return None

    return rate / 100.0
