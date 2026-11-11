import csv
import io
from datetime import date, datetime, timedelta, timezone
import hashlib

from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_current_unit_cost_adapter import FifoCurrentUnitCostAdapter
from services.product_unit_economics_query_service import ProductUnitEconomicsQueryService
from services.telegram_fifo_cost_history_service import TelegramFifoCostHistoryService
from services.fifo_cost_non_sale_movement_service import (
    FifoCostNonSaleMovementService,
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
    mr05_sale_quantity=0, additional_sales=(), mapping_complete_through=None,
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

    sale_inputs = [
        ("mr01", "2026-11-08", 5),
        ("mr02", "2026-11-10", 110),
        ("mr03", "2026-11-12", 10),
    ]
    if mr05_sale_quantity:
        sale_inputs.append(("mr04", "2026-11-14", mr05_sale_quantity))
    sale_inputs.extend(additional_sales)
    complete_through = max(
        "2026-11-15",
        max(effective_date for _posting, effective_date, _quantity in sale_inputs),
    )
    mapping_complete_through = max(
        complete_through, mapping_complete_through or complete_through,
    )
    capture_date = (
        date.fromisoformat(complete_through) + timedelta(days=1)
    ).isoformat()
    sale_source = {
        "kind": "OZON_REALIZATION",
        "method": "OZON_REALIZATION_REPORT",
        "status": "COMPLETE",
        "provenance": "OZON_CONFIRMED_FIELD",
        "coverage_status": "COMPLETE",
        "captured_at": capture_date + "T12:00:00Z",
        "source_as_of": complete_through + "T23:59:59Z",
        "inventory_cutoff": ANCHOR_DATE,
    }
    sale_digests = []
    sale_events = []
    for posting_number, effective_date, quantity in sale_inputs:
        identity_digest = FifoCostSaleEvidenceNormalizer.build_identity_digest(
            store_id=IDENTITY["store_id"],
            posting_number=posting_number,
            finance_sku=IDENTITY["sku"],
            identity={
                "mapping_confirmed": True,
                "product_id": IDENTITY["product_id"],
                "offer_id": IDENTITY["offer_id"],
            },
        )["source_identity_digest"]
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
                    mapping_set_id, stream_id, ANCHOR_DATE, mapping_complete_through,
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


def _preview_saleable_return(
    service, *, posting_number, return_id, quantity, confirmed_on,
):
    return service.preview_return(
        store_id=IDENTITY["store_id"], product_id=IDENTITY["product_id"],
        offer_id=IDENTITY["offer_id"], sku=IDENTITY["sku"],
        finance_sku=IDENTITY["sku"],
        identity={
            "mapping_confirmed": True,
            "product_id": IDENTITY["product_id"],
            "offer_id": IDENTITY["offer_id"],
        },
        return_record={
            "id": return_id, "posting_number": posting_number,
            "sku": IDENTITY["sku"], "quantity": quantity,
            "type": "ClientReturn",
            "visual_status_sys_name": "ArrivedAtReturnPlace",
            "compensation_status_sys_name": None,
        },
        recovery_evidence={
            "error": False, "return_id": return_id,
            "posting_number": posting_number, "sku": IDENTITY["sku"],
            "quantity": quantity, "recovery_state": "SALEABLE_RESTORED",
            "confirmed_on": confirmed_on,
            "source": "SELLER_CONFIRMED_BOT",
            "inventory_recovery_confirmed": True,
        },
        return_sample_complete=True, cutoff_bridge_confirmed=True,
    )


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


def test_fr11_history_current_cost_export_and_period_profit_use_replayed_rates(tmp_path):
    db_path = tmp_path / "fr11-multi-rate-readers.sqlite"
    repository = FifoCostRepository(
        db_path=db_path,
        now_provider=lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc),
    )
    token = set_current_tenant_user_id(
        make_store_tenant_scope("owner-multirate", IDENTITY["store_id"]),
    )
    try:
        _seed_three_rate_scenario(repository)
        preview = repository.preview_current_allocation(**IDENTITY)
        assert preview["error"] is False, preview
        committed = repository.append_allocation_revision(
            **IDENTITY, preview=preview,
            idempotency_key="fr11-reader-allocation01",
        )
        assert committed["error"] is False, committed

        # A new repository instance must read the same immutable revision.
        reopened = FifoCostRepository(db_path=db_path)
        history = FifoCostHistoryService(reopened).get_sku_history(
            **IDENTITY, as_of_date=date(2026, 11, 16),
        )
        assert history["error"] is False, history
        assert history["remaining_status"] == "AFTER_CONFIRMED_REPLAY"
        assert history["latest_allocation"]["revision"] == committed["allocation_revision"]
        assert history["allocation_revision"] == committed["allocation_revision"]
        assert history["cutoff_mapping_revision"] == 1
        assert history["complete_through"] == "2026-11-15"
        assert [row["remaining_units"] for row in history["reconciled_rate_layers"]] == [0, 0]
        assert history["next_unit_cost_rub"] == "18.00", history["latest_allocation"]
        assert history["next_unit_cost_basis"] == "OPEN_RATE_QUANTITY_UNKNOWN"

        class _NoLegacyCost:
            @staticmethod
            def get_cost(_product_id):
                return None

            @staticmethod
            def get_current_cost_date():
                return "2026-11-16"

        current = FifoCurrentUnitCostAdapter(
            _NoLegacyCost(), FifoCostHistoryService(reopened),
        ).resolve_current_cost(
            {
                "product_id": IDENTITY["product_id"],
                "offer_id": IDENTITY["offer_id"],
                "sku": IDENTITY["sku"],
            },
            store_id=IDENTITY["store_id"],
            as_of_date="2026-11-16",
        )
        assert current["cost_per_unit_rub"] == "18.00"
        assert current["cost_basis"]["next_unit_cost_basis"] == "OPEN_RATE_QUANTITY_UNKNOWN"
        assert current["cost_basis"]["stream_revision"] == history["revision"]
        assert current["cost_basis"]["allocation_revision"] == committed["allocation_revision"]
        assert current["cost_basis"]["cutoff_mapping_revision"] == 1
        assert current["cost_basis"]["complete_through"] == "2026-11-15"
        current_basis_lines = ProductUnitEconomicsQueryService._format_current_cost_basis(
            current["cost_basis"],
        )
        assert any("мост отсечки 1" in line for line in current_basis_lines)
        assert any("по 2026-11-15" in line for line in current_basis_lines)

        ui = TelegramFifoCostHistoryService(FifoCostHistoryService(reopened))
        rendered = ui._render_history({
            "snapshot": history, "display_name": "Товар",
            "sku": IDENTITY["sku"], "token": "private-token",
        })
        assert "границе следующей ставки" in rendered["message"]
        assert "не новая поставка" in rendered["message"]
        assert "2026-11-15" in rendered["message"]
        assert "ревизия mapping 1" in rendered["message"]
        exported = ui._export_history({
            "snapshot": history, "sku": IDENTITY["sku"], "identity": IDENTITY,
        })
        assert exported["error"] is False, exported
        records = list(csv.DictReader(
            io.StringIO(exported["file_content"].lstrip("\ufeff")), delimiter=";",
        ))
        rate_boundaries = [row for row in records if row["Тип записи"] == "RATE_BOUNDARY"]
        assert len(rate_boundaries) == 2
        assert all(row["Количество / остаток на границе"] != "" for row in rate_boundaries)
        assert all(row["Остаток после полного replay"] == "0" for row in rate_boundaries)
        assert all(row["Ревизия распределения"] == str(committed["allocation_revision"]) for row in records)
        assert all(row["Ревизия mapping cutoff"] == "1" for row in records)
        assert all(row["Покрытие mapping до"] == "2026-11-15" for row in records)

        period = reopened.read_period_allocation_summary(
            **IDENTITY, date_from="2026-11-08", date_to="2026-11-12",
        )
        assert period["error"] is False and period["complete"] is True, period
        assert period["stream_revision"] == history["revision"]
        assert period["allocation_revision"] == committed["allocation_revision"]
        assert period["period_cogs_rub"] == "1872.50"
        assert any(row["basis_kind"] == "RATE" for row in period["layers"])
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


def test_fr10_return_from_closed_rate_replays_exact_basis_without_rewriting_sales(
    tmp_path,
):
    repository = FifoCostRepository(
        db_path=tmp_path / "multirate-return.sqlite",
        now_provider=lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc),
    )
    token = set_current_tenant_user_id(
        make_store_tenant_scope("owner-multirate", IDENTITY["store_id"]),
    )
    try:
        _seed_three_rate_scenario(repository, mr05_sale_quantity=1)
        before = repository.preview_current_allocation(**IDENTITY)
        assert before["error"] is False, before
        initial_commit = repository.append_allocation_revision(
            **IDENTITY, preview=before, idempotency_key="fr10-initial-replay01",
        )
        assert initial_commit["error"] is False, initial_commit
        before_sale_cogs = {
            row["event_id"]: row["total_cost_rub"] for row in before["allocations"]
        }
        assert set(before_sale_cogs.values()) == {
            "92.30", "166.00", "1614.20", "18.00",
        }

        service = FifoCostReturnRestockService(
            repository,
            now_provider=lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc),
        )
        preview = service.preview_return(
            store_id=IDENTITY["store_id"], product_id=IDENTITY["product_id"],
            offer_id=IDENTITY["offer_id"], sku=IDENTITY["sku"],
            finance_sku=IDENTITY["sku"],
            identity={
                "mapping_confirmed": True,
                "product_id": IDENTITY["product_id"],
                "offer_id": IDENTITY["offer_id"],
            },
            return_record={
                "id": "private-return-mr03", "posting_number": "mr03",
                "sku": IDENTITY["sku"], "quantity": 10,
                "type": "ClientReturn",
                "visual_status_sys_name": "ArrivedAtReturnPlace",
                "compensation_status_sys_name": None,
            },
            recovery_evidence={
                "error": False, "return_id": "private-return-mr03",
                "posting_number": "mr03", "sku": IDENTITY["sku"],
                "quantity": 10, "recovery_state": "SALEABLE_RESTORED",
                "confirmed_on": "2026-11-13",
                "source": "SELLER_CONFIRMED_BOT",
                "inventory_recovery_confirmed": True,
            },
            return_sample_complete=True, cutoff_bridge_confirmed=True,
        )
        assert preview["error"] is False, preview
        assert preview["code"] == "FIFO_RETURN_RESTOCK_PREVIEW_READY"
        committed = service.commit_return(
            preview_id=preview["preview_id"],
            active_preview_id=preview["preview_id"],
            idempotency_key="fr10-return-closed-rate01",
            store_id=IDENTITY["store_id"], product_id=IDENTITY["product_id"],
            offer_id=IDENTITY["offer_id"], sku=IDENTITY["sku"],
        )
        assert committed["error"] is False, committed
        assert committed["code"] == "FIFO_RETURN_RESTOCK_COMMITTED", committed

        reopened = FifoCostRepository(
            db_path=tmp_path / "multirate-return.sqlite",
        )
        after = reopened.preview_current_allocation(**IDENTITY)
        assert after["error"] is False, after
        assert after["restored_units"] == 10
        assert after["total_cogs_rub"] == "1888.50"
        after_sale_cogs = {
            row["event_id"]: row["total_cost_rub"] for row in after["allocations"]
        }
        connection = reopened.get_connection()
        try:
            sale_ids = [row["event_id"] for row in connection.execute(
                """SELECT event_id FROM fifo_cost_events
                   WHERE stream_id=(SELECT stream_id FROM fifo_cost_streams WHERE store_id=?)
                     AND event_kind='PHYSICAL_SALE'
                   ORDER BY effective_date, event_id""",
                (IDENTITY["store_id"],),
            ).fetchall()]
        finally:
            connection.close()
        assert [after_sale_cogs[event_id] for event_id in sale_ids] == [
            "92.30", "1614.20", "166.00", "16.00",
        ]
        assert [before_sale_cogs[event_id] for event_id in sale_ids[:3]] == [
            after_sale_cogs[event_id] for event_id in sale_ids[:3]
        ]
        connection = reopened.get_connection()
        try:
            return_basis = connection.execute(
                """SELECT rate_change_id, quantity, unit_cost_rub, total_cost_rub
                   FROM fifo_cost_return_basis ORDER BY basis_line_number""",
            ).fetchall()
            sale_lineage = connection.execute(
                """SELECT line.rate_change_id, line.unit_cost_rub,
                          line.basis_allocation_id, line.basis_line_number
                   FROM fifo_cost_allocation_rate_lines AS line
                   JOIN fifo_cost_events AS event ON event.event_id=line.event_id
                   WHERE event.stream_id=(SELECT stream_id FROM fifo_cost_streams WHERE store_id=?)
                     AND line.allocation_id=(
                         SELECT allocation_id FROM fifo_cost_allocations
                         WHERE stream_id=event.stream_id ORDER BY revision DESC LIMIT 1
                     )
                     AND event.event_kind='PHYSICAL_SALE'
                     AND event.effective_date='2026-11-14'""",
                (IDENTITY["store_id"],),
            ).fetchall()
        finally:
            connection.close()
        assert [tuple(row) for row in return_basis] == [
            ("rate-multi-2", 7, "16.00", "112.00"),
            ("rate-multi-3", 3, "18.00", "54.00"),
        ]
        assert len(sale_lineage) == 1
        assert sale_lineage[0]["rate_change_id"] == "rate-multi-2"
        assert sale_lineage[0]["unit_cost_rub"] == "16.00"
        assert sale_lineage[0]["basis_allocation_id"] is not None
        assert sale_lineage[0]["basis_line_number"] is not None

        overflow_preview = _preview_saleable_return(
            service, posting_number="mr03", return_id="private-return-overflow",
            quantity=1, confirmed_on="2026-11-14",
        )
        assert overflow_preview["error"] is False, overflow_preview
        assert overflow_preview["code"] == "FIFO_RETURN_RESTOCK_BLOCKED"
        assert overflow_preview["reason_code"] == "FIFO_RETURN_QUANTITY_EXCEEDS_ORIGIN"
    finally:
        reset_current_tenant_user_id(token)


def test_fr10_partial_return_with_one_rate_basis_keeps_exact_cost(tmp_path):
    repository = FifoCostRepository(
        db_path=tmp_path / "multirate-partial-return.sqlite",
        now_provider=lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc),
    )
    token = set_current_tenant_user_id(
        make_store_tenant_scope("owner-multirate", IDENTITY["store_id"]),
    )
    try:
        _seed_three_rate_scenario(repository, mr05_sale_quantity=2)
        before = repository.preview_current_allocation(**IDENTITY)
        assert before["error"] is False, before
        committed_allocation = repository.append_allocation_revision(
            **IDENTITY, preview=before,
            idempotency_key="fr10-single-rate-before01",
        )
        assert committed_allocation["error"] is False, committed_allocation
        service = FifoCostReturnRestockService(
            repository,
            now_provider=lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc),
        )
        preview = _preview_saleable_return(
            service, posting_number="mr04", return_id="private-return-mr04-part",
            quantity=1, confirmed_on="2026-11-15",
        )
        assert preview["error"] is False, preview
        assert preview["code"] == "FIFO_RETURN_RESTOCK_PREVIEW_READY"
        returned = service.commit_return(
            preview_id=preview["preview_id"],
            active_preview_id=preview["preview_id"],
            idempotency_key="fr10-partial-single-rate01",
            store_id=IDENTITY["store_id"], product_id=IDENTITY["product_id"],
            offer_id=IDENTITY["offer_id"], sku=IDENTITY["sku"],
        )
        assert returned["error"] is False, returned
        assert returned["code"] == "FIFO_RETURN_RESTOCK_COMMITTED", returned

        reopened = FifoCostRepository(
            db_path=tmp_path / "multirate-partial-return.sqlite",
        )
        after = reopened.preview_current_allocation(**IDENTITY)
        assert after["error"] is False, after
        assert after["restored_units"] == 1
        assert after["total_cogs_rub"] == "1908.50"
        mr05 = [
            row for row in after["allocations"]
            if row["total_cost_rub"] == "36.00"
        ]
        assert len(mr05) == 1
        assert mr05[0]["total_cost_rub"] == "36.00"
        connection = reopened.get_connection()
        try:
            rows = connection.execute(
                """SELECT rate_change_id, quantity, unit_cost_rub, total_cost_rub
                   FROM fifo_cost_return_basis""",
            ).fetchall()
        finally:
            connection.close()
        assert [tuple(row) for row in rows] == [
            ("rate-multi-3", 1, "18.00", "18.00"),
        ]
    finally:
        reset_current_tenant_user_id(token)


def test_fr10_partial_return_restores_last_fifo_basis_for_mr04_mr05(tmp_path):
    repository = FifoCostRepository(
        db_path=tmp_path / "multirate-partial-mixed-return.sqlite",
        now_provider=lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc),
    )
    token = set_current_tenant_user_id(
        make_store_tenant_scope("owner-multirate", IDENTITY["store_id"]),
    )
    try:
        stream_id = _seed_three_rate_scenario(repository, mr05_sale_quantity=1)
        before = repository.preview_current_allocation(**IDENTITY)
        assert before["error"] is False, before
        committed_allocation = repository.append_allocation_revision(
            **IDENTITY, preview=before,
            idempotency_key="fr10-partial-mixed-before01",
        )
        assert committed_allocation["error"] is False, committed_allocation
        before_sale_cogs = {
            row["event_id"]: row["total_cost_rub"]
            for row in before["allocations"]
        }
        service = FifoCostReturnRestockService(
            repository,
            now_provider=lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc),
        )
        preview = _preview_saleable_return(
            service, posting_number="mr02", return_id="private-return-mr04",
            quantity=1, confirmed_on="2026-11-13",
        )
        assert preview["error"] is False, preview
        assert preview["code"] == "FIFO_RETURN_RESTOCK_PREVIEW_READY", preview
        committed = service.commit_return(
            preview_id=preview["preview_id"],
            active_preview_id=preview["preview_id"],
            idempotency_key="fr10-partial-mixed-mr04",
            store_id=IDENTITY["store_id"], product_id=IDENTITY["product_id"],
            offer_id=IDENTITY["offer_id"], sku=IDENTITY["sku"],
        )
        assert committed["error"] is False, committed
        assert committed["code"] == "FIFO_RETURN_RESTOCK_COMMITTED", committed

        reopened = FifoCostRepository(
            db_path=tmp_path / "multirate-partial-mixed-return.sqlite",
        )
        after = reopened.preview_current_allocation(**IDENTITY)
        assert after["error"] is False, after
        assert after["restored_units"] == 1
        assert after["total_cogs_rub"] == "1888.50"
        replayed_return = reopened.append_allocation_revision(
            **IDENTITY, preview=after,
            idempotency_key="fr11-return-reader-allocation01",
        )
        assert replayed_return["error"] is False, replayed_return
        return_history = FifoCostHistoryService(
            FifoCostRepository(db_path=tmp_path / "multirate-partial-mixed-return.sqlite"),
        ).get_sku_history(**IDENTITY, as_of_date=date(2026, 11, 16))
        assert return_history["latest_allocation"]["revision"] == replayed_return[
            "allocation_revision"
        ]
        assert [row["remaining_units"] for row in return_history["reconciled_rate_layers"]] == [0, 0]
        assert return_history["next_unit_cost_rub"] == "18.00"
        assert return_history["next_unit_cost_basis"] == "OPEN_RATE_QUANTITY_UNKNOWN"
        after_sale_cogs = {
            row["event_id"]: row["total_cost_rub"]
            for row in after["allocations"]
        }
        connection = repository.get_connection()
        try:
            sale_rows = connection.execute(
                """SELECT event_id, effective_date
                   FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='PHYSICAL_SALE'
                   ORDER BY effective_date""",
                (stream_id,),
            ).fetchall()
            basis = connection.execute(
                """SELECT b.rate_change_id, b.quantity, b.unit_cost_rub,
                          b.total_cost_rub, b.allocation_line_number,
                          r.event_id AS basis_sale_event_id,
                          r.rate_change_id AS allocated_rate_change_id
                   FROM fifo_cost_return_basis AS b
                   JOIN fifo_cost_allocation_rate_lines AS r
                     ON r.allocation_id=b.allocation_id
                    AND r.line_number=b.allocation_line_number
                   WHERE b.origin_sale_event_id=?""",
                (next(row["event_id"] for row in sale_rows
                      if row["effective_date"] == "2026-11-10"),),
            ).fetchall()
            count = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='SALEABLE_RETURN_RESTOCK'""",
                (stream_id,),
            ).fetchone()[0]
        finally:
            connection.close()
        assert count == 1
        assert [
            (row["effective_date"], after_sale_cogs[row["event_id"]])
            for row in sale_rows
        ] == [
            ("2026-11-08", "92.30"),
            ("2026-11-10", "1614.20"),
            ("2026-11-12", "166.00"),
            ("2026-11-14", "16.00"),
        ]
        for row in sale_rows[:3]:
            assert before_sale_cogs[row["event_id"]] == after_sale_cogs[row["event_id"]]
        assert len(basis) == 1
        assert basis[0]["rate_change_id"] == "rate-multi-2"
        assert basis[0]["quantity"] == 1
        assert basis[0]["unit_cost_rub"] == "16.00"
        assert basis[0]["total_cost_rub"] == "16.00"
        assert basis[0]["basis_sale_event_id"] == next(
            row["event_id"] for row in sale_rows
            if row["effective_date"] == "2026-11-10"
        )
        assert basis[0]["allocated_rate_change_id"] == "rate-multi-2"
    finally:
        reset_current_tenant_user_id(token)


def test_fr10_repeated_partial_returns_consume_latest_origin_basis_first(tmp_path):
    repository = FifoCostRepository(
        db_path=tmp_path / "multirate-repeated-partial-return.sqlite",
        now_provider=lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc),
    )
    token = set_current_tenant_user_id(
        make_store_tenant_scope("owner-multirate", IDENTITY["store_id"]),
    )
    try:
        stream_id = _seed_three_rate_scenario(repository)
        before = repository.preview_current_allocation(**IDENTITY)
        assert before["error"] is False, before
        allocation = repository.append_allocation_revision(
            **IDENTITY, preview=before,
            idempotency_key="fr10-repeated-partial-before01",
        )
        assert allocation["error"] is False, allocation
        service = FifoCostReturnRestockService(
            repository,
            now_provider=lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc),
        )

        for index, date in enumerate(("2026-11-13", "2026-11-14", "2026-11-15"), start=1):
            return_id = f"private-return-repeated-{index}"
            preview = _preview_saleable_return(
                service, posting_number="mr02", return_id=return_id,
                quantity=1, confirmed_on=date,
            )
            assert preview["code"] == "FIFO_RETURN_RESTOCK_PREVIEW_READY", preview
            committed = service.commit_return(
                preview_id=preview["preview_id"],
                active_preview_id=preview["preview_id"],
                idempotency_key=f"fr10-repeated-partial-{index}",
                store_id=IDENTITY["store_id"], product_id=IDENTITY["product_id"],
                offer_id=IDENTITY["offer_id"], sku=IDENTITY["sku"],
            )
            assert committed["code"] == "FIFO_RETURN_RESTOCK_COMMITTED", committed

        connection = repository.get_connection()
        try:
            sale_id = connection.execute(
                """SELECT event_id FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='PHYSICAL_SALE'
                     AND effective_date='2026-11-10'""",
                (stream_id,),
            ).fetchone()["event_id"]
            rows = connection.execute(
                """SELECT b.rate_change_id, b.quantity, b.unit_cost_rub,
                          b.total_cost_rub, e.effective_date
                   FROM fifo_cost_return_basis AS b
                   JOIN fifo_cost_events AS e ON e.event_id=b.return_event_id
                   WHERE b.origin_sale_event_id=?
                   ORDER BY e.effective_date, e.event_id""",
                (sale_id,),
            ).fetchall()
        finally:
            connection.close()

        assert [
            (row["rate_change_id"], row["quantity"], row["unit_cost_rub"],
             row["total_cost_rub"])
            for row in rows
        ] == [
            ("rate-multi-2", 1, "16.00", "16.00"),
            ("rate-multi-2", 1, "16.00", "16.00"),
            ("rate-multi-1", 1, "14.65", "14.65"),
        ]
        after = FifoCostRepository(
            db_path=tmp_path / "multirate-repeated-partial-return.sqlite",
        ).preview_current_allocation(**IDENTITY)
        assert after["error"] is False, after
        assert after["restored_units"] == 3
        assert after["total_cogs_rub"] == "1872.50"
    finally:
        reset_current_tenant_user_id(token)


def test_fr_review_full_return_preserves_two_same_rate_lines_from_distinct_origins(
    tmp_path,
):
    db_path = tmp_path / "same-rate-return-lines.sqlite"
    now = lambda: datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
    repository = FifoCostRepository(db_path=db_path, now_provider=now)
    token = set_current_tenant_user_id(
        make_store_tenant_scope("owner-multirate", IDENTITY["store_id"]),
    )
    try:
        _seed_three_rate_scenario(
            repository,
            additional_sales=(
                ("mr04", "2026-11-13", 1),
                ("mr05", "2026-11-14", 1),
                ("mr06", "2026-11-17", 2),
            ),
            mapping_complete_through="2026-11-18",
        )
        initial = repository.preview_current_allocation(**IDENTITY)
        assert initial["error"] is False, initial
        committed = repository.append_allocation_revision(
            **IDENTITY, preview=initial,
            idempotency_key="fr-review-same-rate-initial01",
        )
        assert committed["error"] is False, committed

        returns = FifoCostReturnRestockService(repository, now_provider=now)
        for index, posting_number in enumerate(("mr04", "mr05"), start=1):
            preview = _preview_saleable_return(
                returns, posting_number=posting_number,
                return_id=f"private-same-rate-origin-{index}", quantity=1,
                confirmed_on="2026-11-15" if index == 1 else "2026-11-16",
            )
            assert preview["code"] == "FIFO_RETURN_RESTOCK_PREVIEW_READY", preview
            restored = returns.commit_return(
                preview_id=preview["preview_id"],
                active_preview_id=preview["preview_id"],
                idempotency_key=f"fr-review-same-rate-origin-{index}",
                store_id=IDENTITY["store_id"], product_id=IDENTITY["product_id"],
                offer_id=IDENTITY["offer_id"], sku=IDENTITY["sku"],
            )
            assert restored["code"] == "FIFO_RETURN_RESTOCK_COMMITTED", restored
            if index == 1:
                refreshed = repository.preview_current_allocation(**IDENTITY)
                assert refreshed["error"] is False, refreshed
                refreshed_commit = repository.append_allocation_revision(
                    **IDENTITY, preview=refreshed,
                    idempotency_key="fr-review-same-rate-between-returns01",
                )
                assert refreshed_commit["error"] is False, refreshed_commit

        before_final_sale_return = repository.preview_current_allocation(**IDENTITY)
        assert before_final_sale_return["error"] is False, before_final_sale_return
        sale_cogs = {
            row["event_id"]: row["total_cost_rub"]
            for row in before_final_sale_return["allocations"]
        }
        assert len(sale_cogs) == 6
        final_sale = repository.append_allocation_revision(
            **IDENTITY, preview=before_final_sale_return,
            idempotency_key="fr-review-same-rate-before-final-return01",
        )
        assert final_sale["error"] is False, final_sale

        connection = repository.get_connection()
        try:
            sale_event = connection.execute(
                """SELECT event_id FROM fifo_cost_events
                   WHERE stream_id=(SELECT stream_id FROM fifo_cost_streams WHERE store_id=?)
                     AND event_kind='PHYSICAL_SALE' AND effective_date='2026-11-17'""",
                (IDENTITY["store_id"],),
            ).fetchone()
            same_rate_lines = connection.execute(
                """SELECT line_number, rate_change_id, quantity, unit_cost_rub,
                          total_cost_rub
                   FROM fifo_cost_allocation_rate_lines
                   WHERE allocation_id=? AND event_id=? ORDER BY line_number""",
                (final_sale["allocation_id"], sale_event["event_id"]),
            ).fetchall()
        finally:
            connection.close()
        assert [
            (row["rate_change_id"], row["quantity"], row["unit_cost_rub"],
             row["total_cost_rub"])
            for row in same_rate_lines
        ] == [
            ("rate-multi-3", 1, "18.00", "18.00"),
            ("rate-multi-3", 1, "18.00", "18.00"),
        ]
        sale_line_numbers = [row["line_number"] for row in same_rate_lines]
        assert len(set(sale_line_numbers)) == 2

        full_return = _preview_saleable_return(
            returns, posting_number="mr06", return_id="private-same-rate-full",
            quantity=2, confirmed_on="2026-11-18",
        )
        assert full_return["code"] == "FIFO_RETURN_RESTOCK_PREVIEW_READY", full_return
        committed_return = returns.commit_return(
            preview_id=full_return["preview_id"],
            active_preview_id=full_return["preview_id"],
            idempotency_key="fr-review-same-rate-full-return01",
            store_id=IDENTITY["store_id"], product_id=IDENTITY["product_id"],
            offer_id=IDENTITY["offer_id"], sku=IDENTITY["sku"],
        )
        assert committed_return["code"] == "FIFO_RETURN_RESTOCK_COMMITTED", committed_return

        reopened = FifoCostRepository(db_path=db_path, now_provider=now)
        after = reopened.preview_current_allocation(**IDENTITY)
        assert after["error"] is False, after
        assert after["complete"] is True, after
        assert after["total_cogs_rub"] == "1944.50"
        after_sale_cogs = {
            row["event_id"]: row["total_cost_rub"] for row in after["allocations"]
        }
        assert sale_cogs == after_sale_cogs
        connection = reopened.get_connection()
        try:
            return_basis = connection.execute(
                """SELECT b.allocation_line_number, b.quantity, b.unit_cost_rub,
                          b.total_cost_rub
                   FROM fifo_cost_return_basis AS b
                   WHERE b.origin_sale_event_id=(
                       SELECT event_id FROM fifo_cost_events
                       WHERE stream_id=(SELECT stream_id FROM fifo_cost_streams WHERE store_id=?)
                         AND event_kind='PHYSICAL_SALE'
                         AND effective_date='2026-11-17'
                   )
                   ORDER BY b.basis_line_number""",
                (IDENTITY["store_id"],),
            ).fetchall()
        finally:
            connection.close()
        assert [
            (row["quantity"], row["unit_cost_rub"], row["total_cost_rub"])
            for row in return_basis
        ] == [(1, "18.00", "18.00"), (1, "18.00", "18.00")]
        assert [row["allocation_line_number"] for row in return_basis] == sale_line_numbers
    finally:
        reset_current_tenant_user_id(token)


def test_fr10_non_sale_movement_uses_restored_rate_basis_outside_sales_cogs(tmp_path):
    repository = FifoCostRepository(
        db_path=tmp_path / "multirate-return-outflow.sqlite",
        now_provider=lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc),
    )
    token = set_current_tenant_user_id(
        make_store_tenant_scope("owner-multirate", IDENTITY["store_id"]),
    )
    try:
        _seed_three_rate_scenario(repository)
        before = repository.preview_current_allocation(**IDENTITY)
        assert before["error"] is False, before
        allocation = repository.append_allocation_revision(
            **IDENTITY, preview=before,
            idempotency_key="fr10-outflow-before01",
        )
        assert allocation["error"] is False, allocation
        now = lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
        returns = FifoCostReturnRestockService(repository, now_provider=now)
        return_preview = _preview_saleable_return(
            returns, posting_number="mr03", return_id="private-return-outflow",
            quantity=10, confirmed_on="2026-11-13",
        )
        assert return_preview["error"] is False, return_preview
        returned = returns.commit_return(
            preview_id=return_preview["preview_id"],
            active_preview_id=return_preview["preview_id"],
            idempotency_key="fr10-return-before-outflow01",
            store_id=IDENTITY["store_id"], product_id=IDENTITY["product_id"],
            offer_id=IDENTITY["offer_id"], sku=IDENTITY["sku"],
        )
        assert returned["code"] == "FIFO_RETURN_RESTOCK_COMMITTED", returned

        movements = FifoCostNonSaleMovementService(repository, now_provider=now)
        movement_preview = movements.preview_movement(
            store_id=IDENTITY["store_id"], product_id=IDENTITY["product_id"],
            offer_id=IDENTITY["offer_id"], sku=IDENTITY["sku"],
            movement_id="private-movement-mr06", reason_code="HOME_SHORTAGE",
            quantity=1, effective_date="2026-11-14",
            cutoff_bridge_confirmed=True,
        )
        assert movement_preview["code"] == "FIFO_NON_SALE_MOVEMENT_PREVIEW_READY", movement_preview
        assert movement_preview["estimated_fifo_value_rub"] == "16.00"
        assert movement_preview["included_in_sales_cogs"] is False
        movement = movements.commit_movement(
            preview_id=movement_preview["preview_id"],
            active_preview_id=movement_preview["preview_id"],
            idempotency_key="fr10-outflow-mr06-01",
            store_id=IDENTITY["store_id"], product_id=IDENTITY["product_id"],
            offer_id=IDENTITY["offer_id"], sku=IDENTITY["sku"],
        )
        assert movement["code"] == "FIFO_NON_SALE_MOVEMENT_COMMITTED", movement
        assert movement["estimated_outflow_value_rub"] == "16.00"
        assert movement["included_in_sales_cogs"] is False

        reopened = FifoCostRepository(
            db_path=tmp_path / "multirate-return-outflow.sqlite",
        )
        after = reopened.preview_current_allocation(**IDENTITY)
        assert after["error"] is False, after
        assert after["total_cogs_rub"] == "1872.50"
        assert after["non_sale_outflow_value_rub"] == "16.00"
        assert len(after["outflows"]) == 1
        assert after["outflows"][0]["estimated_value_rub"] == "16.00"
    finally:
        reset_current_tenant_user_id(token)
