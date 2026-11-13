from __future__ import annotations

from datetime import datetime, timezone

from cryptography.fernet import Fernet

from services.fifo_cost_physical_sales_evidence_service import (
    FifoCostPhysicalSalesEvidenceService,
)
from services.fifo_cost_physical_sales_import_service import (
    FifoCostPhysicalSalesImportService,
)
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_contracts import (
    CostInputMode,
    EvidenceCompleteness,
    EvidenceSourceKind,
    ScopeIdentity,
    TransitionCase,
    TransitionMetadata,
    TransitionReasonCode,
    TransitionState,
    UnknownValue,
)
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


OWNER = "owner-fr14"
STORE = "store-fr14"
TENANT = make_store_tenant_scope(OWNER, STORE)
SCOPE = ScopeIdentity(
    owner_id=OWNER, store_id=STORE, product_id="product-3921245627",
    offer_id="hook-2", sku="3921245627",
)
MASTER_KEY = Fernet.generate_key().decode("ascii")
HEADER = FifoCostPhysicalSalesImportService.TEMPLATE_HEADER
RAW_CSV = (
    "\ufeff" + HEADER + "\r\n"
    "posting-111;3921245627;2;2026-11-05;source-row-1\r\n"
    "posting-222;3921245627;3;2026-11-06;source-row-2\r\n"
).encode("utf-8")
PERIOD = {"period_from": "2026-11-01", "period_to": "2026-11-07"}
TIMEZONE = "Europe/Moscow"


def _repository(path):
    return FifoCostRepository(
        db_path=path,
        now_provider=lambda: datetime(2026, 11, 9, 12, tzinfo=timezone.utc),
    )


def _case():
    metadata = TransitionMetadata(
        scope=SCOPE,
        source_kind=EvidenceSourceKind.OWNER_INPUT,
        completeness=EvidenceCompleteness.PARTIAL,
        source_fingerprint="a" * 64,
        store_timezone=TIMEZONE,
    )
    return TransitionCase(
        metadata=metadata, case_id="case_fr14_0001", case_revision=1,
        state=TransitionState.DRAFT,
        created_at="2026-11-09T10:00:00Z", updated_at="2026-11-09T10:00:00Z",
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


def _create_case(repository):
    return repository.save_transition_case(
        case=_case(), expected_revision=0,
        idempotency_key="create-fr14-case-001",
    )


def _parse():
    result = FifoCostPhysicalSalesImportService().parse_csv(
        filename="physical-sales.csv", payload=RAW_CSV, scope=SCOPE,
    )
    assert result.document is not None, result.issue_codes
    return result.document


def _confirm(service, repository, saved, preview, *, revision=2, **overrides):
    values = {
        "repository": repository,
        "case_id": "case_fr14_0001",
        "scope": SCOPE,
        "evidence_id": saved["evidence_id"],
        "expected_evidence_fingerprint": saved["payload_fingerprint"],
        "expected_case_revision": revision,
        "expected_document_fingerprint": preview["document_fingerprint"],
        "expected_rows_fingerprint": preview["rows_fingerprint"],
        "expected_identity_fingerprint": preview["identity_fingerprint"],
        "expected_row_count": preview["row_count"],
        **PERIOD,
        "timezone_name": TIMEZONE,
        "semantics": "PHYSICAL_OUTFLOW",
        "idempotency_key": "confirm-fr14-physical-001",
    }
    values.update(overrides)
    return service.confirm_document(**values)


def test_physical_csv_is_encrypted_restartable_and_confirmed_separately(tmp_path, monkeypatch):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", MASTER_KEY)
    tenant_token = set_current_tenant_user_id(TENANT)
    try:
        database = tmp_path / "physical-sales.sqlite"
        repository = _repository(database)
        assert _create_case(repository)["error"] is False
        service = FifoCostPhysicalSalesEvidenceService()
        document = _parse()
        preview = service.preview_document(
            document=document, **PERIOD, timezone_name=TIMEZONE,
        )
        assert preview["error"] is False
        assert preview["row_count"] == 2 and preview["unit_count"] == 5
        assert preview["completeness"] == "PARTIAL"
        assert preview["coverage_verified"] is False
        assert "posting-111" not in repr(preview)
        assert "source-row-1" not in repr(preview)

        saved = service.save_document(
            repository=repository, case_id="case_fr14_0001", scope=SCOPE,
            filename="physical-sales.csv", payload=RAW_CSV, document=document,
            **PERIOD, timezone_name=TIMEZONE,
            captured_at="2026-11-09T10:30:00Z",
            expected_case_revision=1, idempotency_key="save-fr14-physical-001",
        )
        assert saved["error"] is False, saved
        assert saved["case_revision"] == 2
        assert saved["state"] == "AWAITING_EVIDENCE"
        assert saved["preview"]["confirmed"] is False
        replay = service.save_document(
            repository=repository, case_id="case_fr14_0001", scope=SCOPE,
            filename="physical-sales.csv", payload=RAW_CSV, document=document,
            **PERIOD, timezone_name=TIMEZONE,
            captured_at="2026-11-09T10:30:00Z",
            expected_case_revision=1, idempotency_key="save-fr14-physical-001",
        )
        assert replay["error"] is False and replay["replayed"] is True
        assert replay["evidence_id"] == saved["evidence_id"]

        connection = repository.get_connection()
        try:
            row = connection.execute(
                "SELECT payload_json, encrypted_payload FROM fifo_cost_transition_bridge_evidence WHERE evidence_id=?",
                (saved["evidence_id"],),
            ).fetchone()
            assert row is not None
            assert "posting-111" not in row["payload_json"]
            assert b"posting-111" not in row["encrypted_payload"]
            assert len(row["encrypted_payload"]) <= 16 * 1024 * 1024
        finally:
            connection.close()

        restarted = _repository(database)
        loaded = service.read_document(
            repository=restarted, case_id="case_fr14_0001", scope=SCOPE,
            evidence_id=saved["evidence_id"],
        )
        assert loaded["error"] is False, loaded
        assert loaded["document"] == document
        assert loaded["confirmed"] is False
        assert loaded["case_revision"] == 2

        stale = _confirm(
            service, restarted, saved, saved["preview"],
            expected_rows_fingerprint="f" * 64,
        )
        assert stale["code"] == "FIFO_TRANSITION_PREVIEW_STALE"
        assert restarted.read_transition_case(
            case_id="case_fr14_0001", store_id=STORE,
            product_id=SCOPE.product_id, offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )["case_revision"] == 2

        # A new upload/preview after restart has a new capture timestamp and
        # idempotency attempt, but identical immutable CSV coverage. Reuse the
        # saved evidence instead of conflicting on captured_at.
        reuploaded = service.save_document(
            repository=restarted, case_id="case_fr14_0001", scope=SCOPE,
            filename="physical-sales.csv", payload=RAW_CSV, document=document,
            **PERIOD, timezone_name=TIMEZONE,
            captured_at="2026-11-09T10:46:00Z",
            expected_case_revision=2,
            idempotency_key="save-fr14-physical-new-preview",
        )
        assert reuploaded["error"] is False, reuploaded
        assert reuploaded["replayed"] is True
        assert reuploaded["evidence_id"] == saved["evidence_id"]
        assert reuploaded["payload_fingerprint"] == saved["payload_fingerprint"]
        assert reuploaded["case_revision"] == 2
        all_physical = restarted.read_transition_bridge_evidence(
            case_id="case_fr14_0001", store_id=STORE,
            product_id=SCOPE.product_id, offer_id=SCOPE.offer_id, sku=SCOPE.sku,
            evidence_kind="PHYSICAL_SALES_DOCUMENT", limit=10,
        )
        assert all_physical["error"] is False
        assert len(all_physical["items"]) == 1

        confirmed = _confirm(service, restarted, saved, saved["preview"])
        assert confirmed["error"] is False, confirmed
        assert confirmed["confirmed"] is True
        assert confirmed["row_count"] == 2 and confirmed["unit_count"] == 5
        after_restart = _repository(database)
        restored = service.read_document(
            repository=after_restart, case_id="case_fr14_0001", scope=SCOPE,
            evidence_id=saved["evidence_id"],
        )
        assert restored["error"] is False, restored
        assert restored["confirmed"] is True
        assert restored["preview"]["confirmed"] is True
        assert restored["confirmed_fields"] == {
            "document_fingerprint": document.document_fingerprint,
            "row_count": 2,
            "rows_fingerprint": document.row_references_fingerprint,
            "period_from": PERIOD["period_from"],
            "period_to": PERIOD["period_to"],
            "timezone": TIMEZONE,
            "semantics": "PHYSICAL_OUTFLOW",
        }
        assert "posting-111" not in repr(restored)
        assert "source-row-1" not in repr(restored)
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_physical_document_wrong_key_retains_case_and_blocks_confirmation(tmp_path, monkeypatch):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", MASTER_KEY)
    tenant_token = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path / "wrong-key.sqlite")
        assert _create_case(repository)["error"] is False
        service = FifoCostPhysicalSalesEvidenceService()
        document = _parse()
        saved = service.save_document(
            repository=repository, case_id="case_fr14_0001", scope=SCOPE,
            filename="physical-sales.csv", payload=RAW_CSV, document=document,
            **PERIOD, timezone_name=TIMEZONE,
            captured_at="2026-11-09T10:30:00Z",
            expected_case_revision=1, idempotency_key="save-fr14-physical-002",
        )
        monkeypatch.setenv(
            "OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"),
        )
        blocked = service.read_document(
            repository=repository, case_id="case_fr14_0001", scope=SCOPE,
            evidence_id=saved["evidence_id"],
        )
        assert blocked["code"] == "FIFO_TRANSITION_ENCRYPTION_UNAVAILABLE"
        current = repository.read_transition_case(
            case_id="case_fr14_0001", store_id=STORE,
            product_id=SCOPE.product_id, offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        assert current["case_revision"] == 2
        assert current["state"] == "AWAITING_EVIDENCE"
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_physical_document_requires_case_timezone_and_dates_inside_confirmed_period(tmp_path, monkeypatch):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", MASTER_KEY)
    tenant_token = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path / "period.sqlite")
        assert _create_case(repository)["error"] is False
        service = FifoCostPhysicalSalesEvidenceService()
        document = _parse()
        wrong_timezone = service.save_document(
            repository=repository, case_id="case_fr14_0001", scope=SCOPE,
            filename="physical-sales.csv", payload=RAW_CSV, document=document,
            **PERIOD, timezone_name="Europe/London",
            captured_at="2026-11-09T10:30:00Z",
            expected_case_revision=1, idempotency_key="save-fr14-wrong-zone",
        )
        assert wrong_timezone["code"] == "FIFO_TRANSITION_TIMEZONE_MISMATCH"
        outside = service.save_document(
            repository=repository, case_id="case_fr14_0001", scope=SCOPE,
            filename="physical-sales.csv", payload=RAW_CSV, document=document,
            period_from="2026-11-06", period_to="2026-11-07",
            timezone_name=TIMEZONE,
            captured_at="2026-11-09T10:30:00Z",
            expected_case_revision=1, idempotency_key="save-fr14-outside-period",
        )
        assert outside["code"] == "FIFO_PHYSICAL_SALES_DATE_OUTSIDE_PERIOD"
        current = repository.read_transition_case(
            case_id="case_fr14_0001", store_id=STORE,
            product_id=SCOPE.product_id, offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        assert current["case_revision"] == 1
    finally:
        reset_current_tenant_user_id(tenant_token)
