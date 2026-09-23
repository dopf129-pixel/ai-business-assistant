from math import isfinite

from api.ozon_performance_client import OzonPerformanceClient
from services.ozon_performance_account_repository import OzonPerformanceAccountRepository
from services.ozon_promotion_history_repository import PromotionHistoryRepository
from services.tenant_context import get_current_tenant_user_id


class PeriodProfitSkuAdvertisingService:
    """Exact CPC advertising expense from a single batched Performance call."""

    def __init__(self, repository=None, client_factory=None, history_repository=None):
        self.repository = repository or OzonPerformanceAccountRepository()
        self.client_factory = client_factory or OzonPerformanceClient
        self._clients = {}
        self.history_repository = history_repository or PromotionHistoryRepository()

    def load(self, date_from, date_to, accepted_skus):
        tenant = get_current_tenant_user_id()
        imported = self.history_repository.load_exact(
            tenant, date_from, date_to, accepted_skus
        )
        if imported is not None:
            return imported
        credentials = self.repository.get_performance(tenant)
        if not credentials:
            return {
                "error": False,
                "status": "PERIOD_PROFIT_SKU_ADVERTISING_NOT_CONFIGURED",
                "configured": False,
                "complete": False,
            }
        key = (tenant, credentials["client_id"])
        client = self._clients.get(key)
        if client is None:
            client = self.client_factory(credentials["client_id"], credentials["client_secret"])
            self._clients[key] = client
        result = client.get_sku_expenses(date_from, date_to)
        if (isinstance(result, dict) and result.get("code") in {
                "OZON_PERFORMANCE_HISTORICAL_SKU_UNAVAILABLE",
                "OZON_PERFORMANCE_HTTP_400",
        }):
            # Only use manually imported evidence for the exact same date range.
            # Missing reports must retain the original fail-closed error.
            historical = self.history_repository.load_exact(
                tenant, date_from, date_to, accepted_skus
            )
            if historical is not None:
                return historical
        if not isinstance(result, dict) or result.get("error") is True:
            return {
                "error": True,
                "code": (result.get("code") if isinstance(result, dict) else None)
                or "PERIOD_PROFIT_SKU_ADVERTISING_UNAVAILABLE",
                **({key: result[key] for key in (
                    "failed_window_from", "failed_window_to", "status_code"
                ) if key in result} if isinstance(result, dict) else {}),
            }
        rows = result.get("rows")
        if not isinstance(rows, list):
            return {"error": True, "code": "PERIOD_PROFIT_SKU_ADVERTISING_INVALID"}
        targets = {str(value or "").strip() for value in accepted_skus if str(value or "").strip()}
        total = 0.0
        campaigns = set()
        matched = 0
        for row in rows:
            if not isinstance(row, dict):
                return {"error": True, "code": "PERIOD_PROFIT_SKU_ADVERTISING_INVALID"}
            sku = str(row.get("sku") or "").strip()
            if sku not in targets:
                continue
            try:
                expense = float(row.get("expense"))
            except (TypeError, ValueError, OverflowError):
                return {"error": True, "code": "PERIOD_PROFIT_SKU_ADVERTISING_INVALID"}
            if not isfinite(expense) or expense < 0:
                return {"error": True, "code": "PERIOD_PROFIT_SKU_ADVERTISING_INVALID"}
            total += expense
            if not isfinite(total):
                return {"error": True, "code": "PERIOD_PROFIT_SKU_ADVERTISING_INVALID"}
            matched += 1
            campaign = str(row.get("campaignId") or "").strip()
            if campaign:
                campaigns.add(campaign)
        return {
            "error": False,
            "status": "PERIOD_PROFIT_SKU_ADVERTISING_READY",
            "configured": True,
            "complete": True,
            "scope": "OZON_PERFORMANCE_CPC_SKU",
            "expense": round(total, 2),
            "matched_row_count": matched,
            "campaign_count": len(campaigns),
            "external_call_count": result.get("external_call_count", 1),
        }
