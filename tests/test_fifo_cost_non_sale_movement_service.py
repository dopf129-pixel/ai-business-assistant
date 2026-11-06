from datetime import datetime, timezone
import sqlite3

import pytest

from services.fifo_cost_non_sale_movement_service import FifoCostNonSaleMovementService
from services.fifo_cost_repository import FifoCostRepository
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import (
    reset_current_tenant_user_id, set_current_tenant_user_id,
)


def _source(kind="OWNER_CONFIRMATION", method="OWNER_CONFIRMED_FIFO_CUTOFF",
            status="OWNER_CONFIRMED", provenance="OWNER_CONFIRMED",
            coverage="OWNER_CONFIRMED", captured_at="2026-11-06T12:00:00Z",
            cutoff="2026-11-01", references=None):
    return {
        "kind": kind, "method": method, "status": status,
        "completeness": status, "provenance": provenance,
        "coverage_status": coverage, "captured_at": captured_at,
        "inventory_cutoff": cutoff, "references": references or [],
    }


def _event(kind, quantity, *, effective_date="2026-11-02", **kwargs):
    if kind == "OPENING_FIFO_ANCHOR":
        effective_date = "2026-11-01"
    row = {"kind": kind, "quantity": quantity, "effective_date": effective_date}
    if kind == "OPENING_FIFO_ANCHOR":
        row.update(unit_cost_rub="20.00", inventory_cutoff="2026-11-01", location_to="OZON")
    row.update(kwargs)
    return row


def _command(repo, events, source):
    preview = repo.preview_command(
        store_id="store-a", product_id="product-a", offer_id="offer-a",
        sku="sku-a", events=events, source=source,
    )
    assert preview["error"] is False, preview
    return repo.commit_command(
        preview_id=preview["preview_id"], active_preview_id=preview["preview_id"],
        idempotency_key=f"movement-test-{preview['next_revision']:04d}",
    )


def _ready_repo(tmp_path):
    repo = FifoCostRepository(db_path=tmp_path / "fifo-movement.sqlite")
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    _command(repo, [_event("OPENING_FIFO_ANCHOR", 5)], _source())
    sale_source = _source(
        "OZON_REALIZATION", "OZON_REALIZATION_REPORT", "COMPLETE",
        "OZON_CONFIRMED_FIELD", "COMPLETE", "2026-11-06T12:05:00Z",
    )
    _command(repo, [_event(
        "PHYSICAL_SALE", 2, source_identity_digest="a" * 64,
    )], sale_source)
    connection = repo.get_connection()
    try:
        connection.execute("UPDATE fifo_cost_projections SET cutoff_status='RECONCILED'")
    finally:
        connection.close()
    guard = repo.read_allocation_guard(
        store_id="store-a", product_id="product-a", offer_id="offer-a", sku="sku-a",
    )
    connection = repo.get_connection()
    try:
        identity = repo._normalize_identity("store-a", "product-a", "offer-a", "sku-a", 1)
        stream_id = "fifo_" + repo._sha256(identity)[:40]
        preview = repo._preview_allocation_from_connection(
            connection, stream_id, stream_revision=guard["stream_revision"],
            allocation_revision=guard["allocation_revision"],
            source_fingerprint=guard["source_set_fingerprint"],
            cutoff_status="RECONCILED", anchor_cutoff_date="2026-11-01",
        )
    finally:
        connection.close()
    published = repo.append_allocation_revision(
        store_id="store-a", product_id="product-a", offer_id="offer-a", sku="sku-a",
        preview=preview, idempotency_key="movement-initial-alloc-01",
    )
    assert published["error"] is False, published
    return repo, token


def test_movement_preview_commit_keeps_loss_value_out_of_sales_cogs(tmp_path):
    repo, token = _ready_repo(tmp_path)
    service = FifoCostNonSaleMovementService(
        repo, now_provider=lambda: datetime(2026, 11, 6, 12, 15, tzinfo=timezone.utc),
    )
    try:
        preview = service.preview_movement(
            store_id="store-a", product_id="product-a", offer_id="offer-a", sku="sku-a",
            movement_id="owner-note-001", reason_code="HOME_SHORTAGE", quantity=2,
            effective_date="2026-11-04", cutoff_bridge_confirmed=True,
        )
        assert preview["code"] == "FIFO_NON_SALE_MOVEMENT_PREVIEW_READY", repr(preview)
        assert preview["estimated_fifo_value_rub"] == "40.00"
        assert preview["included_in_sales_cogs"] is False
        committed = service.commit_movement(
            preview_id=preview["preview_id"], active_preview_id=preview["preview_id"],
            idempotency_key="movement-owner-note-001",
            store_id="store-a", product_id="product-a", offer_id="offer-a", sku="sku-a",
        )
        assert committed["code"] == "FIFO_NON_SALE_MOVEMENT_COMMITTED", committed
        assert committed["estimated_outflow_value_rub"] == "40.00"
        summary = repo.read_period_allocation_summary(
            store_id="store-a", product_id="product-a", offer_id="offer-a", sku="sku-a",
            date_from="2026-11-02", date_to="2026-11-05",
        )
        assert summary["allocations"][0]["total_cogs_rub"] == "40.00"
        connection = repo.get_connection()
        try:
            rows = connection.execute(
                "SELECT quantity, unit_cost_rub, estimated_value_rub, valuation_method "
                "FROM fifo_cost_allocation_outflow_lines"
            ).fetchall()
            assert [tuple(row) for row in rows] == [(2, "20.00", "40.00", "FIFO_FINITE_LAYER_ESTIMATE")]
            assert connection.execute(
                "SELECT total_cost_rub FROM fifo_cost_allocation_lines WHERE event_id IN "
                "(SELECT event_id FROM fifo_cost_events WHERE event_kind='PHYSICAL_SALE')"
            ).fetchone()[0] == "40.00"
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE fifo_cost_allocation_outflow_lines SET quantity=3"
                )
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)



