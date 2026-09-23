from math import isfinite
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from api.ozon_performance_client import OzonPerformanceClient
from services.ozon_performance_account_repository import OzonPerformanceAccountRepository
from services.tenant_context import get_current_tenant_user_id


class PeriodProfitSkuAdvertisingService:
    """Exact CPC advertising expense from a single batched Performance call."""

    def __init__(self, repository=None, client_factory=None):
        self.repository = repository or OzonPerformanceAccountRepository()
        self.client_factory = client_factory or OzonPerformanceClient
        self._clients = {}

    def load(self, date_from, date_to, accepted_skus):
        tenant = get_current_tenant_user_id()
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
        # The live SKU endpoint only supports yesterday onward. Historical
        # periods must use the asynchronous SKU-level campaign reports.
        from api.ozon_performance_historical_reports import HistoricalPerformanceReports
        try:
            historical = date.fromisoformat(date_from) < date.today() - timedelta(days=1)
        except ValueError:
            return {"error": True, "code": "OZON_PERFORMANCE_PERIOD_INVALID"}
        result = (HistoricalPerformanceReports(client).load(date_from, date_to)
                  if historical else client.get_sku_expenses(date_from, date_to))
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
        total = Decimal("0")
        campaigns = set()
        matched = 0
        for row in rows:
            if not isinstance(row, dict):
                return {"error": True, "code": "PERIOD_PROFIT_SKU_ADVERTISING_INVALID"}
            sku = str(row.get("sku") or "").strip()
            if sku not in targets:
                continue
            try:
                expense = Decimal(str(row.get("expense")))
            except (TypeError, ValueError, InvalidOperation):
                return {"error": True, "code": "PERIOD_PROFIT_SKU_ADVERTISING_INVALID"}
            if not isfinite(expense) or expense < 0:
                return {"error": True, "code": "PERIOD_PROFIT_SKU_ADVERTISING_INVALID"}
            total += expense
            if not total.is_finite():
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
            "scope": ("OZON_PERFORMANCE_CPC_AND_CPO_SKU" if historical
                      else "OZON_PERFORMANCE_CPC_SKU"),
            "expense": round(float(total), 2),
            "matched_row_count": matched,
            "campaign_count": len(campaigns),
            "external_call_count": result.get("external_call_count", 1),
        }
