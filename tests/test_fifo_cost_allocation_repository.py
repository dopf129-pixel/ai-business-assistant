import sqlite3

import pytest

from services.fifo_cost_allocation_service import (
    FifoCostLayer,
    FifoOpenCostRate,
    FifoSaleEvent,
)
from services.fifo_cost_replay_service import (
    FifoCostReplayService,
    FifoDatedAllocationEvent,
)
from services.fifo_cost_repository import FifoCostRepository
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


def _source():
    return {
        "kind": "OWNER_CONFIRMATION",
        "method": "OWNER_CONFIRMED_FIFO_CUTOFF",
        "status": "OWNER_CONFIRMED",
        "provenance": "OWNER_CONFIRMED",
        "coverage_status": "OWNER_CONFIRMED",
        "captured_at": "2026-11-06T12:00:00Z",
        "inventory_cutoff": "2026-11-01",
    }


def _event(kind, quantity, **kwargs):
    row = {"kind": kind, "quantity": quantity,
           "effective_date": "2026-11-01" if kind == "OPENING_FIFO_ANCHOR" else "2026-11-02"}
    if kind in {"OPENING_FIFO_ANCHOR", "COST_LAYER_RECEIPT"}:
        row["unit_cost_rub"] = "10.00"
    if kind == "OPENING_FIFO_ANCHOR":
        row["location_to"] = "OZON"
    row.update(kwargs)
    return row


def _command(repo, *, events, source=None):
    preview = repo.preview_command(
        store_id="store-a", product_id="product-1", offer_id="offer-1",
        sku="sku-1", events=events, source=source or _source(),
    )
    assert preview["error"] is False
    committed = repo.commit_command(
        preview_id=preview["preview_id"], active_preview_id=preview["preview_id"],
        idempotency_key=f"fifo-cmd-{len(events)}-{events[0]['kind'].lower()}",
    )
    assert committed["error"] is False
    return committed


def _ready_fixture(tmp_path):
    repository = FifoCostRepository(db_path=tmp_path / "fifo-allocation.sqlite")
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-1", "store-a"))
    _command(repository, events=[_event("OPENING_FIFO_ANCHOR", 5)])
    sale_source = {
        "kind": "OZON_REALIZATION",
        "method": "OZON_REALIZATION_REPORT",
        "status": "COMPLETE",
        "provenance": "OZON_CONFIRMED_FIELD",
        "coverage_status": "COMPLETE",
        "captured_at": "2026-11-06T12:05:00Z",
        "inventory_cutoff": "2026-11-01",
        "source_as_of": "2026-11-03T00:00:00Z",
    }
    sale = _command(repository, events=[_event(
        "PHYSICAL_SALE", 2, source_identity_digest="b" * 64,
    )], source=sale_source)
    connection = repository.get_connection()
    try:
        connection.execute(
            "UPDATE fifo_cost_projections SET cutoff_status='RECONCILED'"
        )
    finally:
        connection.close()
    guard = repository.read_allocation_guard(
        store_id="store-a", product_id="product-1", offer_id="offer-1", sku="sku-1",
    )
    connection = repository.get_connection()
    try:
        layer_id = connection.execute(
            "SELECT layer_id FROM fifo_cost_layers"
        ).fetchone()[0]
        sale_row = connection.execute(
            "SELECT event_id, quantity, effective_date, source_identity_digest "
            "FROM fifo_cost_events WHERE event_kind='PHYSICAL_SALE'"
        ).fetchone()
        layer = connection.execute(
            "SELECT unit_cost_rub, quantity FROM fifo_cost_layers WHERE layer_id=?",
            (layer_id,),
        ).fetchone()
    finally:
        connection.close()
    preview = FifoCostReplayService().preview(
        layers=[FifoCostLayer(layer_id, layer["unit_cost_rub"], layer["quantity"])],
        events=[FifoDatedAllocationEvent(
            event=FifoSaleEvent(sale_row["event_id"], sale_row["quantity"]),
            effective_at=None, effective_date=sale_row["effective_date"],
            source_identity_digest=sale_row["source_identity_digest"],
            physical_time_confirmed=True, cutoff_bridge_confirmed=True,
        )],
        stream_revision=guard["stream_revision"],
        expected_allocation_revision=guard["allocation_revision"],
        source_set_fingerprint=guard["source_set_fingerprint"],
        anchor_cutoff_date="2026-11-01",
        anchor_status="CONFIRMED", cutoff_status="RECONCILED",
        source_completeness="COMPLETE",
    )
    return repository, token, guard, preview


def _two_sale_fixture(tmp_path, *, quantities=(2, 2)):
    repository = FifoCostRepository(db_path=tmp_path / "two-sale.sqlite")
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-1", "store-a"))
    _command(repository, events=[
        _event("OPENING_FIFO_ANCHOR", 2, unit_cost_rub="10.00"),
        _event("OPENING_FIFO_ANCHOR", 3, unit_cost_rub="20.00"),
    ])
    sale_source = {
        "kind": "OZON_REALIZATION",
        "method": "OZON_REALIZATION_REPORT",
        "status": "COMPLETE",
        "provenance": "OZON_CONFIRMED_FIELD",
        "coverage_status": "COMPLETE",
        "captured_at": "2026-11-06T12:05:00Z",
        "inventory_cutoff": "2026-11-01",
        "source_as_of": "2026-11-05T00:00:00Z",
    }
    _command(repository, events=[
        _event(
            "PHYSICAL_SALE", quantities[0], effective_date="2026-11-02",
            source_identity_digest="d" * 64,
        ),
        _event(
            "PHYSICAL_SALE", quantities[1], effective_date="2026-11-03",
            source_identity_digest="e" * 64,
        ),
    ], source=sale_source)
    connection = repository.get_connection()
    try:
        connection.execute(
            "UPDATE fifo_cost_projections SET cutoff_status='RECONCILED'"
        )
    finally:
        connection.close()
    guard = repository.read_allocation_guard(
        store_id="store-a", product_id="product-1", offer_id="offer-1", sku="sku-1",
    )
    connection = repository.get_connection()
    try:
        layers = [FifoCostLayer(row["layer_id"], row["unit_cost_rub"], row["quantity"])
                  for row in connection.execute(
                      "SELECT layer_id, unit_cost_rub, quantity FROM fifo_cost_layers "
                      "ORDER BY layer_sequence"
                  )]
        sales = [FifoDatedAllocationEvent(
            event=FifoSaleEvent(row["event_id"], row["quantity"]),
            effective_at=row["effective_at"], effective_date=row["effective_date"],
            source_identity_digest=row["source_identity_digest"],
            physical_time_confirmed=True, cutoff_bridge_confirmed=True,
        ) for row in connection.execute(
            "SELECT event_id, quantity, effective_at, effective_date, "
            "source_identity_digest FROM fifo_cost_events "
            "WHERE event_kind='PHYSICAL_SALE' ORDER BY effective_date"
        )]
    finally:
        connection.close()
    preview = FifoCostReplayService().preview(
        layers=layers, events=sales,
        stream_revision=guard["stream_revision"],
        expected_allocation_revision=guard["allocation_revision"],
        source_set_fingerprint=guard["source_set_fingerprint"],
        anchor_cutoff_date="2026-11-01", anchor_status="CONFIRMED",
        cutoff_status="RECONCILED", source_completeness="COMPLETE",
    )
    return repository, token, guard, preview


def test_fc28_period_summary_reconciles_layer_amounts_without_exposing_internal_ids(tmp_path):
    repository, token, _guard, preview = _two_sale_fixture(tmp_path)
    try:
        committed = repository.append_allocation_revision(
            store_id="store-a", product_id="product-1", offer_id="offer-1",
            sku="sku-1", preview=preview,
            idempotency_key="fc28-layer-summary",
        )
        assert committed["error"] is False

        result = repository.read_period_allocation_summary(
            store_id="store-a", product_id="product-1", offer_id="offer-1",
            sku="sku-1", date_from="2026-11-02", date_to="2026-11-03",
        )

        assert result["error"] is False
        assert result["complete"] is True
        assert result["period_units"] == 4
        assert result["period_cogs_rub"] == "60.00"
        assert result["layer_breakdown_complete"] is True
        assert [
            (item["quantity"], item["unit_cost_rub"], item["total_cogs_rub"])
            for item in result["layers"]
        ] == [(2, "10.00", "20.00"), (2, "20.00", "40.00")]
        assert {item["effective_date"] for item in result["layers"]} == {"2026-11-01"}
        assert {item["provenance"] for item in result["layers"]} == {"OWNER_CONFIRMED"}
        assert {item["source_method"] for item in result["layers"]} == {
            "OWNER_CONFIRMED_FIFO_CUTOFF",
        }
        assert all(item["basis_ref"].startswith("fifo-basis-") for item in result["layers"])
        serialized = str(result["layers"])
        assert "layer_id" not in serialized
        assert "event_id" not in serialized
        assert "source_identity_digest" not in serialized
    finally:
        reset_current_tenant_user_id(token)


def test_fc28_zero_sale_period_is_complete_with_empty_layers_and_zero_cogs(tmp_path):
    repository = FifoCostRepository(db_path=tmp_path / "zero-sale.sqlite")
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-1", "store-a"))
    try:
        _command(repository, events=[_event("OPENING_FIFO_ANCHOR", 5)])
        connection = repository.get_connection()
        try:
            connection.execute(
                "UPDATE fifo_cost_projections SET cutoff_status='RECONCILED'"
            )
        finally:
            connection.close()

        result = repository.read_period_allocation_summary(
            store_id="store-a", product_id="product-1", offer_id="offer-1",
            sku="sku-1", date_from="2026-11-02", date_to="2026-11-30",
        )

        assert result["error"] is False
        assert result["complete"] is True
        assert result["allocation_revision"] == 0
        assert result["layers"] == []
        assert result["period_units"] == 0
        assert result["period_cogs_rub"] == "0.00"
        assert result["layer_breakdown_complete"] is True
    finally:
        reset_current_tenant_user_id(token)


def test_fc16_guard_exposes_unreconciled_cutoff_and_never_claims_publication_ready(tmp_path):
    repository = FifoCostRepository(db_path=tmp_path / "blocked.sqlite")
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-1", "store-a"))
    try:
        _command(repository, events=[_event("OPENING_FIFO_ANCHOR", 5)])
        guard = repository.read_allocation_guard(
            store_id="store-a", product_id="product-1", offer_id="offer-1", sku="sku-1",
        )

        assert guard["error"] is False
        assert guard["cutoff_status"] == "INVENTORY_CUTOFF_UNRECONCILED"
        assert guard["eligible_for_publication"] is False
    finally:
        reset_current_tenant_user_id(token)


def test_fc16_append_allocation_is_atomic_immutable_and_idempotent(tmp_path):
    repo, token, guard, preview = _ready_fixture(tmp_path)
    try:
        assert preview["complete"] is True
        result = repo.append_allocation_revision(
            store_id="store-a", product_id="product-1", offer_id="offer-1", sku="sku-1",
            preview=preview, idempotency_key="allocation-confirm-01",
        )
        repeated = repo.append_allocation_revision(
            store_id="store-a", product_id="product-1", offer_id="offer-1", sku="sku-1",
            preview=preview, idempotency_key="allocation-confirm-01",
        )
        assert result["error"] is False
        assert result["idempotent"] is False
        assert result["allocation_revision"] == 1
        assert result["line_count"] == 1
        assert repeated["idempotent"] is True
        assert repeated["allocation_id"] == result["allocation_id"]

        connection = repo.get_connection()
        try:
            header = connection.execute(
                "SELECT revision, stream_revision, status, cutoff_status "
                "FROM fifo_cost_allocations"
            ).fetchone()
            line = connection.execute(
                "SELECT quantity, unit_cost_rub, total_cost_rub "
                "FROM fifo_cost_allocation_lines"
            ).fetchone()
            assert tuple(header) == (1, guard["stream_revision"], "COMPLETE", "RECONCILED")
            assert tuple(line) == (2, "10.00", "20.00")
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE fifo_cost_allocations SET status='PARTIAL'"
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM fifo_cost_allocation_lines")
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_fc16_stale_stream_revision_and_changed_cutoff_cannot_publish(tmp_path):
    repo, token, _, preview = _ready_fixture(tmp_path)
    try:
        _command(repo, events=[_event(
            "INVENTORY_TRANSFER", 1,
            location_from="OZON", location_to="HOME",
        )])
        result = repo.append_allocation_revision(
            store_id="store-a", product_id="product-1", offer_id="offer-1", sku="sku-1",
            preview=preview, idempotency_key="allocation-stale-01",
        )
        assert result == {"error": True, "code": "FIFO_REVISION_CONFLICT"}
        connection = repo.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_allocations"
            ).fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_fc16_forged_or_incomplete_totals_are_rejected_without_writes(tmp_path):
    repo, token, _, preview = _ready_fixture(tmp_path)
    try:
        preview["allocations"][0]["lines"][0]["total_cost_rub"] = "19.00"
        preview["preview_fingerprint"] = FifoCostReplayService._fingerprint(preview)
        result = repo.append_allocation_revision(
            store_id="store-a", product_id="product-1", offer_id="offer-1", sku="sku-1",
            preview=preview, idempotency_key="allocation-invalid-01",
        )
        assert result == {"error": True, "code": "FIFO_ALLOCATION_TOTAL_MISMATCH"}
        connection = repo.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_allocations"
            ).fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_fc16_publication_requires_full_sale_coverage(tmp_path):
    repo, token, _, preview = _ready_fixture(tmp_path)
    try:
        preview["allocations"] = []
        preview["total_cogs_rub"] = "0.00"
        preview["preview_fingerprint"] = FifoCostReplayService._fingerprint(preview)
        missing_sale = repo.append_allocation_revision(
            store_id="store-a", product_id="product-1", offer_id="offer-1", sku="sku-1",
            preview=preview, idempotency_key="allocation-omitted-sale01",
        )
        assert missing_sale == {
            "error": True, "code": "FIFO_ALLOCATION_COVERAGE_MISMATCH",
        }

    finally:
        reset_current_tenant_user_id(token)


def test_fc16_allocation_cannot_replace_source_layer_cost(tmp_path):
    repo, token, _, preview = _ready_fixture(tmp_path)
    try:
        allocation = preview["allocations"][0]
        allocation["lines"][0]["unit_cost_rub"] = "11.00"
        allocation["lines"][0]["total_cost_rub"] = "22.00"
        allocation["total_cost_rub"] = "22.00"
        preview["total_cogs_rub"] = "22.00"
        preview["preview_fingerprint"] = FifoCostReplayService._fingerprint(preview)
        result = repo.append_allocation_revision(
            store_id="store-a", product_id="product-1", offer_id="offer-1", sku="sku-1",
            preview=preview, idempotency_key="allocation-altered-rate01",
        )
        assert result == {"error": True, "code": "FIFO_ALLOCATION_RATE_MISMATCH"}
    finally:
        reset_current_tenant_user_id(token)


def test_fc16_valid_hash_cannot_reorder_layers_while_preserving_total_cogs(tmp_path):
    repo, token, _, preview = _two_sale_fixture(tmp_path)
    try:
        assert preview["complete"] is True
        first_sale, second_sale = preview["allocations"]
        assert first_sale["lines"][0]["unit_cost_rub"] == "10.00"
        assert second_sale["lines"][0]["unit_cost_rub"] == "20.00"
        first_layer_id = first_sale["lines"][0]["layer_id"]
        second_layer_id = second_sale["lines"][0]["layer_id"]
        # Keep each sale's line arithmetic and the aggregate total valid while
        # trying to consume the newer, more expensive layer first.
        first_sale["lines"][0].update({
            "layer_id": second_layer_id,
            "unit_cost_rub": "20.00", "total_cost_rub": "40.00",
        })
        first_sale["total_cost_rub"] = "40.00"
        second_sale["lines"][0].update({
            "layer_id": first_layer_id,
            "unit_cost_rub": "10.00", "total_cost_rub": "20.00",
        })
        second_sale["total_cost_rub"] = "20.00"
        preview["preview_fingerprint"] = FifoCostReplayService._fingerprint(preview)

        result = repo.append_allocation_revision(
            store_id="store-a", product_id="product-1", offer_id="offer-1", sku="sku-1",
            preview=preview, idempotency_key="allocation-forged-fifo-01",
        )
        assert result == {"error": True, "code": "FIFO_ALLOCATION_REPLAY_MISMATCH"}
        connection = repo.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_allocations"
            ).fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_fc16_read_guard_blocks_sales_exceeding_confirmed_fifo_quantity(tmp_path):
    repo, token, guard, preview = _two_sale_fixture(tmp_path, quantities=(4, 4))
    try:
        assert preview["complete"] is False
        assert preview["reason_code"] == "FIFO_CONFIRMED_QUANTITY_EXHAUSTED"
        assert guard["eligible_for_publication"] is False
        assert guard["replay_reason_code"] == "FIFO_CONFIRMED_QUANTITY_EXHAUSTED"
        result = repo.append_allocation_revision(
            store_id="store-a", product_id="product-1", offer_id="offer-1", sku="sku-1",
            preview=preview, idempotency_key="allocation-oversold-fifo-01",
        )
        assert result == {"error": True, "code": "FIFO_ALLOCATION_PREVIEW_INCOMPLETE"}
    finally:
        reset_current_tenant_user_id(token)


def test_fc17_period_read_uses_only_latest_complete_allocations_and_exact_dates(tmp_path):
    repo, token, _, preview = _two_sale_fixture(tmp_path)
    try:
        before = repo.read_period_allocation_summary(
            store_id="store-a", product_id="product-1", offer_id="offer-1",
            sku="sku-1", date_from="2026-11-02", date_to="2026-11-03",
        )
        assert before["active"] is True
        assert before["complete"] is False
        assert before["reason_code"] == "FIFO_ALLOCATION_STALE_OR_MISSING"

        committed = repo.append_allocation_revision(
            store_id="store-a", product_id="product-1", offer_id="offer-1", sku="sku-1",
            preview=preview, idempotency_key="allocation-period-read-01",
        )
        assert committed["error"] is False
        whole_period = repo.read_period_allocation_summary(
            store_id="store-a", product_id="product-1", offer_id="offer-1",
            sku="sku-1", date_from="2026-11-02", date_to="2026-11-03",
        )
        first_day = repo.read_period_allocation_summary(
            store_id="store-a", product_id="product-1", offer_id="offer-1",
            sku="sku-1", date_from="2026-11-02", date_to="2026-11-02",
        )
        assert whole_period["complete"] is True
        assert whole_period["allocation_revision"] == 1
        assert [row["source_identity_digest"] for row in whole_period["allocations"]] == [
            "d" * 64, "e" * 64,
        ]
        assert [row["total_cogs_rub"] for row in whole_period["allocations"]] == [
            "20.00", "40.00",
        ]
        assert first_day["complete"] is True
        assert [(row["quantity"], row["total_cogs_rub"])
                for row in first_day["allocations"]] == [(2, "20.00")]
    finally:
        reset_current_tenant_user_id(token)


def test_fc16_v5_migration_adds_stream_revision_and_rate_lines_without_rewriting_headers(tmp_path):
    database = tmp_path / "fifo-v5.sqlite"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE fifo_cost_schema (singleton INTEGER PRIMARY KEY, version INTEGER NOT NULL)"
        )
        connection.execute("INSERT INTO fifo_cost_schema VALUES (1, 5)")
        connection.execute(
            """CREATE TABLE fifo_cost_allocations (
                allocation_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                policy_version INTEGER NOT NULL,
                source_set_fingerprint TEXT NOT NULL,
                cutoff_status TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(stream_id, revision)
            )"""
        )
        connection.execute(
            """INSERT INTO fifo_cost_allocations VALUES (
                'allocation-old', 'stream-old', 1, 1, ?,
                'INVENTORY_CUTOFF_UNRECONCILED', 'SOURCE_BLOCKED', '2026-11-01'
            )""",
            ("a" * 64,),
        )
        connection.commit()
    finally:
        connection.close()

    migrated = FifoCostRepository(db_path=database).get_connection()
    try:
        assert migrated.execute(
            "SELECT version FROM fifo_cost_schema WHERE singleton=1"
        ).fetchone()[0] == FifoCostRepository.SCHEMA_VERSION
        assert tuple(migrated.execute(
            "SELECT revision, status, stream_revision FROM fifo_cost_allocations"
        ).fetchone()) == (1, "SOURCE_BLOCKED", 0)
        assert migrated.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND name='fifo_cost_allocation_rate_lines'"
        ).fetchone()[0] == 1
    finally:
        migrated.close()


def test_fc16_rate_only_units_are_persisted_separately_from_finite_layers(tmp_path):
    repository = FifoCostRepository(db_path=tmp_path / "rate-lines.sqlite")
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-1", "store-a"))
    try:
        _command(repository, events=[_event("OPENING_FIFO_ANCHOR", 1)])
        rate_preview = repository.preview_cost_rate_change(
            store_id="store-a", product_id="product-1", offer_id="offer-1", sku="sku-1",
            effective_date="2026-11-03", purchase_cost_rub="15.00",
            delivery_cost_rub="0.00", packaging_cost_rub="0.00",
            owner_old_home_units=0, expected_revision=1,
        )
        assert rate_preview["error"] is False
        rate_commit = repository.commit_cost_rate_change(
            preview_id=rate_preview["preview_id"],
            active_preview_id=rate_preview["preview_id"],
            idempotency_key="rate-confirm-01",
        )
        assert rate_commit["error"] is False
        sale_source = {
            "kind": "OZON_REALIZATION",
            "method": "OZON_REALIZATION_REPORT",
            "status": "COMPLETE",
            "provenance": "OZON_CONFIRMED_FIELD",
            "coverage_status": "COMPLETE",
            "captured_at": "2026-11-06T12:05:00Z",
            "inventory_cutoff": "2026-11-01",
            "source_as_of": "2026-11-05T00:00:00Z",
        }
        _command(repository, events=[_event(
            "PHYSICAL_SALE", 2, effective_date="2026-11-04",
            source_identity_digest="c" * 64,
        )], source=sale_source)
        connection = repository.get_connection()
        try:
            connection.execute(
                "UPDATE fifo_cost_projections SET cutoff_status='RECONCILED'"
            )
            layer = connection.execute(
                "SELECT layer_id, unit_cost_rub, quantity FROM fifo_cost_layers"
            ).fetchone()
            rate = connection.execute(
                "SELECT rate_change_id, unit_cost_rub FROM fifo_cost_rate_changes"
            ).fetchone()
            sale = connection.execute(
                "SELECT event_id, quantity, effective_date, source_identity_digest "
                "FROM fifo_cost_events WHERE event_kind='PHYSICAL_SALE'"
            ).fetchone()
        finally:
            connection.close()
        guard = repository.read_allocation_guard(
            store_id="store-a", product_id="product-1", offer_id="offer-1", sku="sku-1",
        )
        assert guard["stream_state"] == "FIFO_PARTIAL"
        assert guard["eligible_for_publication"] is True
        preview = FifoCostReplayService().preview(
            layers=[FifoCostLayer(layer["layer_id"], layer["unit_cost_rub"], layer["quantity"])],
            open_rate=FifoOpenCostRate(rate["rate_change_id"], rate["unit_cost_rub"]),
            open_rate_effective_date="2026-11-03",
            events=[FifoDatedAllocationEvent(
                FifoSaleEvent(sale["event_id"], sale["quantity"]),
                None, sale["effective_date"], sale["source_identity_digest"], True, True,
            )],
            stream_revision=guard["stream_revision"],
            expected_allocation_revision=guard["allocation_revision"],
            source_set_fingerprint=guard["source_set_fingerprint"],
            anchor_cutoff_date="2026-11-01",
            anchor_status="CONFIRMED", cutoff_status="RECONCILED",
            source_completeness="COMPLETE",
        )
        assert preview["total_cogs_rub"] == "25.00"
        committed = repository.append_allocation_revision(
            store_id="store-a", product_id="product-1", offer_id="offer-1", sku="sku-1",
            preview=preview, idempotency_key="allocation-rate-confirm-01",
        )
        assert committed["error"] is False
        connection = repository.get_connection()
        try:
            finite = connection.execute(
                "SELECT quantity, unit_cost_rub, total_cost_rub "
                "FROM fifo_cost_allocation_lines"
            ).fetchone()
            rate_line = connection.execute(
                "SELECT quantity, unit_cost_rub, total_cost_rub "
                "FROM fifo_cost_allocation_rate_lines"
            ).fetchone()
            assert tuple(finite) == (1, "10.00", "10.00")
            assert tuple(rate_line) == (1, "15.00", "15.00")
        finally:
            connection.close()
        report = repository.read_period_allocation_summary(
            store_id="store-a", product_id="product-1", offer_id="offer-1",
            sku="sku-1", date_from="2026-11-04", date_to="2026-11-04",
        )
        assert report["complete"] is True
        assert report["period_units"] == 2
        assert report["period_cogs_rub"] == "25.00"
        assert [(row["basis_kind"], row["quantity"], row["unit_cost_rub"])
                for row in report["layers"]] == [
            ("LAYER", 1, "10.00"), ("RATE", 1, "15.00"),
        ]
        assert [row["effective_date"] for row in report["layers"]] == [
            "2026-11-01", "2026-11-03",
        ]
        assert all(row["source_method"] in {
            "OWNER_CONFIRMED_FIFO_CUTOFF", "OWNER_CONFIRMED_NEW_COST_RATE",
        } for row in report["layers"])
    finally:
        reset_current_tenant_user_id(token)
