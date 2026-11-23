from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from zoneinfo import ZoneInfo

import pytest

from services.fifo_cost_provisional_replay_service import FifoCostProvisionalReplayService
from services.fifo_cost_provisional_timeline_contracts import (
    ProvisionalEventSource as Source,
    ProvisionalStockZone as Zone,
    ProvisionalTimelineEvent,
    ProvisionalTimelineEventKind as Kind,
    ProvisionalTimelineIssue as Issue,
)


SCOPE = "a" * 64
SKU = "123456789"
START = date(2026, 11, 6)
END = date(2026, 11, 30)
SERVICE = FifoCostProvisionalReplayService()


def _digest(value):
    return sha256(value.encode()).hexdigest()


def _event(kind, reference, *, qty=1, day=None, at=None,
           precision="INSTANT", posting=None, zone=None, resellable=None,
           source=Source.OWNER_MOVEMENTS_CSV):
    moment = datetime.fromisoformat(at) if at else None
    if day is None:
        day = (moment.astimezone(ZoneInfo("Europe/Moscow")).date().isoformat()
               if moment else "2026-11-07")
    return ProvisionalTimelineEvent(
        event_key=_digest("event:" + reference),
        source_key=_digest("source:" + reference),
        scope_fingerprint=SCOPE,
        event_kind=kind,
        finance_sku=SKU,
        quantity=qty,
        local_date=date.fromisoformat(day),
        effective_at_utc=moment,
        time_precision=precision,
        source=source,
        posting_key=_digest("posting:" + posting) if posting else None,
        stock_zone=zone,
        resellable=resellable,
    )


def _replay(events, *, opening=0, caps=None, old="21.00", new="14.65"):
    return SERVICE.replay(
        events=events,
        scope_fingerprint=SCOPE,
        finance_sku=SKU,
        timezone_name="Europe/Moscow",
        model_start=START,
        model_end=END,
        opening_available_units=opening,
        old_unit_cost_rub=old,
        new_unit_cost_rub=new,
        posting_capacities=caps or {},
    )


def test_dispatch_splits_between_finite_layers_and_reserves_but_does_not_expense_cogs():
    receipt = _event(
        Kind.SUPPLY_RECEIVED, "receipt", qty=4, at="2026-11-07T10:00:00+03:00",
        zone=Zone.AVAILABLE,
    )
    dispatch = _event(
        Kind.BUYER_DISPATCH, "dispatch", qty=5, at="2026-11-08T10:00:00+03:00",
        posting="p-1",
    )

    result = _replay((dispatch, receipt), opening=3, caps={dispatch.posting_key: 5})

    assert result.status == "REPLAY_OK"
    assert result.complete is True
    allocations = result.buyer_dispatch_reserves[dispatch.posting_key]
    assert [(row.quantity, row.unit_cost_rub) for row in allocations] == [
        (3, Decimal("21.00")), (2, Decimal("14.65")),
    ]
    assert result.buyer_dispatch_units_total == 5
    assert result.pending_reserve_units == 5
    assert result.pending_reserve_cost_rub == Decimal("92.30")
    assert result.dispatch_cogs_rub == Decimal("0.00")
    assert result.available_units == 2
    assert result.factual_writes == 0
    assert result.read_only is True


def test_opening_transit_link_creates_separate_old_cost_reserve_without_touching_available_stock():
    link = _event(
        Kind.OPENING_TRANSIT_LINK, "opening", qty=3, day="2026-11-05",
        precision="DAY", posting="old-p",
    )

    result = _replay((link,), opening=7, caps={link.posting_key: 5})

    reserve = result.opening_transit_reserves[link.posting_key]
    assert [(row.quantity, row.unit_cost_rub) for row in reserve] == [(3, Decimal("21.00"))]
    assert result.available_units == 7
    assert result.buyer_dispatch_units_total == 0
    assert result.pending_reserve_units == 3
    assert result.dispatch_cogs_rub == Decimal("0.00")


def test_pre_window_dispatch_buyout_keeps_old_cost_and_does_not_respend_opening_stock():
    link = _event(
        Kind.OPENING_TRANSIT_LINK, "opening", qty=2, day="2026-11-05",
        precision="DAY", posting="old-p",
    )
    receipt = _event(
        Kind.SUPPLY_RECEIVED, "receipt", qty=3, at="2026-11-07T09:00:00+03:00",
        zone=Zone.AVAILABLE,
    )
    buyout = _event(
        Kind.BUYOUT, "old-buyout", qty=2, at="2026-11-07T10:00:00+03:00",
        posting="old-p",
    )

    result = _replay((link, receipt, buyout), opening=4,
                     caps={link.posting_key: 2})

    assert result.complete is True
    assert result.gross_buyout_cogs_rub == Decimal("42.00")
    assert result.available_units == 7
    assert result.pending_reserve_units == 0
    assert result.opening_transit_reserves == {}


def test_identical_duplicate_event_is_idempotent_and_does_not_double_reserve():
    dispatch = _event(
        Kind.BUYER_DISPATCH, "dispatch", qty=2, at="2026-11-08T10:00:00+03:00",
        posting="p-1",
    )

    result = _replay((dispatch, dispatch), opening=3, caps={dispatch.posting_key: 2})

    assert result.complete is True
    assert result.events_processed == 1
    assert result.buyer_dispatch_units_total == 2
    assert result.pending_reserve_units == 2
    assert result.available_units == 1


def test_same_event_key_with_changed_payload_is_a_conflict():
    original = _event(
        Kind.BUYER_DISPATCH, "dispatch", qty=1, at="2026-11-08T10:00:00+03:00",
        posting="p-1",
    )
    changed = replace(original, quantity=2)

    result = _replay((original, changed), opening=3,
                     caps={original.posting_key: 3})

    assert result.issue_codes == (Issue.EVENT_DUPLICATE_CONFLICT,)
    assert result.events_processed == 0


def test_distinct_dispatch_events_cannot_claim_the_same_posting_twice():
    first = _event(
        Kind.BUYER_DISPATCH, "dispatch-a", qty=1, at="2026-11-08T10:00:00+03:00",
        posting="p-1",
    )
    second = _event(
        Kind.BUYER_DISPATCH, "dispatch-b", qty=1, at="2026-11-08T11:00:00+03:00",
        posting="p-1",
    )

    result = _replay((first, second), opening=3, caps={first.posting_key: 2})

    assert result.issue_codes == (Issue.TIMELINE_DUPLICATE_POSTING,)
    assert result.events_processed == 0


def test_dispatch_cannot_drive_available_stock_below_zero():
    dispatch = _event(
        Kind.BUYER_DISPATCH, "dispatch", qty=2, at="2026-11-08T10:00:00+03:00",
        posting="p-1",
    )

    result = _replay((dispatch,), opening=1, caps={dispatch.posting_key: 2})

    assert result.status == "REPLAY_GAP"
    assert result.issue_codes == (Issue.TIMELINE_NEGATIVE_AVAILABLE_STOCK,)
    assert result.available_units == 1
    assert result.buyer_dispatch_units_total == 0
    assert result.dispatch_cogs_rub == Decimal("0.00")


def test_opening_link_requires_a_known_posting_capacity_and_cannot_exceed_it():
    link = _event(
        Kind.OPENING_TRANSIT_LINK, "opening", qty=3, day="2026-11-05",
        precision="DAY", posting="old-p",
    )

    absent = _replay((link,), opening=4)
    excess = _replay((link,), opening=4, caps={link.posting_key: 2})

    assert absent.issue_codes == (Issue.TIMELINE_OPENING_LINK_INVALID,)
    assert excess.issue_codes == (Issue.TIMELINE_OPENING_LINK_INVALID,)


def test_opening_links_for_one_posting_are_bounded_in_aggregate():
    first = _event(
        Kind.OPENING_TRANSIT_LINK, "opening-a", qty=2, day="2026-11-05",
        precision="DAY", posting="old-p",
    )
    second = _event(
        Kind.OPENING_TRANSIT_LINK, "opening-b", qty=2, day="2026-11-05",
        precision="DAY", posting="old-p",
    )

    result = _replay((first, second), opening=1, caps={first.posting_key: 3})

    assert result.issue_codes == (Issue.TIMELINE_OPENING_LINK_INVALID,)


def test_same_day_events_without_an_order_proof_are_not_stably_guessed():
    receipt = _event(
        Kind.SUPPLY_RECEIVED, "receipt", qty=2, day="2026-11-07", precision="DAY",
        zone=Zone.AVAILABLE,
    )
    dispatch = _event(
        Kind.BUYER_DISPATCH, "dispatch", qty=2, day="2026-11-07", precision="DAY",
        posting="p-1",
    )

    result = _replay((dispatch, receipt), opening=0, caps={dispatch.posting_key: 2})

    assert result.issue_codes == (Issue.TIMELINE_EVENT_ORDER_AMBIGUOUS,)
    assert result.events_processed == 0
    assert result.buyer_dispatch_units_total == 0


def test_distinct_confirmed_instants_on_same_day_are_replayed_in_time_order():
    receipt = _event(
        Kind.SUPPLY_RECEIVED, "receipt", qty=2, at="2026-11-07T10:00:00+03:00",
        zone=Zone.AVAILABLE,
    )
    dispatch = _event(
        Kind.BUYER_DISPATCH, "dispatch", qty=2, at="2026-11-07T11:00:00+03:00",
        posting="p-1",
    )

    result = _replay((dispatch, receipt), opening=0, caps={dispatch.posting_key: 2})

    assert result.complete is True
    assert result.buyer_dispatch_reserves[dispatch.posting_key][0].unit_cost_rub == Decimal("14.65")
    assert result.available_units == 0


def test_supply_in_held_zone_keeps_its_layer_and_is_not_available_for_dispatch():
    receipt = _event(
        Kind.SUPPLY_RECEIVED, "receipt", qty=4, at="2026-11-07T10:00:00+03:00",
        zone=Zone.CHECKING,
    )
    dispatch = _event(
        Kind.BUYER_DISPATCH, "dispatch", qty=3, at="2026-11-08T10:00:00+03:00",
        posting="p-1",
    )

    result = _replay((receipt, dispatch), opening=2, caps={dispatch.posting_key: 3})

    assert result.issue_codes == (Issue.TIMELINE_NEGATIVE_AVAILABLE_STOCK,)
    assert result.available_units == 2
    assert result.held_units_by_zone == {"checking": 4}
    assert result.held_layers[0].unit_cost_rub == Decimal("14.65")


def test_buyout_consumes_exact_dispatch_reserve_and_is_the_first_gross_cogs_event():
    receipt = _event(
        Kind.SUPPLY_RECEIVED, "receipt", qty=3, at="2026-11-07T09:00:00+03:00",
        zone=Zone.AVAILABLE,
    )
    dispatch = _event(
        Kind.BUYER_DISPATCH, "dispatch", qty=2, at="2026-11-07T10:00:00+03:00",
        posting="p-1",
    )
    buyout = _event(
        Kind.BUYOUT, "buyout", qty=2, at="2026-11-08T10:00:00+03:00",
        posting="p-1",
    )

    result = _replay((receipt, dispatch, buyout), opening=1,
                     caps={dispatch.posting_key: 2})

    assert result.complete is True
    assert result.buyer_dispatch_reserves == {}
    assert result.pending_reserve_units == 0
    assert [line.quantity for line in result.bought_out_allocations[buyout.posting_key]] == [1, 1]
    assert [line.unit_cost_rub for line in result.bought_out_allocations[buyout.posting_key]] == [
        Decimal("21.00"), Decimal("14.65"),
    ]
    assert result.gross_buyout_cogs_rub == Decimal("35.65")
    assert result.dispatch_cogs_rub == Decimal("0.00")
    assert result.available_units == 2


def test_partial_sale_return_restores_last_consumed_layer_without_reversing_gross_cogs():
    receipt = _event(
        Kind.SUPPLY_RECEIVED, "receipt", qty=2, at="2026-11-07T09:00:00+03:00",
        zone=Zone.AVAILABLE,
    )
    dispatch = _event(
        Kind.BUYER_DISPATCH, "dispatch", qty=3, at="2026-11-07T10:00:00+03:00",
        posting="p-1",
    )
    buyout = _event(
        Kind.BUYOUT, "buyout", qty=3, at="2026-11-08T10:00:00+03:00",
        posting="p-1",
    )
    returned = _event(
        Kind.SALE_RETURN_RESTOCK, "sale-return", qty=1,
        at="2026-11-09T10:00:00+03:00", posting="p-1", resellable=True,
    )

    result = _replay((returned, buyout, dispatch, receipt), opening=1,
                     caps={dispatch.posting_key: 3})

    assert result.complete is True
    assert result.sale_returned_units == 1
    assert result.returned_cost_basis_rub == Decimal("14.65")
    assert result.financial_cogs_reversal_rub == Decimal("0.00")
    assert result.gross_buyout_cogs_rub == Decimal("50.30")
    assert result.available_units == 1
    assert result.available_layers[0].unit_cost_rub == Decimal("14.65")
    assert result.available_layers[0].effective_date == date(2026, 11, 7)


def test_multiple_partial_sale_returns_restore_newest_fifo_allocations_first():
    receipt = _event(
        Kind.SUPPLY_RECEIVED, "receipt", qty=2, at="2026-11-07T09:00:00+03:00",
        zone=Zone.AVAILABLE,
    )
    dispatch = _event(
        Kind.BUYER_DISPATCH, "dispatch", qty=3, at="2026-11-07T10:00:00+03:00",
        posting="p-1",
    )
    buyout = _event(
        Kind.BUYOUT, "buyout", qty=3, at="2026-11-08T10:00:00+03:00",
        posting="p-1",
    )
    returned_one = _event(
        Kind.SALE_RETURN_RESTOCK, "return-one", qty=1,
        at="2026-11-09T10:00:00+03:00", posting="p-1", resellable=True,
    )
    returned_two = _event(
        Kind.SALE_RETURN_RESTOCK, "return-two", qty=1,
        at="2026-11-10T10:00:00+03:00", posting="p-1", resellable=True,
    )

    result = _replay((receipt, dispatch, buyout, returned_one, returned_two),
                     opening=1, caps={dispatch.posting_key: 3})

    assert result.complete is True
    assert result.sale_returned_units == 2
    assert result.returned_cost_basis_rub == Decimal("29.30")
    assert result.gross_buyout_cogs_rub == Decimal("50.30")
    assert [(layer.quantity, layer.unit_cost_rub) for layer in result.available_layers] == [
        (2, Decimal("14.65")),
    ]


def test_non_buyout_return_restores_original_layer_without_creating_cogs():
    dispatch = _event(
        Kind.BUYER_DISPATCH, "dispatch", qty=2, at="2026-11-07T10:00:00+03:00",
        posting="p-1",
    )
    returned = _event(
        Kind.NON_BUYOUT_RESTOCK, "cancel-return", qty=2,
        at="2026-11-09T10:00:00+03:00", posting="p-1", resellable=True,
    )

    result = _replay((dispatch, returned), opening=2,
                     caps={dispatch.posting_key: 2})

    assert result.complete is True
    assert result.non_buyout_restocked_units == 2
    assert result.pending_reserve_units == 0
    assert result.available_units == 2
    assert result.gross_buyout_cogs_rub == Decimal("0.00")
    assert result.returned_cost_basis_rub == Decimal("42.00")


def test_non_resellable_customer_return_is_held_and_not_available():
    dispatch = _event(
        Kind.BUYER_DISPATCH, "dispatch", qty=1, at="2026-11-07T10:00:00+03:00",
        posting="p-1",
    )
    returned = _event(
        Kind.NON_BUYOUT_RESTOCK, "cancel-return", qty=1,
        at="2026-11-09T10:00:00+03:00", posting="p-1", resellable=False,
    )

    result = _replay((dispatch, returned), opening=1,
                     caps={dispatch.posting_key: 1})

    assert result.complete is True
    assert result.available_units == 0
    assert result.held_units_by_zone == {"non_resellable_customer_return": 1}
    assert result.non_resellable_return_holds[returned.event_key][0].unit_cost_rub == Decimal("21.00")


def test_repeated_return_event_is_idempotent_but_return_above_buyout_is_a_gap():
    dispatch = _event(
        Kind.BUYER_DISPATCH, "dispatch", qty=2, at="2026-11-07T10:00:00+03:00",
        posting="p-1",
    )
    buyout = _event(
        Kind.BUYOUT, "buyout", qty=2, at="2026-11-08T10:00:00+03:00",
        posting="p-1",
    )
    returned = _event(
        Kind.SALE_RETURN_RESTOCK, "sale-return", qty=1,
        at="2026-11-09T10:00:00+03:00", posting="p-1", resellable=True,
    )
    excessive = _event(
        Kind.SALE_RETURN_RESTOCK, "sale-return-excess", qty=2,
        at="2026-11-10T10:00:00+03:00", posting="p-1", resellable=True,
    )

    repeated = _replay((dispatch, buyout, returned, returned), opening=2,
                       caps={dispatch.posting_key: 2})
    over_return = _replay((dispatch, buyout, returned, excessive), opening=2,
                          caps={dispatch.posting_key: 2})

    assert repeated.complete is True
    assert repeated.sale_returned_units == 1
    assert repeated.available_units == 1
    assert over_return.status == "REPLAY_GAP"
    assert Issue.TIMELINE_SALE_RETURN_EXCEEDS_BUYOUT in over_return.issue_codes


def test_buyout_requires_exact_reserve_and_duplicate_buyout_fails_closed():
    dispatch = _event(
        Kind.BUYER_DISPATCH, "dispatch", qty=2, at="2026-11-07T10:00:00+03:00",
        posting="p-1",
    )
    partial = _event(
        Kind.BUYOUT, "buyout-partial", qty=1, at="2026-11-08T10:00:00+03:00",
        posting="p-1",
    )
    buyout = _event(
        Kind.BUYOUT, "buyout", qty=2, at="2026-11-08T11:00:00+03:00",
        posting="p-1",
    )
    second = _event(
        Kind.BUYOUT, "buyout-second", qty=2, at="2026-11-08T12:00:00+03:00",
        posting="p-1",
    )

    mismatch = _replay((dispatch, partial), opening=2,
                       caps={dispatch.posting_key: 2})
    duplicate = _replay((dispatch, buyout, second), opening=2,
                        caps={dispatch.posting_key: 2})

    assert mismatch.issue_codes == (Issue.TIMELINE_BUYOUT_QUANTITY_MISMATCH,)
    assert duplicate.issue_codes == (Issue.TIMELINE_BUYOUT_DUPLICATE,)


def test_partial_non_buyout_return_from_multiple_cost_layers_is_not_guessed():
    receipt = _event(
        Kind.SUPPLY_RECEIVED, "receipt", qty=2, at="2026-11-07T09:00:00+03:00",
        zone=Zone.AVAILABLE,
    )
    dispatch = _event(
        Kind.BUYER_DISPATCH, "dispatch", qty=2, at="2026-11-07T10:00:00+03:00",
        posting="p-1",
    )
    returned = _event(
        Kind.NON_BUYOUT_RESTOCK, "cancel-return", qty=1,
        at="2026-11-08T10:00:00+03:00", posting="p-1", resellable=True,
    )

    result = _replay((receipt, dispatch, returned), opening=1,
                     caps={dispatch.posting_key: 2})

    assert Issue.TIMELINE_RETURN_ALLOCATION_AMBIGUOUS in result.issue_codes
    assert result.available_units == 1
    assert result.gross_buyout_cogs_rub == Decimal("0.00")


def test_out_of_scope_or_unsupported_buyout_event_fails_closed():
    buyout = _event(
        Kind.BUYOUT, "buyout", qty=1, day="2026-11-08", precision="DAY",
        posting="p-1",
    )

    result = _replay((buyout,), opening=1, caps={buyout.posting_key: 1})

    assert result.complete is False
    assert result.issue_codes == (Issue.TIMELINE_BUYOUT_UNMATCHED,)
    assert result.buyer_dispatch_units_total == 0


def test_event_outside_selected_window_and_wrong_scope_fail_closed():
    outside = _event(
        Kind.SUPPLY_RECEIVED, "outside", qty=1, day="2026-12-01", precision="DAY",
        zone=Zone.AVAILABLE,
    )
    foreign = replace(
        _event(Kind.SUPPLY_RECEIVED, "foreign", qty=1, day="2026-11-08",
               precision="DAY", zone=Zone.AVAILABLE),
        scope_fingerprint="b" * 64,
    )

    result = _replay((outside,))
    wrong_scope = _replay((foreign,))

    assert result.issue_codes == (Issue.TIMELINE_EVENT_OUTSIDE_WINDOW,)
    assert wrong_scope.issue_codes == (Issue.TIMELINE_SCOPE_MISMATCH,)


@pytest.mark.parametrize("invalid_cost", [True, 14.65, "NaN", "-1", "1000000000.01"])
def test_cost_inputs_reject_booleans_floats_nonfinite_negative_and_out_of_range(invalid_cost):
    result = _replay((), old=invalid_cost)

    assert result.status == "REPLAY_GAP"
    assert result.issue_codes == (Issue.TIMELINE_COST_INVALID,)
    assert result.available_layers == ()
