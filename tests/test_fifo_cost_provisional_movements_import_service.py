from __future__ import annotations

from dataclasses import replace
import reprlib

import pytest

from services.fifo_cost_provisional_movements_import_service import (
    FifoCostProvisionalMovementsImportService,
)
from services.fifo_cost_provisional_timeline_contracts import (
    ProvisionalStockZone,
    ProvisionalTimelineEventKind as Kind,
)
from services.fifo_cost_transition_contracts import ScopeIdentity


SCOPE = ScopeIdentity(
    owner_id="owner-test", store_id="store-test", product_id="1",
    offer_id="hook-2", sku="3921245627",
)
SERVICE = FifoCostProvisionalMovementsImportService()
HEADER = SERVICE.HEADER


def _csv(*rows, bom=False):
    payload = (";".join(HEADER) + "\r\n" + "".join(
        ";".join(row) + "\r\n" for row in rows
    )).encode("utf-8")
    return b"\xef\xbb\xbf" + payload if bom else payload


def _row(kind="SUPPLY_RECEIVED", ref="event-1", at="2026-11-06T12:00:00+03:00",
         sku="3921245627", qty="2", posting="", zone="available",
         resellable="", source="statement-row-7"):
    return kind, ref, at, sku, qty, posting, zone, resellable, source


def _parse(payload, *, scope=SCOPE, timezone_name="Europe/Moscow"):
    return SERVICE.parse_csv(
        filename="movements.csv", payload=payload, scope=scope,
        timezone_name=timezone_name,
    )


def test_csv_template_parses_all_allowed_owner_movement_kinds_and_redacts_references():
    rows = (
        _row(),
        _row("OPENING_TRANSIT_LINK", "event-2", posting="posting-1", zone=""),
        _row("NON_BUYOUT_RESTOCK", "event-3", posting="posting-2", zone="", resellable="false"),
        _row("SALE_RETURN_RESTOCK", "event-4", posting="posting-3", zone="", resellable="true"),
        _row("RELEASE_HOLD", "event-5", zone="checking"),
        _row("NON_SALE_REMOVE", "event-6", zone="available"),
    )
    result = _parse(_csv(*rows, bom=True))
    assert result.status == "COMPLETE", result.issue_codes
    document = result.document
    assert document.row_count == 6
    assert document.total_units == 12
    assert document.event_counts == {
        "NON_BUYOUT_RESTOCK": 1,
        "NON_SALE_REMOVE": 1,
        "OPENING_TRANSIT_LINK": 1,
        "RELEASE_HOLD": 1,
        "SALE_RETURN_RESTOCK": 1,
        "SUPPLY_RECEIVED": 1,
    }
    assert {event.event_kind for event in document.events} == set(Kind) - {
        Kind.BUYER_DISPATCH, Kind.BUYOUT,
    }
    assert all(event.effective_at_utc.isoformat() == "2026-11-06T09:00:00+00:00"
               for event in document.events)
    rendered = reprlib.repr(document)
    for private in ("event-1", "posting-1", "statement-row-7"):
        assert private not in rendered
    assert document.events[0].scope_fingerprint == document.scope_fingerprint


def test_timestamp_requires_instant_and_rejects_ambiguous_or_nonexistent_local_time():
    day = _parse(_csv(_row(at="2026-11-06")))
    assert day.issue_codes == ("FIFO_PROVISIONAL_MOVEMENTS_TIME_INVALID",)
    ambiguous = _parse(
        _csv(_row(at="2026-11-01 01:30:00")),
        timezone_name="America/New_York",
    )
    assert ambiguous.issue_codes == ("FIFO_PROVISIONAL_FBO_TIME_AMBIGUOUS",)
    nonexistent = _parse(
        _csv(_row(at="2026-03-08 02:30:00")),
        timezone_name="America/New_York",
    )
    assert nonexistent.issue_codes == ("FIFO_PROVISIONAL_FBO_TIME_NONEXISTENT",)
    offset = _parse(_csv(_row(at="2026-11-06T09:00:00Z")))
    assert offset.status == "COMPLETE"
    assert offset.document.events[0].local_date.isoformat() == "2026-11-06"


def test_event_specific_fields_and_references_fail_closed_without_echoing_values():
    invalid_rows = (
        (_row("SUPPLY_RECEIVED", posting="posting-1"), "FIFO_PROVISIONAL_MOVEMENTS_FIELDS_INVALID"),
        (_row("SUPPLY_RECEIVED", zone="buyer_delivery"), "FIFO_PROVISIONAL_MOVEMENTS_FIELDS_INVALID"),
        (_row("OPENING_TRANSIT_LINK", zone="available"), "FIFO_PROVISIONAL_MOVEMENTS_FIELDS_INVALID"),
        (_row("SALE_RETURN_RESTOCK", posting="posting-1"), "FIFO_PROVISIONAL_MOVEMENTS_FIELDS_INVALID"),
        (_row("RELEASE_HOLD", zone="unknown"), "FIFO_PROVISIONAL_MOVEMENTS_ZONE_INVALID"),
        (_row("NON_SALE_REMOVE", zone="available", resellable="true"), "FIFO_PROVISIONAL_MOVEMENTS_FIELDS_INVALID"),
        (_row("SUPPLY_RECEIVED", source="https://example.invalid/private"), "FIFO_PROVISIONAL_MOVEMENTS_SOURCE_REFERENCE_INVALID"),
        (_row("SUPPLY_RECEIVED", source="freeform-note"), "FIFO_PROVISIONAL_MOVEMENTS_SOURCE_REFERENCE_INVALID"),
        (_row("SUPPLY_RECEIVED", sku="999"), "FIFO_PROVISIONAL_MOVEMENTS_SKU_MISMATCH"),
        (_row("SUPPLY_RECEIVED", qty="0"), "FIFO_PROVISIONAL_MOVEMENTS_QUANTITY_INVALID"),
    )
    for row, expected in invalid_rows:
        result = _parse(_csv(row))
        assert result.issue_codes == (expected,)
        assert result.document is None
        assert "private" not in repr(result)


def test_supply_receipt_cannot_be_typed_into_buyer_delivery_reserve():
    event = _parse(_csv(_row())).document.events[0]

    with pytest.raises(ValueError, match="FIFO_PROVISIONAL_TIMELINE_ZONE_INVALID"):
        replace(event, stock_zone=ProvisionalStockZone.BUYER_DELIVERY)


def test_duplicate_event_reference_and_unknown_header_are_rejected():
    duplicate = _parse(_csv(_row(), _row(at="2026-11-06T13:00:00+03:00")))
    assert duplicate.issue_codes == ("FIFO_PROVISIONAL_MOVEMENTS_DUPLICATE_REFERENCE",)
    assert duplicate.document is None
    reordered = _parse(_csv(_row(),),)
    assert reordered.status == "COMPLETE"
    with_extra = _csv(_row()).replace(
        b";source_reference\r\n", b";source_reference;customer_name\r\n",
    )
    assert _parse(with_extra).issue_codes == ("FIFO_PROVISIONAL_MOVEMENTS_HEADER_INVALID",)


def test_document_scope_changes_fingerprint_and_limits_are_bounded():
    one = _parse(_csv(_row()))
    other_scope = ScopeIdentity(
        owner_id="other-owner", store_id="store-test", product_id="1",
        offer_id="hook-2", sku="3921245627",
    )
    other = _parse(_csv(_row()), scope=other_scope)
    assert one.status == other.status == "COMPLETE"
    assert one.document.scope_fingerprint != other.document.scope_fingerprint
    oversized = _parse(b"x" * (SERVICE.MAX_FILE_BYTES + 1))
    assert oversized.issue_codes == ("FIFO_PROVISIONAL_MOVEMENTS_FILE_SIZE_INVALID",)
