"""Resolve exact-SKU FIFO allocations for the canonical Period Profit pipeline."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from services.fifo_cost_repository import FifoCostRepository
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

    def __init__(self, repository: FifoCostRepository | None = None, tenant_scope_provider=None):
        self.repository = repository or FifoCostRepository()
        self.tenant_scope_provider = tenant_scope_provider or get_current_tenant_user_id
        self.normalizer = FifoCostSaleEvidenceNormalizer()

    def get_scope_mode(self, product):
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
        return {
            "error": False,
            "active": True,
            "code": result.get("code"),
            "stream_state": result.get("stream_state"),
            "stream_revision": result.get("stream_revision"),
            **scope,
        }

    def reconcile_period_sales(
        self, *, product, finance_sku, date_from, date_to, sales,
    ):
        scope = self._identity_and_store(product)
        if scope.get("error") is True:
            return scope
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
        return {
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
