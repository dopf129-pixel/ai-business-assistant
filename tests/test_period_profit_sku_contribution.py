from period_profit_sku_contribution import (
    build_period_profit_sku_contribution,
)


def _summary(profit, rows):
    return {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "profit": profit,
        "finance_sku_scope_applied": True,
        "product_revenue_reconciled": True,
        "product_count": len(rows),
        "products": rows,
    }


def _row(sku, profit, *, product_id=None, offer_id=None, catalog_sku=None):
    return {
        "sku": sku,
        "product_id": product_id,
        "offer_id": offer_id,
        "catalog_sku": catalog_sku,
        "profit": profit,
    }


def _contract(current_profit, previous_profit, *, ready=True):
    return {
        "error": False,
        "read_only": True,
        "executed": False,
        "profit_bases": {
            "B": {
                "status": "CONFIRMED" if ready else "UNAVAILABLE",
                "current_value": current_profit,
                "previous_value": previous_profit,
            }
        },
    }


def test_reference_sku_deltas_reconcile_to_store_with_account_residual():
    previous_rows = [
        _row("sku-a-old", 10000, product_id="1", offer_id="a"),
        _row("sku-b", 3000, product_id="2", offer_id="b"),
        _row("sku-c", 1000, product_id="3", offer_id="c"),
    ]
    current_rows = [
        _row("sku-a", 8000, product_id="1", offer_id="a"),
        _row("sku-b", 7000, product_id="2", offer_id="b"),
        _row("sku-c", 2000, product_id="3", offer_id="c"),
    ]

    result = build_period_profit_sku_contribution(
        _contract(19300, 15200),
        _summary(19300, current_rows),
        _summary(15200, previous_rows),
    )

    assert result["status"] == "PERIOD_PROFIT_SKU_CONTRIBUTION_READY"
    assert result["top_growth"][0]["sku"] == "sku-b"
    assert result["top_growth"][0]["delta"] == 4000
    assert result["top_decline"][0]["sku"] == "sku-a"
    assert result["top_decline"][0]["delta"] == -2000
    assert result["matched_sku_profit_delta"] == 3000
    assert result["store_profit_delta"] == 4100
    assert result["store_minus_sku_delta"] == 1100
    assert result["unmatched_rows_are_zero"] is False
    assert result["read_only"] is True
    assert result["executed"] is False


def test_exact_confirmed_catalog_identity_matches_changed_finance_sku():
    result = build_period_profit_sku_contribution(
        _contract(24, 20),
        _summary(
            24,
            [_row("finance-new", 24, product_id=71, offer_id="offer-1", catalog_sku="catalog-1")],
        ),
        _summary(
            20,
            [_row("finance-legacy", 20, product_id=71, offer_id="offer-1", catalog_sku="catalog-1")],
        ),
    )

    assert result["matched_sku_count"] == 1
    assert result["top_growth"][0]["previous_sku"] == "finance-legacy"
    assert result["top_growth"][0]["current_sku"] == "finance-new"
    assert result["top_growth"][0]["delta"] == 4


def test_absent_counterpart_is_not_silently_treated_as_zero():
    result = build_period_profit_sku_contribution(
        _contract(500, 0),
        _summary(500, [_row("new-sku", 500, product_id="new", offer_id="new-offer")]),
        _summary(0, []),
    )

    assert result["status"] == "PERIOD_PROFIT_SKU_CONTRIBUTION_PARTIAL"
    assert result["coverage_status"] == "PARTIAL"
    assert result["top_growth"] == []
    assert result["matched_sku_profit_delta"] == 0
    assert result["store_minus_sku_delta"] == 500
    assert result["unmatched_current_count"] == 1
    assert result["unmatched_rows_are_zero"] is False


def test_conflicting_or_ambiguous_identity_never_merges_variants():
    conflicting = build_period_profit_sku_contribution(
        _contract(20, 10),
        _summary(20, [_row("same-sku", 20, product_id="current", offer_id="offer")]),
        _summary(10, [_row("same-sku", 10, product_id="retired", offer_id="offer")]),
    )
    assert conflicting["matched_sku_count"] == 0
    assert conflicting["unmatched_current_count"] == 1
    assert conflicting["unmatched_previous_count"] == 1

    ambiguous = build_period_profit_sku_contribution(
        _contract(30, 10),
        _summary(
            30,
            [
                _row("current-1", 10, offer_id="duplicate"),
                _row("current-2", 20, offer_id="duplicate"),
            ],
        ),
        _summary(
            10,
            [
                _row("previous-1", 5, offer_id="duplicate"),
                _row("previous-2", 5, offer_id="duplicate"),
            ],
        ),
    )
    assert ambiguous["matched_sku_count"] == 0
    assert ambiguous["ambiguous_identity_count"] == 4
    assert ambiguous["top_growth"] == []


def test_deterministic_ties_and_only_five_ranked_rows_are_exposed():
    previous_rows = [
        _row(f"sku-{index:02}", 1, product_id=str(index), offer_id=f"o-{index}")
        for index in range(14)
    ]
    current_rows = [
        _row(
            f"sku-{index:02}",
            2 if index < 7 else 0,
            product_id=str(index),
            offer_id=f"o-{index}",
        )
        for index in range(14)
    ]
    result = build_period_profit_sku_contribution(
        _contract(14, 14),
        _summary(14, current_rows),
        _summary(14, previous_rows),
    )

    assert [row["sku"] for row in result["top_growth"]] == [
        "sku-00", "sku-01", "sku-02", "sku-03", "sku-04"
    ]
    assert [row["sku"] for row in result["top_decline"]] == [
        "sku-07", "sku-08", "sku-09", "sku-10", "sku-11"
    ]


def test_unconfirmed_contract_or_incomplete_summary_coverage_is_unavailable():
    current = _summary(10, [])
    previous = _summary(10, [])
    assert build_period_profit_sku_contribution(
        _contract(10, 10, ready=False), current, previous
    )["coverage_status"] == "UNAVAILABLE"

    del current["product_revenue_reconciled"]
    assert build_period_profit_sku_contribution(
        _contract(10, 10), current, previous
    )["code"] == "PERIOD_PROFIT_SKU_SUMMARY_COVERAGE_UNAVAILABLE"


def test_invalid_row_money_and_store_contract_mismatch_fail_closed():
    invalid_row = build_period_profit_sku_contribution(
        _contract(10, 10),
        _summary(10, [_row("sku", float("nan"), product_id="1", offer_id="a")]),
        _summary(10, [_row("sku", 10, product_id="1", offer_id="a")]),
    )
    assert invalid_row["coverage_status"] == "UNAVAILABLE"
    assert invalid_row["code"] == "PERIOD_PROFIT_SKU_ROW_PROFIT_INVALID"

    mismatch = build_period_profit_sku_contribution(
        _contract(11, 10),
        _summary(10, []),
        _summary(10, []),
    )
    assert mismatch["coverage_status"] == "UNAVAILABLE"
    assert mismatch["code"] == "PERIOD_PROFIT_SKU_STORE_PROFIT_MISMATCH"
