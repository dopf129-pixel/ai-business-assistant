from datetime import datetime, timezone

from cryptography.fernet import Fernet

from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_source_normalizer import FifoCostSourceNormalizer
from services.fifo_cost_transition_contracts import (
    AcceptedQuantityKind,
    CostInputMode,
    EvidenceCompleteness,
    EvidencePresence,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    ScopeIdentity,
    SupplyObservation,
    TransitionCase,
    TransitionMetadata,
    TransitionReasonCode,
    TransitionState,
    UnknownValue,
    SupplyReferenceKind,
    supply_reference_digest,
)
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


IDENTITY = {
    "store_id": "store-a",
    "product_id": "product-101",
    "offer_id": "hook-2",
    "sku": "3921245627",
}
OWNER_SCOPE = make_store_tenant_scope("owner-a", "store-a")


def _supply_reference_digest(reference_id):
    return supply_reference_digest(
        owner_id="owner-a", store_id="store-a",
        reference_kind=SupplyReferenceKind.SUPPLY, reference_id=reference_id,
    )


def _case():
    metadata = TransitionMetadata(
        scope=ScopeIdentity(
            owner_id="owner-a", store_id=IDENTITY["store_id"],
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
            sku=IDENTITY["sku"],
        ),
        source_kind=EvidenceSourceKind.OWNER_INPUT,
        completeness=EvidenceCompleteness.PARTIAL,
        source_fingerprint="a" * 64,
    )
    return TransitionCase(
        metadata=metadata,
        case_id="case_fl09_0001",
        case_revision=1,
        state=TransitionState.DRAFT,
        created_at="2026-11-08T10:00:00Z",
        updated_at="2026-11-08T10:00:00Z",
        dispatch_date="2026-11-05",
        old_unit_cost_rub="21.00",
        new_unit_cost_rub="14.65",
        cost_input_mode=CostInputMode.TOTAL_LANDED,
        cost_components=None,
        owner_old_home_units=0,
        owner_old_transit_units=0,
        new_home_quantity=None,
        declared_shipped_units=148,
        unknown_values={
            "new_home_quantity": UnknownValue(
                TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
                EvidenceSourceKind.OWNER_INPUT,
            ),
        },
    )


def _partial_receipt(case, declaration_id):
    metadata = TransitionMetadata(
        scope=case.metadata.scope,
        source_kind=EvidenceSourceKind.OZON_API,
        completeness=EvidenceCompleteness.COMPLETE,
        source_fingerprint="b" * 64,
    )
    return SupplyObservation(
        metadata=metadata,
        declaration_id=declaration_id,
        captured_at="2026-11-08T10:30:00Z",
        source_as_of=None,
        raw_status="ACCEPTANCE_AT_STORAGE_WAREHOUSE",
        normalized_status=NormalizedSupplyStatus.PARTIALLY_ACCEPTED,
        declared_quantity=148,
        accepted_quantity=40,
        accepted_quantity_kind=AcceptedQuantityKind.CUMULATIVE,
        act_reference_digest=None,
        act_version_digest=None,
        scope_complete=True,
        pagination_complete=True,
        presence=EvidencePresence.PRESENT,
    )


def test_missing_refresh_appends_without_erasing_declaration_or_partial_receipt(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv(
        "OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"),
    )
    tenant = set_current_tenant_user_id(OWNER_SCOPE)
    try:
        repository = FifoCostRepository(
            db_path=tmp_path / "fifo-transition-observation.sqlite",
            now_provider=lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc),
        )
        service = FifoCostTransitionService(
            repository,
            now_provider=lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc),
        )
        created = service.create_case(
            case=_case(), idempotency_key="fl09-create-case-001",
        )
        assert created["error"] is False
        declared = service.declare_supply(
            case_id="case_fl09_0001", **IDENTITY,
            reference_kind="SUPPLY", reference_id="2001",
            declared_shipped_units=148, dispatch_date="2026-11-05",
            expected_case_revision=1, idempotency_key="fl09-declare-148",
        )
        assert declared["error"] is False, declared
        assert declared["case_revision"] == 2
        manifest_before = service.get_supply_manifest(
            case_id="case_fl09_0001", **IDENTITY,
        )
        declaration_id = manifest_before["declarations"][0]["declaration_id"]

        partial = _partial_receipt(_case(), declaration_id)
        partial_result = repository.append_supply_observation(
            case_id="case_fl09_0001", observation=partial,
            expected_case_revision=2, idempotency_key="fl09-partial-40",
        )
        assert partial_result["error"] is False, partial_result
        assert partial_result["case_revision"] == 3

        missing_snapshot = FifoCostSourceNormalizer().normalize_active_supply_snapshot(
            supply_reference_digest=_supply_reference_digest("2001"),
            store_id=IDENTITY["store_id"],
            captured_at=datetime(2026, 11, 8, 11, tzinfo=timezone.utc),
            source_fingerprint="c" * 64, presence="MISSING", raw_status=None,
            order_id=None, scope_complete=True, pagination_complete=True,
            source_status="COMPLETE",
        )
        assert missing_snapshot.status == "MISSING"
        wrong_reference = service.record_supply_observation(
            case_id="case_fl09_0001", **IDENTITY,
            declaration_id=declaration_id,
            reference_id="2002", snapshot=missing_snapshot,
            expected_case_revision=3, idempotency_key="fl09-missing-wrong-id",
        )
        assert wrong_reference["error"] is True
        assert wrong_reference["code"] == "FIFO_TRANSITION_SUPPLY_REFERENCE_MISMATCH"

        missing = service.record_supply_observation(
            case_id="case_fl09_0001", **IDENTITY,
            declaration_id=declaration_id,
            reference_id="2001", snapshot=missing_snapshot,
            expected_case_revision=3, idempotency_key="fl09-missing-lookup",
        )
        assert missing["error"] is False, missing
        assert missing["case_revision"] == 4

        evidence = repository.read_transition_evidence(
            case_id="case_fl09_0001", **IDENTITY,
            kind="SUPPLY_OBSERVATION", limit=100,
        )
        observations = evidence["items"]
        assert len(observations) == 2
        assert observations[0]["accepted_quantity"] == 40
        assert observations[0]["declared_quantity"] == 148
        assert observations[1]["presence"] == "MISSING"
        assert observations[1]["accepted_quantity"] is None
        assert observations[1]["declared_quantity"] is None
        assert observations[1]["payload"]["normalized_status"] == "UNKNOWN"
        assert "2001" not in repr(observations)

        manifest = service.get_supply_manifest(
            case_id="case_fl09_0001", **IDENTITY,
        )
        assert manifest["known_assigned_units"] == 148
        assert manifest["declarations"][0]["declared_shipped_units"] == 148
        assert repository.read_cost_history_snapshot(
            **IDENTITY,
        )["code"] == "FIFO_HISTORY_NOT_INITIALIZED"
    finally:
        reset_current_tenant_user_id(tenant)
