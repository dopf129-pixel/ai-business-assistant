from copy import deepcopy

from services.unit_price_tariff_resolver import UnitPriceTariffResolver
from services.unit_price_tariff_snapshot_adapter import UnitPriceTariffSnapshotAdapter


DAY = "2026-10-27"
IDENTITY = {
    "owner_id": "owner-1", "store_id": "store-1", "product_id": "product-1",
    "offer_id": "offer-1", "sku": "sku-1",
}


def _profile():
    return {
        "profile_id": "tariff-1", "revision": 2, "state_revision": 3,
        "owner_id": "owner-1", "store_id": "store-1",
        "identity": {key: IDENTITY[key] for key in ("product_id", "offer_id", "sku")},
        "sale_schema": "FBO", "price_basis": "SELLER_PRICE_RUB", "currency": "RUB",
        "origin": "MANUAL_SELLER_ASSUMPTION", "source_ref": None,
        "recorded_at": "2026-10-27T10:00:00+00:00", "confirmed_by_owner": True,
        "effective_from": DAY, "effective_to": None,
        "bands": [
            {"price_from_cents": 9_500, "price_to_cents": 10_000, "commission_rate": "12"},
            {"price_from_cents": 10_001, "price_to_cents": 11_000, "commission_rate": "14"},
        ],
    }


def _frozen_snapshot():
    profile = _profile()
    resolved = UnitPriceTariffResolver().resolve(
        seller_price_cents=9_800, identity=IDENTITY, sale_schema="FBO",
        effective_date=DAY, profiles=[profile],
    )
    return UnitPriceTariffSnapshotAdapter.freeze(
        resolved, profile, candidate_profiles=[profile], effective_date=DAY,
    )


def test_freeze_and_validate_keep_exact_profile_version_and_source_origin():
    snapshot = _frozen_snapshot()

    validated = UnitPriceTariffSnapshotAdapter.validate(
        snapshot, IDENTITY, {"price": "98", "commission_rate": "12"},
    )

    assert validated == snapshot
    assert snapshot["selected_profile"] == {
        "profile_id": "tariff-1", "revision": 2, "state_revision": 3,
    }
    assert snapshot["profiles"][0]["origin"] == "MANUAL_SELLER_ASSUMPTION"
    assert snapshot["profiles"][0]["bands"] == _profile()["bands"]


def test_restored_frozen_profile_resolves_other_price_without_any_source_read():
    snapshot = _frozen_snapshot()
    result = UnitPriceTariffSnapshotAdapter.resolve_frozen(
        snapshot, IDENTITY, 10_500,
    )

    assert result["available"] is True
    assert result["status"] == "MANUAL_RANGE"
    assert result["commission_rate"] == "14"
    assert result["profile"]["revision"] == 2


def test_frozen_snapshot_preserves_explicit_session_profile_over_stored_overlap():
    stored = _profile()
    stored["bands"] = [{
        "price_from_cents": 1, "price_to_cents": 20_000,
        "commission_rate": "14",
    }]
    session = deepcopy(stored)
    session.update({
        "profile_id": "session-1", "revision": 1, "state_revision": 1,
        "source_ref": "MANUAL_SESSION_ONLY",
        "bands": [{
            "price_from_cents": 1, "price_to_cents": 20_000,
            "commission_rate": "12",
        }],
    })
    resolution = UnitPriceTariffResolver().resolve(
        seller_price_cents=10_000, identity=IDENTITY, sale_schema="FBO",
        effective_date=DAY, profiles=[stored, session],
        selected_profile_id=session["profile_id"],
        selected_revision=session["revision"],
        selected_state_revision=session["state_revision"],
    )
    snapshot = UnitPriceTariffSnapshotAdapter.freeze(
        resolution, session, candidate_profiles=[stored, session],
        effective_date=DAY,
    )

    candidate = UnitPriceTariffSnapshotAdapter.resolve_frozen(
        snapshot, IDENTITY, 9_500,
    )

    assert candidate["available"] is True
    assert candidate["commission_rate"] == "12"
    assert candidate["selected_profile"]["profile_id"] == "session-1"


def test_unknown_price_stays_unknown_and_never_reuses_saved_point_rate():
    snapshot = _frozen_snapshot()
    result = UnitPriceTariffSnapshotAdapter.resolve_frozen(
        snapshot, IDENTITY, 12_000,
    )

    assert result["available"] is False
    assert result["status"] == "UNKNOWN"
    assert result["commission_rate"] is None


def test_tampered_identity_price_revision_or_rate_rejects_saved_snapshot():
    snapshot = _frozen_snapshot()
    assert UnitPriceTariffSnapshotAdapter.validate(
        snapshot, {**IDENTITY, "store_id": "other-store"},
        {"price": "98", "commission_rate": "12"},
    ) is None
    assert UnitPriceTariffSnapshotAdapter.validate(
        snapshot, IDENTITY, {"price": "99", "commission_rate": "12"},
    ) is None
    assert UnitPriceTariffSnapshotAdapter.validate(
        snapshot, IDENTITY, {"price": "98", "commission_rate": "13"},
    ) is None
    changed_revision = deepcopy(snapshot)
    changed_revision["profiles"][0]["revision"] = 9
    assert UnitPriceTariffSnapshotAdapter.validate(
        changed_revision, IDENTITY, {"price": "98", "commission_rate": "12"},
    ) is None


def test_unknown_snapshot_requires_null_commission_and_allowlisted_reason():
    snapshot = {
        "snapshot_version": 1, "status": "UNKNOWN", "reason": "PRICE_OUTSIDE_PROFILE_BANDS",
        "effective_date": DAY, "price_basis": "SELLER_PRICE_RUB", "seller_price_cents": 12_000,
        "commission_rate": None, "matched_band": None, "selected_profile": None,
        "profiles": [_frozen_snapshot()["profiles"][0]],
    }
    assert UnitPriceTariffSnapshotAdapter.validate(
        snapshot, IDENTITY, {"price": "120", "commission_rate": None},
    ) == snapshot
    assert UnitPriceTariffSnapshotAdapter.validate(
        snapshot, IDENTITY, {"price": "120", "commission_rate": "12"},
    ) is None


def test_source_unavailable_snapshot_cannot_resolve_from_a_partial_profile_list():
    snapshot = UnitPriceTariffSnapshotAdapter.freeze(
        {
            "error": False, "available": False, "status": "SOURCE_UNAVAILABLE",
            "reason": "PROFILE_LIMIT", "seller_price_cents": 9_800,
            "price_basis": "SELLER_PRICE_RUB", "effective_date": DAY,
        },
        candidate_profiles=[_profile()], effective_date=DAY,
    )

    result = UnitPriceTariffSnapshotAdapter.resolve_frozen(snapshot, IDENTITY, 10_000)

    assert result["available"] is False
    assert result["status"] == "SOURCE_UNAVAILABLE"
    assert result["reason"] == "PROFILE_LIMIT"
    assert result.get("commission_rate") is None


def test_exact_manual_scenario_point_overrides_frozen_range_only_at_captured_price():
    range_profile = _profile()
    point_profile = {
        **_profile(),
        "profile_id": "manual-scenario-override",
        "origin": "MANUAL_SELLER_ASSUMPTION",
        "source_ref": "MANUAL_SCENARIO_COMMISSION_OVERRIDE",
        "recorded_at": "2026-10-27T11:00:00+00:00",
        "effective_from": "2026-10-27",
        "effective_to": "2026-10-27",
        "bands": [{
            "price_from_cents": 10_000,
            "price_to_cents": 10_000,
            "commission_rate": "13",
        }],
    }
    resolution = UnitPriceTariffResolver().resolve(
        seller_price_cents=10_000, identity=IDENTITY, sale_schema="FBO",
        effective_date=DAY, profiles=[range_profile, point_profile],
        selected_profile_id=point_profile["profile_id"],
        selected_revision=point_profile["revision"],
        selected_state_revision=point_profile["state_revision"],
    )
    snapshot = UnitPriceTariffSnapshotAdapter.freeze(
        resolution, point_profile,
        candidate_profiles=[range_profile, point_profile], effective_date=DAY,
    )

    exact = UnitPriceTariffSnapshotAdapter.resolve_frozen(snapshot, IDENTITY, 10_000)
    outside = UnitPriceTariffSnapshotAdapter.resolve_frozen(snapshot, IDENTITY, 10_500)

    assert exact["available"] is True
    assert exact["commission_rate"] == "13"
    assert outside["available"] is True
    assert outside["commission_rate"] == "14"
