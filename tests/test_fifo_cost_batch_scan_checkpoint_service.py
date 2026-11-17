from dataclasses import replace
from decimal import Decimal
import hashlib
import sqlite3

from cryptography.fernet import Fernet
import pytest

from services.fifo_cost_batch_rule_contracts import (
    BatchRuleEventKind,
    BatchRuleRevision,
    BatchStartDayPolicy,
    DispatchTimeStatus,
    SupplyMembership,
    SupplyScanCoverage,
    SupplySkuObservation,
)
from services.fifo_cost_batch_scan_checkpoint_service import (
    FifoCostBatchScanCheckpointService,
)
from services.fifo_cost_batch_supply_store import FifoCostBatchSupplyStore
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    ScopeIdentity,
)


_OWNER = "checkpoint-owner"
_TENANT = "checkpoint-tenant"
_TENANT_FP = hashlib.sha256(_TENANT.encode()).hexdigest()
_SCOPE = ScopeIdentity(
    owner_id=_OWNER, store_id="store-1", sku="sku-1",
    product_id="product-1", offer_id="offer-1",
)
_CASE_ID = "case-checkpoint-1"
_RULE_ID = "rule-checkpoint-1"
_RULE_FP = hashlib.sha256(b"rule-fingerprint").hexdigest()
_NOW = "2026-11-13T10:05:00Z"


def _digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _rule():
    return BatchRuleRevision(
        scope=_SCOPE, case_id=_CASE_ID, rule_id=_RULE_ID,
        rule_revision=1, policy_version=1, start_local_date="2026-11-05",
        store_timezone="Europe/Moscow",
        start_day_policy=BatchStartDayPolicy.ALL_OWNER_CONFIRMED,
        new_unit_cost_rub=Decimal("14.65"),
        cost_input_fingerprint=_digest("cost-input"),
        old_home_confirmed_zero=True, old_transit_confirmed_zero=True,
        boundary_supply_digests=(_digest("boundary"),),
        predecessor_rule_id=None, predecessor_rule_revision=None,
        event_kind=BatchRuleEventKind.CONFIRM, end_local_date_exclusive=None,
        owner_confirmation_fingerprint=_digest("owner-confirmation"),
        confirmed_at_utc="2026-11-13T10:00:00Z", rule_fingerprint=_RULE_FP,
    )


def _observation(*, source_fingerprint="source-1", quantity=100, captured_at="2026-11-13T10:01:00Z"):
    return SupplySkuObservation(
        scope=_SCOPE, record_key=_digest("supply-sku-1"),
        order_ref_digest=_digest("order-1"), supply_ref_digest=_digest("supply-1"),
        encrypted_lookup_payload="gAAAA" + "A" * 96,
        source_profile_version="synthetic-v1",
        source_fingerprint=_digest(source_fingerprint), captured_at=captured_at,
        source_as_of=None, source_status="IN_TRANSIT",
        normalized_status=NormalizedSupplyStatus.IN_TRANSIT, is_crossdock=True,
        dispatch_local_date="2026-11-05", dispatch_local_time=None,
        dispatch_time_status=DispatchTimeStatus.CONFIRMED,
        planned_declared_quantity=quantity, shipped_composition_quantity=quantity,
        accepted_quantity=None, quantity_source_kind=EvidenceSourceKind.OZON_API,
        quantity_coverage=EvidenceCompleteness.COMPLETE, acceptance_fingerprint=None,
        acceptance_version=None, explicit_zero_fields=(), membership=SupplyMembership.ELIGIBLE,
    )


def _coverage(*, revision=1, scan_id="scan-checkpoint-1", resumable_token=None):
    return SupplyScanCoverage(
        scan_id=scan_id, revision=revision, scope=_SCOPE, case_id=_CASE_ID,
        rule_revision=1, requested_from="2026-11-05", requested_through="2026-11-13",
        captured_at=f"2026-11-13T10:{revision:02d}:00Z", source_as_of=None,
        supported_state_profile=("IN_TRANSIT", "COMPLETED"),
        list_pagination_complete=False, details_complete=False,
        sku_composition_complete=False, historical_window_proven=False,
        membership_complete=False, quantity_complete=False,
        physical_receipt_timing_complete=False,
        observation_set_fingerprint=_digest("placeholder-set"),
        source_contract_version="synthetic-v1", orders_seen=revision,
        supplies_seen=revision, sku_rows_seen=revision,
        unknown_order_count=0, unknown_supply_count=0,
        unknown_quantity_supply_count=0, issue_codes=("SCAN_IN_PROGRESS",),
        resumable_token=resumable_token,
    )


def _repository(tmp_path, monkeypatch):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode())
    repository = FifoCostRepository(db_path=tmp_path / "scan-checkpoint.sqlite")
    connection = repository.get_connection()
    owner_fp = hashlib.sha256(_OWNER.encode()).hexdigest()
    connection.execute(
        """INSERT INTO fifo_cost_transition_cases (
            case_id, schema_version, owner_fingerprint, tenant_fingerprint,
            store_id, product_id, offer_id, sku, current_revision, current_state,
            created_at, updated_at
        ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, 1, 'DRAFT', 'now', 'now')""",
        (_CASE_ID, owner_fp, _TENANT_FP, _SCOPE.store_id, _SCOPE.product_id,
         _SCOPE.offer_id, _SCOPE.sku),
    )
    connection.commit()
    connection.execute("BEGIN IMMEDIATE")
    stored = FifoCostBatchSupplyStore.append_rule_revision(
        connection, _rule(), tenant_fingerprint=_TENANT_FP,
        idempotency_key="checkpoint-rule-1", recorded_at=_NOW,
    )
    assert stored["error"] is False
    connection.commit()
    connection.close()
    return repository


def _commit(service, *, revision, expected_revision, observation, status="PARTIAL", state=None):
    return service.commit_page(
        coverage=_coverage(revision=revision), tenant_fingerprint=_TENANT_FP,
        rule_id=_RULE_ID, rule_fingerprint=_RULE_FP, expected_case_revision=1,
        expected_scan_revision=expected_revision,
        observations=() if observation is None else (observation,),
        status=status, expires_at="2026-11-13T10:25:00Z",
        updated_at=f"2026-11-13T10:{revision + 5:02d}:00Z",
        continuation_state=state if status in {"STAGING", "PARTIAL"} else None,
        now=_NOW,
    )


def _load(service, token, **overrides):
    values = {
        "scope": _SCOPE, "case_id": _CASE_ID, "tenant_fingerprint": _TENANT_FP,
        "rule_id": _RULE_ID, "rule_revision": 1, "rule_fingerprint": _RULE_FP,
        "expected_case_revision": 1, "source_contract_version": "synthetic-v1",
        "supported_state_profile": ("IN_TRANSIT", "COMPLETED"),
        "requested_from": "2026-11-05", "requested_through": "2026-11-13",
        "continuation_token": token, "now": _NOW,
    }
    values.update(overrides)
    return service.load_continuation(**values)


def test_checkpoint_resumes_after_service_restart_and_replays_stale_reference_safely(
    tmp_path, monkeypatch,
):
    repository = _repository(tmp_path, monkeypatch)
    state = {
        "cursor": "page-2", "seen_cursor_digests": (_digest("page-1"),),
        "pages_scanned": 1,
    }
    first = _commit(
        FifoCostBatchScanCheckpointService(repository), revision=1,
        expected_revision=0, observation=_observation(), state=state,
    )
    assert first["code"] == "FIFO_BATCH_SCAN_PAGE_COMMITTED"
    assert first["continuation_token"] == "scan-checkpoint-1_r1"

    restarted = FifoCostBatchScanCheckpointService(repository)
    resumed = _load(restarted, first["continuation_token"])
    assert resumed["code"] == "FIFO_BATCH_SCAN_RESUMED"
    assert resumed["continuation_state"] == {
        "cursor": "page-2", "seen_cursor_digests": (_digest("page-1"),),
        "pages_scanned": 1,
    }

    second = _commit(
        restarted, revision=2, expected_revision=1,
        observation=_observation(source_fingerprint="source-2", quantity=80),
        state={
            "cursor": "page-3", "seen_cursor_digests": (_digest("page-1"), _digest("page-2")),
            "pages_scanned": 2,
        },
    )
    assert second["scan_revision"] == 2
    assert _load(restarted, first["continuation_token"])["resumed_from_stale_token"] is True

    final = _commit(
        restarted, revision=3, expected_revision=2, observation=None, status="PUBLISHED",
    )
    assert final["continuation_token"] is None
    assert _load(restarted, second["continuation_token"])["code"] == "FIFO_BATCH_SCAN_NOT_RESUMABLE"
    connection = repository.get_connection()
    try:
        refs = FifoCostBatchSupplyStore.read_scan_observation_refs(
            connection, scope=_SCOPE, case_id=_CASE_ID,
            tenant_fingerprint=_TENANT_FP, scan_id="scan-checkpoint-1",
        )
        assert len(refs) == 2
        assert [row["observation_revision"] for row in refs] == [1, 2]
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_batch_supply_observations WHERE case_id=?",
            (_CASE_ID,),
        ).fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_rate_changes").fetchone()[0] == 0
    finally:
        connection.close()


def test_checkpoint_binds_case_rule_scope_range_profile_and_ttl(tmp_path, monkeypatch):
    repository = _repository(tmp_path, monkeypatch)
    service = FifoCostBatchScanCheckpointService(repository)
    stored = _commit(
        service, revision=1, expected_revision=0, observation=None,
        state={"cursor": "next", "seen_cursor_digests": (), "pages_scanned": 1},
    )
    token = stored["continuation_token"]
    assert _load(service, token, expected_case_revision=2)["code"] == "FIFO_BATCH_CASE_REVISION_CONFLICT"
    assert _load(service, token, rule_fingerprint=_digest("different-rule"))["code"] == "FIFO_BATCH_SCAN_BINDING_CONFLICT"
    assert _load(service, token, requested_from="2026-11-06")["code"] == "FIFO_BATCH_SCAN_BINDING_CONFLICT"
    assert _load(service, token, source_contract_version="synthetic-v2")["code"] == "FIFO_BATCH_SCAN_BINDING_CONFLICT"
    assert _load(service, token, now="2026-11-13T10:26:00Z")["code"] == "FIFO_BATCH_SCAN_EXPIRED"
    assert _load(service, "scan-checkpoint-1_r99")["code"] == "FIFO_BATCH_SCAN_REVISION_CONFLICT"

    other_scope = replace(_SCOPE, store_id="store-2")
    assert _load(service, token, scope=other_scope)["code"] == "FIFO_BATCH_SCAN_NOT_FOUND"


def test_checkpoint_cas_failure_rolls_back_observation_and_link(tmp_path, monkeypatch):
    repository = _repository(tmp_path, monkeypatch)
    service = FifoCostBatchScanCheckpointService(repository)
    first = _commit(
        service, revision=1, expected_revision=0, observation=None,
        state={"cursor": "next", "seen_cursor_digests": (), "pages_scanned": 1},
    )
    failed = _commit(
        service, revision=2, expected_revision=0,
        observation=_observation(), state={"cursor": "next-2", "seen_cursor_digests": (), "pages_scanned": 2},
    )
    assert failed["code"] == "FIFO_BATCH_SCAN_REVISION_CONFLICT"
    connection = repository.get_connection()
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_batch_supply_observations WHERE case_id=?",
            (_CASE_ID,),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_batch_scan_observations WHERE case_id=?",
            (_CASE_ID,),
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_checkpoint_rejects_duplicate_page_keys_and_bad_or_oversized_continuation(
    tmp_path, monkeypatch,
):
    repository = _repository(tmp_path, monkeypatch)
    service = FifoCostBatchScanCheckpointService(repository)
    observation = _observation()
    duplicate_page = service.commit_page(
        coverage=_coverage(), tenant_fingerprint=_TENANT_FP,
        rule_id=_RULE_ID, rule_fingerprint=_RULE_FP, expected_case_revision=1,
        expected_scan_revision=0, observations=(observation, observation),
        status="PARTIAL", expires_at="2026-11-13T10:25:00Z",
        updated_at="2026-11-13T10:06:00Z",
        continuation_state={"cursor": "next", "seen_cursor_digests": (), "pages_scanned": 1},
        now=_NOW,
    )
    assert duplicate_page["code"] == "FIFO_BATCH_SCAN_DUPLICATE_PAGE_ROW"
    bad_state = _commit(
        service, revision=1, expected_revision=0, observation=None,
        state={"cursor": "next", "seen_cursor_digests": (_digest("same"), _digest("same")), "pages_scanned": 1},
    )
    assert bad_state["code"] == "FIFO_BATCH_SCAN_TOKEN_INVALID"
    too_many_cursors = [_digest(f"cursor-{index}") for index in range(101)]
    too_many = _commit(
        service, revision=1, expected_revision=0, observation=None,
        state={"cursor": "next", "seen_cursor_digests": too_many_cursors, "pages_scanned": 1},
    )
    assert too_many["code"] == "FIFO_BATCH_SCAN_TOKEN_INVALID"


def test_checkpoint_fails_closed_when_tenant_encryption_key_is_unavailable(
    tmp_path, monkeypatch,
):
    repository = _repository(tmp_path, monkeypatch)
    monkeypatch.delenv("OZON_CREDENTIAL_MASTER_KEY")
    service = FifoCostBatchScanCheckpointService(repository)
    result = _commit(
        service, revision=1, expected_revision=0, observation=_observation(),
        state={"cursor": "next", "seen_cursor_digests": (), "pages_scanned": 1},
    )
    assert result["code"] == "FIFO_BATCH_SCAN_ENCRYPTION_UNAVAILABLE"
    connection = repository.get_connection()
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_batch_supply_scans WHERE case_id=?",
            (_CASE_ID,),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_batch_supply_observations WHERE case_id=?",
            (_CASE_ID,),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_batch_scan_observations WHERE case_id=?",
            (_CASE_ID,),
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_checkpoint_publishes_only_after_all_page_links_and_link_rows_are_append_only(
    tmp_path, monkeypatch,
):
    repository = _repository(tmp_path, monkeypatch)
    service = FifoCostBatchScanCheckpointService(repository)
    published = _commit(
        service, revision=1, expected_revision=0, observation=_observation(),
        status="PUBLISHED",
    )
    assert published["status"] == "PUBLISHED"
    connection = repository.get_connection()
    try:
        link = connection.execute(
            "SELECT * FROM fifo_cost_batch_scan_observations WHERE case_id=?",
            (_CASE_ID,),
        ).fetchone()
        assert link is not None
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE fifo_cost_batch_scan_observations SET linked_at='changed' "
                "WHERE case_id=?", (_CASE_ID,),
            )
    finally:
        connection.close()
