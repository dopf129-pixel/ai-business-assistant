from services.period_profit_finance_posting_identity_scope_service import (
    PeriodProfitFinancePostingIdentityScopeService,
)
from services.period_profit_finance_sku_scope_service import (
    PeriodProfitFinanceSkuScopeService,
)
from services.seller_confirmed_product_identity_repository import (
    SellerConfirmedProductIdentityRepository,
)


class PeriodProfitSellerConfirmedIdentityScopeService(
    PeriodProfitFinancePostingIdentityScopeService
):
    """Apply explicit seller-confirmed legacy SKU aliases before weaker fallbacks.

    A confirmed alias proves product identity only. It never supplies or mutates a
    historical cost. The downstream effective-cost service still has to prove the
    monetary value for every sale date.
    """

    def __init__(
        self,
        summary_service,
        finance_service,
        sku_ozon_client=None,
        identity_mapping_repository=None,
    ):
        super().__init__(
            summary_service,
            finance_service,
            sku_ozon_client=sku_ozon_client,
        )
        self.identity_mapping_repository = (
            identity_mapping_repository
            or SellerConfirmedProductIdentityRepository(self.cost_service)
        )

    def _recover_missing_product(self, sku, at_date):
        direct = PeriodProfitFinanceSkuScopeService._recover_missing_product(
            self,
            sku,
            at_date,
        )
        if direct is not None:
            result = dict(direct)
            result["historical_sku_identity_recovered"] = True
            result["historical_sku_identity_source"] = (
                "SELLER_CONFIRMED_HISTORICAL_COST_IDENTITY"
                if result.get("historical_cost_evidence") is True
                else "SELLER_CURRENT_COST_EXACT_SKU_IDENTITY"
            )
            return result

        mapping_status, mapped = self._recover_from_seller_confirmed_mapping(sku)
        if mapping_status == "READY":
            return mapped
        if mapping_status != "MISSING":
            return None

        # No explicit seller alias exists, so retain the current READ-ONLY Ozon
        # related-SKU / finance-posting recovery chain and all of its fail-closed gates.
        return super()._recover_missing_product(sku, at_date)

    def _recover_from_seller_confirmed_mapping(self, sku):
        finance_sku = self._text(sku)
        if not finance_sku:
            self._record_sku_recovery_diagnostic("SELLER_MAPPING_INPUT_INVALID")
            return "BLOCKED", None

        getter = getattr(self.identity_mapping_repository, "get_mapping", None)
        if not callable(getter):
            self._record_sku_recovery_diagnostic("SELLER_MAPPING_UNAVAILABLE")
            return "BLOCKED", None

        try:
            mapping = getter(finance_sku)
        except Exception:
            self._record_sku_recovery_diagnostic("SELLER_MAPPING_EXCEPTION")
            return "BLOCKED", None

        if not isinstance(mapping, dict):
            self._record_sku_recovery_diagnostic("SELLER_MAPPING_RESPONSE_INVALID")
            return "BLOCKED", None
        if mapping.get("error") is True:
            self._record_sku_recovery_diagnostic("SELLER_MAPPING_STORAGE_ERROR")
            return "BLOCKED", None
        if mapping.get("status") == "SELLER_PRODUCT_IDENTITY_MAPPING_MISSING":
            return "MISSING", None
        if (
            mapping.get("status") != "SELLER_PRODUCT_IDENTITY_MAPPING_READY"
            or mapping.get("mapping_confirmed") is not True
            or mapping.get("seller_confirmed") is not True
        ):
            self._record_sku_recovery_diagnostic("SELLER_MAPPING_INVALID")
            return "BLOCKED", None

        mapped_finance_sku = self._text(mapping.get("finance_sku"))
        product_id = self._text(mapping.get("current_product_id"))
        catalog_sku = self._text(mapping.get("current_sku"))
        offer_id = self._text(mapping.get("current_offer_id"))
        if (
            mapped_finance_sku != finance_sku
            or not product_id
            or not catalog_sku
            or catalog_sku == finance_sku
        ):
            self._record_sku_recovery_diagnostic("SELLER_MAPPING_ROW_INVALID")
            return "BLOCKED", None

        candidate = self._catalog_by_sku.get(catalog_sku)
        if not isinstance(candidate, dict):
            self._record_sku_recovery_diagnostic("SELLER_MAPPING_CATALOG_MISSING")
            return "BLOCKED", None

        candidate_product_id = self._text(candidate.get("product_id"))
        candidate_offer_id = self._text(candidate.get("offer_id"))
        if candidate_product_id != product_id:
            self._record_sku_recovery_diagnostic("SELLER_MAPPING_PRODUCT_CONFLICT")
            return "BLOCKED", None
        if offer_id and candidate_offer_id and candidate_offer_id != offer_id:
            self._record_sku_recovery_diagnostic("SELLER_MAPPING_OFFER_CONFLICT")
            return "BLOCKED", None

        result = dict(candidate)
        result["product_id"] = product_id
        result["offer_id"] = offer_id or candidate_offer_id or catalog_sku
        result["catalog_sku"] = catalog_sku
        result["sku"] = finance_sku
        result["historical_sku_identity_recovered"] = True
        result["historical_sku_identity_source"] = (
            "SELLER_CONFIRMED_PRODUCT_IDENTITY_MAPPING"
        )
        result["seller_confirmed_identity_mapping"] = True
        return "READY", result
