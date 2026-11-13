from datetime import datetime, timezone

import pytest

from services.fifo_cost_late_entry_correction_service import (
    FifoCostLateEntryCorrectionService,
)
from services.fifo_cost_late_entry_reconstruction_service import (
    FifoCostLateEntryReconstructionService,
)
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_source_normalizer import FifoCostSourceNormalizer
from services.fifo_cost_supply_evidence_service import FifoCostSupplyEvidenceService
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


IDENTITY = {
    "store_id": "store-a", "product_id": "product-a",
    "offer_id": "offer-a", "sku": "3921245627",
}
SUMMARY = [{
    "period": "2026-11", "complete": True, "source_fingerprint": "d" * 64,
    "sale_identity_digests": ["a" * 64],
    "revenue": "1000.00", "discount_points": "0.00", "net_accrual": "500.00",
    "current_total_product_cost": "100.00", "current_sku_product_cost": "100.00",
}]
TAX = {"error": False, "configured": True, "policy": {
    "mode": "NONE", "tax_rate": 0, "minimum_tax_rate": 1,
}}


def _source(kind, method, status, provenance, coverage, captured_at, cutoff):
    return {
        "kind": kind, "method": method, "status": status,
        "completeness": status, "provenance": provenance,
        "coverage_status": coverage, "captured_at": captured_at,
        "inventory_cutoff": cutoff,
    }


def _command(repository, events, source):
    preview = repository.preview_command(**IDENTITY, events=events, source=source)
    assert preview["error"] is False, preview
    result = repository.commit_command(
        preview_id=preview["preview_id"], active_preview_id=preview["preview_id"],
        idempotency_key=f"late-correction-{preview['next_revision']:04d}",
    )
    assert result["error"] is False, result


@pytest.fixture
def ready_correction(tmp_path):
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    now = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
    repository = FifoCostRepository(
        db_path=tmp_path / "late-correction.sqlite", now_provider=lambda: now,
    )
    _command(repository, [{
        "kind": "OPENING_FIFO_ANCHOR", "quantity": 100,
        "unit_cost_rub": "20.00", "effective_date": "2026-11-01",
        "inventory_cutoff": "2026-11-01", "location_to": "OZON",
    }], _source(
        "OWNER_CONFIRMATION", "OWNER_CONFIRMED_FIFO_CUTOFF", "OWNER_CONFIRMED",
        "OWNER_CONFIRMED", "OWNER_CONFIRMED", "2026-11-06T12:00:00Z", "2026-11-01",
    ))
    _command(repository, [{
        "kind": "PHYSICAL_SALE", "quantity": 5,
        "effective_date": "2026-11-05", "inventory_cutoff": "2026-11-01",
        "source_identity_digest": "a" * 64,
    }], _source(
        "OZON_REALIZATION", "OZON_REALIZATION_REPORT", "COMPLETE",
        "OZON_CONFIRMED_FIELD", "COMPLETE", "2026-11-06T12:05:00Z", "2026-11-01",
    ))
    products = {"supply_acts": [{
        "act_id": 3001, "type": "ACCEPTANCE", "items": [{
            "sku_info": {"sku": int(IDENTITY["sku"])},
            "declared_quantity": 100, "approved_quantity": 0,
            "fact_quantity": 100, "unidentified_quantity": 0,
        }],
    }]}
    summary = {"supplies_acts": [{
        "supply_id": 2001, "is_agreement_completed": True,
        "supply_acts": [{
            "act_id": 3001, "type": "ACCEPTANCE", "act_state": "ACCEPTED",
            "created_date": "2026-11-04",
            "summary": {"fact_quantity": 100, "unidentified_quantity": 0},
        }],
    }]}
    snapshot = FifoCostSourceNormalizer().normalize_supply_act_snapshot(
        products, summary, store_id=IDENTITY["store_id"],
        expected_supply_id=2001, expected_order_id=11, captured_at=now,
        products_complete=True, summary_complete=True,
    )
    draft = FifoCostSupplyEvidenceService(repository).record_late_entry_draft(
        **IDENTITY, expected_revision=2, snapshot=snapshot,
        owner_effective_date="2026-11-03", owner_old_home_units=12,
        purchase_cost_rub="40.00", delivery_cost_rub="3.00",
        packaging_cost_rub="1.50",
    )
    assert draft["error"] is False, draft
    connection = repository.get_connection()
    connection.execute(
        "UPDATE fifo_cost_projections SET cutoff_status='RECONCILED', queue_complete=1",
    )
    connection.close()
    service = FifoCostLateEntryCorrectionService(
        repository,
        reconstruction_service=FifoCostLateEntryReconstructionService(repository),
        now_provider=lambda: now,
    )
    try:
        yield repository, service, draft["draft_id"]
    finally:
        reset_current_tenant_user_id(token)


def _preview(repo_service, draft_id, summaries=SUMMARY):
    _, service, _ = repo_service
    return service.preview(
        **IDENTITY, draft_id=draft_id,
        period_summaries=summaries, tax_policy_result=TAX,
    )


def _confirm(service, preview, draft_id, *, key="late-correction-confirm-01", summaries=SUMMARY):
    return service.confirm(
        preview_id=preview["preview_id"], active_preview_id=preview["active_preview_id"],
        idempotency_key=key, **IDENTITY, draft_id=draft_id,
        period_summaries=summaries, tax_policy_result=TAX,
    )


def test_fc22_atomic_commit_appends_rate_and_correction_without_publishing_stale_profit(
    ready_correction,
):
    repository, service, draft_id = ready_correction
    preview = _preview(ready_correction, draft_id)
    assert preview["code"] == "FIFO_LATE_ENTRY_CORRECTION_PREVIEW_READY", preview
    assert preview["periods"][0]["delta_cogs_rub"] == "0.00"

    result = _confirm(service, preview, draft_id)

    assert result["code"] == "FIFO_LATE_ENTRY_CORRECTION_COMMITTED", result
    assert result["period_profit_changed"] is False
    assert result["replay_required"] is True
    assert repository.read_cost_history_snapshot(**IDENTITY)["revision"] == 3
    assert len(repository.read_cost_history_snapshot(**IDENTITY)["rates"]) == 1
    drafts = repository.read_late_entry_drafts(**IDENTITY)["drafts"]
    assert drafts[0]["correction_id"] == result["correction_id"]
    corrections = repository.read_late_entry_corrections(**IDENTITY)["corrections"]
    assert len(corrections) == 1
    assert corrections[0]["impact"]["periods"][0]["delta_cogs_rub"] == "0.00"
    connection = repository.get_connection()
    projection = connection.execute(
        "SELECT state, queue_complete FROM fifo_cost_projections",
    ).fetchone()
    assert tuple(projection) == ("FIFO_PARTIAL", 0)
    connection.close()


def test_fc22_confirm_is_idempotent_and_rejects_different_key(ready_correction):
    _, service, draft_id = ready_correction
    preview = _preview(ready_correction, draft_id)
    first = _confirm(service, preview, draft_id)
    repeated = _confirm(service, preview, draft_id)
    conflict = _confirm(service, preview, draft_id, key="other-correction-key-02")

    assert first["code"] == "FIFO_LATE_ENTRY_CORRECTION_COMMITTED"
    assert repeated["idempotent"] is True
    assert repeated["correction_id"] == first["correction_id"]
    assert conflict["reason_code"] == "FIFO_IDEMPOTENCY_CONFLICT"


def test_fc22_changed_period_source_invalidates_preview_without_writes(ready_correction):
    repository, service, draft_id = ready_correction
    preview = _preview(ready_correction, draft_id)
    changed = [dict(SUMMARY[0], source_fingerprint="e" * 64)]

    result = _confirm(service, preview, draft_id, summaries=changed)

    assert result["reason_code"] == "FIFO_LATE_ENTRY_SOURCE_STALE"
    assert repository.read_cost_history_snapshot(**IDENTITY)["revision"] == 2
    assert repository.read_cost_history_snapshot(**IDENTITY)["rates"] == []
    assert repository.read_late_entry_corrections(**IDENTITY)["corrections"] == []


def test_fc22_changed_financial_recognition_period_invalidates_preview_without_writes(
    ready_correction,
):
    repository, service, draft_id = ready_correction
    preview = _preview(ready_correction, draft_id)
    changed_period = [dict(SUMMARY[0], period="2026-10")]

    result = _confirm(service, preview, draft_id, summaries=changed_period)

    assert result["reason_code"] == "FIFO_LATE_ENTRY_SOURCE_STALE"
    assert repository.read_cost_history_snapshot(**IDENTITY)["revision"] == 2
    assert repository.read_cost_history_snapshot(**IDENTITY)["rates"] == []
    assert repository.read_late_entry_corrections(**IDENTITY)["corrections"] == []


def test_fc22_cannot_prepare_confirmation_without_financial_sale_mapping(ready_correction):
    repository, service, draft_id = ready_correction
    unassigned = [dict(SUMMARY[0])]
    unassigned[0].pop("sale_identity_digests")

    result = service.preview(
        **IDENTITY, draft_id=draft_id,
        period_summaries=unassigned, tax_policy_result=TAX,
    )

    assert result["code"] == "FIFO_LATE_ENTRY_IMPACT_CANDIDATE_ONLY"
    assert result["reason_code"] == "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"
    assert "preview_id" not in result
    assert repository.read_cost_history_snapshot(**IDENTITY)["revision"] == 2
    assert repository.read_late_entry_corrections(**IDENTITY)["corrections"] == []


def test_fc22_new_sale_revision_invalidates_preview_before_commit(ready_correction):
    repository, service, draft_id = ready_correction
    preview = _preview(ready_correction, draft_id)
    _command(repository, [{
        "kind": "PHYSICAL_SALE", "quantity": 1,
        "effective_date": "2026-11-06", "inventory_cutoff": "2026-11-01",
        "source_identity_digest": "b" * 64,
    }], _source(
        "OZON_REALIZATION", "OZON_REALIZATION_REPORT", "COMPLETE",
        "OZON_CONFIRMED_FIELD", "COMPLETE", "2026-11-06T12:10:00Z", "2026-11-01",
    ))

    result = _confirm(service, preview, draft_id)

    assert result["code"] == "FIFO_LATE_ENTRY_CORRECTION_BLOCKED"
    assert result["reason_code"] == "FIFO_LATE_ENTRY_SOURCE_STALE"
    assert repository.read_cost_history_snapshot(**IDENTITY)["revision"] == 3
    assert repository.read_cost_history_snapshot(**IDENTITY)["rates"] == []
    assert repository.read_late_entry_corrections(**IDENTITY)["corrections"] == []


def test_fc22_correction_insert_failure_rolls_back_rate_and_projection(ready_correction):
    repository, service, draft_id = ready_correction
    preview = _preview(ready_correction, draft_id)
    connection = repository.get_connection()
    connection.execute(
        """CREATE TRIGGER test_fail_late_correction BEFORE INSERT
           ON fifo_cost_late_entry_corrections
           BEGIN SELECT RAISE(ABORT, 'forced rollback'); END""",
    )
    connection.close()

    result = _confirm(service, preview, draft_id)

    assert result["error"] is True
    snapshot = repository.read_cost_history_snapshot(**IDENTITY)
    assert snapshot["revision"] == 2
    assert snapshot["rates"] == []
    assert repository.read_late_entry_corrections(**IDENTITY)["corrections"] == []
    connection = repository.get_connection()
    projection = connection.execute(
        "SELECT revision, queue_complete FROM fifo_cost_projections",
    ).fetchone()
    assert tuple(projection) == (1, 1)
    connection.close()


def test_fc22_other_store_cannot_confirm_owner_ticket(ready_correction):
    _, service, draft_id = ready_correction
    preview = _preview(ready_correction, draft_id)
    token = set_current_tenant_user_id(make_store_tenant_scope("other-owner", "store-b"))
    try:
        result = service.confirm(
            preview_id=preview["preview_id"],
            active_preview_id=preview["active_preview_id"],
            idempotency_key="late-correction-confirm-01",
            **{**IDENTITY, "store_id": "store-b"}, draft_id=draft_id,
            period_summaries=SUMMARY, tax_policy_result=TAX,
        )
    finally:
        reset_current_tenant_user_id(token)

    assert result["reason_code"] == "FIFO_PREVIEW_STALE"
