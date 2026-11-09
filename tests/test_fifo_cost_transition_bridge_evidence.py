from dataclasses import replace
from datetime import datetime, timezone
import inspect
import json

from cryptography.fernet import Fernet
import pytest

from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_contracts import (
    CostInputMode,
    EvidenceCompleteness,
    EvidenceSourceKind,
    ScopeIdentity,
    TransitionBridgeEvidence,
    TransitionBridgeEvidenceKind,
    TransitionCase,
    TransitionEvidenceConfirmation,
    TransitionEvidenceConfirmationKind,
    TransitionMetadata,
    TransitionState,
    UnknownValue,
    TransitionReasonCode,
)
from services.fifo_cost_transition_store import FifoCostTransitionStore
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


STORE = "store-transition"
OWNER = "owner-transition"
TENANT = make_store_tenant_scope(OWNER, STORE)
IDENTITY = {
    "store_id": STORE,
    "product_id": "product-1",
    "offer_id": "offer-1",
    "sku": "sku-1",
}
MASTER_KEY = Fernet.generate_key().decode("ascii")


def _metadata(*, source_kind=EvidenceSourceKind.OZON_API,
              completeness=EvidenceCompleteness.COMPLETE, owner=OWNER):
    return TransitionMetadata(
        scope=ScopeIdentity(
            owner_id=owner, store_id=STORE, product_id="product-1",
            offer_id="offer-1", sku="sku-1",
        ),
        source_kind=source_kind,
        completeness=completeness,
        source_fingerprint="a" * 64,
    )


def _case():
    return TransitionCase(
        metadata=_metadata(
            source_kind=EvidenceSourceKind.OWNER_INPUT,
            completeness=EvidenceCompleteness.PARTIAL,
        ),
        case_id="case_000001", case_revision=1, state=TransitionState.DRAFT,
        created_at="2026-11-08T10:00:00Z", updated_at="2026-11-08T10:00:00Z",
        dispatch_date="2026-11-05", old_unit_cost_rub="21.00",
        new_unit_cost_rub="14.65", cost_input_mode=CostInputMode.TOTAL_LANDED,
        cost_components=None, owner_old_home_units=0, owner_old_transit_units=0,
        new_home_quantity=None, declared_shipped_units=6982,
        unknown_values={
            "new_home_quantity": UnknownValue(
                reason_code=TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
                source_kind=EvidenceSourceKind.OWNER_INPUT,
            ),
        },
    )


def _evidence(*, kind=TransitionBridgeEvidenceKind.FINANCE_IDENTITY_SNAPSHOT,
              source_kind=EvidenceSourceKind.OZON_API,
              completeness=EvidenceCompleteness.COMPLETE,
              sensitive_payload='{"posting_number":"secret-123"}'):
    if kind is TransitionBridgeEvidenceKind.FINANCE_IDENTITY_SNAPSHOT:
        payload = {
            "snapshot_fingerprint": "b" * 64,
            "identity_fingerprint": "c" * 64,
            "row_count": 1,
            "matched_rows": 1,
            "page_count": 1,
            "scope_complete": True,
            "pagination_complete": True,
        }
        return TransitionBridgeEvidence(
            metadata=_metadata(source_kind=source_kind, completeness=completeness),
            evidence_kind=kind, captured_at="2026-11-08T11:00:00Z",
            as_of="2026-11-08T10:59:00Z", row_count=1, payload=payload,
            sensitive_payload=sensitive_payload,
        )
    payload = {
        "document_fingerprint": "b" * 64,
        "row_count": 1,
        "period_from": "2026-11-01",
        "period_to": "2026-11-07",
        "timezone": "Europe/Moscow",
        "semantics": "PHYSICAL_OUTFLOW",
        "identity_fingerprint": "c" * 64,
    }
    return TransitionBridgeEvidence(
        metadata=_metadata(
            source_kind=EvidenceSourceKind.OWNER_IMPORTED,
            completeness=completeness,
        ),
        evidence_kind=TransitionBridgeEvidenceKind.PHYSICAL_SALES_DOCUMENT,
        captured_at="2026-11-08T11:00:00Z", period_from="2026-11-01",
        period_to="2026-11-07", complete_through="2026-11-07",
        row_count=1, payload=payload, sensitive_payload=sensitive_payload,
    )


def _repository(tmp_path):
    return FifoCostRepository(
        db_path=tmp_path / "bridge-evidence.sqlite",
        now_provider=lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc),
    )


def _create_case(repository):
    return repository.save_transition_case(
        case=_case(), expected_revision=0,
        idempotency_key="create-case-0001",
    )


def test_bridge_evidence_api_is_keyword_only_and_enforces_encryption_and_restart(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", MASTER_KEY)
    token = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path)
        assert _create_case(repository)["error"] is False
        saved = repository.append_transition_bridge_evidence(
            case_id="case_000001", evidence=_evidence(),
            expected_case_revision=1, idempotency_key="append-evidence-001",
        )
        assert saved["error"] is False, saved
        assert saved["case_revision"] == 2
        assert saved["state"] == "AWAITING_EVIDENCE"
        replay = repository.append_transition_bridge_evidence(
            case_id="case_000001", evidence=_evidence(),
            expected_case_revision=1, idempotency_key="append-evidence-001",
        )
        assert replay["replayed"] is True
        assert replay["case_revision"] == 2

        read = repository.read_transition_bridge_evidence(
            case_id="case_000001", **IDENTITY,
        )
        assert read["error"] is False
        item = read["items"][0]
        assert item["sensitive_payload_available"] is True
        assert "sensitive_payload" not in item
        assert "secret-123" not in repr(read)

        decrypted = repository.read_transition_bridge_evidence(
            case_id="case_000001", **IDENTITY, include_sensitive_payload=True,
        )
        assert decrypted["items"][0]["sensitive_payload"] == (
            '{"posting_number":"secret-123"}'
        )

        confirmation = TransitionEvidenceConfirmation(
            confirmation_kind=TransitionEvidenceConfirmationKind.EVIDENCE_REVIEW,
            confirmed_fields={
                "reviewed_fingerprint": saved["payload_fingerprint"],
                "review_outcome": "CONFIRMED",
            },
        )
        mismatched_confirmation = TransitionEvidenceConfirmation(
            confirmation_kind=TransitionEvidenceConfirmationKind.PHYSICAL_SALES,
            confirmed_fields={
                "document_fingerprint": "b" * 64,
                "row_count": 1,
                "rows_fingerprint": "c" * 64,
                "period_from": "2026-11-01",
                "period_to": "2026-11-07",
                "timezone": "Europe/Moscow",
                "semantics": "PHYSICAL_OUTFLOW",
            },
        )
        mismatched = repository.confirm_transition_evidence(
            case_id="case_000001", metadata=_evidence().metadata,
            evidence_id=saved["evidence_id"],
            expected_evidence_fingerprint=saved["payload_fingerprint"],
            confirmation=mismatched_confirmation, expected_case_revision=2,
            idempotency_key="confirm-wrong-kind-01",
        )
        assert mismatched["code"] == "FIFO_TRANSITION_CONFIRMATION_INVALID"
        confirmed = repository.confirm_transition_evidence(
            case_id="case_000001", metadata=_evidence().metadata,
            evidence_id=saved["evidence_id"],
            expected_evidence_fingerprint=saved["payload_fingerprint"],
            confirmation=confirmation, expected_case_revision=2,
            idempotency_key="confirm-evidence-01",
        )
        assert confirmed["error"] is False, confirmed
        assert confirmed["case_revision"] == 3
        repeated_confirmation = repository.confirm_transition_evidence(
            case_id="case_000001", metadata=_evidence().metadata,
            evidence_id=saved["evidence_id"],
            expected_evidence_fingerprint=saved["payload_fingerprint"],
            confirmation=confirmation, expected_case_revision=2,
            idempotency_key="confirm-evidence-01",
        )
        assert repeated_confirmation["error"] is False
        assert repeated_confirmation["replayed"] is True

        stored = repository.get_connection()
        try:
            row = stored.execute(
                "SELECT payload_json, encrypted_payload FROM fifo_cost_transition_bridge_evidence"
            ).fetchone()
            assert "secret-123" not in row["payload_json"]
            assert b"secret-123" not in row["encrypted_payload"]
        finally:
            stored.close()

        restarted = _repository(tmp_path)
        durable = restarted.read_transition_bridge_evidence(
            case_id="case_000001", **IDENTITY, include_sensitive_payload=True,
        )
        assert durable["error"] is False
        assert durable["items"][0]["payload_fingerprint"] == item["payload_fingerprint"]
        assert durable["items"][0]["sensitive_payload"] == decrypted["items"][0]["sensitive_payload"]
        visible = restarted.read_transition_bridge_evidence(
            case_id="case_000001", **IDENTITY,
        )
        assert visible["items"][0]["confirmations"][0]["confirmed_fields"] == {
            "reviewed_fingerprint": saved["payload_fingerprint"],
            "review_outcome": "CONFIRMED",
        }
        assert all(
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
            for name in (
                "append_transition_bridge_evidence", "confirm_transition_evidence",
                "read_transition_bridge_evidence", "read_transition_preview",
            )
            for parameter in inspect.signature(getattr(FifoCostRepository, name)).parameters.values()
            if parameter.name != "self"
        )
    finally:
        reset_current_tenant_user_id(token)


def test_bridge_evidence_requires_typed_completeness_and_rejects_unsafe_payloads():
    from services.fifo_cost_transition_contracts import TransitionContractError

    incomplete = _evidence(completeness=EvidenceCompleteness.PARTIAL)
    assert incomplete.metadata.completeness is EvidenceCompleteness.PARTIAL
    bad = _evidence()
    with pytest.raises(TransitionContractError):
        replace(
            bad,
            payload={**dict(bad.payload), "pagination_complete": False},
        )
    with pytest.raises(TransitionContractError):
        replace(bad, payload={**dict(bad.payload), "raw_posting_number": "private"})
    with pytest.raises(TransitionContractError):
        replace(bad, payload={**dict(bad.payload), "pagination_complete": 1})
    with pytest.raises(TransitionContractError):
        replace(bad, payload={**dict(bad.payload), "matched_rows": True})
    physical = _evidence(kind=TransitionBridgeEvidenceKind.PHYSICAL_SALES_DOCUMENT)
    with pytest.raises(TransitionContractError):
        replace(physical, row_count=2)


def test_encryption_key_failure_preserves_case_but_blocks_evidence_and_confirmation(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", MASTER_KEY)
    token = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path)
        assert _create_case(repository)["error"] is False
        saved = repository.append_transition_bridge_evidence(
            case_id="case_000001", evidence=_evidence(),
            expected_case_revision=1, idempotency_key="append-evidence-002",
        )
        assert saved["error"] is False
        monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
        read = repository.read_transition_bridge_evidence(
            case_id="case_000001", **IDENTITY, include_sensitive_payload=True,
        )
        assert read["error"] is False
        assert read["items"][0]["sensitive_payload_available"] is False
        assert read["items"][0]["blocker"] == "FIFO_TRANSITION_ENCRYPTION_UNAVAILABLE"
        confirmation = TransitionEvidenceConfirmation(
            confirmation_kind=TransitionEvidenceConfirmationKind.EVIDENCE_REVIEW,
            confirmed_fields={
                "reviewed_fingerprint": saved["payload_fingerprint"],
                "review_outcome": "CONFIRMED",
            },
        )
        confirmed = repository.confirm_transition_evidence(
            case_id="case_000001", metadata=_evidence().metadata,
            evidence_id=saved["evidence_id"],
            expected_evidence_fingerprint=saved["payload_fingerprint"],
            confirmation=confirmation, expected_case_revision=2,
            idempotency_key="confirm-evidence-01",
        )
        assert confirmed["code"] == "FIFO_TRANSITION_ENCRYPTION_UNAVAILABLE"
        assert repository.read_transition_case(
            case_id="case_000001", **IDENTITY,
        )["case_revision"] == 2
    finally:
        reset_current_tenant_user_id(token)


def test_bridge_evidence_wrong_tenant_and_case_revision_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", MASTER_KEY)
    owner = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path)
        assert _create_case(repository)["error"] is False
        stale = repository.append_transition_bridge_evidence(
            case_id="case_000001", evidence=_evidence(),
            expected_case_revision=2, idempotency_key="stale-evidence-01",
        )
        assert stale["code"] == "FIFO_TRANSITION_REVISION_CONFLICT"
        saved = repository.append_transition_bridge_evidence(
            case_id="case_000001", evidence=_evidence(),
            expected_case_revision=1, idempotency_key="append-evidence-003",
        )
        assert saved["error"] is False
        other = set_current_tenant_user_id(make_store_tenant_scope("other-owner", STORE))
        try:
            result = repository.read_transition_bridge_evidence(
                case_id="case_000001", **IDENTITY,
            )
            assert result["code"] == "FIFO_TRANSITION_CASE_NOT_FOUND"
        finally:
            reset_current_tenant_user_id(other)
    finally:
        reset_current_tenant_user_id(owner)


def test_missing_key_and_cancelled_case_do_not_append_evidence(tmp_path, monkeypatch):
    monkeypatch.delenv("OZON_CREDENTIAL_MASTER_KEY", raising=False)
    token = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path)
        assert _create_case(repository)["error"] is False
        no_key = repository.append_transition_bridge_evidence(
            case_id="case_000001", evidence=_evidence(),
            expected_case_revision=1, idempotency_key="append-evidence-005",
        )
        assert no_key["code"] == "FIFO_TRANSITION_ENCRYPTION_UNAVAILABLE"
        assert repository.read_transition_case(
            case_id="case_000001", **IDENTITY,
        )["case_revision"] == 1

        cancelled_case = replace(
            _case(), case_revision=2, state=TransitionState.CANCELLED,
            updated_at="2026-11-08T12:00:00Z",
        )
        cancelled = repository.cancel_transition_case(
            case=cancelled_case, expected_revision=1,
            idempotency_key="cancel-case-0001",
        )
        assert cancelled["error"] is False
        monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", MASTER_KEY)
        closed = repository.append_transition_bridge_evidence(
            case_id="case_000001", evidence=_evidence(),
            expected_case_revision=2, idempotency_key="append-evidence-006",
        )
        assert closed["code"] == "FIFO_TRANSITION_CASE_NOT_READY"
        connection = repository.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_transition_bridge_evidence"
            ).fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_corrupted_bridge_payload_fails_hash_check(tmp_path, monkeypatch):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", MASTER_KEY)
    token = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path)
        assert _create_case(repository)["error"] is False
        saved = repository.append_transition_bridge_evidence(
            case_id="case_000001", evidence=_evidence(),
            expected_case_revision=1, idempotency_key="append-evidence-007",
        )
        assert saved["error"] is False
        connection = repository.get_connection()
        connection.execute(
            "DROP TRIGGER IF EXISTS trg_fifo_cost_transition_bridge_evidence_no_update"
        )
        connection.execute(
            "UPDATE fifo_cost_transition_bridge_evidence SET payload_json='{}' WHERE evidence_id=?",
            (saved["evidence_id"],),
        )
        connection.commit()
        connection.close()
        read = repository.read_transition_bridge_evidence(
            case_id="case_000001", **IDENTITY,
        )
        assert read["code"] == "FIFO_TRANSITION_EVIDENCE_CORRUPT"
    finally:
        reset_current_tenant_user_id(token)


def test_new_evidence_invalidates_ready_case_and_keeps_old_preview_seal(tmp_path, monkeypatch):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", MASTER_KEY)
    token = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path)
        assert _create_case(repository)["error"] is False
        connection = repository.get_connection()
        payload = {
            "schema_version": 1, "case_id": "case_000001", "case_revision": 1,
            "base_fifo_revision": 1, "base_allocation_revision": 1,
            "evidence_set_fingerprint": "d" * 64,
            "tax_policy_fingerprint": "e" * 64,
        }
        fingerprint = repository._sha256(payload)
        preview_id = "transpreview_" + fingerprint[:40]
        connection.execute("BEGIN IMMEDIATE")
        current = connection.execute(
            "SELECT payload_json FROM fifo_cost_transition_case_revisions WHERE case_id=? AND case_revision=1",
            ("case_000001",),
        ).fetchone()
        case_payload = json.loads(current["payload_json"])
        case_payload["case_revision"] = 2
        case_payload["state"] = "READY_TO_CONFIRM"
        case_payload["last_preview"] = {"preview_id": preview_id}
        case_payload_json = repository._canonical_json(case_payload)
        connection.execute(
            "UPDATE fifo_cost_transition_cases SET current_revision=2, current_state='READY_TO_CONFIRM' WHERE case_id='case_000001'"
        )
        FifoCostTransitionStore._insert_case_revision(
            connection, case_id="case_000001", case_revision=2,
            state="READY_TO_CONFIRM", payload_json=case_payload_json,
            fingerprint=FifoCostTransitionStore._digest(case_payload_json),
            idempotency_key="ready-preview-case-revision",
            created_at="2026-11-08T11:00:00.000000Z",
            updated_at="2026-11-08T11:00:00.000000Z",
        )
        connection.execute(
            """INSERT INTO fifo_cost_transition_previews (
                preview_id, case_id, case_revision, fifo_revision, allocation_revision,
                evidence_set_fingerprint, tax_policy_fingerprint, preview_fingerprint,
                created_at, expires_at, payload_json
            ) VALUES (?, 'case_000001', 2, 1, 1, ?, ?, ?, ?, ?, ?)""",
            (preview_id, "d" * 64, "e" * 64, fingerprint,
             "2026-11-08T11:00:00.000000Z", "2026-11-08T11:10:00.000000Z",
             repository._canonical_json(payload)),
        )
        connection.commit()
        connection.close()

        old_preview = repository.read_transition_preview(
            case_id="case_000001", preview_id=preview_id, **IDENTITY,
        )
        assert old_preview["error"] is False
        assert old_preview["is_current"] is True
        appended = repository.append_transition_bridge_evidence(
            case_id="case_000001", evidence=_evidence(),
            expected_case_revision=2, idempotency_key="append-evidence-004",
        )
        assert appended["error"] is False
        assert appended["state"] == "AWAITING_EVIDENCE"
        historical = repository.read_transition_preview(
            case_id="case_000001", preview_id=preview_id, **IDENTITY,
        )
        assert historical["error"] is False
        assert historical["preview"] == payload
        assert historical["is_current"] is False
    finally:
        reset_current_tenant_user_id(token)


def test_bridge_evidence_can_be_read_by_exact_scoped_id(tmp_path, monkeypatch):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", MASTER_KEY)
    token = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path)
        assert _create_case(repository)["error"] is False
        first = repository.append_transition_bridge_evidence(
            case_id="case_000001", evidence=_evidence(),
            expected_case_revision=1, idempotency_key="append-exact-read-01",
        )
        second = repository.append_transition_bridge_evidence(
            case_id="case_000001", evidence=_evidence(),
            expected_case_revision=2, idempotency_key="append-exact-read-02",
        )
        assert first["error"] is False and second["error"] is False
        exact = repository.read_transition_bridge_evidence(
            case_id="case_000001", **IDENTITY,
            evidence_kind=TransitionBridgeEvidenceKind.FINANCE_IDENTITY_SNAPSHOT,
            evidence_id=first["evidence_id"], limit=1,
        )
        assert exact["error"] is False
        assert len(exact["items"]) == 1
        assert exact["items"][0]["evidence_id"] == first["evidence_id"]
        missing = repository.read_transition_bridge_evidence(
            case_id="case_000001", **IDENTITY,
            evidence_kind=TransitionBridgeEvidenceKind.FINANCE_IDENTITY_SNAPSHOT,
            evidence_id="bridge_" + "f" * 40, limit=1,
        )
        assert missing["error"] is False and missing["items"] == []
        invalid = repository.read_transition_bridge_evidence(
            case_id="case_000001", **IDENTITY, evidence_id="plaintext-id",
        )
        assert invalid["code"] == "FIFO_TRANSITION_EVIDENCE_INVALID"
    finally:
        reset_current_tenant_user_id(token)


def test_read_preview_returns_corruption_for_tampered_seal(tmp_path):
    token = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path)
        assert _create_case(repository)["error"] is False
        connection = repository.get_connection()
        payload = {
            "case_id": "case_000001", "case_revision": 1,
            "base_fifo_revision": 1, "base_allocation_revision": 1,
            "evidence_set_fingerprint": "d" * 64,
            "tax_policy_fingerprint": "e" * 64,
        }
        fingerprint = repository._sha256(payload)
        preview_id = "transpreview_" + fingerprint[:40]
        connection.execute(
            "DROP TRIGGER IF EXISTS trg_fifo_cost_transition_previews_no_update"
        )
        connection.execute(
            """INSERT INTO fifo_cost_transition_previews (
                preview_id, case_id, case_revision, fifo_revision, allocation_revision,
                evidence_set_fingerprint, tax_policy_fingerprint, preview_fingerprint,
                created_at, expires_at, payload_json
            ) VALUES (?, 'case_000001', 1, 1, 1, ?, ?, ?, ?, ?, ?)""",
            (preview_id, "d" * 64, "e" * 64, fingerprint,
             "2026-11-08T11:00:00.000000Z", "2026-11-08T11:10:00.000000Z",
             repository._canonical_json(payload)),
        )
        connection.execute(
            "UPDATE fifo_cost_transition_previews SET payload_json='{}' WHERE preview_id=?",
            (preview_id,),
        )
        connection.commit()
        connection.close()
        assert repository.read_transition_preview(
            case_id="case_000001", preview_id=preview_id, **IDENTITY,
        )["code"] == "FIFO_TRANSITION_PREVIEW_CORRUPT"
    finally:
        reset_current_tenant_user_id(token)
