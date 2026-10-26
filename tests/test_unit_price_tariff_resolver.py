from decimal import Decimal

import pytest

from services.tax_service import TaxService
from services.unit_price_scenario_service import UnitPriceScenarioService
from services.unit_price_tariff_resolver import UnitPriceTariffResolver


IDENTITY = {
    "owner_id": "owner-1",
    "store_id": "store-1",
    "product_id": "product-1",
    "offer_id": "offer-1",
    "sku": "sku-1",
}


def _profile(*, bands=None, **overrides):
    profile = {
        "profile_id": "profile-1",
        "revision": 1,
        "state_revision": 1,
        "owner_id": IDENTITY["owner_id"],
        "store_id": IDENTITY["store_id"],
        "identity": {
            "product_id": IDENTITY["product_id"],
            "offer_id": IDENTITY["offer_id"],
            "sku": IDENTITY["sku"],
        },
        "sale_schema": "FBO",
        "price_basis": "SELLER_PRICE_RUB",
        "currency": "RUB",
        "origin": "MANUAL_SELLER_ASSUMPTION",
        "confirmed_by_owner": True,
        "recorded_at": "2026-10-27T10:00:00+00:00",
        "effective_from": "2026-10-01",
        "effective_to": None,
        "bands": bands or [
            {"price_from_cents": 1, "price_to_cents": 10_000, "commission_rate": "11"},
            {"price_from_cents": 10_001, "price_to_cents": 30_000, "commission_rate": "22"},
        ],
    }
    profile.update(overrides)
    return profile


def _resolve(price_cents, profiles=None, **overrides):
    request = {
        "seller_price_cents": price_cents,
        "identity": dict(IDENTITY),
        "sale_schema": "FBO",
        "effective_date": "2026-10-27",
        "profiles": [_profile()] if profiles is None else profiles,
    }
    request.update(overrides)
    return UnitPriceTariffResolver().resolve(**request)


@pytest.mark.parametrize(
    ("price_cents", "rate"),
    [(10_000, "11"), (10_001, "22"), (10_100, "22")],
)
def test_inclusive_tariff_boundaries_resolve_exactly(price_cents, rate):
    result = _resolve(price_cents)

    assert result["error"] is False
    assert result["available"] is True
    assert result["status"] == "MANUAL_RANGE"
    assert result["commission_rate"] == rate
    assert result["seller_price_cents"] == price_cents


def test_canonical_forward_keeps_n03_boundary_commission_amounts():
    resolver = UnitPriceTariffResolver()
    calculator = UnitPriceScenarioService(TaxService())
    results = []
    for price_cents in (10_000, 10_001, 10_100):
        resolved = resolver.resolve(
            seller_price_cents=price_cents,
            identity=IDENTITY,
            sale_schema="FBO",
            effective_date="2026-10-27",
            profiles=[_profile()],
        )
        inputs = {
            "price": format(Decimal(price_cents) / 100, ".2f"),
            "cost": "0",
            "commission_rate": resolved["commission_rate"],
            "logistics_per_unit": "0",
            "last_mile_per_unit": "0",
            "acquiring_per_unit": "0",
            "advertising_rate": "0",
            "discount_points_rate": "0",
            "tax_mode": "NONE",
        }
        result = calculator.calculate(inputs)
        results.append(result["calculated"]["commission"])

    assert results == [11.0, 22.0, 22.22]


def test_gap_remains_unknown_and_does_not_use_nearest_rate():
    profile = _profile(bands=[
        {"price_from_cents": 1, "price_to_cents": 9_999, "commission_rate": "11"},
        {"price_from_cents": 10_002, "price_to_cents": 30_000, "commission_rate": "22"},
    ])

    result = _resolve(10_000, [profile])

    assert result["status"] == "UNKNOWN"
    assert result["available"] is False
    assert result["commission_rate"] is None
    assert result["reason"] == "PRICE_OUTSIDE_PROFILE_BANDS"


def test_inclusive_band_overlap_is_rejected_even_on_shared_cent():
    profile = _profile(bands=[
        {"price_from_cents": 1, "price_to_cents": 10_000, "commission_rate": "11"},
        {"price_from_cents": 10_000, "price_to_cents": 30_000, "commission_rate": "22"},
    ])

    result = _resolve(10_000, [profile])

    assert result == {
        "error": True,
        "code": "TARIFF_PROFILE_INVALID",
        "reason": "BAND_OVERLAP",
        "read_only": True,
        "executed": False,
    }


def test_conflicting_profiles_fail_closed_unless_exact_revision_selected():
    second = _profile(profile_id="profile-2", bands=[
        {"price_from_cents": 1, "price_to_cents": 30_000, "commission_rate": "13"},
    ])

    conflict = _resolve(5_000, [_profile(), second])
    selected = _resolve(
        5_000,
        [_profile(), second],
        selected_profile_id="profile-2",
        selected_revision=1,
        selected_state_revision=1,
    )

    assert conflict["status"] == "CONFLICT"
    assert conflict["commission_rate"] is None
    assert selected["status"] == "MANUAL_RANGE"
    assert selected["commission_rate"] == "13"


def test_stale_selected_profile_state_is_not_used():
    result = _resolve(
        5_000,
        [_profile()],
        selected_profile_id="profile-1",
        selected_revision=1,
        selected_state_revision=2,
    )

    assert result["status"] == "CONFLICT"
    assert result["reason"] == "SELECTED_PROFILE_STATE_STALE"
    assert result["commission_rate"] is None


def test_current_price_point_never_confirms_neighbouring_price():
    point = _profile(
        origin="CURRENT_PRICE_POINT",
        source_ref="current-product-info",
        recorded_at="2026-10-27T10:00:00+00:00",
        observed_at="2026-10-27T10:00:00+00:00",
        confirmed_by_owner=False,
        effective_from="2026-10-27",
        effective_to="2026-10-27",
        bands=[{"price_from_cents": 10_000, "price_to_cents": 10_000, "commission_rate": "11"}],
    )

    same = _resolve(10_000, [point])
    neighbour = _resolve(9_999, [point])

    assert same["status"] == "CURRENT_PRICE_POINT_ONLY"
    assert same["commission_rate"] == "11"
    assert neighbour["status"] == "CURRENT_PRICE_POINT_ONLY"
    assert neighbour["commission_rate"] is None


@pytest.mark.parametrize("rate", ["NaN", "Infinity", "-Infinity", "-0.01", "100.01", True, None, 1.5])
def test_invalid_or_non_decimal_rates_are_rejected(rate):
    profile = _profile(bands=[
        {"price_from_cents": 1, "price_to_cents": 30_000, "commission_rate": rate},
    ])

    result = _resolve(10_000, [profile])

    assert result["error"] is True
    assert result["reason"] == "BAND_VALUES_INVALID"


def test_explicit_zero_rate_is_valid():
    result = _resolve(10_000, [_profile(bands=[
        {"price_from_cents": 1, "price_to_cents": 30_000, "commission_rate": "0"},
    ])])

    assert result["available"] is True
    assert result["commission_rate"] == "0"


def test_explicit_zero_rate_is_valid_even_with_decimal_exponent():
    result = _resolve(10_000, [_profile(bands=[
        {"price_from_cents": 1, "price_to_cents": 30_000, "commission_rate": "0E-1000000"},
    ])])

    assert result["available"] is True
    assert result["commission_rate"] == "0"


def test_expired_profile_is_not_used_even_for_an_exact_selected_revision():
    expired = _profile(effective_to="2026-10-26")

    result = _resolve(
        5_000,
        [expired],
        selected_profile_id="profile-1",
        selected_revision=1,
        selected_state_revision=1,
    )

    assert result["status"] == "EXPIRED"
    assert result["commission_rate"] is None


def test_source_reference_is_allowlisted_before_being_returned():
    profile = _profile(
        origin="CONFIRMED_OFFICIAL_SOURCE",
        source_ref="https://example.invalid/path?token=secret",
        confirmed_by_owner=False,
    )

    result = _resolve(5_000, [profile])

    assert result["error"] is True
    assert result["reason"] == "SOURCE_PROVENANCE_REQUIRED"
    assert "secret" not in str(result)


@pytest.mark.parametrize(
    ("profile_change", "request_change"),
    [
        ({"owner_id": "owner-other"}, {}),
        ({"store_id": "store-other"}, {}),
        ({"identity": {"product_id": "product-other", "offer_id": "offer-1", "sku": "sku-1"}}, {}),
        ({"identity": {"product_id": "product-1", "offer_id": "offer-other", "sku": "sku-1"}}, {}),
        ({"identity": {"product_id": "product-1", "offer_id": "offer-1", "sku": "sku-other"}}, {}),
        ({}, {"effective_date": "2026-09-30"}),
    ],
)
def test_wrong_scope_or_effective_date_never_applies(profile_change, request_change):
    profile = _profile(**profile_change)

    result = _resolve(5_000, [profile], **request_change)

    assert result["available"] is False
    assert result["commission_rate"] is None


def test_fbs_is_explicitly_unsupported_even_if_an_fbo_profile_exists():
    result = _resolve(10_000, sale_schema="FBS")

    assert result["status"] == "UNSUPPORTED_SCHEME"
    assert result["commission_rate"] is None


@pytest.mark.parametrize("bad_price", [0, -1, 1.0, True, UnitPriceTariffResolver.MAX_PRICE_CENTS + 1])
def test_invalid_or_over_limit_price_cents_are_rejected(bad_price):
    result = _resolve(bad_price)

    assert result["error"] is True
    assert result["reason"] == "SELLER_PRICE_CENTS_INVALID"


def test_profile_rule_and_candidate_profile_limits_are_enforced():
    too_many_bands = _profile(bands=[
        {"price_from_cents": index * 2 + 1, "price_to_cents": index * 2 + 1, "commission_rate": "1"}
        for index in range(21)
    ])
    too_many_profiles = [_profile(profile_id=f"p{index}") for index in range(21)]

    assert _resolve(1, [too_many_bands])["reason"] == "BAND_COUNT_LIMIT"
    assert _resolve(1, too_many_profiles)["reason"] == "PROFILE_COUNT_LIMIT"
