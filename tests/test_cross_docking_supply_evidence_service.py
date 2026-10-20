from datetime import date, timedelta, timezone

import pytest

from services.cross_docking_supply_evidence_service import (
    CrossDockingSupplyEvidenceService,
)


@pytest.fixture
def service(monkeypatch):
    # Windows pytest runs without the operating-system IANA database; production
    # installs tzdata. Use Moscow's configured +03 offset for deterministic
    # pure-function boundary tests, and test missing tzdata separately below.
    monkeypatch.setattr(
        CrossDockingSupplyEvidenceService,
        "resolve_timezone",
        classmethod(lambda cls: timezone(timedelta(hours=3))),
    )
    return CrossDockingSupplyEvidenceService()


def _source(
    *,
    order_id=1001,
    supply_id=2001,
    sku=3921245627,
    fact_quantity=100,
    declared_quantity=200,
    order_state="COMPLETED",
    supply_state="COMPLETED",
    is_crossdock=True,
    state_updated_date="2026-09-29T09:22:15.203154Z",
    act_state="ACCEPTED",
    act_type="ACCEPTANCE",
    summary_quantity=100,
    summary_unidentified=0,
    product_act_id=3001,
    summary_act_id=3001,
    items=None,
):
    order = {
        "order_id": order_id,
        "state": order_state,
        "state_updated_date": state_updated_date,
        "supplies": [
            {
                "supply_id": supply_id,
                "state": supply_state,
                "is_crossdock": is_crossdock,
            }
        ],
    }
    if items is None:
        items = [
            {
                "sku_info": {"sku": sku},
                "declared_quantity": declared_quantity,
                "approved_quantity": 100,
                "fact_quantity": fact_quantity,
            }
        ]
    summary = {
        str(order_id): {
            "error": False,
            "supplies_acts": [
                {
                    "supply_id": supply_id,
                    "is_agreement_completed": True,
                    "supply_acts": [
                        {
                            "act_id": summary_act_id,
                            "act_state": act_state,
                            "type": act_type,
                            "created_date": "2026-09-28T12:00:00Z",
                            "summary": {
                                "fact_quantity": summary_quantity,
                                "approved_quantity": 0,
                                "unidentified_quantity": summary_unidentified,
                            },
                        }
                    ],
                }
            ],
        }
    }
    products = {
        str(supply_id): {
            "error": False,
            "supply_acts": [
                {
                    "act_id": product_act_id,
                    "type": "ACCEPTANCE",
                    "items": items,
                }
            ],
        }
    }
    return order, summary, products


def _normalize(service, source, **kwargs):
    order, summaries, products = source
    return service.normalize_window(
        orders=[order],
        summaries_by_order_id=summaries,
        products_by_supply_id=products,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
        **kwargs,
    )


def test_uses_fact_quantity_for_partial_receipt_and_maps_one_supply_to_one_sku(service):
    result = _normalize(
        service,
        _source(fact_quantity=100, declared_quantity=200, summary_quantity=100),
    )

    assert result.status == "COMPLETE"
    assert result.total_units == 100
    assert result.units_by_sku == (("3921245627", 100),)
    assert result.supplies[0].completed_date == date(2026, 9, 29)
    assert result.supplies[0].sku == "3921245627"
    assert len(result.supplies[0].identity_fingerprint) == 64
    assert result.supplies[0].identity_fingerprint != "2001"


def test_summary_approved_quantity_and_declared_quantity_do_not_replace_fact(service):
    result = _normalize(
        service,
        _source(fact_quantity=100, declared_quantity=200, summary_quantity=100),
    )

    assert result.complete is True
    assert result.total_units == 100


def test_moscow_local_calendar_date_controls_window_boundary(service):
    order, summaries, products = _source(
        state_updated_date="2026-08-31T22:00:00Z"
    )

    result = service.normalize_window(
        orders=[order],
        summaries_by_order_id=summaries,
        products_by_supply_id=products,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 1),
    )

    assert result.status == "COMPLETE"
    assert result.total_units == 100
    assert result.supplies[0].completed_date == date(2026, 9, 1)


def test_outside_window_supply_is_not_requested_or_counted(service):
    result = _normalize(
        service,
        _source(state_updated_date="2026-08-31T20:00:00Z"),
    )

    assert result.status == "NO_CROSSDOCK_SUPPLIES"
    assert result.total_units == 0
    assert result.excluded_outside_window == 1


def test_direct_supply_is_excluded_as_observed_no_crossdock_supply(service):
    order, _, _ = _source(is_crossdock=False)
    result = service.normalize_window(
        orders=[order],
        summaries_by_order_id={},
        products_by_supply_id={},
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )

    assert result.status == "NO_CROSSDOCK_SUPPLIES"
    assert result.total_units == 0
    assert result.excluded_direct_supplies == 1


def test_noncompleted_crossdock_supply_fails_closed(service):
    result = _normalize(service, _source(supply_state="CANCELLED"))

    assert result.status == "INCOMPLETE"
    assert result.total_units is None
    assert "CROSSDOCK_SUPPLY_NOT_COMPLETED" in result.issue_codes


def test_unknown_crossdock_flag_fails_closed(service):
    result = _normalize(service, _source(is_crossdock=None))

    assert result.status == "INCOMPLETE"
    assert result.total_units is None
    assert "CROSSDOCK_FLAG_UNKNOWN" in result.issue_codes


def test_multi_supply_order_is_not_assigned_one_parent_timestamp(service):
    order, summaries, products = _source()
    order["supplies"].append(
        {"supply_id": 2002, "state": "COMPLETED", "is_crossdock": True}
    )
    result = service.normalize_window(
        orders=[order],
        summaries_by_order_id=summaries,
        products_by_supply_id=products,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )

    assert result.status == "INCOMPLETE"
    assert result.total_units is None
    assert "MULTI_SUPPLY_COMPLETION_DATE_UNVERIFIED" in result.issue_codes


def test_old_multi_supply_order_does_not_make_current_window_incomplete(service):
    order, summaries, products = _source(
        state_updated_date="2026-08-31T20:00:00Z"
    )
    order["supplies"].append(
        {"supply_id": 2002, "state": "COMPLETED", "is_crossdock": True}
    )

    result = service.normalize_window(
        orders=[order],
        summaries_by_order_id=summaries,
        products_by_supply_id=products,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )

    assert result.status == "NO_CROSSDOCK_SUPPLIES"
    assert result.total_units == 0
    assert result.excluded_outside_window == 2


def test_acceptance_act_must_match_exact_act_id(service):
    result = _normalize(service, _source(product_act_id=3002))

    assert result.status == "INCOMPLETE"
    assert "ACT_PRODUCT_ID_MISMATCH_OR_AMBIGUOUS" in result.issue_codes


def test_acceptance_act_must_be_accepted(service):
    result = _normalize(service, _source(act_state="PENDING"))

    assert result.status == "INCOMPLETE"
    assert "ACCEPTED_ACT_MISSING_OR_AMBIGUOUS" in result.issue_codes


def test_supply_acceptance_must_be_agreed(service):
    source = _source()
    source[1]["1001"]["supplies_acts"][0]["is_agreement_completed"] = False
    result = _normalize(service, source)

    assert result.status == "INCOMPLETE"
    assert "SUPPLY_ACCEPTANCE_AGREEMENT_INCOMPLETE" in result.issue_codes


def test_nonzero_or_unknown_unidentified_quantity_fails_closed(service):
    nonzero = _normalize(service, _source(summary_unidentified=1))
    missing_source = _source()
    missing_source[1]["1001"]["supplies_acts"][0]["supply_acts"][0][
        "summary"
    ].pop("unidentified_quantity")
    unknown = _normalize(service, missing_source)

    assert nonzero.status == "INCOMPLETE"
    assert "UNIDENTIFIED_QUANTITY_PRESENT" in nonzero.issue_codes
    assert unknown.status == "INCOMPLETE"
    assert "UNIDENTIFIED_QUANTITY_UNKNOWN" in unknown.issue_codes


def test_more_than_one_distinct_sku_in_supply_fails_closed(service):
    items = [
        {"sku_info": {"sku": 10}, "fact_quantity": 2},
        {"sku_info": {"sku": 11}, "fact_quantity": 3},
    ]
    result = _normalize(service, _source(items=items, summary_quantity=5))

    assert result.status == "INCOMPLETE"
    assert "SUPPLY_PRODUCT_IDENTITY_AMBIGUOUS" in result.issue_codes


@pytest.mark.parametrize(
    "value",
    [None, -1, 1.5, True, "100"],
)
def test_invalid_fact_quantity_fails_closed(service, value):
    items = [{"sku_info": {"sku": 12}, "fact_quantity": value}]
    result = _normalize(service, _source(items=items, summary_quantity=0))

    assert result.status == "INCOMPLETE"
    assert "FACT_QUANTITY_MISSING_OR_INVALID" in result.issue_codes


def test_product_quantity_must_reconcile_to_accepted_act_summary(service):
    result = _normalize(service, _source(fact_quantity=100, summary_quantity=99))

    assert result.status == "INCOMPLETE"
    assert "ACT_SUMMARY_PRODUCT_QUANTITY_MISMATCH" in result.issue_codes


def test_missing_summary_fact_quantity_fails_closed(service):
    source = _source()
    source[1]["1001"]["supplies_acts"][0]["supply_acts"][0]["summary"].pop(
        "fact_quantity"
    )
    result = _normalize(service, source)

    assert result.status == "INCOMPLETE"
    assert "ACT_SUMMARY_FACT_QUANTITY_UNKNOWN" in result.issue_codes


def test_incomplete_source_pages_never_publish_partial_unit_total(service):
    result = _normalize(service, _source(), list_complete=False)

    assert result.status == "INCOMPLETE"
    assert result.total_units is None
    assert "SUPPLY_LIST_INCOMPLETE" in result.issue_codes


def test_missing_order_details_never_publish_partial_unit_total(service):
    order, summaries, products = _source()
    result = service.normalize_window(
        orders=[order],
        summaries_by_order_id=summaries,
        products_by_supply_id=products,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
        expected_order_ids=[order["order_id"], 1002],
    )

    assert result.status == "INCOMPLETE"
    assert result.total_units is None
    assert "SUPPLY_DETAILS_MISSING_ORDER" in result.issue_codes


def test_identical_duplicate_order_does_not_double_count_supply(service):
    order, summaries, products = _source()
    result = service.normalize_window(
        orders=[order, order.copy()],
        summaries_by_order_id=summaries,
        products_by_supply_id=products,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )

    assert result.status == "COMPLETE"
    assert result.total_units == 100
    assert len(result.supplies) == 1


def test_conflicting_duplicate_order_fails_closed(service):
    order, summaries, products = _source()
    conflicting = {**order, "state_updated_date": "2026-09-30T09:22:15Z"}
    result = service.normalize_window(
        orders=[order, conflicting],
        summaries_by_order_id=summaries,
        products_by_supply_id=products,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )

    assert result.status == "INCOMPLETE"
    assert result.total_units is None
    assert "CONFLICTING_DUPLICATE_ORDER" in result.issue_codes


def test_missing_timezone_database_fails_closed(monkeypatch):
    monkeypatch.setattr(
        CrossDockingSupplyEvidenceService,
        "resolve_timezone",
        classmethod(lambda cls: None),
    )
    service = CrossDockingSupplyEvidenceService()
    result = _normalize(service, _source())

    assert result.status == "INCOMPLETE"
    assert result.total_units is None
    assert "TIMEZONE_DATA_UNAVAILABLE" in result.issue_codes
