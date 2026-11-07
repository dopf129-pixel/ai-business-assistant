"""Resolve exact-SKU FIFO allocations for the canonical Period Profit pipeline."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from services.fifo_cost_repository import FifoCostRepository
from datetime import date

from services.fifo_cost_sale_evidence_normalizer import (
    FifoCostSaleEvidenceNormalizer,
)
from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id


class FifoCostPeriodProfitSourceService:
    """Bridge immutable FIFO allocations to confirmed Period Profit sale identities.

    The active FIFO stream is an explicit per-SKU cutover. Once active, any
    missing, stale or mismatched allocation is an error; this service never
    falls back to the current unit rate.
    """

    _CONFIRMED_CATALOG_SKU_SOURCES = frozenset({
        "OZON_FINANCE_POSTING_TO_CURRENT_CATALOG_SKU",
        "OZON_FINANCE_POSTING_TO_CURRENT_CATALOG_OFFER_ID",
        "OZON_RELATED_SKU_TO_CURRENT_CATALOG",
        "OZON_RELATED_SKU_TO_SELLER_COST_IDENTITY",
        "OZON_FINANCE_UNIT_TO_FBO_POSTING_OFFER_ID",
        "OZON_REALIZATION_POSTING_TO_CURRENT_CATALOG_OFFER_ID",
        "OZON_FBO_SNAPSHOT_TO_CURRENT_CATALOG_OFFER_ID",
        "OZON_FBO_POSTING_OFFER_ID",
        "SELLER_CONFIRMED_PRODUCT_IDENTITY_MAPPING",
    })

    def __init__(self, repository: FifoCostRepository | None = None, tenant_scope_provider=None):
        self.repository = repository or FifoCostRepository()
        self.tenant_scope_provider = tenant_scope_provider or get_current_tenant_user_id
        self.normalizer = FifoCostSaleEvidenceNormalizer()

    def get_scope_mode(self, product, *, date_from=None, date_to=None):
        scope = self._identity_and_store(product)
        if scope.get("error") is True:
            return scope
        result = self.repository.read_cost_mode_status(
            store_id=scope["store_id"],
            product_id=scope["product_id"],
            offer_id=scope["offer_id"],
            sku=scope["sku"],
        )
        if not isinstance(result, dict) or result.get("error") is not False:
            return self._error("FIFO_COST_MODE_UNAVAILABLE")
        if result.get("active") is not True:
            return {"error": False, "active": False, "code": result.get("code")}
        cutoff_date = result.get("cutoff_date")
        start = self._date_text(date_from)
        end = self._date_text(date_to)
        if cutoff_date and start and end:
            if end <= cutoff_date:
                return {
                    "error": False, "active": False,
                    "code": "FIFO_COST_MODE_PRE_CUTOFF",
                    "cutoff_date": cutoff_date,
                }
            if start <= cutoff_date:
                return {
                    "error": False, "active": True,
                    "period_cutover_overlap": True,
                    "code": "FIFO_PERIOD_SPANS_COST_CUTOFF",
                    "cutoff_date": cutoff_date,
                    **scope,
                }
        return {
            "error": False,
            "active": True,
            "code": result.get("code"),
            "stream_state": result.get("stream_state"),
            "stream_revision": result.get("stream_revision"),
            **scope,
        }

    @staticmethod
    def _date_text(value):
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        if not isinstance(value, str):
            return None
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return None
        return parsed.isoformat() if parsed.isoformat() == value else None

    def reconcile_period_sales(
        self, *, product, finance_sku, date_from, date_to, sales,
    ):
        scope = self._identity_and_store(product)
        if scope.get("error") is True:
            return scope
        mode = self.repository.read_cost_mode_status(
            store_id=scope["store_id"],
            product_id=scope["product_id"],
            offer_id=scope["offer_id"],
            sku=scope["sku"],
        )
        if not isinstance(mode, dict) or mode.get("error") is not False:
            return self._error("FIFO_COST_MODE_UNAVAILABLE")
        if mode.get("active") is not True:
            return {"error": False, "active": False}
        cutoff = mode.get("cutoff_date")
        start = self._date_text(date_from)
        end = self._date_text(date_to)
        if cutoff and start and end:
            if end <= cutoff:
                return {"error": False, "active": False, "code": "FIFO_COST_MODE_PRE_CUTOFF"}
            if start <= cutoff:
                return {
                    "error": False, "active": True, "complete": False,
                    "reason_code": "FIFO_PERIOD_SPANS_COST_CUTOFF",
                }
        result = self.repository.read_period_allocation_summary(
            store_id=scope["store_id"],
            product_id=scope["product_id"],
            offer_id=scope["offer_id"],
            sku=scope["sku"],
            date_from=date_from,
            date_to=date_to,
        )
        if not isinstance(result, dict) or result.get("error") is not False:
            return self._error("FIFO_COST_PERIOD_UNAVAILABLE")
        if result.get("active") is not True:
            return {"error": False, "active": False}
        if result.get("complete") is not True:
            return {
                "error": False, "active": True, "complete": False,
                "reason_code": result.get("reason_code") or "FIFO_ALLOCATION_INCOMPLETE",
            }

        mapping_confirmed = bool(
            product.get("seller_confirmed_identity_mapping") is True
            or (
                self._text(product.get("sku")) == self._text(finance_sku)
                and (scope["offer_id"] or scope["product_id"])
            )
        )
        identity = {
            "mapping_confirmed": mapping_confirmed,
            "offer_id": scope["offer_id"],
            "product_id": scope["product_id"],
        }
        expected = {}
        for sale in sales or ():
            if not isinstance(sale, dict):
                return self._incomplete("FIFO_FINANCE_SALE_IDENTITY_INVALID")
            quantity = sale.get("quantity")
            if type(quantity) is not int or quantity <= 0:
                return self._incomplete("FIFO_FINANCE_SALE_QUANTITY_INVALID")
            digest = self.normalizer.build_identity_digest(
                store_id=scope["store_id"],
                posting_number=sale.get("posting_number"),
                finance_sku=finance_sku,
                identity=identity,
            )
            if digest.get("error") is True:
                return self._incomplete(digest.get("code"))
            key = digest["source_identity_digest"]
            if key in expected:
                return self._incomplete("FIFO_FINANCE_SALE_IDENTITY_DUPLICATE")
            expected[key] = quantity

        actual = {}
        total_cogs = Decimal("0.00")
        total_units = 0
        allocations = result.get("allocations")
        if not isinstance(allocations, list):
            return self._incomplete("FIFO_ALLOCATION_RESPONSE_INVALID")
        try:
            for allocation in allocations:
                if not isinstance(allocation, dict):
                    return self._incomplete("FIFO_ALLOCATION_RESPONSE_INVALID")
                digest = allocation.get("source_identity_digest")
                quantity = allocation.get("quantity")
                amount = Decimal(str(allocation.get("total_cogs_rub")))
                if (
                    not self._digest(digest)
                    or type(quantity) is not int or quantity <= 0
                    or not amount.is_finite() or amount < 0
                    or amount.quantize(Decimal("0.01")) != amount
                    or digest in actual
                ):
                    return self._incomplete("FIFO_ALLOCATION_RESPONSE_INVALID")
                actual[digest] = quantity
                total_units += quantity
                total_cogs += amount
        except (InvalidOperation, TypeError, ValueError, OverflowError):
            return self._incomplete("FIFO_ALLOCATION_RESPONSE_INVALID")

        if expected != actual:
            return self._incomplete("FIFO_ALLOCATION_SALE_COVERAGE_MISMATCH")
        response = {
            "error": False,
            "active": True,
            "complete": True,
            "source": "FIFO_ALLOCATION_REVISION",
            "stream_revision": result.get("stream_revision"),
            "allocation_revision": result.get("allocation_revision"),
            "cutoff_date": result.get("cutoff_date"),
            "units_sold": total_units,
            "product_cost": format(total_cogs.quantize(Decimal("0.01")), ".2f"),
        }
        if isinstance(result.get("layers"), list):
            from services.fifo_cost_period_explanation_service import (
                FifoCostPeriodExplanationService,
            )

            response["fifo_cost_explanation"] = (
                FifoCostPeriodExplanationService().build(
                    allocation_result=result,
                    repository=self.repository,
                    store_id=scope["store_id"],
                    product=product,
                    sku=scope["sku"],
                    date_from=date_from,
                    date_to=date_to,
                    units=total_units,
                    product_cost=total_cogs,
                )
            )
        return response

    def _identity_and_store(self, product):
        if not isinstance(product, dict):
            return self._error("FIFO_COST_PRODUCT_IDENTITY_INVALID")
        scope_text = self.tenant_scope_provider()
        _owner_id, store_id = split_store_tenant_scope(scope_text)
        if not store_id:
            return self._error("FIFO_ACTIVE_STORE_SCOPE_UNAVAILABLE")
        product_id = self._text(product.get("product_id"))
        offer_id = self._text(product.get("offer_id"))
        sku = self._text(product.get("sku"))
        if not sku or not product_id and not offer_id:
            return self._error("FIFO_COST_PRODUCT_IDENTITY_INVALID")
        catalog_sku = self._text(product.get("catalog_sku"))
        if catalog_sku and catalog_sku != sku:
            source = self._text(product.get("historical_sku_identity_source"))
            if (
                product.get("historical_sku_identity_recovered") is not True
                or source not in self._CONFIRMED_CATALOG_SKU_SOURCES
            ):
                return self._error("FIFO_COST_PRODUCT_IDENTITY_INVALID")
            # Finance SKU remains the sale/digest identity. The exact current
            # catalog SKU selects the separately anchored FIFO cost stream only
            # after an allowlisted identity-recovery service proved the mapping.
            sku = catalog_sku
        return {
            "error": False, "store_id": store_id,
            "product_id": product_id, "offer_id": offer_id, "sku": sku,
        }

    @staticmethod
    def _text(value):
        if value is None or isinstance(value, bool):
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _digest(value):
        return (
            isinstance(value, str) and len(value) == 64
            and all(char in "0123456789abcdef" for char in value)
        )

    @staticmethod
    def _incomplete(reason):
        return {
            "error": False, "active": True, "complete": False,
            "reason_code": str(reason or "FIFO_COST_SCOPE_INCOMPLETE"),
        }

    @staticmethod
    def _error(code):
        return {"error": True, "code": str(code)}
