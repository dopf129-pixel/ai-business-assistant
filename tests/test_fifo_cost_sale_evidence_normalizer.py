from services.fifo_cost_sale_evidence_normalizer import (
    FifoCostSaleEvidenceNormalizer,
)


def _normalize(**overrides):
    values = {
        "store_id": "store-a",
        "posting_number": "posting-a",
        "finance_sku": "old-catalog-sku",
        "identity": {
            "offer_id": "seller-offer",
            "product_id": "product-1",
            "mapping_confirmed": True,
        },
        "quantity": 3,
        "sale_authority": "OZON_REALIZATION_REPORT",
        "sale_authority_confirmed": True,
        "financial_accrual_dates": ["2026-08-31", "2026-09-01", "2026-08-31"],
    }
    values.update(overrides)
    return FifoCostSaleEvidenceNormalizer().normalize_sale(**values)


def test_fc15_sale_identity_survives_catalog_sku_rewrite_for_same_confirmed_offer():
    old = _normalize(finance_sku="old-catalog-sku")
    new = _normalize(finance_sku="new-catalog-sku")

    assert old["error"] is False
    assert new["error"] is False
    assert old["source_identity_digest"] == new["source_identity_digest"]
    assert old["quantity"] == new["quantity"] == 3
    assert "posting-a" not in old["source_identity_digest"]
    assert "old-catalog-sku" not in old["source_identity_digest"]


def test_fc15_sale_identity_is_scoped_to_store_posting_and_stable_product():
    baseline = _normalize()

    assert _normalize(store_id="store-b")["source_identity_digest"] != baseline[
        "source_identity_digest"
    ]
    assert _normalize(posting_number="posting-b")["source_identity_digest"] != baseline[
        "source_identity_digest"
    ]
    assert _normalize(identity={
        "offer_id": "different-offer",
        "product_id": "product-1",
        "mapping_confirmed": True,
    })["source_identity_digest"] != baseline["source_identity_digest"]


def test_fc15_financial_accrual_dates_are_deduplicated_but_never_used_as_sale_date():
    result = _normalize()

    assert result["financial_accrual_dates"] == ["2026-08-31", "2026-09-01"]
    assert result["physical_effective_date"] is None
    assert result["status"] == "IDENTITY_CONFIRMED_TIME_UNAVAILABLE"
    assert result["allocation_eligible"] is False


def test_fc15_reported_date_needs_explicit_semantics_and_cutoff_proof():
    unconfirmed = _normalize(
        physical_effective_date="2026-08-31",
        financial_accrual_dates=["2026-09-01"],
    )
    date_confirmed = _normalize(
        physical_effective_date="2026-08-31",
        effective_date_semantics_confirmed=True,
    )
    complete = _normalize(
        physical_effective_date="2026-08-31",
        effective_date_semantics_confirmed=True,
        inventory_cutoff_bridge_confirmed=True,
    )

    assert unconfirmed["physical_effective_date"] is None
    assert unconfirmed["allocation_eligible"] is False
    assert date_confirmed["physical_effective_date"] == "2026-08-31"
    assert date_confirmed["status"] == "IDENTITY_CONFIRMED_CUTOFF_UNRECONCILED"
    assert date_confirmed["allocation_eligible"] is False
    assert complete["status"] == "READY_FOR_FIFO_EVENT"
    assert complete["allocation_eligible"] is True


def test_fc15_requires_supported_physical_sale_authority_and_stable_identity():
    assert _normalize(sale_authority="FBO_POSTING_STATUS") == {
        "error": True,
        "code": "FIFO_SALE_AUTHORITY_UNSUPPORTED",
    }
    assert _normalize(sale_authority_confirmed=False) == {
        "error": True,
        "code": "FIFO_SALE_AUTHORITY_UNCONFIRMED",
    }
    assert _normalize(identity={
        "offer_id": None,
        "product_id": None,
        "mapping_confirmed": True,
    }) == {
        "error": True,
        "code": "FIFO_SALE_STABLE_PRODUCT_KEY_UNAVAILABLE",
    }


def test_fc15_rejects_invalid_quantity_and_date_without_silent_fallback():
    for quantity in (True, 0, -1, 1.5, 100_001):
        result = _normalize(quantity=quantity)
        assert result == {"error": True, "code": "FIFO_SALE_QUANTITY_INVALID"}

    assert _normalize(financial_accrual_dates=["not-a-date"]) == {
        "error": True,
        "code": "FIFO_SALE_FINANCE_DATES_INVALID",
    }
    assert _normalize(physical_effective_date="2026-02-30") == {
        "error": True,
        "code": "FIFO_SALE_PHYSICAL_DATE_INVALID",
    }
