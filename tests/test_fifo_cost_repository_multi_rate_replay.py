from datetime import datetime, timezone
import hashlib

from services.fifo_cost_repository import FifoCostRepository
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


IDENTITY = {
    "store_id": "store-multirate",
    "product_id": "product-multirate",
    "offer_id": "offer-multirate",
    "sku": "sku-multirate",
}
ANCHOR_DATE = "2026-11-06"


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _command(repository, *, events, source, idempotency_key):
    preview = repository.preview_command(
        **IDENTITY, events=events, source=source,
    )
    assert preview["error"] is False
    committed = repository.commit_command(
        preview_id=preview["preview_id"],
        active_preview_id=preview["preview_id"],
        idempotency_key=idempotency_key,
    )
    assert committed["error"] is False
    return committed


def _rate_source(fingerprint, captured_at):
    return {
        "source_id": "source_" + fingerprint[:32],
        "store_id": IDENTITY["store_id"],
        "source_kind": "OWNER_CONFIRMATION",
        "source_method": "OWNER_CONFIRMED_FIFO_RATE_CHANGE",
        "source_status": "OWNER_CONFIRMED",
        "provenance": "OWNER_CONFIRMED",
        "source_fingerprint": fingerprint,
        "captured_at": captured_at,
        "source_as_of": None,
        "coverage_status": "OWNER_CONFIRMED",
        "record_count": None,
        "page_count": None,
        "created_at": "2026-11-16T12:00:00.000000Z",
    }


def _seed_three_rate_scenario(
    repository, *, include_last_reconciliation=True, include_mapping=True,
):
    opening_source = {
        "kind": "OWNER_CONFIRMATION",
        "method": "OWNER_CONFIRMED_FIFO_CUTOFF",
        "status": "OWNER_CONFIRMED",
        "provenance": "OWNER_CONFIRMED",
        "coverage_status": "OWNER_CONFIRMED",
        "captured_at": "2026-11-06T12:00:00Z",
        "inventory_cutoff": ANCHOR_DATE,
    }
    _command(repository, events=[
        {
            "kind": "OPENING_FIFO_ANCHOR", "quantity": 3,
            "unit_cost_rub": "21.00", "effective_date": ANCHOR_DATE,
            "location_to": "OZON",
        },
        {
            "kind": "OPENING_FIFO_ANCHOR", "quantity": 100,
            "unit_cost_rub": "14.65", "effective_date": ANCHOR_DATE,
            "location_to": "OZON",
        },
    ], source=opening_source, idempotency_key="multirate-anchor01")

    sale_source = {
        "kind": "OZON_REALIZATION",
        "method": "OZON_REALIZATION_REPORT",
        "status": "COMPLETE",
        "provenance": "OZON_CONFIRMED_FIELD",
        "coverage_status": "COMPLETE",
        "captured_at": "2026-11-16T12:00:00Z",
        "source_as_of": "2026-11-15T00:00:00Z",
        "inventory_cutoff": ANCHOR_DATE,
    }
    sale_inputs = [
        ("2026-11-08", 5),
        ("2026-11-10", 110),
        ("2026-11-12", 10),
    ]
    sale_digests = []
    sale_events = []
    for index, (effective_date, quantity) in enumerate(sale_inputs, start=1):
        identity_digest = _digest(f"physical-sale-{index}")
        sale_digests.append((identity_digest, quantity, effective_date))
        sale_events.append({
            "kind": "PHYSICAL_SALE",
            "quantity": quantity,
            "effective_date": effective_date,
            "inventory_cutoff": ANCHOR_DATE,
            "source_identity_digest": identity_digest,
        })
    _command(repository, events=sale_events, source=sale_source,
             idempotency_key="multirate-sales01")

    connection = repository.get_connection()
    try:
        stream_id = connection.execute(
            "SELECT stream_id FROM fifo_cost_streams WHERE store_id=?",
            (IDENTITY["store_id"],),
        ).fetchone()[0]
        stream = connection.execute(
            "SELECT revision, policy_version FROM fifo_cost_streams WHERE stream_id=?",
            (stream_id,),
        ).fetchone()
        rates = [
            (1, "2026-11-07", "14.65", "a" * 64),
            (2, "2026-11-09", "16.00", "b" * 64),
            (3, "2026-11-11", "18.00", "c" * 64),
        ]
        for sequence, (rate_sequence, effective_date, unit_cost, source_fp) in enumerate(
            rates, start=1,
        ):
            source = _rate_source(source_fp, f"{effective_date}T12:00:00.000000Z")
            connection.execute(
                """INSERT INTO fifo_cost_sources (
                    source_id, store_id, source_kind, source_method, source_status,
                    provenance, source_fingerprint, captured_at, source_as_of,
                    coverage_status, record_count, page_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                tuple(source[key] for key in (
                    "source_id", "store_id", "source_kind", "source_method",
                    "source_status", "provenance", "source_fingerprint",
                    "captured_at", "source_as_of", "coverage_status",
                    "record_count", "page_count", "created_at",
                )),
            )
            rate_id = f"rate-multi-{rate_sequence}"
            connection.execute(
                """INSERT INTO fifo_cost_rate_changes (
                    rate_change_id, stream_id, stream_revision, rate_sequence,
                    effective_date, unit_cost_rub, cost_input_mode,
                    purchase_cost_rub, delivery_cost_rub, packaging_cost_rub,
                    owner_old_home_units, source_id, source_fingerprint,
                    payload_fingerprint, idempotency_key, recorded_at, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'COMPONENTS', ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)""",
                (
                    rate_id, stream_id, stream["revision"] + sequence,
                    rate_sequence, effective_date, unit_cost, unit_cost,
                    "0.00", "0.00", source["source_id"], source_fp,
                    _digest(f"rate-payload-{rate_sequence}"),
                    f"multi-rate-{rate_sequence}",
                    "2026-11-16T12:00:00.000000Z",
                    source["captured_at"],
                ),
            )

        reconciliation_rows = (
            (2, "2026-11-09", 108, 98, 10, "d" * 64),
            (3, "2026-11-11", 7, 0, 7, "e" * 64),
        )
        if not include_last_reconciliation:
            reconciliation_rows = reconciliation_rows[:-1]
        for transition, effective_date, total, finite, prior, fp in reconciliation_rows:
            connection.execute(
                """INSERT INTO fifo_cost_rate_reconciliations (
                    reconciliation_id, stream_id, stream_revision,
                    transition_rate_sequence, reconciled_rate_sequence,
                    effective_date, reconciled_total_units, older_finite_units,
                    prior_rate_units, fbo_units, reserved_units, transit_units,
                    home_units, source_fingerprint, captured_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?, ?)""",
                (
                    f"reconciliation-{transition}", stream_id,
                    stream["revision"] + transition, transition, transition - 1,
                    effective_date, total, finite, prior, total, fp,
                    f"{effective_date}T12:00:00.000000Z",
                    "2026-11-16T12:00:00.000000Z",
                ),
            )

        mapping_set_id = "mapping-set-multirate-01"
        if include_mapping:
            connection.execute(
                """INSERT INTO fifo_cost_cutoff_sale_mapping_sets (
                    mapping_set_id, stream_id, mapping_revision, cutoff_date,
                    complete_through, bridge_fingerprint, mapping_count, created_at
                ) VALUES (?, ?, 1, ?, ?, ?, ?, ?)""",
                (
                    mapping_set_id, stream_id, ANCHOR_DATE, "2026-11-15",
                    "f" * 64, len(sale_digests), "2026-11-16T12:00:00.000000Z",
                ),
            )
            for identity_digest, quantity, effective_date in sale_digests:
                connection.execute(
                    """INSERT INTO fifo_cost_cutoff_sale_mappings (
                        mapping_set_id, source_identity_digest, quantity,
                        physical_effective_date, partition
                    ) VALUES (?, ?, ?, ?, 'POST_CUTOFF')""",
                    (mapping_set_id, identity_digest, quantity, effective_date),
                )
        connection.execute(
            """UPDATE fifo_cost_streams
               SET revision=?, state='FIFO_PARTIAL' WHERE stream_id=?""",
            (stream["revision"] + 3, stream_id),
        )
        connection.execute(
            """UPDATE fifo_cost_projections
               SET revision=?, state='FIFO_PARTIAL', queue_complete=0,
                   cutoff_status='RECONCILED', inventory_cutoff=?
               WHERE stream_id=?""",
            (stream["revision"] + 3, ANCHOR_DATE, stream_id),
        )
        connection.commit()
    finally:
        connection.close()
    return stream_id


def test_fr08_repository_replays_and_persists_three_rate_chain(tmp_path):
    repository = FifoCostRepository(
        db_path=tmp_path / "multi-rate.sqlite",
        now_provider=lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc),
    )
    token = set_current_tenant_user_id(
        make_store_tenant_scope("owner-multirate", IDENTITY["store_id"]),
    )
    try:
        stream_id = _seed_three_rate_scenario(repository)
        connection = repository.get_connection()
        try:
            stream = connection.execute(
                "SELECT revision, policy_version FROM fifo_cost_streams WHERE stream_id=?",
                (stream_id,),
            ).fetchone()
            source_fingerprint = repository._allocation_source_fingerprint(
                connection, stream_id, stream["revision"],
                stream["policy_version"], "RECONCILED",
            )
            preview = repository._preview_allocation_from_connection(
                connection, stream_id,
                stream_revision=stream["revision"],
                allocation_revision=0,
                source_fingerprint=source_fingerprint,
                cutoff_status="RECONCILED",
                anchor_cutoff_date=ANCHOR_DATE,
            )
        finally:
            connection.close()

        assert preview["complete"] is True
        assert [row["total_cost_rub"] for row in preview["allocations"]] == [
            "92.30", "1614.20", "166.00",
        ]
        assert preview["rate_balances"] == {
            "rate-multi-1": {
                "remaining_units": 0, "unit_cost_rub": "14.65",
                "reconciliation_evidence_fingerprint": "a" * 64,
            },
            "rate-multi-2": {
                "remaining_units": 0, "unit_cost_rub": "16.00",
                "reconciliation_evidence_fingerprint": "d" * 64,
            },
            "rate-multi-3": {
                "remaining_units": None, "unit_cost_rub": "18.00",
                "reconciliation_evidence_fingerprint": "e" * 64,
            },
        }
        assert preview["complete_through"] == "2026-11-15"
        assert preview["store_timezone"] == "Europe/Moscow"

        committed = repository.append_allocation_revision(
            **IDENTITY, preview=preview, idempotency_key="multi-rate-allocation01",
        )
        assert committed["error"] is False
        assert committed["line_count"] == 7

        connection = repository.get_connection()
        try:
            persisted = connection.execute(
                """SELECT ordinal, rate_change_id, remaining_units,
                          unit_cost_rub, original_basis_kind
                   FROM fifo_cost_allocation_rate_balances
                   WHERE allocation_id=? ORDER BY ordinal""",
                (committed["allocation_id"],),
            ).fetchall()
            assert [tuple(row) for row in persisted] == [
                (1, "rate-multi-1", 0, "14.65", "MATERIALIZED_RATE_BALANCE"),
                (2, "rate-multi-2", 0, "16.00", "MATERIALIZED_RATE_BALANCE"),
                (3, "rate-multi-3", None, "18.00", "RATE_BOUNDARY"),
            ]
        finally:
            connection.close()

        reopened = FifoCostRepository(db_path=tmp_path / "multi-rate.sqlite")
        snapshot = reopened.read_cost_history_snapshot(**IDENTITY)
        assert snapshot["error"] is False
        assert snapshot["latest_allocation"]["replayed_rate_balances"] == [
            {
                "sequence": 1, "unit_cost_rub": "14.65", "remaining_units": 0,
                "basis_kind": "MATERIALIZED_RATE_BALANCE",
                "reconciliation_fingerprint": "d" * 64,
            },
            {
                "sequence": 2, "unit_cost_rub": "16.00", "remaining_units": 0,
                "basis_kind": "MATERIALIZED_RATE_BALANCE",
                "reconciliation_fingerprint": "e" * 64,
            },
            {
                "sequence": 3, "unit_cost_rub": "18.00", "remaining_units": None,
                "basis_kind": "RATE_BOUNDARY",
                "reconciliation_fingerprint": "e" * 64,
            },
        ]
        guard = reopened.read_allocation_guard(**IDENTITY)
        assert guard["error"] is False
        assert guard["eligible_for_publication"] is True
        assert guard["unsupported_rate_transition_count"] == 0
    finally:
        reset_current_tenant_user_id(token)


def test_fr08_repository_blocks_missing_rate_reconciliation_and_keeps_no_write(tmp_path):
    repository = FifoCostRepository(
        db_path=tmp_path / "missing-reconciliation.sqlite",
        now_provider=lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc),
    )
    token = set_current_tenant_user_id(
        make_store_tenant_scope("owner-multirate", IDENTITY["store_id"]),
    )
    try:
        stream_id = _seed_three_rate_scenario(
            repository, include_last_reconciliation=False,
        )
        connection = repository.get_connection()
        try:
            stream = connection.execute(
                "SELECT revision, policy_version FROM fifo_cost_streams WHERE stream_id=?",
                (stream_id,),
            ).fetchone()
            source_fingerprint = repository._allocation_source_fingerprint(
                connection, stream_id, stream["revision"],
                stream["policy_version"], "RECONCILED",
            )
            preview = repository._preview_allocation_from_connection(
                connection, stream_id,
                stream_revision=stream["revision"], allocation_revision=0,
                source_fingerprint=source_fingerprint,
                cutoff_status="RECONCILED", anchor_cutoff_date=ANCHOR_DATE,
            )
            allocations_before = connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_allocations WHERE stream_id=?",
                (stream_id,),
            ).fetchone()[0]
        finally:
            connection.close()
        assert preview["complete"] is False
        assert preview["reason_code"] == "FIFO_RATE_CHAIN_CONFLICT"
        assert allocations_before == 0
    finally:
        reset_current_tenant_user_id(token)


def test_fr08_repository_requires_full_cutoff_mapping_horizon(tmp_path):
    repository = FifoCostRepository(
        db_path=tmp_path / "missing-mapping.sqlite",
        now_provider=lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc),
    )
    token = set_current_tenant_user_id(
        make_store_tenant_scope("owner-multirate", IDENTITY["store_id"]),
    )
    try:
        stream_id = _seed_three_rate_scenario(repository, include_mapping=False)
        connection = repository.get_connection()
        try:
            stream = connection.execute(
                "SELECT revision, policy_version FROM fifo_cost_streams WHERE stream_id=?",
                (stream_id,),
            ).fetchone()
            preview = repository._preview_allocation_from_connection(
                connection, stream_id,
                stream_revision=stream["revision"], allocation_revision=0,
                source_fingerprint=repository._allocation_source_fingerprint(
                    connection, stream_id, stream["revision"],
                    stream["policy_version"], "RECONCILED",
                ),
                cutoff_status="RECONCILED", anchor_cutoff_date=ANCHOR_DATE,
            )
        finally:
            connection.close()
        assert preview["complete"] is False
        assert preview["reason_code"] == "FIFO_RATE_BOUNDARY_UNPROVEN"
    finally:
        reset_current_tenant_user_id(token)


def test_fr08_source_fingerprint_seals_multirate_mapping_set_before_append(tmp_path):
    repository = FifoCostRepository(
        db_path=tmp_path / "changed-mapping.sqlite",
        now_provider=lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc),
    )
    token = set_current_tenant_user_id(
        make_store_tenant_scope("owner-multirate", IDENTITY["store_id"]),
    )
    try:
        stream_id = _seed_three_rate_scenario(repository)
        connection = repository.get_connection()
        try:
            stream = connection.execute(
                "SELECT revision, policy_version FROM fifo_cost_streams WHERE stream_id=?",
                (stream_id,),
            ).fetchone()
            old_fingerprint = repository._allocation_source_fingerprint(
                connection, stream_id, stream["revision"],
                stream["policy_version"], "RECONCILED",
            )
            preview = repository._preview_allocation_from_connection(
                connection, stream_id,
                stream_revision=stream["revision"], allocation_revision=0,
                source_fingerprint=old_fingerprint,
                cutoff_status="RECONCILED", anchor_cutoff_date=ANCHOR_DATE,
            )
            previous_set = connection.execute(
                """SELECT mapping_set_id, complete_through, mapping_count
                   FROM fifo_cost_cutoff_sale_mapping_sets
                   WHERE stream_id=? ORDER BY mapping_revision DESC LIMIT 1""",
                (stream_id,),
            ).fetchone()
            previous_mappings = connection.execute(
                """SELECT source_identity_digest, quantity, physical_effective_date,
                          partition FROM fifo_cost_cutoff_sale_mappings
                   WHERE mapping_set_id=? ORDER BY source_identity_digest""",
                (previous_set["mapping_set_id"],),
            ).fetchall()
            new_set_id = "mapping-set-multirate-02"
            connection.execute(
                """INSERT INTO fifo_cost_cutoff_sale_mapping_sets (
                    mapping_set_id, stream_id, mapping_revision, cutoff_date,
                    complete_through, bridge_fingerprint, mapping_count, created_at
                ) VALUES (?, ?, 2, ?, ?, ?, ?, ?)""",
                (
                    new_set_id, stream_id, ANCHOR_DATE,
                    previous_set["complete_through"], "9" * 64,
                    previous_set["mapping_count"], "2026-11-16T12:01:00.000000Z",
                ),
            )
            connection.executemany(
                """INSERT INTO fifo_cost_cutoff_sale_mappings (
                    mapping_set_id, source_identity_digest, quantity,
                    physical_effective_date, partition
                ) VALUES (?, ?, ?, ?, ?)""",
                [
                    (
                        new_set_id, row["source_identity_digest"], row["quantity"],
                        row["physical_effective_date"], row["partition"],
                    ) for row in previous_mappings
                ],
            )
            connection.commit()
            new_fingerprint = repository._allocation_source_fingerprint(
                connection, stream_id, stream["revision"],
                stream["policy_version"], "RECONCILED",
            )
        finally:
            connection.close()

        assert new_fingerprint != old_fingerprint
        append = repository.append_allocation_revision(
            **IDENTITY, preview=preview,
            idempotency_key="multi-rate-stale-mapping01",
        )
        assert append == {
            "error": True, "code": "FIFO_SOURCE_REVISION_CONFLICT",
        }
        connection = repository.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_allocations WHERE stream_id=?",
                (stream_id,),
            ).fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)
