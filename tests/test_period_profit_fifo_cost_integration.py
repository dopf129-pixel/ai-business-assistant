from datetime import date

from services.period_profit_effective_cost_sale_quantity_summary_service import (
    PeriodProfitEffectiveCostSaleQuantitySummaryService,
)
from services.fifo_cost_sale_evidence_normalizer import (
    FifoCostSaleEvidenceNormalizer,
)
from services.period_profit_fifo_explanation_view_service import (
    PeriodProfitFifoExplanationViewService,
)


class _Finance:
    def __init__(self, skus):
        self.skus = list(skus)

    def get_daily_finance(self, _day, *, sku):
        return {
            "error": False, "sales_count": 1, "gross_sales": 100.0,
            "discount_points": 0.0, "net_accrual": 80.0,
            "commission": -10.0, "logistics": -20.0,
            "acquiring": -2.0, "other_fees": 0.0,
            "fee_breakdown": {}, "accrual_type_breakdown": {},
        }

    def get_daily_sale_posting_evidence(self, day):
        return {
            "error": False, "complete": True,
            "records": [{
                "posting_number": "post-" + sku,
                "sku": sku,
                "accrual_date": day,
            } for sku in self.skus],
        }


class _Cost:
    def get_cost(self, product_id):
        if product_id == "product-sku-fifo":
            raise AssertionError("active FIFO SKU must not resolve the current cost")
        return 30.0

    def get_effective_cost_evidence(self, *_args, **_kwargs):
        raise AssertionError("legacy dated cost must not price an active FIFO SKU")


class _FifoSource:
    def __init__(self, active_skus, *, incomplete_skus=(), cutoff_dates=None):
        self.active_skus = set(active_skus)
        self.incomplete_skus = set(incomplete_skus)
        self.cutoff_dates = dict(cutoff_dates or {})
        self.periods = []
        self.sale_counts = []

    def get_scope_mode(self, product, *, date_from=None, date_to=None):
        active = product.get("sku") in self.active_skus
        cutoff = self.cutoff_dates.get(product.get("sku"))
        if active and cutoff and date_from and date_to:
            if date_to <= cutoff:
                return {"error": False, "active": False, "code": "FIFO_COST_MODE_PRE_CUTOFF"}
            if date_from <= cutoff:
                return {
                    "error": False, "active": True,
                    "period_cutover_overlap": True,
                    "code": "FIFO_PERIOD_SPANS_COST_CUTOFF",
                    "cutoff_date": cutoff,
                }
        return {"error": False, "active": active}

    def reconcile_period_sales(self, *, product, sales, **_kwargs):
        self.periods.append((_kwargs.get("date_from"), _kwargs.get("date_to")))
        self.sale_counts.append(len(sales))
        sku = product.get("sku")
        cutoff = self.cutoff_dates.get(sku)
        start = _kwargs.get("date_from")
        end = _kwargs.get("date_to")
        if cutoff and start and end:
            if end <= cutoff:
                return {"error": False, "active": False, "code": "FIFO_COST_MODE_PRE_CUTOFF"}
            if start <= cutoff:
                return {
                    "error": False, "active": True, "complete": False,
                    "reason_code": "FIFO_PERIOD_SPANS_COST_CUTOFF",
                    "cutoff_date": cutoff,
                }
        if sku not in self.active_skus:
            return {"error": False, "active": False}
        if sku in self.incomplete_skus:
            return {
                "error": False, "active": True, "complete": False,
                "reason_code": "FIFO_ALLOCATION_STALE_OR_MISSING",
            }
        units = sum(item["quantity"] for item in sales)
        return {
            "error": False, "active": True, "complete": True,
            "source": "FIFO_ALLOCATION_REVISION",
            "stream_revision": 4, "allocation_revision": 2,
            "cutoff_date": "2026-10-31", "units_sold": units,
            "product_cost": format(units * 20, ".2f"),
        }


class _MixedCostService(PeriodProfitEffectiveCostSaleQuantitySummaryService):
    def _load_direct_finance_quantity_map(self, *_args, **_kwargs):
        return {"map": {}, "expected": set(), "fatal": None}

    def _load_realization_quantity_map(self, *_args, **_kwargs):
        return {
            ("post-sku-fifo", "sku-fifo"): 1,
            ("post-sku-legacy", "sku-legacy"): 1,
        }

    def _load_fbo_list_quantity_map(self, *_args, **_kwargs):
        return {}

    def _load_posting_quantity_for_identity(self, *_args, **_kwargs):
        return None

    def _effective_cost_evidence(self, row, accrual_date):
        if row["sku"] == "sku-fifo":
            raise AssertionError("FIFO scope must never fall back to legacy cost")
        return {
            "error": False, "effective_cost_confirmed": True,
            "historical_cost_confirmed": True,
            "cost_price": 30.0, "effective_from": accrual_date,
            "effective_through": accrual_date, "history_id": "legacy-history",
            "cost_basis": "SELLER_CONFIRMED_BOUNDED_PERIOD",
            "source": "SELLER_CONFIRMED_OPERATIONAL_HISTORY",
        }


class _LegacyForCutoverCostService(_MixedCostService):
    def _effective_cost_evidence(self, row, accrual_date):
        return {
            "error": False, "effective_cost_confirmed": True,
            "historical_cost_confirmed": True,
            "cost_price": 30.0, "effective_from": "2026-10-01",
            "effective_through": "2026-11-05", "history_id": "legacy-before-cutoff",
            "cost_basis": "SELLER_CONFIRMED_BOUNDED_PERIOD",
            "source": "SELLER_CONFIRMED_OPERATIONAL_HISTORY",
        }


def _service(skus, fifo, *, cost=None):
    finance = _Finance(skus)
    service = _MixedCostService(
        finance_service=finance,
        cost_service=cost or _Cost(),
        tax_rate=0.06,
        fifo_cost_source_service=fifo,
    )
    service._load_period_skus = lambda *_args, **_kwargs: {
        "map": {}, "expected": set(), "fatal": None,
    }
    return service


def _products(skus):
    return [{
        "product_id": "product-" + sku,
        "offer_id": "offer-" + sku,
        "sku": sku,
    } for sku in skus]


def test_period_profit_uses_fifo_cost_for_cutover_sku_without_legacy_fallback():
    fifo = _FifoSource(["sku-fifo"])
    service = _service(["sku-fifo"], fifo)
    result = service.calculate(
        date(2026, 11, 2), date(2026, 11, 2), _products(["sku-fifo"]),
    )

    assert result["error"] is False, result
    assert fifo.periods == [("2026-11-02", "2026-11-02")]
    assert result["product_cost"] == 20.0
    assert result["profit"] == 54.0
    assert result["products"][0]["cost_source"] == "FIFO_ALLOCATION_REVISION"
    assert result["products"][0]["fifo_allocation_revision"] == 2
    assert result["fifo_cost_source_counts"] == {"fifo": 1, "legacy": 0}
    assert result["fifo_cogs_reconciled"] is True


def test_period_profit_mixes_fifo_and_dated_legacy_per_exact_sku():
    skus = ["sku-fifo", "sku-legacy"]
    service = _service(skus, _FifoSource(["sku-fifo"]))
    result = service.calculate("2026-11-02", "2026-11-02", _products(skus))

    assert result["error"] is False, result
    assert result["units_sold"] == 2
    assert result["product_cost"] == 50.0
    assert result["profit"] == 98.0
    by_sku = {row["sku"]: row for row in result["products"]}
    assert by_sku["sku-fifo"]["cost_source"] == "FIFO_ALLOCATION_REVISION"
    assert by_sku["sku-legacy"]["cost_source"] == "LEGACY_DATED_COST"
    assert result["fifo_cost_source_counts"] == {"fifo": 1, "legacy": 1}


def test_period_profit_groups_confirmed_finance_sku_aliases_by_exact_fifo_stream():
    class AliasAwareFifoSource:
        def __init__(self):
            self.calls = []

        def resolve_scope_identity(self, product):
            return {
                "error": False, "store_id": "store-a",
                "product_id": product["product_id"],
                "offer_id": product["offer_id"],
                "sku": product["catalog_sku"],
            }

        def get_scope_mode(self, product, **_kwargs):
            return {
                "error": False, "active": True,
                "store_id": "store-a",
                "product_id": product["product_id"],
                "offer_id": product["offer_id"],
                "sku": product["catalog_sku"],
            }

        def reconcile_period_sales(
            self, *, product, finance_sku, sales,
            finance_sku_alias_products=None, **_kwargs,
        ):
            aliases = finance_sku_alias_products or [product]
            self.calls.append({
                "finance_sku": finance_sku,
                "sales_skus": sorted(sale["sku"] for sale in sales),
                "alias_skus": sorted(item["sku"] for item in aliases),
            })
            selected = [sale for sale in sales if sale["sku"] == finance_sku]
            units = sum(sale["quantity"] for sale in selected)
            unit_cost = {"old-finance-sku-a": 10, "old-finance-sku-b": 15}[
                finance_sku
            ]
            return {
                "error": False, "active": True, "complete": True,
                "source": "FIFO_ALLOCATION_REVISION",
                "stream_revision": 4, "allocation_revision": 2,
                "cutoff_date": "2026-10-31", "units_sold": units,
                "product_cost": format(units * unit_cost, ".2f"),
            }

    class AliasService(_MixedCostService):
        def _load_realization_quantity_map(self, *_args, **_kwargs):
            return {
                ("post-old-finance-sku-a", "old-finance-sku-a"): 2,
                ("post-old-finance-sku-b", "old-finance-sku-b"): 1,
            }

    fifo = AliasAwareFifoSource()
    service = AliasService(
        finance_service=_Finance(["old-finance-sku-a", "old-finance-sku-b"]),
        cost_service=_Cost(), tax_rate=0.06, fifo_cost_source_service=fifo,
    )
    service._load_period_skus = lambda *_args, **_kwargs: {
        "map": {}, "expected": set(), "fatal": None,
    }
    products = [{
        "product_id": "product-shared", "offer_id": "offer-shared",
        "sku": sku, "catalog_sku": "current-catalog-sku",
        "historical_sku_identity_recovered": True,
        "historical_sku_identity_source": (
            "OZON_FINANCE_POSTING_TO_CURRENT_CATALOG_OFFER_ID"
        ),
    } for sku in ("old-finance-sku-a", "old-finance-sku-b")]

    result = service.calculate("2026-11-02", "2026-11-02", products)

    assert result["error"] is False, result
    by_sku = {row["sku"]: row for row in result["products"]}
    assert by_sku["old-finance-sku-a"]["units_sold"] == 2
    assert by_sku["old-finance-sku-a"]["product_cost"] == 20.0
    assert by_sku["old-finance-sku-b"]["units_sold"] == 1
    assert by_sku["old-finance-sku-b"]["product_cost"] == 15.0
    assert result["units_sold"] == 3
    assert result["product_cost"] == 35.0
    assert fifo.calls == [
        {
            "finance_sku": "old-finance-sku-a",
            "sales_skus": ["old-finance-sku-a", "old-finance-sku-b"],
            "alias_skus": ["old-finance-sku-a", "old-finance-sku-b"],
        },
        {
            "finance_sku": "old-finance-sku-b",
            "sales_skus": ["old-finance-sku-a", "old-finance-sku-b"],
            "alias_skus": ["old-finance-sku-a", "old-finance-sku-b"],
        },
    ]


def test_reaccrued_finance_sale_consumes_fifo_once_across_period_days():
    fifo = _FifoSource(["sku-fifo"])
    service = _service(["sku-fifo"], fifo)
    result = service.calculate(
        "2026-11-02", "2026-11-03", _products(["sku-fifo"]),
    )

    assert result["error"] is False, result
    assert result["units_sold"] == 1
    assert result["product_cost"] == 20.0
    assert result["sale_quantity_positive_event_count"] == 2
    assert result["sale_quantity_reaccrued_event_count"] == 1
    assert fifo.sale_counts == [1]


def test_period_profit_active_fifo_gap_is_incomplete_and_does_not_use_legacy():
    service = _service(
        ["sku-fifo"], _FifoSource(["sku-fifo"], incomplete_skus=["sku-fifo"]),
    )
    result = service.calculate("2026-11-02", "2026-11-02", _products(["sku-fifo"]))

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_FIFO_COGS_INCOMPLETE"
    assert result["fifo_reason_code"] == "FIFO_ALLOCATION_STALE_OR_MISSING"


def test_period_profit_before_fifo_cutoff_keeps_dated_legacy_cost():
    fifo = _FifoSource(
        ["sku-fifo"], cutoff_dates={"sku-fifo": "2026-11-05"},
    )
    class LegacyCost(_Cost):
        def get_cost(self, product_id):
            return 30.0

    service = _LegacyForCutoverCostService(
        finance_service=_Finance(["sku-fifo"]), cost_service=LegacyCost(),
        tax_rate=0.06, fifo_cost_source_service=fifo,
    )
    service._load_period_skus = lambda *_args, **_kwargs: {
        "map": {}, "expected": set(), "fatal": None,
    }

    result = service.calculate(
        "2026-10-01", "2026-11-05", _products(["sku-fifo"]),
    )

    assert result["error"] is False, result
    assert result["products"][0]["cost_source"] == "LEGACY_DATED_COST"
    assert result["fifo_cost_source_counts"] == {"fifo": 0, "legacy": 1}


def test_period_profit_refuses_period_spanning_fifo_cutoff():
    service = _service(
        ["sku-fifo"],
        _FifoSource(["sku-fifo"], cutoff_dates={"sku-fifo": "2026-11-05"}),
    )

    result = service.calculate(
        "2026-11-05", "2026-11-06", _products(["sku-fifo"]),
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_FIFO_COGS_INCOMPLETE"
    assert result["fifo_reason_code"] == "FIFO_PERIOD_SPANS_COST_CUTOFF"
    assert result["fifo_cutoff_date"] == "2026-11-05"


def test_period_profit_combines_physical_pre_cutoff_legacy_and_post_cutoff_fifo_once():
    class PeriodFinance(_Finance):
        def get_daily_sale_posting_evidence(self, day):
            posting = "legacy-posting" if day == "2026-11-05" else "fifo-posting"
            return {
                "error": False, "complete": True,
                "records": [{
                    "posting_number": posting, "sku": "sku-fifo",
                    "accrual_date": day,
                }],
            }

    class PartitionedFifoSource:
        def get_scope_mode(self, _product, **_kwargs):
            return {
                "error": False, "active": True,
                "period_cutover_overlap": True,
                "code": "FIFO_PERIOD_SPANS_COST_CUTOFF",
                "cutoff_date": "2026-11-05",
            }

        def build_sale_identity_digest(self, _product, sale):
            return FifoCostSaleEvidenceNormalizer.build_identity_digest(
                store_id="store-a", posting_number=sale["posting_number"],
                finance_sku=sale["sku"], identity={
                    "mapping_confirmed": True,
                    "offer_id": "offer-sku-fifo",
                    "product_id": "product-sku-fifo",
                },
            )

        def reconcile_period_sales(self, *, sales, **_kwargs):
            legacy = next(item for item in sales if item["posting_number"] == "legacy-posting")
            digest = self.build_sale_identity_digest({}, legacy)["source_identity_digest"]
            return {
                "error": False, "active": True, "complete": True,
                "partitioned_cutoff": True,
                "source": "FIFO_ALLOCATION_REVISION",
                "stream_revision": 4, "allocation_revision": 2,
                "cutoff_date": "2026-11-05",
                "cutoff_mapping_revision": 3,
                "cutoff_bridge_fingerprint": "b" * 64,
                "units_sold": 5, "product_cost": "43.95",
                "fifo_units_sold": 3, "fifo_product_cost": "43.95",
                "legacy_units_sold": 2,
                "legacy_sales": [{
                    "source_identity_digest": digest,
                    "quantity": 2,
                    "physical_effective_date": "2026-11-05",
                }],
                "fifo_cost_explanation": {
                    "cost_mode": "FIFO", "status": "CONFIRMED",
                    "reason_code": None, "cutoff_date": "2026-11-05",
                    "stream_revision": 4, "allocation_revision": 2,
                    "layers": [{
                        "basis_ref": "fifo-basis-00000000000000000001",
                        "basis_kind": "FIFO_LAYER", "sequence": 1,
                        "effective_date": "2026-11-05",
                        "confirmation": "OWNER_CONFIRMED",
                        "source_method": "OWNER_CONFIRMED_FIFO_CUTOFF",
                        "source_status": "OWNER_CONFIRMED",
                        "coverage_status": "OWNER_CONFIRMED",
                        "quantity": 3, "unit_cost_rub": "14.65",
                        "total_cogs_rub": "43.95",
                    }],
                    "corrections": {
                        "status": "NO_CORRECTION", "reason_code": None,
                        "revisions": [],
                    },
                },
            }

    class CutoffProfitService(_MixedCostService):
        def _load_realization_quantity_map(self, *_args, **_kwargs):
            return {
                ("legacy-posting", "sku-fifo"): 2,
                ("fifo-posting", "sku-fifo"): 3,
            }

        def _effective_cost_evidence(self, row, physical_date):
            assert physical_date == "2026-11-05"
            return {
                "error": False, "effective_cost_confirmed": True,
                "historical_cost_confirmed": True,
                "cost_price": 21.0,
                "effective_from": "2026-01-01",
                "effective_through": "2026-11-05",
                "history_id": "confirmed-old-rate",
                "source": "SELLER_CONFIRMED_OPERATIONAL_HISTORY",
                "cost_basis": "SELLER_CONFIRMED_BOUNDED_PERIOD",
            }

    service = CutoffProfitService(
        finance_service=PeriodFinance(["sku-fifo"]),
        cost_service=_Cost(), tax_rate=0.06,
        fifo_cost_source_service=PartitionedFifoSource(),
    )
    service._load_period_skus = lambda *_args, **_kwargs: {
        "map": {}, "expected": set(), "fatal": None,
    }

    result = service.calculate(
        "2026-11-05", "2026-11-06", _products(["sku-fifo"]),
    )
    assert result["error"] is False, result
    assert result["units_sold"] == 5
    assert result["product_cost"] == 85.95
    assert result["profit"] == 62.05
    product = result["products"][0]
    assert product["cost_source"] == "CUTOFF_PARTITIONED_FIFO_AND_LEGACY"
    assert product["fifo_units_sold"] == 3
    assert product["fifo_product_cost"] == 43.95
    assert product["legacy_cutoff_units_sold"] == 2
    assert product["legacy_cutoff_product_cost"] == 42.0
    assert product["fifo_stream_revision"] == 4
    assert product["fifo_allocation_revision"] == 2
    assert product["fifo_cutoff_mapping_revision"] == 3

    explanation = result["fifo_cost_explanation"]
    assert explanation["cost_mode"] == "MIXED_CUTOFF"
    assert explanation["status"] == "CONFIRMED"
    assert explanation["total_cogs_rub"] == "85.95"
    assert explanation["fifo_cogs_rub"] == "43.95"
    assert explanation["legacy_cogs_rub"] == "42.00"
    detail = "\n".join(PeriodProfitFifoExplanationViewService.detail_lines(explanation))
    assert "stream rev 4" in detail
    assert "allocation rev 2" in detail
    assert "mapping rev 3" in detail

    export_projection = PeriodProfitFifoExplanationViewService().sanitize_projection(
        explanation,
    )
    assert export_projection["status"] == "CONFIRMED"
    assert export_projection["fifo_cogs_rub"] == explanation["fifo_cogs_rub"]
    assert export_projection["legacy_cogs_rub"] == explanation["legacy_cogs_rub"]
    assert export_projection["products"][0]["allocation_revision"] == 2
    assert export_projection["products"][0]["cutoff_mapping_revision"] == 3
