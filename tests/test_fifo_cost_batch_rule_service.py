from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from cryptography.fernet import Fernet
import pytest

from services.fifo_cost_batch_rule_contracts import (
    BatchRuleInput,
    BatchStartDayPolicy,
)
from services.fifo_cost_batch_rule_service import FifoCostBatchRuleService
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_contracts import (
    CostInputMode,
    EvidenceCompleteness,
    EvidenceSourceKind,
    ScopeIdentity,
    SupplyTotalMode,
    TransitionCase,
    TransitionMetadata,
    TransitionReasonCode,
    TransitionState,
    TransitionContractError,
    UnknownValue,
)
from services.fifo_cost_transition_store import FifoCostTransitionStore
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.fifo_cost_batch_supply_store import FifoCostBatchSupplyStore
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


SCOPE = ScopeIdentity(
    owner_id="owner-a", store_id="store-a", product_id="product-101",
    offer_id="hook-2", sku="3921245627",
)
TENANT_SCOPE = make_store_tenant_scope("owner-a", "store-a")
NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


def _case(*, revision=1, updated_at="2026-11-13T10:00:00Z", cost="14.65"):
    unknown = {
        "new_home_quantity": UnknownValue(
            reason_code=TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
            source_kind=EvidenceSourceKind.OWNER_INPUT,
        ),
        "declared_shipped_units": UnknownValue(
            reason_code=TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
            source_kind=EvidenceSourceKind.OWNER_INPUT,
        ),
    }
    return TransitionCase(
        metadata=TransitionMetadata(
            scope=SCOPE,
            source_kind=EvidenceSourceKind.OWNER_INPUT,
            completeness=EvidenceCompleteness.PARTIAL,
            source_fingerprint="a" * 64,
            store_timezone="Europe/Moscow",
        ),
        case_id="case_batch_001",
        case_revision=revision,
        state=TransitionState.AWAITING_EVIDENCE,
        created_at="2026-11-13T10:00:00Z",
        updated_at=updated_at,
        dispatch_date="2026-11-05",
        old_unit_cost_rub="21.00",
        new_unit_cost_rub=cost,
        cost_input_mode=CostInputMode.TOTAL_LANDED,
        cost_components=None,
        owner_old_home_units=0,
        owner_old_transit_units=0,
        new_home_quantity=None,
        declared_shipped_units=None,
        supply_total_mode=SupplyTotalMode.LEGACY_OWNER_TOTAL,
        unknown_values=unknown,
    )


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"),
    )
    repository = FifoCostRepository(
        db_path=tmp_path / "batch-rule.sqlite",
        now_provider=lambda: NOW,
    )
    tenant_token = set_current_tenant_user_id(TENANT_SCOPE)
    created = repository.save_transition_case(
        case=_case(), expected_revision=0, idempotency_key="create-case-001",
    )
    assert created["error"] is False, created
    service = FifoCostBatchRuleService(
        repository, now_provider=lambda: NOW,
    )
    return repository, service, tenant_token


def _preview(service, *, start="2026-11-05", policy=BatchStartDayPolicy.ALL_OWNER_CONFIRMED,
             digests=()):
    return service.preview_rule(
        SCOPE, "case_batch_001", 1,
        BatchRuleInput(
            start_local_date=start,
            start_day_policy=policy,
            boundary_supply_digests=digests,
        ),
    )


def _count(repository, table):
    connection = repository.get_connection()
    try:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        connection.close()


def test_preview_is_read_only_and_confirm_only_switches_case_mode(tmp_path, monkeypatch):
    repository, service, token = _setup(tmp_path, monkeypatch)
    try:
        preview_result = _preview(service)
        assert preview_result["error"] is False, preview_result
        preview = preview_result["preview"]
        assert _count(repository, "fifo_cost_batch_rule_revisions") == 0
        assert _count(repository, "fifo_cost_transition_case_revisions") == 1
        assert _count(repository, "fifo_cost_events") == 0
        assert _count(repository, "fifo_cost_layers") == 0
        assert _count(repository, "fifo_cost_allocations") == 0
        assert _count(repository, "fifo_cost_streams") == 0

        confirmed = service.confirm_rule(
            SCOPE, "case_batch_001", 1, preview.preview_id,
            preview.preview_fingerprint, "confirm-rule-001",
        )
        assert confirmed == {
            "error": False,
            "code": "FIFO_BATCH_RULE_CONFIRMED",
            "case_id": "case_batch_001",
            "case_revision": 2,
            "rule_id": preview.rule_id,
            "rule_revision": 1,
            "replayed": False,
        }
        case_result = repository.read_transition_case(
            case_id="case_batch_001", store_id=SCOPE.store_id,
            product_id=SCOPE.product_id, offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        assert case_result["case"]["supply_total_mode"] == "AUTO_FROM_SUPPLIES"
        assert case_result["case"]["declared_shipped_units"] is None
        assert _count(repository, "fifo_cost_batch_rule_revisions") == 1
        assert _count(repository, "fifo_cost_events") == 0
        assert _count(repository, "fifo_cost_layers") == 0
        assert _count(repository, "fifo_cost_allocations") == 0
        assert _count(repository, "fifo_cost_streams") == 0
    finally:
        reset_current_tenant_user_id(token)


def test_explicit_first_day_supply_set_must_be_nonempty():
    with pytest.raises(TransitionContractError):
        BatchRuleInput(
            "2026-11-05", BatchStartDayPolicy.EXPLICIT_SUPPLY_SET, (),
        )


@pytest.mark.parametrize("field,value", [
    ("owner_old_home_units", 1),
    ("owner_old_transit_units", 1),
])
def test_preview_rejects_nonzero_old_stock(tmp_path, monkeypatch, field, value):
    repository, service, token = _setup(tmp_path, monkeypatch)
    try:
        original = _case()
        changed = replace(original, case_revision=2, updated_at="2026-11-13T11:00:00Z",
                          **{field: value})
        repository.save_transition_case(
            case=changed, expected_revision=1, idempotency_key="change-case-001",
        )
        result = service.preview_rule(
            SCOPE, "case_batch_001", 2,
            BatchRuleInput("2026-11-05", BatchStartDayPolicy.ALL_OWNER_CONFIRMED),
        )
        assert result["error"] is True
        assert result["code"] == (
            "FIFO_BATCH_OLD_HOME_NOT_CONFIRMED_ZERO"
            if field == "owner_old_home_units"
            else "FIFO_BATCH_OLD_TRANSIT_NOT_CONFIRMED_ZERO"
        )
        assert _count(repository, "fifo_cost_batch_rule_revisions") == 0
    finally:
        reset_current_tenant_user_id(token)


def test_unknown_old_stock_and_first_day_mismatch_fail_closed(tmp_path, monkeypatch):
    repository, service, token = _setup(tmp_path, monkeypatch)
    try:
        case = _case()
        unknown_home = UnknownValue(
            reason_code=TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
            source_kind=EvidenceSourceKind.OWNER_INPUT,
        )
        changed = replace(
            case, case_revision=2, updated_at="2026-11-13T11:00:00Z",
            owner_old_home_units=None,
            unknown_values={**case.unknown_values, "owner_old_home_units": unknown_home},
        )
        repository.save_transition_case(
            case=changed, expected_revision=1, idempotency_key="unknown-old-001",
        )
        blocked = service.preview_rule(
            SCOPE, "case_batch_001", 2,
            BatchRuleInput("2026-11-05", BatchStartDayPolicy.ALL_OWNER_CONFIRMED),
        )
        assert blocked["code"] == "FIFO_BATCH_OLD_HOME_NOT_CONFIRMED_ZERO"

        restored = replace(
            changed, case_revision=3, updated_at="2026-11-13T11:30:00Z",
            owner_old_home_units=0,
            unknown_values={
                "new_home_quantity": case.unknown_values["new_home_quantity"],
                "declared_shipped_units": case.unknown_values["declared_shipped_units"],
            },
        )
        repository.save_transition_case(
            case=restored, expected_revision=2, idempotency_key="restore-old-001",
        )
        mismatch = service.preview_rule(
            SCOPE, "case_batch_001", 3,
            BatchRuleInput("2026-11-06", BatchStartDayPolicy.ALL_OWNER_CONFIRMED),
        )
        assert mismatch["code"] == "FIFO_BATCH_FIRST_BOUNDARY_MUST_MATCH_DISPATCH_DATE"
    finally:
        reset_current_tenant_user_id(token)


def test_same_idempotency_replays_but_changed_payload_conflicts(tmp_path, monkeypatch):
    repository, service, token = _setup(tmp_path, monkeypatch)
    try:
        result = _preview(service)
        preview = result["preview"]
        first = service.confirm_rule(
            SCOPE, "case_batch_001", 1, preview.preview_id,
            preview.preview_fingerprint, "confirm-rule-002",
        )
        restarted_service = FifoCostBatchRuleService(
            repository, now_provider=lambda: NOW,
        )
        replay = restarted_service.confirm_rule(
            SCOPE, "case_batch_001", 1, preview.preview_id,
            preview.preview_fingerprint, "confirm-rule-002",
        )
        assert first["error"] is False
        assert replay["error"] is False
        assert replay["replayed"] is True
        conflict = service.confirm_rule(
            SCOPE, "case_batch_001", 1, preview.preview_id,
            "0" * 64, "confirm-rule-002",
        )
        assert conflict["code"] == "FIFO_BATCH_IDEMPOTENCY_CONFLICT"
        assert _count(repository, "fifo_cost_batch_rule_revisions") == 1
    finally:
        reset_current_tenant_user_id(token)


def test_confirm_rolls_back_rule_when_case_revision_save_fails(
    tmp_path, monkeypatch,
):
    repository, service, token = _setup(tmp_path, monkeypatch)
    try:
        preview = _preview(service)["preview"]
        original = FifoCostTransitionStore.save_case

        def fail_case_save(*args, **kwargs):
            return {"error": True, "code": "INJECTED_CASE_WRITE_FAILURE"}

        monkeypatch.setattr(FifoCostTransitionStore, "save_case", fail_case_save)
        failed = service.confirm_rule(
            SCOPE, "case_batch_001", 1, preview.preview_id,
            preview.preview_fingerprint, "confirm-rule-003",
        )
        assert failed["code"] == "INJECTED_CASE_WRITE_FAILURE"
        assert _count(repository, "fifo_cost_batch_rule_revisions") == 0
        assert _count(repository, "fifo_cost_transition_case_revisions") == 1
        assert _count(repository, "fifo_cost_events") == 0
        assert _count(repository, "fifo_cost_layers") == 0
        monkeypatch.setattr(FifoCostTransitionStore, "save_case", original)
    finally:
        reset_current_tenant_user_id(token)


def test_stale_cost_preview_cannot_confirm_after_case_change(tmp_path, monkeypatch):
    repository, service, token = _setup(tmp_path, monkeypatch)
    try:
        preview = _preview(service)["preview"]
        changed = replace(
            _case(), case_revision=2, updated_at="2026-11-13T11:00:00Z",
            new_unit_cost_rub=Decimal("13.90"),
        )
        saved = repository.save_transition_case(
            case=changed, expected_revision=1, idempotency_key="change-cost-001",
        )
        assert saved["error"] is False
        result = service.confirm_rule(
            SCOPE, "case_batch_001", 1, preview.preview_id,
            preview.preview_fingerprint, "stale-preview-001",
        )
        assert result["code"] == "FIFO_BATCH_CASE_REVISION_CONFLICT"
        assert _count(repository, "fifo_cost_batch_rule_revisions") == 0
        assert _count(repository, "fifo_cost_transition_case_revisions") == 2
    finally:
        reset_current_tenant_user_id(token)


def test_preview_callback_is_bound_to_exact_store_product_offer_and_sku(
    tmp_path, monkeypatch,
):
    repository, service, token = _setup(tmp_path, monkeypatch)
    try:
        preview = _preview(service)["preview"]
        wrong_scope = ScopeIdentity(
            owner_id=SCOPE.owner_id,
            store_id=SCOPE.store_id,
            product_id=SCOPE.product_id,
            offer_id="different-offer",
            sku=SCOPE.sku,
        )
        result = service.confirm_rule(
            wrong_scope, "case_batch_001", 1, preview.preview_id,
            preview.preview_fingerprint, "wrong-scope-001",
        )
        assert result["code"] == "FIFO_BATCH_PREVIEW_MISMATCH"
        assert _count(repository, "fifo_cost_batch_rule_revisions") == 0
        assert _count(repository, "fifo_cost_transition_case_revisions") == 1
    finally:
        reset_current_tenant_user_id(token)


def test_successor_atomically_closes_previous_rule_and_same_day_is_rejected(
    tmp_path, monkeypatch,
):
    repository, service, token = _setup(tmp_path, monkeypatch)
    try:
        first_preview = _preview(service)["preview"]
        first = service.confirm_rule(
            SCOPE, "case_batch_001", 1, first_preview.preview_id,
            first_preview.preview_fingerprint, "first-rule-001",
        )
        assert first["error"] is False
        current = repository.read_transition_case(
            case_id="case_batch_001", store_id=SCOPE.store_id,
            product_id=SCOPE.product_id, offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        case = FifoCostTransitionService._case_from_payload(current["case"])
        next_case = replace(
            case, case_revision=3, updated_at="2026-11-13T13:00:00Z",
            new_unit_cost_rub=Decimal("13.50"),
        )
        changed = repository.save_transition_case(
            case=next_case, expected_revision=2, idempotency_key="next-cost-001",
        )
        assert changed["error"] is False

        same_day = service.preview_rule(
            SCOPE, "case_batch_001", 3,
            BatchRuleInput("2026-11-05", BatchStartDayPolicy.ALL_OWNER_CONFIRMED),
        )
        assert same_day["code"] == "FIFO_BATCH_SAME_DAY_BOUNDARY_NEEDS_REVIEW"

        successor_preview = service.preview_rule(
            SCOPE, "case_batch_001", 3,
            BatchRuleInput("2026-11-20", BatchStartDayPolicy.ALL_OWNER_CONFIRMED),
        )["preview"]
        successor = service.confirm_rule(
            SCOPE, "case_batch_001", 3, successor_preview.preview_id,
            successor_preview.preview_fingerprint, "successor-rule-001",
        )
        assert successor["error"] is False, successor
        assert successor["rule_revision"] == 3
        connection = repository.get_connection()
        try:
            rows = FifoCostBatchSupplyStore.read_rule_revisions(
                connection, scope=SCOPE, case_id="case_batch_001",
                tenant_fingerprint=repository._tenant_scope(SCOPE.store_id)[
                    "tenant_fingerprint"
                ],
            )
        finally:
            connection.close()
        ordered = sorted(rows, key=lambda row: row["rule_revision"])
        assert [(row["event_kind"], row["rule_revision"]) for row in ordered] == [
            ("CONFIRM", 1), ("CLOSE", 2), ("REPLACE", 3),
        ]
        assert ordered[1]["end_local_date_exclusive"] == "2026-11-20"
        assert ordered[2]["predecessor_rule_revision"] == 2
        assert _count(repository, "fifo_cost_events") == 0
        assert _count(repository, "fifo_cost_layers") == 0
    finally:
        reset_current_tenant_user_id(token)


def test_successor_timezone_change_fails_closed_for_manual_review(tmp_path, monkeypatch):
    repository, service, token = _setup(tmp_path, monkeypatch)
    try:
        first = _preview(service)["preview"]
        confirmed = service.confirm_rule(
            SCOPE, "case_batch_001", 1, first.preview_id,
            first.preview_fingerprint, "timezone-rule-001",
        )
        assert confirmed["error"] is False
        current = repository.read_transition_case(
            case_id="case_batch_001", store_id=SCOPE.store_id,
            product_id=SCOPE.product_id, offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        case = FifoCostTransitionService._case_from_payload(current["case"])
        changed = replace(
            case,
            case_revision=3,
            updated_at="2026-11-13T13:00:00Z",
            metadata=replace(case.metadata, store_timezone="Asia/Yekaterinburg"),
            new_unit_cost_rub=Decimal("13.50"),
        )
        saved = repository.save_transition_case(
            case=changed, expected_revision=2, idempotency_key="change-zone-001",
        )
        assert saved["error"] is False
        result = service.preview_rule(
            SCOPE, "case_batch_001", 3,
            BatchRuleInput("2026-11-20", BatchStartDayPolicy.ALL_OWNER_CONFIRMED),
        )
        assert result["code"] == "FIFO_BATCH_TIMEZONE_CHANGE_NEEDS_REVIEW"
        assert _count(repository, "fifo_cost_batch_rule_revisions") == 1
    finally:
        reset_current_tenant_user_id(token)
