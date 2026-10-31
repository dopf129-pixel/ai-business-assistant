from copy import deepcopy

import pytest

from services.product_unit_economics_historical_pre_ad_margin_service import (
    ProductUnitEconomicsHistoricalPreAdMarginService,
)
from services.product_unit_economics_query_service import ProductUnitEconomicsQueryService
from services.unit_economics_advertising_evidence_service import (
    UnitEconomicsAdvertisingEvidenceService,
)
from services.unit_economics_expense_normalizer import UnitEconomicsExpenseNormalizer


IDENTITY = {
    "owner_id": "owner-a",
    "store_id": "store-a",
    "product_id": "product-a",
    "offer_id": "offer-a",
    "sku": "sku-a",
    "sale_schema": "FBO",
}
PERIOD = {"date_from": "2026-10-01", "date_to": "2026-10-07"}
WINDOW = {
    "from_date": PERIOD["date_from"],
    "to_date": PERIOD["date_to"],
    "date_basis": "OZON_ACCRUAL_DATE",
    "timezone": "Europe/Moscow",
}
AD_KEYS = [
    "FINANCE_ADVERTISING_CPC",
    "FINANCE_ADVERTISING_CPO",
    "FINANCE_ADVERTISING_OTHER",
]


def _ad_part(component_id, key, signed_amount, *, attribution="EXACT_SKU", ownership="BASE_ALREADY_INCLUDED"):
    category = {
        "FINANCE_ADVERTISING_CPC": "ADVERTISING_CPC",
        "FINANCE_ADVERTISING_CPO": "ADVERTISING_CPO",
        "FINANCE_ADVERTISING_OTHER": "ADVERTISING_OTHER",
    }[key]
    return {
        "component_id": component_id,
        "component_key": key,
        "category": category,
        "signed_source_amount_rub": signed_amount,
        "ownership": ownership,
        "attribution": attribution,
        "origin": "OFFICIAL_SOURCE",
        "recurrence": "RECURRING",
        "correction_state": "CORRECTED_AS_OF",
    }


def _resolved_evidence(*parts, expected_keys=None, cohort=False):
    snapshot = {
        "schema_version": 1,
        "identity": deepcopy(IDENTITY),
        "source": "SELLER_FINANCE",
        "source_method": "/v3/finance/transaction/list",
        "source_contract_version": "v3",
        "source_window": {**WINDOW},
        "received_at": "2026-10-08T10:00:00Z",
        "as_of": "2026-10-08T10:00:00Z",
        "coverage": {
            "requested_pages": 1,
            "received_pages": 1,
            "has_more": False,
            "stop_reason": "END_OF_DATA",
            "source_complete": True,
        },
        "expected_component_keys": list(AD_KEYS if expected_keys is None else expected_keys),
        "operations": [
            {
                "operation_id": f"operation-{index}",
                "identity": deepcopy(IDENTITY),
                "components": [deepcopy(part)],
            }
            for index, part in enumerate(parts)
        ],
    }
    if cohort:
        snapshot["cohort_ref"] = "a" * 64
    normalized = UnitEconomicsExpenseNormalizer.normalize(snapshot)
    return UnitEconomicsAdvertisingEvidenceService.resolve(normalized)


def _metric(**overrides):
    value = {
        "product_id": "product-a",
        "sku": "sku-a",
        "units_sold": 30,
        "revenue": 3000.0,
        "net_profit": 645.0,
        "profit_per_unit": 21.5,
        "margin_percent": 21.5,
        "product_cost": 900.0,
        "tax": 135.0,
    }
    value.update(overrides)
    return value


@pytest.fixture
def service():
    return ProductUnitEconomicsHistoricalPreAdMarginService()


def test_historical_n09_adds_back_only_complete_financial_ads_and_preserves_tax(service):
    evidence = _resolved_evidence(
        _ad_part("cpc-charge", AD_KEYS[0], "-400.00"),
        _ad_part("cpc-credit", AD_KEYS[0], "40.00"),
    )
    # A separate CPC check is diagnostic only and must not enter the add-back.
    evidence["performance_reconciliation"] = {
        "performance_reconciliation_rub": "359.98",
        "performance_is_additional_expense": False,
    }

    result = service.build(_metric(), evidence, IDENTITY, PERIOD)

    assert evidence["financial"]["complete_for_sku"] is True
    assert evidence["financial"]["exact_sku_attribution_complete"] is True
    assert evidence["financial"]["known_sku_scoped_expense_rub"] == "360.00"
    assert result["status"] == "AVAILABLE"
    assert result["profit_rub"] == 1005.0
    assert result["profit_per_unit_rub"] == 33.5
    assert result["margin_percent"] == 33.5
    assert result["tax_rub"] == 135.0
    assert result["tax_basis"] == "AS_RECORDED_IN_PERIOD_RESULT"
    assert result["tax_provenance"] == "EXISTING_HISTORICAL_QUERY_RESULT"
    assert result["after_ad"] == {
        "profit_rub": 645.0,
        "profit_per_unit_rub": 21.5,
        "margin_percent": 21.5,
    }
    assert result["advertising"]["amount_rub"] == 360.0
    assert result["advertising"]["performance_cpc_added"] is False
    assert result["expense_scope"]["status"] == "PARTIAL"


def test_historical_profit_tax_basis_is_not_replaced_with_no_ad_scenario_tax(service):
    evidence = _resolved_evidence(
        _ad_part("cpc", AD_KEYS[0], "-12.00"),
    )

    result = service.build(
        _metric(
            units_sold=1,
            revenue=100.0,
            net_profit=22.10,
            profit_per_unit=22.10,
            margin_percent=22.10,
            product_cost=62.0,
            tax=3.90,
        ),
        evidence,
        IDENTITY,
        PERIOD,
    )

    assert result["profit_rub"] == 34.1
    assert result["profit_per_unit_rub"] == 34.1
    assert result["margin_percent"] == 34.1
    assert result["tax_rub"] == 3.9
    assert result["tax_basis"] != "NO_ADVERTISING_SCENARIO"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"units_sold": 0}, "HISTORICAL_SUCCESSFUL_UNITS_UNAVAILABLE"),
        ({"units_sold": None}, "HISTORICAL_SUCCESSFUL_UNITS_UNAVAILABLE"),
        ({"revenue": 0.0}, "HISTORICAL_SELLER_REVENUE_UNAVAILABLE"),
    ],
)
def test_historical_zero_or_unknown_denominator_never_becomes_zero_percent_or_per_unit(
    service, overrides, reason,
):
    result = service.build(_metric(**overrides), _resolved_evidence(), IDENTITY, PERIOD)

    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == reason
    assert result["profit_per_unit_rub"] is None
    assert result["margin_percent"] is None


def test_incomplete_cpo_scope_blocks_historical_addback_instead_of_using_cpc_alone(service):
    evidence = _resolved_evidence(
        _ad_part("cpc", AD_KEYS[0], "-360.00"),
        expected_keys=[AD_KEYS[0], AD_KEYS[2]],
    )

    result = service.build(_metric(), evidence, IDENTITY, PERIOD)

    assert evidence["financial"]["component_status"]["CPO"]["status"] == "MISSING"
    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "HISTORICAL_ADVERTISING_SCOPE_INCOMPLETE"
    assert result["profit_rub"] is None


def test_cohort_advertising_is_not_mistaken_for_exact_sku_scope(service):
    evidence = _resolved_evidence(
        _ad_part("cpc", AD_KEYS[0], "-360.00", attribution="EXACT_COHORT"),
        cohort=True,
    )

    result = service.build(_metric(), evidence, IDENTITY, PERIOD)

    assert evidence["financial"]["complete_for_sku"] is True
    assert evidence["financial"]["exact_sku_attribution_complete"] is False
    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "HISTORICAL_ADVERTISING_SCOPE_INCOMPLETE"


def test_additional_ads_are_not_added_back_to_a_net_result_a_second_time(service):
    evidence = _resolved_evidence(
        _ad_part("cpc", AD_KEYS[0], "-360.00", ownership="ADDITIONAL"),
    )

    result = service.build(_metric(), evidence, IDENTITY, PERIOD)

    assert evidence["financial"]["sku_primary_expense_rub"] == "360.00"
    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "HISTORICAL_ADVERTISING_OWNERSHIP_MISMATCH"


def test_hidden_account_allocation_total_blocks_exact_sku_addback(service):
    evidence = _resolved_evidence(
        _ad_part("cpc", AD_KEYS[0], "-360.00"),
    )
    evidence["financial"]["account_level_expense_rub"] = "1.00"

    result = service.build(_metric(), evidence, IDENTITY, PERIOD)

    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "HISTORICAL_ADVERTISING_OWNERSHIP_MISMATCH"


def test_net_advertising_credit_requires_review_and_is_not_made_positive(service):
    evidence = _resolved_evidence(
        _ad_part("cpc-credit", AD_KEYS[0], "50.00"),
    )

    result = service.build(_metric(), evidence, IDENTITY, PERIOD)

    assert evidence["financial"]["known_sku_scoped_expense_rub"] == "-50.00"
    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "HISTORICAL_ADVERTISING_NET_CREDIT_REQUIRES_REVIEW"


def test_exact_evidence_is_attached_to_the_matching_historical_query_row(service):
    metric = _metric()
    evidence = _resolved_evidence(
        _ad_part("cpc-charge", AD_KEYS[0], "-400.00"),
        _ad_part("cpc-credit", AD_KEYS[0], "40.00"),
    )

    class ProductSource:
        def load_products(self):
            return [{"product_id": "product-a", "offer_id": "offer-a", "sku": "sku-a"}]

    class PeriodSource:
        def calculate_period_profit(self, date_from, date_to, products):
            assert (date_from, date_to) == (PERIOD["date_from"], PERIOD["date_to"])
            return {"error": False, "profits": [{
                "product_id": "product-a",
                "sku": "sku-a",
                "historical_advertising_evidence": evidence,
                "historical_expected_identity": IDENTITY,
            }]}

    class AnalyticsSource:
        def get_period(self):
            return {"error": False, **PERIOD}

    class MetricProvider:
        def build(self, rows):
            assert len(rows) == 1
            return [metric]

    query = ProductUnitEconomicsQueryService(
        product_service=ProductSource(),
        period_profit_service=PeriodSource(),
        analytics_service=AnalyticsSource(),
        unit_economics_provider=MetricProvider(),
        historical_pre_ad_margin_service=service,
    )

    result = query.query("sku-a")

    assert result["source"] == "historical"
    assert result["net_profit_per_unit"] == 21.5
    assert result["pre_ad_margin"]["status"] == "AVAILABLE"
    assert result["pre_ad_margin"]["profit_rub"] == 1005.0
    response = query.format_response(result)
    assert "Маржа до рекламы (после налога):" in response
    assert "33.50 ₽ / шт. · 33.50% от цены продавца" in response
    assert "Налог сохранён из результата исторического периода: 4.50 ₽ / шт." in response
    assert "Полнота расходов без рекламы: частичная" in response
    assert "После учтённой рекламы: 21.50 ₽ / шт. · 21.50%" in response
    assert "Исторический период начислений Ozon: 2026-10-01 — 2026-10-07" in response


@pytest.mark.parametrize(
    ("identity", "period", "reason"),
    [
        ({**IDENTITY, "store_id": "other-store"}, PERIOD, "HISTORICAL_ADVERTISING_IDENTITY_UNCONFIRMED"),
        (IDENTITY, {**PERIOD, "date_to": "2026-10-08"}, "HISTORICAL_ADVERTISING_PERIOD_MISMATCH"),
    ],
)
def test_historical_addback_requires_matching_store_and_exact_date_window(
    service, identity, period, reason,
):
    result = service.build(
        _metric(), _resolved_evidence(_ad_part("cpc", AD_KEYS[0], "-360.00")), identity, period,
    )

    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == reason
