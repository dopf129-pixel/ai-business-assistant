from datetime import datetime, timezone
import hashlib
from types import SimpleNamespace
import zipfile

from cryptography.fernet import Fernet

from services.bot_backup_service import BotBackupService
from services.fifo_cost_anchor_service import FifoCostAnchorService
from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_late_entry_correction_service import (
    FifoCostLateEntryCorrectionService,
)
from services.fifo_cost_rate_service import FifoCostRateService
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_replay_service import (
    FifoCostReplayService,
    FifoDatedAllocationEvent,
)
from services.fifo_cost_allocation_service import FifoCostLayer, FifoSaleEvent
from services.fifo_cost_source_normalizer import FifoCostSourceNormalizer
from services.fifo_cost_supply_evidence_service import FifoCostSupplyEvidenceService
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.fifo_cost_transition_contracts import TransitionState
from services.fifo_current_unit_cost_adapter import FifoCurrentUnitCostAdapter
from services.ozon_account_repository import make_store_tenant_scope
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.tenant_cipher_provider import decrypt_tenant_value
from services.tenant_storage import tenant_storage_path
from services.telegram_fifo_cost_history_service import TelegramFifoCostHistoryService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from test_fifo_cost_transition_atomic_apply import (
    CASE_ID,
    _commit as _commit_late_entry,
    _prepared_repository as _prepare_late_entry,
    SCOPE as LATE_ENTRY_SCOPE,
)
from test_fifo_cost_transition_store import _case as _transition_case


OWNER = "fifo-backup-owner"
STORE = "store-a"
TENANT_SCOPE = make_store_tenant_scope(OWNER, STORE)
IDENTITY = {
    "product_id": "product-101",
    "offer_id": "hook-2",
    "sku": "3921245627",
}
ALLOCATION_IDENTITY = {
    "product_id": "product-201", "offer_id": "sale-hook", "sku": "3921245630",
}
CORRECTION_IDENTITY = {
    "product_id": "product-301", "offer_id": "correction-hook", "sku": "3921245640",
}
TRANSIENT_IDENTITY = {
    "product_id": "product-401", "offer_id": "transient-hook", "sku": "3921245650",
}
NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)


class _NoLegacyCost:
    def get_current_cost_date(self):
        return "2026-11-06"

    def get_cost(self, _product_id):
        return None


def _backup_service(project, storage):
    return BotBackupService(
        project_root=project,
        storage_root=storage,
        backup_directory=project / ".local-backups",
        lifecycle_token="synthetic-token",
        lifecycle_inspector=lambda _token: {"state": "STOPPED"},
        lifecycle_state_root=project / ".synthetic-lifecycle",
        revision_reader=lambda _root: "fc31-synthetic",
        now_provider=lambda: NOW,
    )


def _anchor(repository):
    preview = FifoCostAnchorService(repository).preview_opening_anchor(
        **IDENTITY,
        store_id=STORE,
        inventory_cutoff="2026-11-05",
        cost_layers=[{
            "sequence": 1,
            "unit_cost_rub": "10.00",
            "ozon_units": 5,
            "transit_units": 0,
            "home_units": 0,
        }],
        ozon_units_include_reserved_confirmed=True,
        transit_not_in_ozon_confirmed=True,
    )
    assert preview["error"] is False, preview
    result = FifoCostAnchorService(repository).commit_opening_anchor(
        preview_id=preview["preview_id"],
        active_preview_id=preview["preview_id"],
        idempotency_key="fc31-backup-anchor-01",
    )
    assert result["error"] is False, result


def _supply_snapshot(
    identity=IDENTITY, *, fact=2, order_id=11, supply_id=2001, act_id=3001,
):
    products = {"supply_acts": [{
        "act_id": act_id,
        "type": "ACCEPTANCE",
        "items": [{
            "sku_info": {"sku": int(identity["sku"])},
            "declared_quantity": fact,
            "approved_quantity": 0,
            "fact_quantity": fact,
            "unidentified_quantity": 0,
        }],
    }]}
    summary = {"supplies_acts": [{
        "supply_id": supply_id,
        "is_agreement_completed": True,
        "supply_acts": [{
            "act_id": act_id,
            "type": "ACCEPTANCE",
            "act_state": "ACCEPTED",
            "created_date": "2026-11-04",
            "summary": {"fact_quantity": fact, "unidentified_quantity": 0},
        }],
    }]}
    return FifoCostSourceNormalizer().normalize_supply_act_snapshot(
        products,
        summary,
        store_id=STORE,
        expected_supply_id=supply_id,
        expected_order_id=order_id,
        captured_at=NOW,
        products_complete=True,
        summary_complete=True,
    )


def _commit_command(repository, identity, events, source, key):
    preview = repository.preview_command(
        store_id=STORE, **identity, events=events, source=source,
    )
    assert preview["error"] is False, preview
    result = repository.commit_command(
        preview_id=preview["preview_id"],
        active_preview_id=preview["preview_id"],
        idempotency_key=key,
    )
    assert result["error"] is False, result
    return result


def _allocation_preview(repository, identity):
    connection = repository.get_connection()
    try:
        connection.execute(
            "UPDATE fifo_cost_projections SET cutoff_status='RECONCILED' "
            "WHERE stream_id IN (SELECT stream_id FROM fifo_cost_streams WHERE sku=?)",
            (identity["sku"],),
        )
    finally:
        connection.close()
    guard = repository.read_allocation_guard(store_id=STORE, **identity)
    assert guard["error"] is False, guard
    connection = repository.get_connection()
    try:
        layers = [FifoCostLayer(row["layer_id"], row["unit_cost_rub"], row["quantity"])
                  for row in connection.execute(
                      "SELECT layer_id, unit_cost_rub, quantity FROM fifo_cost_layers "
                      "WHERE stream_id=(SELECT stream_id FROM fifo_cost_streams WHERE sku=?) "
                      "ORDER BY layer_sequence", (identity["sku"],),
                  )]
        sales = [FifoDatedAllocationEvent(
            event=FifoSaleEvent(row["event_id"], row["quantity"]),
            effective_at=row["effective_at"],
            effective_date=row["effective_date"],
            source_identity_digest=row["source_identity_digest"],
            physical_time_confirmed=True,
            cutoff_bridge_confirmed=True,
        ) for row in connection.execute(
            "SELECT event_id, quantity, effective_at, effective_date, "
            "source_identity_digest FROM fifo_cost_events "
            "WHERE stream_id=(SELECT stream_id FROM fifo_cost_streams WHERE sku=?) "
            "AND event_kind='PHYSICAL_SALE' ORDER BY effective_date", (identity["sku"],),
        )]
    finally:
        connection.close()
    preview = FifoCostReplayService().preview(
        layers=layers,
        events=sales,
        stream_revision=guard["stream_revision"],
        expected_allocation_revision=guard["allocation_revision"],
        source_set_fingerprint=guard["source_set_fingerprint"],
        anchor_cutoff_date="2026-11-01",
        anchor_status="CONFIRMED",
        cutoff_status="RECONCILED",
        source_completeness="COMPLETE",
    )
    return preview


def _seed_allocation(repository):
    anchor_source = {
        "kind": "OWNER_CONFIRMATION", "method": "OWNER_CONFIRMED_FIFO_CUTOFF",
        "status": "OWNER_CONFIRMED", "provenance": "OWNER_CONFIRMED",
        "coverage_status": "OWNER_CONFIRMED", "captured_at": "2026-11-06T12:00:00Z",
        "inventory_cutoff": "2026-11-01",
    }
    _commit_command(repository, ALLOCATION_IDENTITY, [{
        "kind": "OPENING_FIFO_ANCHOR", "quantity": 5, "unit_cost_rub": "7.00",
        "effective_date": "2026-11-01", "inventory_cutoff": "2026-11-01",
        "location_to": "OZON",
    }], anchor_source, "fc31-allocation-anchor")
    sale_source = {
        "kind": "OZON_REALIZATION", "method": "OZON_REALIZATION_REPORT",
        "status": "COMPLETE", "provenance": "OZON_CONFIRMED_FIELD",
        "coverage_status": "COMPLETE", "captured_at": "2026-11-06T12:05:00Z",
        "inventory_cutoff": "2026-11-01", "source_as_of": "2026-11-03T00:00:00Z",
    }
    _commit_command(repository, ALLOCATION_IDENTITY, [{
        "kind": "PHYSICAL_SALE", "quantity": 2, "effective_date": "2026-11-02",
        "inventory_cutoff": "2026-11-01", "source_identity_digest": "c" * 64,
    }], sale_source, "fc31-allocation-sale")
    preview = _allocation_preview(repository, ALLOCATION_IDENTITY)
    assert preview["complete"] is True, preview
    assert preview["total_cogs_rub"] == "14.00"
    committed = repository.append_allocation_revision(
        store_id=STORE, **ALLOCATION_IDENTITY, preview=preview,
        idempotency_key="fc31-allocation-revision",
    )
    assert committed["error"] is False, committed
    return preview


def _seed_correction(repository):
    anchor_source = {
        "kind": "OWNER_CONFIRMATION", "method": "OWNER_CONFIRMED_FIFO_CUTOFF",
        "status": "OWNER_CONFIRMED", "provenance": "OWNER_CONFIRMED",
        "coverage_status": "OWNER_CONFIRMED", "captured_at": "2026-11-06T12:00:00Z",
        "inventory_cutoff": "2026-11-01",
    }
    _commit_command(repository, CORRECTION_IDENTITY, [{
        "kind": "OPENING_FIFO_ANCHOR", "quantity": 100,
        "unit_cost_rub": "20.00", "effective_date": "2026-11-01",
        "inventory_cutoff": "2026-11-01", "location_to": "OZON",
    }], anchor_source, "fc31-correction-anchor")
    sale_source = {
        "kind": "OZON_REALIZATION", "method": "OZON_REALIZATION_REPORT",
        "status": "COMPLETE", "provenance": "OZON_CONFIRMED_FIELD",
        "coverage_status": "COMPLETE", "captured_at": "2026-11-06T12:05:00Z",
        "inventory_cutoff": "2026-11-01",
    }
    _commit_command(repository, CORRECTION_IDENTITY, [{
        "kind": "PHYSICAL_SALE", "quantity": 5, "effective_date": "2026-11-05",
        "inventory_cutoff": "2026-11-01", "source_identity_digest": "a" * 64,
    }], sale_source, "fc31-correction-sale")
    snapshot = _supply_snapshot(
        CORRECTION_IDENTITY, fact=100, order_id=12, supply_id=2002, act_id=3002,
    )
    draft = FifoCostSupplyEvidenceService(repository).record_late_entry_draft(
        store_id=STORE, **CORRECTION_IDENTITY, expected_revision=2,
        snapshot=snapshot, owner_effective_date="2026-11-03",
        owner_old_home_units=12, purchase_cost_rub="40.00",
        delivery_cost_rub="3.00", packaging_cost_rub="1.50",
    )
    assert draft["error"] is False, draft
    connection = repository.get_connection()
    try:
        connection.execute(
            "UPDATE fifo_cost_projections SET cutoff_status='RECONCILED', "
            "queue_complete=1 WHERE stream_id IN "
            "(SELECT stream_id FROM fifo_cost_streams WHERE sku=?)",
            (CORRECTION_IDENTITY["sku"],),
        )
    finally:
        connection.close()
    service = FifoCostLateEntryCorrectionService(repository, now_provider=lambda: NOW)
    periods = [{
        "period": "2026-11", "complete": True, "source_fingerprint": "d" * 64,
        "sale_identity_digests": ["a" * 64],
        "revenue": "1000.00", "discount_points": "0.00", "net_accrual": "500.00",
        "current_total_product_cost": "100.00", "current_sku_product_cost": "100.00",
    }]
    tax_policy = {"error": False, "configured": True, "policy": {
        "mode": "NONE", "tax_rate": 0, "minimum_tax_rate": 1,
    }}
    reconstruction = service.reconstruction_service.preview(
        store_id=STORE, **CORRECTION_IDENTITY, draft_id=draft["draft_id"],
    )
    assert reconstruction["code"] == "FIFO_LATE_ENTRY_RECONSTRUCTION_READY"
    from services.fifo_cost_late_entry_impact_service import FifoCostLateEntryImpactService

    normalized_policy = FifoCostLateEntryImpactService()._normalize_policy(tax_policy)
    summary_rows = [{
        **periods[0],
        "period_from": "2026-11-01",
        "period_to": "2026-11-30",
        "reconstruction_fingerprint": reconstruction["preview_fingerprint"],
        "tax_policy_fingerprint": normalized_policy["fingerprint"],
    }]
    preview = service.preview(
        store_id=STORE, **CORRECTION_IDENTITY, draft_id=draft["draft_id"],
        period_summaries=summary_rows,
        tax_policy_result=tax_policy,
    )
    assert preview["code"] == "FIFO_LATE_ENTRY_CORRECTION_PREVIEW_READY", preview
    committed = service.confirm(
        preview_id=preview["preview_id"], active_preview_id=preview["active_preview_id"],
        idempotency_key="fc31-late-correction-commit", store_id=STORE,
        **CORRECTION_IDENTITY, draft_id=draft["draft_id"],
        period_summaries=summary_rows, tax_policy_result=tax_policy,
    )
    assert committed["code"] == "FIFO_LATE_ENTRY_CORRECTION_COMMITTED", committed
    return draft["draft_id"], committed


def _plan_payload():
    return {
        "plan_kind": "single",
        "schema_version": 1,
        "calculation_version": 1,
        "target_margin_percent": "25.00",
        "items": [{
            "identity": {
                **IDENTITY,
                "product_name": "Синтетический товар",
                "store_id": STORE,
                "scheme": "FBO",
            },
            "inputs": {
                "price": "500.00", "cost": None, "commission_rate": "20",
                "advertising_rate": "10", "discount_points_rate": "20",
                "logistics_per_unit": "25", "last_mile_per_unit": "5",
                "acquiring_per_unit": "5", "tax_mode": "USN_INCOME",
                "tax_rate": "6", "minimum_tax_rate": None,
            },
            "provenance": {"price": "synthetic", "cost": "unknown"},
            "sources": {
                "periods": {"seller_price_as_of": "2026-11-06T12:00:00+00:00"},
                "as_of": "2026-11-06T12:00:00+00:00",
                "loaded_at": "2026-11-06T12:00:00+00:00",
                "completeness": {"catalog_identity": {"complete": True}},
            },
            "projection": {
                "available": False, "missing_inputs": ["cost"],
                "invalid_inputs": [], "revenue": "500.00", "profit": None,
            },
        }],
    }


def test_backup_restore_reopens_fifo_history_current_cost_export_and_plan(
    tmp_path, monkeypatch,
):
    project = tmp_path / "live-project"
    storage = tmp_path / "live-storage"
    project.mkdir()
    storage.mkdir()
    (project / ".env").write_text(
        "SYNTHETIC_SECRET_DO_NOT_ARCHIVE=FC31_SECRET_SENTINEL\n",
        encoding="utf-8",
    )
    runtime_cache = project / ".runtime-cache"
    runtime_cache.mkdir()
    (runtime_cache / "fifo-callback-tickets.json").write_text(
        '{"synthetic": "transient-ticket-sentinel"}', encoding="utf-8",
    )
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(storage))

    token = set_current_tenant_user_id(TENANT_SCOPE)
    try:
        repository = FifoCostRepository(now_provider=lambda: NOW)
        _anchor(repository)
        rates = FifoCostRateService(repository)
        rate_preview = rates.preview_new_cost(
            **IDENTITY,
            store_id=STORE,
            effective_date="2026-11-08",
            purchase_cost_rub="12.00",
            delivery_cost_rub="2.00",
            packaging_cost_rub="1.00",
            old_home_units=0,
            expected_revision=1,
        )
        assert rate_preview["error"] is False, rate_preview
        rate_result = rates.confirm_new_cost(
            preview_id=rate_preview["preview_id"],
            active_preview_id=rate_preview["preview_id"],
            idempotency_key="fc31-backup-rate-02",
        )
        assert rate_result["error"] is False, rate_result

        snapshot = _supply_snapshot()
        assert snapshot.status == "COMPLETE"
        evidence = FifoCostSupplyEvidenceService(repository).record_collected_supply(
            collection_result=SimpleNamespace(
                read_only=True, status=snapshot.status, supply_snapshot=snapshot,
            ),
            store_id=STORE,
            **IDENTITY,
            expected_revision=2,
        )
        assert evidence["error"] is False, evidence

        planning = PlanningWorkspaceRepository(clock=lambda: NOW)
        saved_plan = planning.save_document(
            title="Synthetic FIFO backup plan",
            payload=_plan_payload(),
            idempotency_key="fc31-plan-backup-01",
        )
        assert saved_plan["error"] is False, saved_plan
        allocation_basis = _seed_allocation(repository)
        correction_draft_id, correction_commit = _seed_correction(repository)
        before_corrections = repository.read_late_entry_corrections(
            store_id=STORE, **CORRECTION_IDENTITY,
        )
        assert before_corrections["error"] is False
        assert len(before_corrections["corrections"]) == 1

        history_service = FifoCostHistoryService(repository)
        before_history = history_service.get_sku_history(
            store_id=STORE, **IDENTITY, as_of_date="2026-11-06",
        )
        assert before_history["error"] is False
        assert before_history["revision"] == 2
        assert len(before_history["layers"]) == 1
        assert len(before_history["rates"]) == 1
        before_cost = FifoCurrentUnitCostAdapter(
            _NoLegacyCost(), history_service,
        ).resolve_current_cost(
            IDENTITY, store_id=STORE, as_of_date="2026-11-06",
        )
        assert before_cost["cost_per_unit_rub"] == "10.00"
        transient_preview = repository.preview_command(
            store_id=STORE,
            **TRANSIENT_IDENTITY,
            events=[{
                "kind": "OPENING_FIFO_ANCHOR", "quantity": 1,
                "unit_cost_rub": "99.00", "effective_date": "2026-11-06",
                "inventory_cutoff": "2026-11-06", "location_to": "OZON",
            }],
            source={
                "kind": "OWNER_CONFIRMATION", "method": "OWNER_CONFIRMED_FIFO_CUTOFF",
                "status": "OWNER_CONFIRMED", "provenance": "OWNER_CONFIRMED",
                "coverage_status": "OWNER_CONFIRMED", "captured_at": "2026-11-06T12:00:00Z",
                "inventory_cutoff": "2026-11-06",
            },
        )
        assert transient_preview["error"] is False, transient_preview

        pre_backup_history_bot = TelegramFifoCostHistoryService(history_service)
        old_callback = pre_backup_history_bot.create_sku_callback(
            user_id="synthetic-telegram-user",
            store_id=STORE,
            display_name="Synthetic item",
            **IDENTITY,
        )
        assert old_callback["error"] is False

        service = _backup_service(project, storage)
        backup = service.backup()
        assert backup["error"] is False, backup
        with zipfile.ZipFile(backup["backup_path"]) as archive:
            names = set(archive.namelist())
            assert "files/project/.env" not in names
            assert not any("runtime-cache" in name for name in names)
            tenant_folder = hashlib.sha256(TENANT_SCOPE.encode("utf-8")).hexdigest()[:24]
            tenant_database = (
                f"files/storage/data/tenants/{tenant_folder}/ozon_assistant.db"
            )
            assert tenant_database in names
            archived_database = archive.read(tenant_database)
            assert b"FC31_SECRET_SENTINEL" not in archived_database
            assert b"transient-ticket-sentinel" not in archived_database
            token_value = old_callback["callback"].rsplit(":", 1)[-1].encode("ascii")
            assert token_value not in archived_database

        target = tmp_path / "restored-root"
        dry_run = service.restore_archive(backup["backup_path"], target, dry_run=True)
        assert dry_run["status"] == "BOT_RESTORE_PLAN_READY", dry_run
        restored = service.restore_archive(backup["backup_path"], target)
        assert restored["status"] == "BOT_RESTORE_COMPLETE", restored
        monkeypatch.setenv(
            "AI_ASSISTANT_STORAGE_ROOT", str(target / "storage"),
        )

        reopened_repository = FifoCostRepository(now_provider=lambda: NOW)
        reopened_history = FifoCostHistoryService(reopened_repository)
        restored_history = reopened_history.get_sku_history(
            store_id=STORE, **IDENTITY, as_of_date="2026-11-06",
        )
        assert restored_history == before_history
        restored_supply = FifoCostSupplyEvidenceService(
            reopened_repository,
        ).read_history(store_id=STORE, **IDENTITY)
        assert restored_supply["error"] is False
        assert len(restored_supply["snapshots"]) == 1
        assert restored_supply["snapshots"][0]["acts"][0]["fact_quantity"] == 2
        assert restored_supply["snapshots"][0]["physical_effective_date"] is None
        connection = reopened_repository.get_connection()
        try:
            source_refs = {
                row[0] for row in connection.execute(
                    "SELECT reference_kind FROM fifo_cost_source_refs "
                    "WHERE source_id IN (SELECT source_id FROM fifo_cost_supply_evidence "
                    "WHERE stream_id IN (SELECT stream_id FROM fifo_cost_streams WHERE sku=?))",
                    (IDENTITY["sku"],),
                )
            }
            assert source_refs == {"ORDER", "SUPPLY"}
        finally:
            connection.close()

        allocation_summary = reopened_repository.read_period_allocation_summary(
            store_id=STORE, **ALLOCATION_IDENTITY,
            date_from="2026-11-02", date_to="2026-11-02",
        )
        assert allocation_summary["error"] is False, allocation_summary
        assert allocation_summary["allocation_revision"] == 1
        assert allocation_summary["period_units"] == 2
        assert allocation_summary["period_cogs_rub"] == "14.00"
        replay_after_restore = _allocation_preview(
            reopened_repository, ALLOCATION_IDENTITY,
        )
        assert replay_after_restore["complete"] is True
        assert replay_after_restore["total_cogs_rub"] == allocation_basis["total_cogs_rub"]
        assert replay_after_restore["allocations"] == allocation_basis["allocations"]

        restored_corrections = reopened_repository.read_late_entry_corrections(
            store_id=STORE, **CORRECTION_IDENTITY,
        )
        assert restored_corrections == before_corrections
        restored_drafts = reopened_repository.read_late_entry_drafts(
            store_id=STORE, **CORRECTION_IDENTITY,
        )
        assert restored_drafts["error"] is False
        assert restored_drafts["drafts"][0]["draft_id"] == correction_draft_id
        assert restored_drafts["drafts"][0]["correction_id"] == correction_commit["correction_id"]

        restored_cost = FifoCurrentUnitCostAdapter(
            _NoLegacyCost(), reopened_history,
        ).resolve_current_cost(
            IDENTITY, store_id=STORE, as_of_date="2026-11-06",
        )
        assert restored_cost["cost_per_unit_rub"] == before_cost["cost_per_unit_rub"]
        assert restored_cost["cost_revision"] == before_cost["cost_revision"]

        # A new process has no in-memory confirmation tickets from the source process.
        FifoCostRepository._ACTIVE_PREVIEWS.clear()
        FifoCostRepository._ACTIVE_RATE_PREVIEWS.clear()
        stale_confirmation = reopened_repository.commit_command(
            preview_id=transient_preview["preview_id"],
            active_preview_id=transient_preview["preview_id"],
            idempotency_key="fc31-transient-confirm",
        )
        assert stale_confirmation == {
            "error": True, "code": "FIFO_PREVIEW_STALE",
        }

        restored_planning = PlanningWorkspaceRepository(clock=lambda: NOW)
        plan = restored_planning.get_document(saved_plan["document_id"])
        assert plan["error"] is False, plan
        assert plan["document"]["revision"] == 1
        restored_plan_item = plan["document"]["payload"]["items"][0]
        assert restored_plan_item["identity"]["sku"] == IDENTITY["sku"]
        assert restored_plan_item["inputs"]["price"] == "500.00"
        assert restored_plan_item["inputs"]["cost"] is None
        assert plan["document"]["payload"]["sales_mix"] is None

        post_restore_bot = TelegramFifoCostHistoryService(reopened_history)
        stale_callback = post_restore_bot.handle_callback(
            "synthetic-telegram-user", old_callback["callback"],
        )
        assert stale_callback["error"] is True
        fresh_callback = post_restore_bot.create_sku_callback(
            user_id="synthetic-telegram-user",
            store_id=STORE,
            display_name="Synthetic item",
            **IDENTITY,
        )
        assert fresh_callback["error"] is False
        export = post_restore_bot.handle_callback(
            "synthetic-telegram-user",
            fresh_callback["callback"].replace(":open:", ":export:", 1),
        )
        assert export["error"] is False, export
        assert export["filename"] == "fifo-cost-history.csv"
        assert "FINITE_LAYER" in export["file_content"]
        assert "OPEN_RATE" in export["file_content"]
        assert old_callback["callback"].rsplit(":", 1)[-1] not in export["file_content"]
    finally:
        reset_current_tenant_user_id(token)


def test_backup_restore_preserves_late_entry_states_ciphertext_and_single_apply(
    tmp_path, monkeypatch,
):
    project = tmp_path / "late-entry-project"
    storage = tmp_path / "late-entry-storage"
    project.mkdir()
    storage.mkdir()
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(storage))
    master_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", master_key)

    tenant = set_current_tenant_user_id(
        make_store_tenant_scope(LATE_ENTRY_SCOPE.owner_id, LATE_ENTRY_SCOPE.store_id),
    )
    active_tenant = None
    try:
        tenant_database = tenant_storage_path("ozon_assistant.db")
        (
            repository, active_tenant, _stock, bridge, impact,
            _cutover, prepared, _clock,
        ) = _prepare_late_entry(tmp_path, db_path=tenant_database)
        applied = _commit_late_entry(repository, bridge, impact, prepared)
        assert applied["error"] is False, applied

        transition_service = FifoCostTransitionService(repository)
        draft = _transition_case(
            case_id="backup-late-draft-01", sku="3921245628",
            owner=LATE_ENTRY_SCOPE.owner_id, store=LATE_ENTRY_SCOPE.store_id,
        )
        draft_saved = transition_service.create_case(
            case=draft, idempotency_key="backup-late-draft-create01",
        )
        assert draft_saved["error"] is False, draft_saved

        awaiting = _transition_case(
            case_id="backup-late-awaiting-01", sku="3921245629",
            owner=LATE_ENTRY_SCOPE.owner_id, store=LATE_ENTRY_SCOPE.store_id,
        )
        awaiting_saved = transition_service.create_case(
            case=awaiting, idempotency_key="backup-late-await-create01",
        )
        assert awaiting_saved["error"] is False, awaiting_saved
        awaiting_identity = {
            "product_id": awaiting.metadata.scope.product_id,
            "offer_id": awaiting.metadata.scope.offer_id,
            "sku": awaiting.metadata.scope.sku,
        }
        awaiting_updated = transition_service.update_owner_inputs(
            case_id=awaiting.case_id, store_id=LATE_ENTRY_SCOPE.store_id,
            **awaiting_identity,
            expected_revision=1, updates={"dispatch_date": "2026-11-05"},
            state=TransitionState.AWAITING_EVIDENCE,
            idempotency_key="backup-late-await-update01",
        )
        assert awaiting_updated["error"] is False, awaiting_updated
        declaration = transition_service.declare_supply(
            case_id=awaiting.case_id,
            store_id=awaiting.metadata.scope.store_id,
            product_id=awaiting.metadata.scope.product_id,
            offer_id=awaiting.metadata.scope.offer_id,
            sku=awaiting.metadata.scope.sku,
            reference_kind="SUPPLY", reference_id="987654321",
            declared_shipped_units=148, dispatch_date="2026-11-05",
            expected_case_revision=2,
            idempotency_key="backup-late-supply-declare01",
        )
        assert declaration["error"] is False, declaration

        before_declaration = repository.read_transition_evidence(
            case_id=awaiting.case_id, store_id=LATE_ENTRY_SCOPE.store_id,
            **awaiting_identity,
            kind="SUPPLY_DECLARATION", limit=10,
            include_encrypted_lookup_reference=True,
        )
        assert before_declaration["error"] is False
        encrypted_reference = before_declaration["items"][0]["encrypted_lookup_reference"]
        assert encrypted_reference and "987654321" not in encrypted_reference

        def fifo_counts(repo):
            connection = repo.get_connection()
            try:
                names = [
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name LIKE 'fifo_cost_%' ORDER BY name",
                    )
                ]
                return {
                    name: connection.execute(
                        f'SELECT COUNT(*) FROM "{name}"',
                    ).fetchone()[0]
                    for name in names
                }
            finally:
                connection.close()

        before_counts = fifo_counts(repository)
        service = _backup_service(project, storage)
        backup = service.backup()
        assert backup["error"] is False, backup
        tenant_folder = hashlib.sha256(
            make_store_tenant_scope(
                LATE_ENTRY_SCOPE.owner_id, LATE_ENTRY_SCOPE.store_id,
            ).encode("utf-8"),
        ).hexdigest()[:24]
        archived_database = (
            f"files/storage/data/tenants/{tenant_folder}/ozon_assistant.db"
        )
        with zipfile.ZipFile(backup["backup_path"]) as archive:
            assert archived_database in archive.namelist()
            archived_bytes = archive.read(archived_database)
            assert b"987654321" not in archived_bytes
            assert encrypted_reference.encode("ascii") in archived_bytes

        target = tmp_path / "late-entry-restored"
        assert service.restore_archive(
            backup["backup_path"], target, dry_run=True,
        )["status"] == "BOT_RESTORE_PLAN_READY"
        restored = service.restore_archive(backup["backup_path"], target)
        assert restored["status"] == "BOT_RESTORE_COMPLETE", restored
        monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(target / "storage"))
        reopened = FifoCostRepository(
            now_provider=lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc),
        )
        reopened_service = FifoCostTransitionService(reopened)
        for case_id, identity, state in (
            (
                draft.case_id,
                {
                    "product_id": draft.metadata.scope.product_id,
                    "offer_id": draft.metadata.scope.offer_id,
                    "sku": draft.metadata.scope.sku,
                },
                "DRAFT",
            ),
            (awaiting.case_id, awaiting_identity, "AWAITING_EVIDENCE"),
            (
                CASE_ID,
                {
                    "product_id": LATE_ENTRY_SCOPE.product_id,
                    "offer_id": LATE_ENTRY_SCOPE.offer_id,
                    "sku": LATE_ENTRY_SCOPE.sku,
                },
                "APPLIED",
            ),
        ):
            case_read = reopened_service.get_case(
                case_id=case_id, store_id=LATE_ENTRY_SCOPE.store_id, **identity,
            )
            assert case_read["error"] is False, case_read
            assert case_read["state"] == state

        restored_declaration = reopened.read_transition_evidence(
            case_id=awaiting.case_id, store_id=LATE_ENTRY_SCOPE.store_id,
            **awaiting_identity,
            kind="SUPPLY_DECLARATION", limit=10,
            include_encrypted_lookup_reference=True,
        )
        assert restored_declaration["error"] is False
        assert restored_declaration["items"][0]["encrypted_lookup_reference"] == encrypted_reference
        wrong_key = Fernet.generate_key().decode("ascii")
        assert decrypt_tenant_value(
            encrypted_reference, master_key=wrong_key,
        ) is None
        monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", wrong_key)
        wrong_key_manifest = reopened_service.get_supply_manifest(
            case_id=awaiting.case_id, store_id=LATE_ENTRY_SCOPE.store_id,
            **awaiting_identity,
        )
        assert wrong_key_manifest["error"] is False
        assert len(wrong_key_manifest["declarations"]) == 1
        assert wrong_key_manifest["declarations"][0]["lookup_status"] == "AVAILABLE"

        assert fifo_counts(reopened) == before_counts
        replay = _commit_late_entry(reopened, bridge, impact, prepared)
        assert replay["error"] is False, replay
        assert replay["replayed"] is True
        assert replay["commit_id"] == applied["commit_id"]
        assert fifo_counts(reopened) == before_counts
    finally:
        if active_tenant is not None:
            reset_current_tenant_user_id(active_tenant)
        reset_current_tenant_user_id(tenant)

