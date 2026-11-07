from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from threading import Barrier

from services.fifo_cost_history_service import FifoCostHistoryService
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


def _case(*, case_id="case_000001", sku=None, revision=1, updated_at=None):
    scope = ScopeIdentity(
        owner_id="owner-a",
        store_id=IDENTITY["store_id"],
        product_id=IDENTITY["product_id"],
        offer_id=IDENTITY["offer_id"],
        sku=sku or IDENTITY["sku"],
    )
    metadata = TransitionMetadata(
        scope=scope,
        source_kind=EvidenceSourceKind.OWNER_INPUT,
        completeness=EvidenceCompleteness.PARTIAL,
        source_fingerprint=("a" if revision == 1 else "b") * 64,
    )
    unknown = {
        "new_home_quantity": UnknownValue(
            reason_code=TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
            source_kind=EvidenceSourceKind.OWNER_INPUT,
        ),
    }
    return TransitionCase(
        metadata=metadata,
        case_id=case_id,
        case_revision=revision,
        state=TransitionState.DRAFT,
        created_at="2026-11-08T10:00:00Z",
        updated_at=updated_at or "2026-11-08T10:00:00Z",
        dispatch_date="2026-11-05",
        old_unit_cost_rub="21.00",
        new_unit_cost_rub="14.65",
        cost_input_mode=CostInputMode.TOTAL_LANDED,
        cost_components=None,
        owner_old_home_units=0,
        owner_old_transit_units=0,
        new_home_quantity=None,
        declared_shipped_units=6982,
        unknown_values=unknown,
    )


def _service(tmp_path):
    repository = FifoCostRepository(
        db_path=tmp_path / "fifo-transition-service.sqlite",
        now_provider=lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc),
    )
    return repository, FifoCostTransitionService(
        repository,
        now_provider=lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc),
    )


def test_case_lifecycle_is_durable_and_does_not_activate_fifo(tmp_path):
    tenant = set_current_tenant_user_id(OWNER_SCOPE)
    try:
        repository, service = _service(tmp_path)
        created = service.create_case(
            case=_case(), idempotency_key="create-transition-001",
        )
        assert created["error"] is False, created
        assert created["case_revision"] == 1
        assert created["state"] == "DRAFT"

        listed = service.list_cases(store_id=IDENTITY["store_id"])
        assert listed["count"] == 1
        assert listed["cases"][0]["case_id"] == "case_000001"
        assert listed["cases"][0]["case"]["dispatch_date"] == "2026-11-05"
        assert listed["cases"][0]["case"]["new_home_quantity"] is None
        assert listed["cases"][0]["case"]["unknown_values"]["new_home_quantity"] == {
            "reason_code": "SOURCE_PROOF_UNAVAILABLE",
            "source_kind": "OWNER_INPUT",
        }

        changed = replace(
            _case(revision=2, updated_at="2026-11-08T11:00:00Z"),
            state=TransitionState.AWAITING_EVIDENCE,
            new_home_quantity=17,
            unknown_values={},
        )
        updated = service.update_case(
            case=changed, expected_revision=1,
            idempotency_key="update-transition-001",
        )
        assert updated["error"] is False, updated
        assert updated["case_revision"] == 2
        assert updated["state"] == "AWAITING_EVIDENCE"
        repeated_update = service.update_case(
            case=changed, expected_revision=1,
            idempotency_key="update-transition-001",
        )
        assert repeated_update["error"] is False
        assert repeated_update["replayed"] is True

        restarted = FifoCostTransitionService(
            FifoCostRepository(db_path=repository.db_path),
            now_provider=lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc),
        )
        durable = restarted.get_case(
            case_id="case_000001", **IDENTITY,
        )
        assert durable["error"] is False
        assert durable["case_revision"] == 2
        assert durable["case"]["new_home_quantity"] == 17

        cancelled = restarted.cancel_case(
            case_id="case_000001", **IDENTITY, expected_revision=2,
            idempotency_key="cancel-transition-001",
        )
        assert cancelled["error"] is False, cancelled
        assert cancelled["case_revision"] == 3
        assert cancelled["state"] == "CANCELLED"
        repeated_cancel = restarted.cancel_case(
            case_id="case_000001", **IDENTITY, expected_revision=2,
            idempotency_key="cancel-transition-001",
        )
        assert repeated_cancel["error"] is False
        assert repeated_cancel["replayed"] is True
        assert restarted.list_cases(store_id=IDENTITY["store_id"])["count"] == 0
        assert restarted.list_cases(
            store_id=IDENTITY["store_id"], states=("CANCELLED",),
        )["count"] == 1

        # Cancellation closes the active transition slot without deleting its audit.
        next_case = replace(
            _case(case_id="case_000002"), created_at="2026-11-08T12:00:00Z",
            updated_at="2026-11-08T12:00:00Z",
        )
        assert restarted.create_case(
            case=next_case, idempotency_key="create-transition-002",
        )["error"] is False
        assert FifoCostHistoryService(repository).get_sku_history(
            **IDENTITY,
        )["code"] == "FIFO_HISTORY_NOT_INITIALIZED"
        connection = repository.get_connection()
        try:
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_streams").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_transition_case_revisions"
            ).fetchone()[0] == 4
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant)


def test_only_one_active_case_per_store_sku_and_other_sku_is_independent(tmp_path):
    tenant = set_current_tenant_user_id(OWNER_SCOPE)
    try:
        _repository, service = _service(tmp_path)
        first = service.create_case(
            case=_case(), idempotency_key="first-transition-001",
        )
        assert first["error"] is False
        competing = service.create_case(
            case=_case(case_id="case_000002"),
            idempotency_key="second-transition-001",
        )
        assert competing == {
            "error": True,
            "code": "FIFO_TRANSITION_ACTIVE_CASE_CONFLICT",
        }
        other_sku = service.create_case(
            case=_case(case_id="case_000003", sku="3921245628"),
            idempotency_key="other-sku-transition01",
        )
        assert other_sku["error"] is False
        assert service.list_cases(
            store_id=IDENTITY["store_id"], sku=IDENTITY["sku"],
        )["count"] == 1
    finally:
        reset_current_tenant_user_id(tenant)


def test_concurrent_case_create_has_one_winner_per_sku(tmp_path):
    database = tmp_path / "fifo-transition-concurrent.sqlite"
    barrier = Barrier(2)
    warmup = FifoCostRepository(db_path=database).get_connection()
    warmup.close()

    def create(case_id, key):
        token = set_current_tenant_user_id(OWNER_SCOPE)
        try:
            repository = FifoCostRepository(db_path=database)
            service = FifoCostTransitionService(repository)
            barrier.wait(timeout=5)
            return service.create_case(
                case=_case(case_id=case_id), idempotency_key=key,
            )
        finally:
            reset_current_tenant_user_id(token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda values: create(*values),
            (
                ("case_000001", "concurrent-transition01"),
                ("case_000002", "concurrent-transition02"),
            ),
        ))
    assert sum(result["error"] is False for result in results) == 1
    assert sum(
        result.get("code") == "FIFO_TRANSITION_ACTIVE_CASE_CONFLICT"
        for result in results
    ) == 1


def test_case_list_is_tenant_store_and_sku_scoped(tmp_path):
    tenant = set_current_tenant_user_id(OWNER_SCOPE)
    try:
        _repository, service = _service(tmp_path)
        assert service.create_case(
            case=_case(), idempotency_key="scope-first-case01",
        )["error"] is False
        assert service.create_case(
            case=_case(case_id="case_000002", sku="3921245628"),
            idempotency_key="scope-second-case01",
        )["error"] is False
        assert service.list_cases(
            store_id=IDENTITY["store_id"], sku=IDENTITY["sku"],
        )["count"] == 1
        assert service.list_cases(store_id=IDENTITY["store_id"])["count"] == 2

        other_owner = set_current_tenant_user_id(
            make_store_tenant_scope("owner-b", "store-a"),
        )
        try:
            assert service.list_cases(store_id=IDENTITY["store_id"])["count"] == 0
        finally:
            reset_current_tenant_user_id(other_owner)

        other_store = set_current_tenant_user_id(
            make_store_tenant_scope("owner-a", "store-b"),
        )
        try:
            assert service.list_cases(store_id="store-a") == {
                "error": True, "code": "FIFO_STORE_SCOPE_MISMATCH",
            }
        finally:
            reset_current_tenant_user_id(other_store)
    finally:
        reset_current_tenant_user_id(tenant)
