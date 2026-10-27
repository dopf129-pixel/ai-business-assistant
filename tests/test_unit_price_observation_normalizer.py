from copy import deepcopy

from services.unit_price_observation_normalizer import UnitPriceObservationNormalizer


def _evidence():
    return {
        "error": False,
        "status": "INSUFFICIENT_DATA",
        "identity": {
            "store_id": "store-a", "product_id": "product-1",
            "offer_id": "offer-1", "sku": "sku-1", "sale_schema": "FBO",
        },
        "seller_price_cents": 10_000,
        "window": {
            "from": "2026-10-01", "to": "2026-10-07",
            "timezone": "Europe/Moscow", "date_basis": "SOURCE_CALENDAR_DATE",
        },
        "sources": [
            {
                "name": "FINANCE", "status": "COMPLETE", "complete": True,
                "row_count": 7, "source_date_basis": "OZON_ACCRUAL_DATE",
                "source_window_start": "2026-10-01", "source_window_end": "2026-10-07",
                "timezone": "Europe/Moscow", "posting_number": "must-not-pass-through",
            },
            {
                "name": "PERFORMANCE", "status": "COMPLETE", "complete": True,
                "row_count": 3, "source_date_basis": "PERFORMANCE_REPORT_DATE",
                "source_window_start": "2026-10-01", "source_window_end": "2026-10-07",
                "timezone": "Europe/Moscow",
            },
        ],
        "metrics": {
            "gross_seller_revenue": "1000.00", "discount_points": "100.00",
            "finance_net": "500.00", "acquiring": "-10.00",
            "commission": "-100.00", "logistics": "-200.00",
            "other_fees": "-190.00", "cpc_spend": "100.00",
            "source_row_count": 7, "sample_days": 7,
            "successful_sale_units": None, "ordered_units": None,
        },
        "completeness": {"finance": "CONFIRMED"},
        "warnings": [],
        "diagnostics": {"raw_response": "must-not-pass-through"},
        "account_totals": {"gross_seller_revenue": "999999.99"},
    }


def test_normalizer_keeps_partial_finance_and_performance_bases_separate():
    evidence = _evidence()
    evidence["metrics"]["attributed_revenue"] = "400.00"
    result = UnitPriceObservationNormalizer.normalize_collected(evidence)

    assert result["error"] is False
    assert result["status"] == "INCOMPARABLE"
    assert result["metrics"]["gross_seller_revenue"] == "1000.00"
    assert result["metrics"]["discount_points"] == "100.00"
    # FinanceService's aggregate zero does not prove that every sale row had
    # explicit discount-point evidence, so the tax base stays unknown.
    assert result["metrics"]["net_seller_revenue"] is None
    assert "DISCOUNT_POINTS_COMPLETENESS_NOT_CONFIRMED" in result["reasons"]
    assert result["metrics"]["finance_net"] == "500.00"
    assert result["metrics"]["cpc_spend"] == "100.00"
    # Accrual date and Performance report date do not prove a shared cohort.
    assert result["metrics"]["seller_revenue_drr_percent"] is None
    assert result["metrics"]["attributed_revenue_drr_percent"] == "25.00"
    assert result["metrics"]["successful_sale_units"] is None
    assert result["metrics"]["successful_unit_denominator"] is None
    assert result["completeness"]["deduplication"] == "UNKNOWN"
    assert result["completeness"]["price_history"] == "PRICE_HISTORY_UNCONFIRMED"
    assert "posting_number" not in str(result)
    assert "raw_response" not in str(result)
    assert "999999.99" not in str(result)
    assert any("DO_NOT_SUBTRACT_PERFORMANCE_CPC_AGAIN" in item for item in result["warnings"])
    assert any("DO_NOT_SUBTRACT_THEM_AGAIN" in item for item in result["warnings"])
    assert any("NOT_ALLOCATED_TO_THIS_SKU" in item for item in result["warnings"])
    assert "observed_profit_per_unit" not in result["metrics"]
    assert "profit_per_unit" not in result["metrics"]


def test_drr_percentages_use_explicitly_distinct_revenue_bases():
    evidence = _evidence()
    evidence["metrics"]["attributed_revenue"] = "400.00"
    evidence["metrics"]["discount_points_complete"] = True
    evidence["sources"][1]["source_date_basis"] = "OZON_ACCRUAL_DATE"

    result = UnitPriceObservationNormalizer.normalize_collected(evidence)

    assert result["metrics"]["seller_revenue_drr_percent"] == "10.00"
    assert result["metrics"]["attributed_revenue_drr_percent"] == "25.00"
    assert result["metrics"]["net_seller_revenue"] == "900.00"
    assert result["metrics"]["revenue_basis"].startswith("GROSS_SELLER_REVENUE")


def test_tax_base_is_not_calculated_from_partial_finance_or_missing_points():
    evidence = _evidence()
    evidence["sources"][0]["complete"] = False
    evidence["sources"][0]["status"] = "PARTIAL"

    result = UnitPriceObservationNormalizer.normalize_collected(evidence)

    assert result["metrics"]["gross_seller_revenue"] == "1000.00"
    assert result["metrics"]["net_seller_revenue"] is None
    assert result["completeness"]["finance"] == "PARTIAL"


def test_effective_date_warning_remains_mixed_price_risk():
    evidence = _evidence()
    evidence["warnings"] = ["WINDOW_INCLUDES_EFFECTIVE_DATE"]

    result = UnitPriceObservationNormalizer.normalize_collected(evidence)

    assert "WINDOW_MAY_CONTAIN_MIXED_PRICES_ON_EFFECTIVE_DATE" in result["reasons"]
    assert result["metrics"]["price_evidence_status"] == "PRICE_HISTORY_UNCONFIRMED"


def test_confirmed_mixed_price_window_stays_incomparable():
    evidence = _evidence()
    evidence["metrics"]["price_evidence_status"] = "MIXED_PRICES"

    result = UnitPriceObservationNormalizer.normalize_collected(evidence)

    assert result["status"] == "INCOMPARABLE"
    assert result["completeness"]["price_history"] == "MIXED_PRICES"
    assert "MULTIPLE_SELLER_PRICES_CONFIRMED_IN_WINDOW" in result["reasons"]


def test_weighted_aggregation_uses_sums_and_keeps_zero_denominator_unknown():
    aggregate = UnitPriceObservationNormalizer.weighted_ratio(
        [
            {"spend": "100.00", "units": 10},
            {"spend": "100.00", "units": 30},
        ],
        numerator_field="spend", denominator_field="units",
    )
    zero = UnitPriceObservationNormalizer.weighted_ratio(
        [{"spend": "100.00", "units": 0}],
        numerator_field="spend", denominator_field="units",
    )

    assert aggregate == {
        "status": "COMPLETE", "numerator": "200.00",
        "denominator": 40, "value": "5.00",
    }
    assert zero["status"] == "ZERO_DENOMINATOR"
    assert zero["value"] is None


def test_weighted_aggregation_does_not_fill_missing_denominator_with_zero():
    result = UnitPriceObservationNormalizer.weighted_ratio(
        [{"spend": "100.00", "units": 10}, {"spend": "50.00"}],
        numerator_field="spend", denominator_field="units",
    )

    assert result == {"status": "INCOMPLETE", "value": None}


def test_identical_rows_deduplicate_but_conflicting_duplicate_is_not_summed():
    base = {
        "units": 1, "seller_price_cents": 10_000, "date": "2026-10-01",
        "date_basis": "SALE_EVENT_DATE", "revenue_basis": "SELLER_REVENUE",
        "scope": "SKU", "sku": "sku-1", "is_correction": False,
    }
    rows = [
        {"row_id": "private-id", "amount": "-12.50", **base},
        {"row_id": "private-id", "amount": "-12.50", **base},
    ]
    identical = UnitPriceObservationNormalizer.deduplicate_rows(rows)
    conflict = UnitPriceObservationNormalizer.deduplicate_rows([
        rows[0], {"row_id": "private-id", "amount": "-13.00", **base},
    ])
    float_conflict = UnitPriceObservationNormalizer.deduplicate_rows([
        {"row_id": "float-id", "amount": 5.0, **base},
        {"row_id": "float-id", "amount": 6.0, **base},
    ])

    assert identical["status"] == "COMPLETE"
    assert identical["unique_row_count"] == 1
    assert identical["duplicate_count"] == 1
    assert len(identical["rows"]) == 1
    assert conflict == {"status": "CONFLICT", "rows": [], "duplicate_count": 0}
    assert float_conflict["status"] == "CONFLICT"
    assert "private-id" not in str(identical)


def test_deduplicator_accepts_only_explicit_sku_scoped_signed_correction_deltas():
    rows = [
        {
            "row_id": "sale-event", "amount": "-120.00", "units": 12,
            "date": "2026-10-01", "date_basis": "SALE_EVENT_DATE",
            "revenue_basis": "SELLER_REVENUE", "scope": "SKU", "sku": "sku-1",
            "seller_price_cents": 10_000, "is_correction": False,
        },
        {
            "row_id": "correction-event", "amount": "20.00", "units": 0,
            "date": "2026-10-02", "date_basis": "ACCRUAL_DATE",
            "revenue_basis": "SELLER_REVENUE", "scope": "SKU", "sku": "sku-1",
            "seller_price_cents": 10_000, "is_correction": True,
            "correction_of": "sale-event", "correction_semantics": "SIGNED_DELTA",
        },
    ]

    result = UnitPriceObservationNormalizer.deduplicate_rows(rows, expected_sku="sku-1")
    out_of_scope = UnitPriceObservationNormalizer.deduplicate_rows(
        [dict(rows[0], scope="ACCOUNT")], expected_sku="sku-1",
    )
    unknown_correction = UnitPriceObservationNormalizer.deduplicate_rows([
        dict(rows[1], correction_semantics="REPLACEMENT"),
    ], expected_sku="sku-1")

    assert result["status"] == "COMPLETE"
    assert [row["amount"] for row in result["rows"]] == ["-120.00", "20.00"]
    assert "row_id" not in result["rows"][0]
    assert "correction_of" not in result["rows"][1]
    assert out_of_scope["status"] == "OUT_OF_SCOPE"
    assert unknown_correction["status"] == "INCOMPLETE"


def test_signed_correction_amounts_are_preserved_by_decimal_weighted_aggregation():
    result = UnitPriceObservationNormalizer.weighted_ratio(
        [
            {"amount": "-120.00", "units": 12},
            {"amount": "20.00", "units": 0},  # signed correction delta
        ],
        numerator_field="amount", denominator_field="units",
    )

    assert result["numerator"] == "-100.00"
    assert result["denominator"] == 12
    assert result["value"] == "-8.33"


def test_invalid_finance_amount_or_negative_tax_base_fails_closed():
    invalid = _evidence()
    invalid["metrics"]["finance_net"] = "NaN"
    assert UnitPriceObservationNormalizer.normalize_collected(invalid)["code"] == "OBSERVATION_AMOUNT_INVALID"

    negative_base = _evidence()
    negative_base["metrics"]["discount_points"] = "1001.00"
    negative_base["metrics"]["discount_points_complete"] = True
    assert UnitPriceObservationNormalizer.normalize_collected(negative_base)["code"] == "OBSERVATION_REVENUE_BASIS_INVALID"


def test_normalizer_does_not_mutate_source_evidence():
    evidence = _evidence()
    before = deepcopy(evidence)

    UnitPriceObservationNormalizer.normalize_collected(evidence)

    assert evidence == before
