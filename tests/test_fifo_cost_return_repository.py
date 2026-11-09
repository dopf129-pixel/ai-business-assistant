import sqlite3
from datetime import datetime, timezone

import pytest

from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_return_evidence_normalizer import (
    FifoCostReturnEvidenceNormalizer,
)
from services.fifo_cost_return_restock_service import FifoCostReturnRestockService
from services.fifo_cost_sale_evidence_normalizer import (
    FifoCostSaleEvidenceNormalizer,
)
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


def _source(kind="OWNER_CONFIRMATION", method="OWNER_CONFIRMED_FIFO_CUTOFF",
            status="OWNER_CONFIRMED", provenance="OWNER_CONFIRMED",
            coverage="OWNER_CONFIRMED", captured_at="2026-11-06T12:00:00Z",
            cutoff="2026-11-01", references=None):
    return {
        "kind": kind,
        "method": method,
        "status": status,
        "completeness": status,
        "provenance": provenance,
        "coverage_status": coverage,
        "captured_at": captured_at,
        "inventory_cutoff": cutoff,
        "references": references or [],
    }


def _event(kind, quantity, *, effective_date="2026-11-02", **kwargs):
    item = {"kind": kind, "quantity": quantity, "effective_date": effective_date}
    if kind == "OPENING_FIFO_ANCHOR":
        item.update(unit_cost_rub=kwargs.pop("unit_cost_rub", "10.00"),
                    inventory_cutoff="2026-11-01", location_to="OZON")
    item.update(kwargs)
    return item


def _command(repo, events, source):
    preview = repo.preview_command(
        store_id="store-a", product_id="product-a", offer_id="offer-a",
        sku="sku-a", events=events, source=source,
    )
    assert preview["error"] is False, preview
    return repo.commit_command(
        preview_id=preview["preview_id"], active_preview_id=preview["preview_id"],
        idempotency_key=f"cmd-{preview['next_revision']:04d}-return-test",
    )


def _ready_repository(tmp_path, *, layers, sale_quantity,
                      sale_identity_digest="d" * 64):
    repo = FifoCostRepository(db_path=tmp_path / "fifo-return.sqlite")
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    _command(repo, [
        _event(
            "OPENING_FIFO_ANCHOR", quantity,
            effective_date="2026-11-01", unit_cost_rub=cost,
        )
        for quantity, cost in layers
    ], _source())
    sale_result = _command(repo, [
        _event(
            "PHYSICAL_SALE", sale_quantity,
            source_identity_digest=sale_identity_digest,
        ),
    ], _source(
        "OZON_REALIZATION", "OZON_REALIZATION_REPORT", "COMPLETE",
        "OZON_CONFIRMED_FIELD", "COMPLETE", "2026-11-06T12:05:00Z",
        references=[],
    ))
    connection = repo.get_connection()
    try:
        connection.execute(
            "UPDATE fifo_cost_projections SET cutoff_status='RECONCILED'"
        )
    finally:
        connection.close()
    guard = repo.read_allocation_guard(
        store_id="store-a", product_id="product-a", offer_id="offer-a", sku="sku-a",
    )
    connection = repo.get_connection()
    try:
        preview = repo._preview_allocation_from_connection(
            connection,
            "fifo_" + repo._sha256(repo._normalize_identity(
                "store-a", "product-a", "offer-a", "sku-a", 1,
            ))[:40],
            stream_revision=guard["stream_revision"],
            allocation_revision=guard["allocation_revision"],
            source_fingerprint=guard["source_set_fingerprint"],
            cutoff_status="RECONCILED",
            anchor_cutoff_date="2026-11-01",
        )
        sale = connection.execute(
            "SELECT event_id FROM fifo_cost_events WHERE event_kind='PHYSICAL_SALE'"
        ).fetchone()
    finally:
        connection.close()
    allocation = repo.append_allocation_revision(
        store_id="store-a", product_id="product-a", offer_id="offer-a", sku="sku-a",
        preview=preview, idempotency_key="sale-allocation-01",
    )
    assert allocation["error"] is False, allocation
    assert sale_result["error"] is False
    return repo, token, sale["event_id"]


def _return_command(repo, sale_event_id, *, quantity, return_id, date="2026-11-04"):
    candidate = {
        "eligible": True,
        "quantity": quantity,
        "effective_date": date,
        "inventory_cutoff": "2026-11-01",
        "source_identity_digest": return_id,
        "origin_sale_identity_digest": "d" * 64,
        "source_method": "OWNER_CONFIRMED_SALEABLE_RETURN_RECOVERY",
        "source_status": "OWNER_CONFIRMED",
        "provenance": "OWNER_CONFIRMED",
        "completeness": "OWNER_CONFIRMED",
        "coverage_status": "OWNER_CONFIRMED",
    }
    source = FifoCostReturnEvidenceNormalizer.build_command_source(
        candidate, captured_at="2026-11-06T12:10:00Z",
    )
    event = FifoCostReturnEvidenceNormalizer.build_event(
        candidate, origin_sale_event_id=sale_event_id,
    )
    return _command(repo, [event], source)


def _publish_current(repo):
    guard = repo.read_allocation_guard(
        store_id="store-a", product_id="product-a", offer_id="offer-a", sku="sku-a",
    )
    connection = repo.get_connection()
    try:
        preview = repo._preview_allocation_from_connection(
            connection,
            "fifo_" + repo._sha256(repo._normalize_identity(
                "store-a", "product-a", "offer-a", "sku-a", 1,
            ))[:40],
            stream_revision=guard["stream_revision"],
            allocation_revision=guard["allocation_revision"],
            source_fingerprint=guard["source_set_fingerprint"],
            cutoff_status="RECONCILED",
            anchor_cutoff_date="2026-11-01",
        )
    finally:
        connection.close()
    return repo.append_allocation_revision(
        store_id="store-a", product_id="product-a", offer_id="offer-a", sku="sku-a",
        preview=preview,
        idempotency_key=f"return-allocation-{guard['stream_revision']:04d}",
    ), preview


def test_fc18_full_return_pins_both_original_cost_layers_and_never_rewrites_sale_cogs(tmp_path):
    repo, token, sale_event_id = _ready_repository(
        tmp_path, layers=[(3, "20.00"), (2, "25.00")], sale_quantity=5,
    )
    try:
        committed = _return_command(
            repo, sale_event_id, quantity=5, return_id="a" * 64,
        )
        assert committed["error"] is False, committed
        allocation, preview = _publish_current(repo)
        assert allocation["error"] is False, allocation
        assert preview["complete"] is True
        assert preview["total_cogs_rub"] == "110.00"
        assert preview["restored_units"] == 5
        assert preview["remaining_confirmed_units"] == 5
        assert [line["quantity"] for line in preview["allocations"][0]["lines"]] == [3, 2]

        connection = repo.get_connection()
        try:
            rows = connection.execute(
                "SELECT quantity, unit_cost_rub, total_cost_rub, allocation_id "
                "FROM fifo_cost_return_basis ORDER BY basis_line_number"
            ).fetchall()
            assert [tuple(row[:3]) for row in rows] == [
                (3, "20.00", "60.00"), (2, "25.00", "50.00"),
            ]
            assert rows[0]["allocation_id"] == rows[1]["allocation_id"]
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM fifo_cost_return_basis")
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_fc18_service_uses_exact_return_recovery_and_publishes_new_revision(tmp_path):
    return_record = {
        "id": "private-return-id",
        "posting_number": "private-posting",
        "sku": "sku-a",
        "quantity": 1,
        "type": "ClientReturn",
        "visual_status_sys_name": "ArrivedAtReturnPlace",
        "compensation_status_sys_name": None,
    }
    identity = {
        "mapping_confirmed": True,
        "offer_id": "offer-a",
        "product_id": "product-a",
    }
    sale_digest = FifoCostSaleEvidenceNormalizer.build_identity_digest(
        store_id="store-a",
        posting_number="private-posting",
        finance_sku="sku-a",
        identity=identity,
    )["source_identity_digest"]
    repo, token, _ = _ready_repository(
        tmp_path, layers=[(4, "20.00")], sale_quantity=2,
        sale_identity_digest=sale_digest,
    )
    service = FifoCostReturnRestockService(
        repo, now_provider=lambda: datetime(2026, 11, 6, 12, 15, tzinfo=timezone.utc),
    )
    recovery = {
        "error": False,
        "return_id": "private-return-id",
        "posting_number": "private-posting",
        "sku": "sku-a",
        "quantity": 1,
        "recovery_state": "SALEABLE_RESTORED",
        "confirmed_on": "2026-11-04",
        "source": "SELLER_CONFIRMED_BOT",
        "inventory_recovery_confirmed": True,
    }
    try:
        preview = service.preview_return(
            store_id="store-a", product_id="product-a", offer_id="offer-a",
            sku="sku-a", finance_sku="sku-a", identity=identity,
            return_record=return_record, recovery_evidence=recovery,
            return_sample_complete=True, cutoff_bridge_confirmed=True,
        )
        assert preview["error"] is False
        assert preview["code"] == "FIFO_RETURN_RESTOCK_PREVIEW_READY"
        assert "private-return-id" not in repr(preview)
        assert "private-posting" not in repr(preview)

        committed = service.commit_return(
            preview_id=preview["preview_id"],
            active_preview_id=preview["preview_id"],
            idempotency_key="return-owner-confirm-01",
            store_id="store-a", product_id="product-a", offer_id="offer-a",
            sku="sku-a",
        )
        assert committed["error"] is False
        assert committed["code"] == "FIFO_RETURN_RESTOCK_COMMITTED"
        assert committed["allocation_revision"] == 2

        retried = service.commit_return(
            preview_id=preview["preview_id"],
            active_preview_id=preview["preview_id"],
            idempotency_key="return-owner-confirm-01",
            store_id="store-a", product_id="product-a", offer_id="offer-a",
            sku="sku-a",
        )
        assert retried["error"] is False
        assert retried["idempotent"] is True
        history = repo.read_cost_history_snapshot(
            store_id="store-a", product_id="product-a", offer_id="offer-a", sku="sku-a",
        )
        assert history["event_counts"]["SALEABLE_RETURN_RESTOCK"] == 1
        assert history["latest_allocation"]["stale"] is False
    finally:
        reset_current_tenant_user_id(token)


def test_fc18_partial_return_of_multilayer_sale_uses_latest_fifo_basis(tmp_path):
    repo, token, sale_event_id = _ready_repository(
        tmp_path, layers=[(3, "20.00"), (2, "25.00")], sale_quantity=5,
    )
    try:
        result = _return_command(
            repo, sale_event_id, quantity=1, return_id="b" * 64,
        )
        assert result["error"] is False, result
        allocation, preview = _publish_current(repo)
        assert allocation["error"] is False, allocation
        assert preview["complete"] is True
        assert preview["total_cogs_rub"] == "110.00"
        assert preview["restored_units"] == 1
        connection = repo.get_connection()
        try:
            rows = connection.execute(
                """SELECT b.layer_id, b.rate_change_id, b.quantity,
                          b.unit_cost_rub, b.total_cost_rub,
                          l.event_id AS basis_sale_event_id
                   FROM fifo_cost_return_basis AS b
                   JOIN fifo_cost_allocation_lines AS l
                     ON l.allocation_id=b.allocation_id
                    AND l.line_number=b.allocation_line_number
                   WHERE b.return_event_id=(
                     SELECT event_id FROM fifo_cost_events
                     WHERE event_kind='SALEABLE_RETURN_RESTOCK'
                   )""",
            ).fetchall()
        finally:
            connection.close()
        assert len(rows) == 1
        assert rows[0]["layer_id"] is not None
        assert rows[0]["rate_change_id"] is None
        assert rows[0]["quantity"] == 1
        assert rows[0]["unit_cost_rub"] == "25.00"
        assert rows[0]["total_cost_rub"] == "25.00"
        assert rows[0]["basis_sale_event_id"] == sale_event_id
    finally:
        reset_current_tenant_user_id(token)


def test_fc18_unknown_origin_sale_is_rejected_without_ledger_write(tmp_path):
    repo, token, _ = _ready_repository(
        tmp_path, layers=[(5, "20.00")], sale_quantity=2,
    )
    try:
        candidate = {
            "eligible": True, "quantity": 1,
            "effective_date": "2026-11-04", "inventory_cutoff": "2026-11-01",
            "source_identity_digest": "b" * 64,
            "origin_sale_identity_digest": "d" * 64,
            "source_method": "OWNER_CONFIRMED_SALEABLE_RETURN_RECOVERY",
            "source_status": "OWNER_CONFIRMED",
            "provenance": "OWNER_CONFIRMED",
            "completeness": "OWNER_CONFIRMED",
            "coverage_status": "OWNER_CONFIRMED",
        }
        preview = repo.preview_command(
            store_id="store-a", product_id="product-a", offer_id="offer-a",
            sku="sku-a",
            events=[FifoCostReturnEvidenceNormalizer.build_event(
                candidate, origin_sale_event_id="evt_" + "0" * 32,
            )],
            source=FifoCostReturnEvidenceNormalizer.build_command_source(
                candidate, captured_at="2026-11-06T12:10:00Z",
            ),
        )
        assert preview["error"] is False
        result = repo.commit_command(
            preview_id=preview["preview_id"],
            active_preview_id=preview["preview_id"],
            idempotency_key="unknown-origin-return",
        )

        assert result["error"] is True
        assert result["code"] == "FIFO_EVENT_TARGET_INVALID"
        connection = repo.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_events "
                "WHERE event_kind='SALEABLE_RETURN_RESTOCK'"
            ).fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_fc18_repeated_single_layer_partial_returns_are_bounded_and_idempotent(tmp_path):
    repo, token, sale_event_id = _ready_repository(
        tmp_path, layers=[(5, "20.00")], sale_quantity=4,
    )
    try:
        first = _return_command(
            repo, sale_event_id, quantity=1, return_id="c" * 64,
        )
        assert first["error"] is False, first
        _, first_preview = _publish_current(repo)
        assert first_preview["restored_units"] == 1

        duplicate = _return_command(
            repo, sale_event_id, quantity=1, return_id="c" * 64,
        )
        assert duplicate["error"] is True
        assert duplicate["code"] == "FIFO_RETURN_IDENTITY_DUPLICATE"

        second = _return_command(
            repo, sale_event_id, quantity=3, return_id="e" * 64,
            date="2026-11-05",
        )
        assert second["error"] is False, second
        _, second_preview = _publish_current(repo)
        assert second_preview["restored_units"] == 4
        assert second_preview["remaining_confirmed_units"] == 5

        excessive = _return_command(
            repo, sale_event_id, quantity=1, return_id="f" * 64,
            date="2026-11-06",
        )
        assert excessive["error"] is True
        assert excessive["code"] == "FIFO_RETURN_QUANTITY_EXCEEDS_ORIGIN"
    finally:
        reset_current_tenant_user_id(token)


def test_fifo_v6_upgrade_adds_return_outflow_and_late_draft_objects(tmp_path):
    repo = FifoCostRepository(db_path=tmp_path / "fifo-v6.sqlite")
    connection = repo.get_connection()
    try:
        connection.execute(
            "CREATE TABLE planning_schema (singleton INTEGER PRIMARY KEY, version INTEGER NOT NULL)"
        )
        connection.execute(
            "INSERT INTO planning_schema(singleton, version) VALUES (1, 9)"
        )
        connection.execute(
            "CREATE TABLE legacy_cost_fixture (value TEXT NOT NULL)"
        )
        connection.execute("INSERT INTO legacy_cost_fixture(value) VALUES ('preserved')")
        connection.execute("DROP TRIGGER trg_fifo_cost_return_basis_no_update")
        connection.execute("DROP TRIGGER trg_fifo_cost_return_basis_no_delete")
        connection.execute("DROP TABLE fifo_cost_return_basis")
        connection.execute("UPDATE fifo_cost_schema SET version=6 WHERE singleton=1")
    finally:
        connection.close()

    migrated = repo.get_connection()
    try:
        assert migrated.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == FifoCostRepository.SCHEMA_VERSION
        assert migrated.execute(
            "SELECT version FROM planning_schema WHERE singleton=1"
        ).fetchone()[0] == 9
        assert migrated.execute(
            "SELECT value FROM legacy_cost_fixture"
        ).fetchone()[0] == "preserved"
        assert migrated.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN "
            "('fifo_cost_return_basis','fifo_cost_allocation_outflow_lines',"
            "'fifo_cost_late_entry_drafts')"
        ).fetchone()[0] == 3
        assert migrated.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
            "AND name='trg_fifo_cost_late_entry_drafts_no_update'"
        ).fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            migrated.execute(
                "INSERT INTO fifo_cost_return_basis "
                "(return_event_id, basis_line_number, allocation_id, "
                "allocation_line_number, origin_sale_event_id, layer_id, "
                "rate_change_id, quantity, unit_cost_rub, total_cost_rub) "
                "VALUES ('missing-event', 1, 'missing-allocation', 1, "
                "'missing-sale', 'missing-layer', NULL, 1, '10.00', '10.00')"
            )
    finally:
        migrated.close()
