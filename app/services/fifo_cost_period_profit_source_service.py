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
        "CONFIRMED_HISTORICAL_COST_IDENTITY_TO_CURRENT_CATALOG",
        "CONFIRMED_CURRENT_COST_IDENTITY_TO_CURRENT_CATALOG",
    })

    def __init__(self, repository: FifoCostRepository | None = None, tenant_scope_provider=None):
        self.repository = repository or FifoCostRepository()
        self.tenant_scope_provider = tenant_scope_provider or get_current_tenant_user_id
        self.normalizer = FifoCostSaleEvidenceNormalizer()

    def resolve_scope_identity(self, product):
        """Resolve the validated exact stream key without reading repository state."""
        return self._identity_and_store(product)

    def build_sale_identity_digest(self, product, sale):
        """Build the stable internal join key used by the cutoff partition."""
        scope = self._identity_and_store(product)
        if scope.get("error") is True or not isinstance(sale, dict):
            return self._error("FIFO_FINANCE_SALE_IDENTITY_INVALID")
        finance_sku = self._text(sale.get("sku")) or self._text(product.get("sku"))
        if finance_sku is None:
            return self._error("FIFO_FINANCE_SALE_IDENTITY_INVALID")
        mapping_confirmed = bool(
            product.get("seller_confirmed_identity_mapping") is True
            or (
                self._text(product.get("sku")) == finance_sku
                and (scope["offer_id"] or scope["product_id"])
            )
        )
        return self.normalizer.build_identity_digest(
            store_id=scope["store_id"],
            posting_number=sale.get("posting_number"),
            finance_sku=finance_sku,
            identity={
                "mapping_confirmed": mapping_confirmed,
                "offer_id": scope["offer_id"],
                "product_id": scope["product_id"],
            },
        )

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
        if (
            isinstance(result, dict)
            and result.get("error") is True
            and result.get("code") == "FIFO_IDENTITY_CONFLICT"
        ):
            return self._error("FIFO_IDENTITY_CONFLICT")
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
        finance_sku_alias_products=None,
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
        if (
            isinstance(mode, dict)
            and mode.get("error") is True
            and mode.get("code") == "FIFO_IDENTITY_CONFLICT"
        ):
            return self._error("FIFO_IDENTITY_CONFLICT")
        if not isinstance(mode, dict) or mode.get("error") is not False:
            return self._error("FIFO_COST_MODE_UNAVAILABLE")
        if mode.get("active") is not True:
            return {"error": False, "active": False}
        cutoff = mode.get("cutoff_date")
        start = self._date_text(date_from)
        end = self._date_text(date_to)
        cutoff = self._date_text(cutoff)
        if cutoff is None or start is None or end is None or start > end:
            return self._incomplete("FIFO_CUTOFF_DATE_UNAVAILABLE")

        alias_products = (
            [product] if finance_sku_alias_products is None
            else finance_sku_alias_products
        )
        if not isinstance(alias_products, (list, tuple)) or not alias_products:
            return self._incomplete("FIFO_FINANCE_SALE_IDENTITY_INVALID")
        products_by_sku = {}
        for alias_product in alias_products:
            alias_scope = self._identity_and_store(alias_product)
            alias_sku = (
                self._text(alias_product.get("sku"))
                if isinstance(alias_product, dict) else None
            )
            if (
                alias_scope.get("error") is True
                or alias_scope != scope
                or alias_sku is None
                or alias_sku in products_by_sku
            ):
                return self._incomplete("FIFO_FINANCE_SALE_IDENTITY_INVALID")
            products_by_sku[alias_sku] = alias_product
        selected_finance_sku = self._text(finance_sku)
        if selected_finance_sku not in products_by_sku:
            return self._incomplete("FIFO_FINANCE_SALE_IDENTITY_INVALID")

        expected = {}
        expected_sku = {}
        for sale in sales or ():
            if not isinstance(sale, dict):
                return self._incomplete("FIFO_FINANCE_SALE_IDENTITY_INVALID")
            quantity = sale.get("quantity")
            if type(quantity) is not int or quantity <= 0:
                return self._incomplete("FIFO_FINANCE_SALE_QUANTITY_INVALID")
            sale_sku = self._text(sale.get("sku"))
            if sale_sku is None:
                if len(products_by_sku) != 1:
                    return self._incomplete("FIFO_FINANCE_SALE_IDENTITY_INVALID")
                sale_sku = next(iter(products_by_sku))
            alias_product = products_by_sku.get(sale_sku)
            if alias_product is None:
                return self._incomplete("FIFO_FINANCE_SALE_IDENTITY_INVALID")
            mapping_confirmed = bool(
                alias_product.get("seller_confirmed_identity_mapping") is True
                or (
                    self._text(alias_product.get("sku")) == sale_sku
                    and (scope["offer_id"] or scope["product_id"])
                )
            )
            identity = {
                "mapping_confirmed": mapping_confirmed,
                "offer_id": scope["offer_id"],
                "product_id": scope["product_id"],
            }
            digest = self.normalizer.build_identity_digest(
                store_id=scope["store_id"],
                posting_number=sale.get("posting_number"),
                finance_sku=sale_sku,
                identity=identity,
            )
            if digest.get("error") is True:
                return self._incomplete(digest.get("code"))
            key = digest["source_identity_digest"]
            if key in expected:
                return self._incomplete("FIFO_FINANCE_SALE_IDENTITY_DUPLICATE")
            expected[key] = quantity
            expected_sku[key] = sale_sku

        try:
            result = self.repository.read_period_allocation_summary(
                store_id=scope["store_id"],
                product_id=scope["product_id"],
                offer_id=scope["offer_id"],
                sku=scope["sku"],
                date_from=date_from,
                date_to=date_to,
                source_identity_digests=tuple(expected),
                require_identity_coverage=False,
            )
        except TypeError:
            # Compatibility implementations without the exact identity selector
            # may still support an all-post-cutoff period through the old complete
            # period API. Mixed/pre-cutoff selection fails below without mapping.
            result = self.repository.read_period_allocation_summary(
                store_id=scope["store_id"],
                product_id=scope["product_id"],
                offer_id=scope["offer_id"],
                sku=scope["sku"], date_from=date_from, date_to=date_to,
            )
        except Exception:
            result = None
        if not isinstance(result, dict) or result.get("error") is not False:
            return self._error("FIFO_COST_PERIOD_UNAVAILABLE")
        if result.get("active") is not True:
            return {"error": False, "active": False}
        if result.get("complete") is not True:
            return self._incomplete(
                result.get("reason_code") or "FIFO_ALLOCATION_INCOMPLETE",
            )
        if result.get("cutoff_date") != cutoff:
            return self._incomplete("FIFO_CUTOFF_SALE_MAPPING_STALE")

        actual = {}
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
                physical_date = self._date_text(allocation.get("effective_date"))
                if physical_date is None:
                    return self._incomplete("FIFO_ALLOCATION_RESPONSE_INVALID")
                actual[digest] = {
                    "quantity": quantity, "total_cogs": amount,
                    "effective_date": physical_date,
                }
        except (InvalidOperation, TypeError, ValueError, OverflowError):
            return self._incomplete("FIFO_ALLOCATION_RESPONSE_INVALID")

        if set(actual) - set(expected) or any(
            expected[digest] != actual[digest]["quantity"]
            for digest in actual
        ):
            return self._incomplete("FIFO_ALLOCATION_SALE_COVERAGE_MISMATCH")

        mapping_reader = getattr(self.repository, "read_cutoff_sale_mapping_set", None)
        try:
            mapping_result = mapping_reader(
                store_id=scope["store_id"],
                product_id=scope["product_id"],
                offer_id=scope["offer_id"], sku=scope["sku"],
            ) if callable(mapping_reader) else None
        except Exception:
            mapping_result = None
        mappings = {}
        mapping_complete_through = None
        mapping_complete = (
            isinstance(mapping_result, dict)
            and mapping_result.get("error") is False
            and mapping_result.get("active") is True
            and mapping_result.get("complete") is True
            and mapping_result.get("cutoff_date") == cutoff
            and type(mapping_result.get("mapping_revision")) is int
            and mapping_result.get("mapping_revision") >= 1
            and self._date_text(mapping_result.get("complete_through")) is not None
            and self._date_text(mapping_result.get("complete_through")) >= cutoff
            and isinstance(mapping_result.get("mappings"), list)
            and self._digest(mapping_result.get("bridge_fingerprint"))
        )
        if mapping_complete:
            mapping_complete_through = self._date_text(
                mapping_result.get("complete_through"),
            )
            for mapping in mapping_result["mappings"]:
                if not isinstance(mapping, dict):
                    return self._incomplete("FIFO_CUTOFF_SALE_MAPPING_INVALID")
                digest = mapping.get("source_identity_digest")
                quantity = mapping.get("quantity")
                physical_date = self._date_text(mapping.get("physical_effective_date"))
                partition = mapping.get("partition")
                if (
                    not self._digest(digest) or digest in mappings
                    or type(quantity) is not int or quantity < 1
                    or physical_date is None
                    or partition not in {"PRE_CUTOFF", "POST_CUTOFF"}
                    or (partition == "PRE_CUTOFF" and physical_date > cutoff)
                    or (partition == "POST_CUTOFF" and physical_date <= cutoff)
                ):
                    return self._incomplete("FIFO_CUTOFF_SALE_MAPPING_INVALID")
                mappings[digest] = {
                    "quantity": quantity,
                    "physical_effective_date": physical_date,
                    "partition": partition,
                }

        # A financial period that reaches the physical cutoff can contain sales
        # whose financial recognition date differs from the physical movement
        # date. Never infer that partition from allocation dates when the bridge
        # evidence is absent or incomplete.
        if expected and start <= cutoff and not mapping_complete:
            return self._incomplete("FIFO_CUTOFF_SALE_MAPPING_UNAVAILABLE")

        selected_alias_digests = {
            digest for digest, sale_sku in expected_sku.items()
            if sale_sku == selected_finance_sku
        }
        pre_cutoff_digests = set()
        post_cutoff_digests = set()
        legacy_sales = []
        for digest, quantity in expected.items():
            allocation = actual.get(digest)
            mapping = mappings.get(digest)
            if mapping is not None:
                if mapping["quantity"] != quantity:
                    return self._incomplete("FIFO_CUTOFF_SALE_MAPPING_QUANTITY_MISMATCH")
                if mapping["partition"] == "PRE_CUTOFF":
                    if allocation is not None:
                        return self._incomplete("FIFO_PRE_CUTOFF_SALE_HAS_FIFO_ALLOCATION")
                    pre_cutoff_digests.add(digest)
                else:
                    if (
                        allocation is None
                        or allocation.get("effective_date") != mapping["physical_effective_date"]
                    ):
                        return self._incomplete("FIFO_POST_CUTOFF_ALLOCATION_MISSING")
                    post_cutoff_digests.add(digest)
            elif allocation is not None:
                event_date = self._date_text(allocation.get("effective_date"))
                if event_date is None or event_date <= cutoff:
                    return self._incomplete("FIFO_CUTOFF_SALE_MAPPING_UNAVAILABLE")
                if (
                    mapping_complete
                    and event_date <= mapping_complete_through
                ):
                    return self._incomplete("FIFO_CUTOFF_SALE_MAPPING_COVERAGE_MISMATCH")
                post_cutoff_digests.add(digest)
            else:
                return self._incomplete("FIFO_CUTOFF_SALE_MAPPING_UNAVAILABLE")
            if digest in selected_alias_digests and digest in pre_cutoff_digests:
                legacy_sales.append({
                    "source_identity_digest": digest,
                    "quantity": quantity,
                    "physical_effective_date": mapping["physical_effective_date"],
                })

        if set(actual) != post_cutoff_digests:
            return self._incomplete("FIFO_ALLOCATION_SALE_COVERAGE_MISMATCH")

        selected_post_cutoff_digests = [
            digest for digest in expected_sku
            if expected_sku[digest] == selected_finance_sku
            and digest in post_cutoff_digests
        ]
        fifo_units = sum(
            actual[digest]["quantity"] for digest in selected_post_cutoff_digests
        )
        fifo_cogs = sum(
            (actual[digest]["total_cogs"] for digest in selected_post_cutoff_digests),
            Decimal("0.00"),
        )
        # Avoid deriving cost or quantity from the period-level date range. The
        # financial row's stable posting identities define the partition.
        legacy_units = sum(item["quantity"] for item in legacy_sales)
        selected_total_units = sum(
            quantity for digest, quantity in expected.items()
            if expected_sku[digest] == selected_finance_sku
        )
        if fifo_units + legacy_units != selected_total_units:
            return self._incomplete("FIFO_CUTOFF_SALE_MAPPING_COVERAGE_MISMATCH")
        partitioned = bool(pre_cutoff_digests.intersection(selected_alias_digests))
        response = {
            "error": False,
            "active": True,
            "complete": True,
            "source": "FIFO_ALLOCATION_REVISION",
            "stream_revision": result.get("stream_revision"),
            "allocation_revision": result.get("allocation_revision"),
            "cutoff_date": result.get("cutoff_date"),
            "units_sold": selected_total_units,
            "product_cost": format(fifo_cogs.quantize(Decimal("0.01")), ".2f"),
        }
        if partitioned:
            response.update({
                "partitioned_cutoff": True,
                "fifo_units_sold": fifo_units,
                "fifo_product_cost": format(fifo_cogs.quantize(Decimal("0.01")), ".2f"),
                "legacy_units_sold": legacy_units,
                "legacy_sales": legacy_sales,
                "cutoff_mapping_revision": mapping_result.get("mapping_revision") if mapping_complete else None,
                "cutoff_bridge_fingerprint": mapping_result.get("bridge_fingerprint") if mapping_complete else None,
            })
        # Repository layer summaries cover every finance-SKU alias in this
        # canonical stream. They cannot be attributed to a single alias safely.
        if len(products_by_sku) == 1 and isinstance(result.get("layers"), list):
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
                    units=fifo_units,
                    product_cost=fifo_cogs,
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
        if (
            product.get("historical_sku_identity_recovered") is True
            and product.get("historical_sku_identity_source")
            == "SELLER_CONFIRMED_HISTORICAL_COST_IDENTITY"
            and not catalog_sku
        ):
            # A retired finance SKU's dated cost identity does not prove that
            # there is no active FIFO stream under its current catalogue SKU.
            # Fail closed instead of treating the unknown stream as legacy mode.
            return self._error(
                "FIFO_COST_HISTORICAL_SKU_CANONICAL_IDENTITY_UNRESOLVED"
            )
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
