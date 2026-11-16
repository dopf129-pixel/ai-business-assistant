from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
from threading import Event, Thread

from cryptography.fernet import Fernet
import pytest

from services.fifo_cost_batch_rule_contracts import (
    BatchRuleInput,
    BatchRuleEventKind,
    BatchStartDayPolicy,
    DispatchTimeStatus,
    ManifestFreshness,
    SupplyMembership,
    SupplyScanCoverage,
    SupplySkuObservation,
)
from services.fifo_cost_batch_rule_service import FifoCostBatchRuleService
from services.fifo_cost_batch_scan_checkpoint_service import (
    FifoCostBatchScanCheckpointService,
)
from services.fifo_cost_batch_manifest_read_service import (
    FifoCostBatchManifestReadService,
)
from services.fifo_cost_batch_supply_deduplicator import (
    FifoCostBatchSupplyDeduplicator,
)
from services.fifo_cost_batch_supply_store import FifoCostBatchSupplyStore
from services.fifo_cost_transition_contracts import (
    CostInputMode,
    EvidenceCompleteness,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    ScopeIdentity,
    SupplyTotalMode,
    TransitionCase,
    TransitionMetadata,
    TransitionReasonCode,
    TransitionState,
    UnknownValue,
)
from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_review_service import FifoCostTransitionReviewService
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


SCOPE = ScopeIdentity(
    owner_id="manifest-owner", store_id="store-a", product_id="product-a",
    offer_id="hook-2", sku="3921245627",
)
IDENTITY = {
    "store_id": SCOPE.store_id, "product_id": SCOPE.product_id,
    "offer_id": SCOPE.offer_id, "sku": SCOPE.sku,
}
NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
NOW_TEXT = "2026-11-15T12:00:00.000000Z"


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _case():
    unknown = {
        "new_home_quantity": UnknownValue(
            TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
            EvidenceSourceKind.OWNER_INPUT,
        ),
        "declared_shipped_units": UnknownValue(
            TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
            EvidenceSourceKind.OWNER_INPUT,
        ),
    }
    return TransitionCase(
        metadata=TransitionMetadata(
            scope=SCOPE, source_kind=EvidenceSourceKind.OWNER_INPUT,
            completeness=EvidenceCompleteness.PARTIAL,
            source_fingerprint=_digest("manifest-case"),
            store_timezone="Europe/Moscow",
        ),
        case_id="manifest-case-01", case_revision=1,
        state=TransitionState.AWAITING_EVIDENCE,
        created_at="2026-11-05T00:00:00Z", updated_at="2026-11-15T11:00:00Z",
        dispatch_date="2026-11-05", old_unit_cost_rub=Decimal("21.00"),
        new_unit_cost_rub=Decimal("14.65"), cost_input_mode=CostInputMode.TOTAL_LANDED,
        cost_components=None, owner_old_home_units=0, owner_old_transit_units=0,
        new_home_quantity=None, declared_shipped_units=None,
        supply_total_mode=SupplyTotalMode.LEGACY_OWNER_TOTAL,
        unknown_values=unknown,
    )


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    repository = FifoCostRepository(
        db_path=tmp_path / "manifest-read.sqlite", now_provider=lambda: NOW,
    )
    tenant_token = set_current_tenant_user_id(
        make_store_tenant_scope(SCOPE.owner_id, SCOPE.store_id),
    )
    created = repository.save_transition_case(
        case=_case(), expected_revision=0, idempotency_key="manifest-create-case",
    )
    assert created["error"] is False, created
    rules = FifoCostBatchRuleService(repository, now_provider=lambda: NOW)
    preview_result = rules.preview_rule(
        SCOPE, _case().case_id, 1,
        BatchRuleInput("2026-11-05", BatchStartDayPolicy.ALL_OWNER_CONFIRMED),
    )
    assert preview_result["error"] is False, preview_result
    preview = preview_result["preview"]
    confirmed = rules.confirm_rule(
        SCOPE, _case().case_id, 1, preview.preview_id,
        preview.preview_fingerprint, "manifest-confirm-rule",
    )
    assert confirmed["error"] is False, confirmed
    tenant = repository._tenant_scope(SCOPE.store_id)
    connection = repository.get_connection()
    try:
        rule_rows = FifoCostBatchSupplyStore.read_rule_revisions(
            connection, scope=SCOPE, case_id=_case().case_id,
            tenant_fingerprint=tenant["tenant_fingerprint"],
        )
    finally:
        connection.close()
    case_result = repository.read_transition_case(
        case_id=_case().case_id, **IDENTITY,
    )
    case = FifoCostTransitionService._case_from_payload(case_result["case"])
    return repository, tenant["tenant_fingerprint"], rule_rows[0], case, tenant_token


def _coverage(*, scan_id, rule_revision=1, captured_at=NOW_TEXT, membership_complete=False,
              issue_codes=("SOURCE_PROFILE_UNVERIFIED",)):
    return SupplyScanCoverage(
        scan_id=scan_id, revision=1, scope=SCOPE, case_id=_case().case_id,
        rule_revision=rule_revision, requested_from="2026-11-05",
        requested_through="2026-11-15", captured_at=captured_at,
        source_as_of=captured_at, supported_state_profile=("IN_TRANSIT",),
        list_pagination_complete=True, details_complete=True,
        sku_composition_complete=True, historical_window_proven=True,
        membership_complete=membership_complete, quantity_complete=True,
        physical_receipt_timing_complete=False,
        observation_set_fingerprint=_digest("placeholder"),
        source_contract_version="synthetic-v1", orders_seen=1,
        supplies_seen=1, sku_rows_seen=1, unknown_order_count=0,
        unknown_supply_count=0, unknown_quantity_supply_count=0,
        issue_codes=issue_codes,
    )


def _observation(*, captured_at=NOW_TEXT, suffix="1", dispatch_date="2026-11-05",
                 accepted=None, source_revision=1, quantity=100):
    supply_ref = _digest(f"supply-{suffix}")
    return SupplySkuObservation(
        scope=SCOPE,
        record_key=FifoCostBatchSupplyDeduplicator.canonical_record_key(SCOPE, supply_ref),
        order_ref_digest=_digest(f"order-{suffix}"), supply_ref_digest=supply_ref,
        encrypted_lookup_payload="gAAAA" + "A" * 96,
        source_profile_version="synthetic-v1",
        source_fingerprint=_digest(f"source-{suffix}-{source_revision}"),
        captured_at=captured_at, source_as_of=captured_at,
        source_status="IN_TRANSIT", normalized_status=NormalizedSupplyStatus.IN_TRANSIT,
        is_crossdock=True, dispatch_local_date=dispatch_date, dispatch_local_time=None,
        dispatch_time_status=DispatchTimeStatus.CONFIRMED,
        planned_declared_quantity=quantity, shipped_composition_quantity=quantity,
        accepted_quantity=accepted, quantity_source_kind=EvidenceSourceKind.OZON_API,
        quantity_coverage=EvidenceCompleteness.COMPLETE,
        acceptance_fingerprint=None if accepted is None else _digest(f"accept-{suffix}-{accepted}"),
        acceptance_version=None if accepted is None else 1, explicit_zero_fields=(),
        membership=SupplyMembership.ELIGIBLE,
    )


def _publish_scan(
    repository, tenant_fingerprint, rule, *, scan_id, status="PUBLISHED", minute=0,
    expected_case_revision=2, observations=None, coverage=None,
):
    captured = f"2026-11-15T12:{minute:02d}:00.000000Z"
    coverage = coverage or _coverage(
        scan_id=scan_id, rule_revision=rule["rule_revision"], captured_at=captured,
    )
    checkpoint = FifoCostBatchScanCheckpointService(repository, now_provider=lambda: NOW)
    result = checkpoint.commit_page(
        coverage=coverage, tenant_fingerprint=tenant_fingerprint,
        rule_id=rule["rule_id"], rule_fingerprint=rule["rule_fingerprint"],
        expected_case_revision=expected_case_revision, expected_scan_revision=0,
        observations=(
            tuple(observations) if observations is not None
            else (_observation(captured_at=captured),) if status == "PUBLISHED" else ()
        ),
        status=status, expires_at="2026-11-15T12:30:00.000000Z",
        updated_at=captured,
        continuation_state=(
            {"cursor": "next", "seen_cursor_digests": (), "pages_scanned": 1}
            if status == "PARTIAL" else None
        ),
        now=NOW_TEXT,
    )
    assert result.get("error") is False, result
    return result


def test_readiness_rehydrates_latest_published_manifest_from_scoped_sqlite(tmp_path, monkeypatch):
    repository, tenant_fp, rule, case, tenant_token = _setup(tmp_path, monkeypatch)
    try:
        _publish_scan(
            repository, tenant_fp, rule, scan_id="manifest-scan-01",
        )
        reader = FifoCostBatchManifestReadService(
            repository, now_provider=lambda: NOW,
        )
        result = reader.read_current_manifest(case=case)

        assert result["error"] is False, result
        manifest = result["manifest"]
        assert manifest.scan_id == "manifest-scan-01"
        assert manifest.declared_in_shipped_supplies == 100
        assert manifest.known_subtotal == 0
        assert manifest.unknown_quantity_supply_count == 1
        assert manifest.coverage.issue_codes == ("SOURCE_PROFILE_UNVERIFIED",)
        assert manifest.coverage.physical_receipt_timing_complete is False
        assert manifest.read_only is True

        transition = FifoCostTransitionService(repository, now_provider=lambda: NOW)
        review = FifoCostTransitionReviewService(
            transition, FifoCostHistoryService(repository),
            automatic_batch_manifest_service=reader,
        )
        reviewed = review.assess(case_id=case.case_id, identity=IDENTITY)
        assert reviewed["error"] is False, reviewed
        assert reviewed["automatic_batch_manifest_status"] == result["code"]
        assert reviewed["automatic_batch_manifest_seal"] == result["seal"]
        requirements = {item.code: item for item in reviewed["readiness"].requirements}
        assert "AUTO_SUPPLY_MANIFEST_UNAVAILABLE" not in requirements
        manifest_requirement = requirements["AUTO_SUPPLY_MANIFEST_INCOMPLETE"]
        assert manifest_requirement.already_saved[0].fingerprint == manifest.manifest_fingerprint
        assert reviewed["ready_to_apply"] is False
        connection = repository.get_connection()
        try:
            for table in ("fifo_cost_events", "fifo_cost_layers", "fifo_cost_allocations"):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_latest_manifest_reconciles_acceptance_against_prior_observations(
    tmp_path, monkeypatch,
):
    repository, tenant_fp, rule, case, tenant_token = _setup(tmp_path, monkeypatch)
    try:
        first_time = "2026-11-15T12:00:00.000000Z"
        second_time = "2026-11-15T12:01:00.000000Z"
        first = _observation(
            captured_at=first_time, suffix="same-supply", accepted=100,
            source_revision=1,
        )
        second = _observation(
            captured_at=second_time, suffix="same-supply", accepted=90,
            source_revision=2,
        )
        _publish_scan(
            repository, tenant_fp, rule, scan_id="manifest-acceptance-before",
            minute=0, observations=(first,),
            coverage=_coverage(
                scan_id="manifest-acceptance-before", captured_at=first_time,
                rule_revision=rule["rule_revision"],
            ),
        )
        _publish_scan(
            repository, tenant_fp, rule, scan_id="manifest-acceptance-after",
            minute=1, observations=(second,),
            coverage=_coverage(
                scan_id="manifest-acceptance-after", captured_at=second_time,
                rule_revision=rule["rule_revision"],
            ),
        )

        result = FifoCostBatchManifestReadService(
            repository, now_provider=lambda: NOW,
        ).read_current_manifest(case=case)

        assert result["error"] is False, result
        assert result["manifest"].scan_id == "manifest-acceptance-after"
        assert result["manifest"].accepted_units is None
        assert "FIFO_BATCH_ACCEPTANCE_DECREASE_REQUIRES_REVIEW" in result["issue_codes"]
        assert result["status"] != "COMPLETE"
    finally:
        reset_current_tenant_user_id(tenant_token)


@pytest.mark.parametrize(
    "prior_count,current_count,dispatch_confirmed",
    [
        pytest.param(2, 1, True, id="one-missing-one-current"),
        pytest.param(2, 0, True, id="all-supplies-missing"),
        pytest.param(3, 1, True, id="more-missing-than-current"),
        pytest.param(3, 1, False, id="missing-and-current-membership-unresolved"),
    ],
)
def test_supply_missing_from_latest_scan_stays_unknown_and_blocks_manifest(
    tmp_path, monkeypatch, prior_count, current_count, dispatch_confirmed,
):
    repository, tenant_fp, rule, case, tenant_token = _setup(tmp_path, monkeypatch)
    try:
        first_time = "2026-11-15T12:00:00.000000Z"
        second_time = "2026-11-15T12:01:00.000000Z"
        before = tuple(
            _observation(captured_at=first_time, suffix=f"supply-{index}", accepted=100)
            for index in range(prior_count)
        )
        _publish_scan(
            repository, tenant_fp, rule, scan_id="manifest-presence-before",
            minute=0, observations=before,
            coverage=replace(
                _coverage(
                    scan_id="manifest-presence-before", captured_at=first_time,
                    rule_revision=rule["rule_revision"], membership_complete=True,
                    issue_codes=(),
                ),
                supplies_seen=prior_count, sku_rows_seen=prior_count,
            ),
        )
        after = tuple(
            replace(
                _observation(
                    captured_at=second_time, suffix=f"supply-{index}", accepted=100,
                    source_revision=2,
                ),
                dispatch_local_date="2026-11-05" if dispatch_confirmed else None,
                dispatch_time_status=(
                    DispatchTimeStatus.CONFIRMED if dispatch_confirmed
                    else DispatchTimeStatus.UNKNOWN
                ),
            )
            for index in range(current_count)
        )
        _publish_scan(
            repository, tenant_fp, rule, scan_id="manifest-presence-after",
            minute=1, observations=after,
            coverage=replace(
                _coverage(
                    scan_id="manifest-presence-after", captured_at=second_time,
                    rule_revision=rule["rule_revision"], membership_complete=True,
                    issue_codes=(),
                ),
                supplies_seen=current_count, sku_rows_seen=current_count,
            ),
        )

        reconciled = FifoCostBatchSupplyDeduplicator.reconcile(
            scope=SCOPE, case_id=case.case_id, observations=after,
            declarations=(), acceptance_history=before,
        )
        missing_records = tuple(
            item for item in reconciled.records if item.current_observation is None
        )
        assert len(missing_records) == prior_count - current_count
        for record in missing_records:
            assert record.effective_accepted_quantity == 100
            assert "FIFO_BATCH_SUPPLY_MISSING_FROM_CURRENT_SCAN" in record.issues

        reader = FifoCostBatchManifestReadService(repository, now_provider=lambda: NOW)
        result = reader.read_current_manifest(case=case)
        assert result["error"] is False, result
        assert result["status"] == ("PARTIAL" if current_count else "UNKNOWN")
        assert "FIFO_BATCH_SUPPLY_MISSING_FROM_CURRENT_SCAN" in result["issue_codes"]
        manifest = result["manifest"]
        assert manifest.found_supply_count == current_count
        assert manifest.undecided_supply_count == (0 if dispatch_confirmed else current_count)
        assert manifest.coverage.unknown_supply_count == len(missing_records)
        assert manifest.coverage.membership_complete is False
        assert manifest.missing_supply_record_keys == tuple(sorted(
            record.record_key for record in missing_records
        ))
        assert manifest.accepted_units is None
        assert manifest.known_subtotal == (100 * current_count if dispatch_confirmed else 0)
        assert manifest.pending_units is None
        assert manifest.freshness is not ManifestFreshness.CURRENT
        # The incomplete result must also pass through the real readiness path.
        review = FifoCostTransitionReviewService(
            FifoCostTransitionService(repository, now_provider=lambda: NOW),
            FifoCostHistoryService(repository), automatic_batch_manifest_service=reader,
        ).assess(case_id=case.case_id, identity=IDENTITY)
        assert review["error"] is False, review
        assert review["ready_to_apply"] is False
        assert "AUTO_SUPPLY_MANIFEST_INCOMPLETE" in {
            item.code for item in review["readiness"].requirements
        }
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_latest_scan_uses_latest_quantity_and_detects_replayed_acceptance_decrease(
    tmp_path, monkeypatch,
):
    repository, tenant_fp, rule, case, tenant_token = _setup(tmp_path, monkeypatch)
    try:
        scans = (
            ("manifest-replay-before", 0, 100, 10, 1),
            ("manifest-replay-middle", 1, 200, 20, 2),
            ("manifest-replay-after", 2, 100, 10, 1),
        )
        for scan_id, minute, quantity, accepted, source_revision in scans:
            captured = f"2026-11-15T12:{minute:02d}:00.000000Z"
            observation = _observation(
                captured_at=captured, suffix="same-supply", accepted=accepted,
                source_revision=source_revision, quantity=quantity,
            )
            _publish_scan(
                repository, tenant_fp, rule, scan_id=scan_id, minute=minute,
                observations=(observation,),
                coverage=_coverage(
                    scan_id=scan_id, captured_at=captured,
                    rule_revision=rule["rule_revision"],
                ),
            )

        result = FifoCostBatchManifestReadService(
            repository, now_provider=lambda: NOW,
        ).read_current_manifest(case=case)

        assert result["error"] is False, result
        manifest = result["manifest"]
        assert manifest.scan_id == "manifest-replay-after"
        assert manifest.declared_in_found_supplies == 100
        assert manifest.accepted_units is None
        assert "FIFO_BATCH_ACCEPTANCE_DECREASE_REQUIRES_REVIEW" in result["issue_codes"]
        assert result["status"] != "COMPLETE"
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_changed_case_cost_invalidates_old_rule_manifest_and_source_basis(
    tmp_path, monkeypatch,
):
    repository, tenant_fp, rule, case, tenant_token = _setup(tmp_path, monkeypatch)
    try:
        _publish_scan(
            repository, tenant_fp, rule,
            scan_id="manifest-cost-before-change",
            observations=(_observation(accepted=100),),
            coverage=_coverage(
                scan_id="manifest-cost-before-change",
                rule_revision=rule["rule_revision"], membership_complete=True,
                issue_codes=(),
            ),
        )
        reader = FifoCostBatchManifestReadService(repository, now_provider=lambda: NOW)
        before = reader.read_current_manifest(case=case)
        assert before["error"] is False, before
        assert before["status"] == "COMPLETE"

        transitions = FifoCostTransitionService(repository, now_provider=lambda: NOW)
        updated = transitions.update_owner_inputs(
            case_id=case.case_id,
            expected_revision=case.case_revision,
            updates={"new_unit_cost_rub": Decimal("16.00")},
            idempotency_key="review-change-cost",
            **IDENTITY,
        )
        assert updated["error"] is False, updated
        current_case_payload = repository.read_transition_case(
            case_id=case.case_id, **IDENTITY,
        )
        current_case = FifoCostTransitionService._case_from_payload(
            current_case_payload["case"],
        )

        stale_rule = FifoCostBatchRuleService(
            repository, now_provider=lambda: NOW,
        ).read_active_rule(SCOPE, case.case_id, current_case.case_revision)
        assert stale_rule["error"] is False, stale_rule
        assert stale_rule["inputs_current"] is False
        basis = FifoCostBatchRuleService(
            repository, now_provider=lambda: NOW,
        ).read_collection_basis(
            SCOPE, case.case_id, current_case.case_revision,
            rule["rule_revision"],
        )
        assert basis["error"] is True
        assert basis["code"] == "FIFO_BATCH_RULE_CASE_INPUTS_STALE"

        stale_manifest = reader.read_current_manifest(case=current_case)
        assert stale_manifest["error"] is False, stale_manifest
        assert stale_manifest["code"] == "FIFO_BATCH_MANIFEST_RULE_CASE_INPUTS_STALE"
        assert stale_manifest["manifest"] is None

        # Editing the case remains recoverable: owner can preview a successor
        # rule using the corrected price, while the old rule stays blocked.
        successor = FifoCostBatchRuleService(
            repository, now_provider=lambda: NOW,
        ).preview_rule(
            SCOPE, case.case_id, current_case.case_revision,
            BatchRuleInput("2026-11-16", BatchStartDayPolicy.ALL_OWNER_CONFIRMED),
        )
        assert successor["error"] is False, successor
        assert successor["preview"].new_unit_cost_rub == Decimal("16.00")
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_rule_rehydration_keeps_closed_base_event_and_manifest_uses_active_interval(
    tmp_path, monkeypatch,
):
    repository, tenant_fp, _initial_rule, case, tenant_token = _setup(tmp_path, monkeypatch)
    try:
        rules = FifoCostBatchRuleService(repository, now_provider=lambda: NOW)
        preview_result = rules.preview_rule(
            SCOPE, case.case_id, case.case_revision,
            BatchRuleInput("2026-11-12", BatchStartDayPolicy.ALL_OWNER_CONFIRMED),
        )
        assert preview_result["error"] is False, preview_result
        preview = preview_result["preview"]
        confirmed = rules.confirm_rule(
            SCOPE, case.case_id, case.case_revision, preview.preview_id,
            preview.preview_fingerprint, "manifest-confirm-successor-rule",
        )
        assert confirmed["error"] is False, confirmed

        connection = repository.get_connection()
        try:
            rule_rows = FifoCostBatchSupplyStore.read_rule_revisions(
                connection, scope=SCOPE, case_id=case.case_id,
                tenant_fingerprint=tenant_fp,
            )
        finally:
            connection.close()
        reader = FifoCostBatchManifestReadService(repository, now_provider=lambda: NOW)
        rule_chain, active = reader._restore_rule_chain(
            scope=SCOPE, case_id=case.case_id, rows=rule_rows,
        )
        assert [item.event_kind for item in rule_chain] == [
            BatchRuleEventKind.CONFIRM,
            BatchRuleEventKind.CLOSE,
            BatchRuleEventKind.REPLACE,
        ]
        assert active.start_local_date == "2026-11-12"

        captured = "2026-11-15T12:01:00.000000Z"
        observations = (
            _observation(
                captured_at=captured, suffix="prior", dispatch_date="2026-11-06",
                accepted=100,
            ),
            _observation(
                captured_at=captured, suffix="active", dispatch_date="2026-11-13",
                accepted=100,
            ),
        )
        coverage = replace(
            _coverage(
                scan_id="manifest-successor-scan", rule_revision=active.rule_revision,
                captured_at=captured, membership_complete=True, issue_codes=(),
            ),
            supplies_seen=2, sku_rows_seen=2,
        )
        active_row = next(
            row for row in rule_rows
            if row["rule_id"] == active.rule_id
            and row["rule_revision"] == active.rule_revision
        )
        _publish_scan(
            repository, tenant_fp, active_row,
            scan_id="manifest-successor-scan",
            expected_case_revision=confirmed["case_revision"],
            observations=observations, coverage=coverage,
        )
        case_result = repository.read_transition_case(
            case_id=case.case_id, **IDENTITY,
        )
        current_case = FifoCostTransitionService._case_from_payload(case_result["case"])
        assert rules._initial_rule_start_date(rule_chain) == "2026-11-05"
        assert rules._initial_rule_start_date(rule_chain[1:]) is None
        assert not rules.case_inputs_match_rule(active, current_case)

        result = reader.read_current_manifest(case=current_case)

        assert result["error"] is False, result
        assert result["status"] == "COMPLETE"
        assert result["manifest"].rule_id == active.rule_id
        assert result["manifest"].declared_in_found_supplies == 200
        assert result["manifest"].declared_in_shipped_supplies == 100
        assert result["manifest"].accepted_units == 100
        assert result["manifest"].included_supply_count == 1
        assert result["manifest"].undecided_supply_count == 0

        transitions = FifoCostTransitionService(repository, now_provider=lambda: NOW)
        updated = transitions.update_owner_inputs(
            case_id=case.case_id,
            expected_revision=current_case.case_revision,
            updates={"dispatch_date": "2026-11-14"},
            idempotency_key="review-change-initial-dispatch-date",
            **IDENTITY,
        )
        assert updated["error"] is False, updated
        updated_payload = repository.read_transition_case(
            case_id=case.case_id, **IDENTITY,
        )
        updated_case = FifoCostTransitionService._case_from_payload(
            updated_payload["case"],
        )

        stale_rule = rules.read_active_rule(
            SCOPE, case.case_id, updated_case.case_revision,
        )
        assert stale_rule["error"] is False, stale_rule
        assert stale_rule["inputs_current"] is False
        stale_basis = rules.read_collection_basis(
            SCOPE, case.case_id, updated_case.case_revision, active.rule_revision,
        )
        assert stale_basis["error"] is True
        assert stale_basis["code"] == "FIFO_BATCH_RULE_CASE_INPUTS_STALE"
        stale_manifest = reader.read_current_manifest(case=updated_case)
        assert stale_manifest["error"] is False, stale_manifest
        assert stale_manifest["code"] == "FIFO_BATCH_MANIFEST_RULE_CASE_INPUTS_STALE"
        assert stale_manifest["manifest"] is None
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_manifest_seal_binds_all_scoped_batch_rows_and_rechecks_on_open_transaction(
    tmp_path, monkeypatch,
):
    repository, tenant_fp, rule, case, tenant_token = _setup(tmp_path, monkeypatch)
    try:
        _publish_scan(repository, tenant_fp, rule, scan_id="manifest-seal-scan-01")
        reader = FifoCostBatchManifestReadService(
            repository, now_provider=lambda: NOW,
        )
        first = reader.read_current_manifest(case=case)
        assert first["error"] is False, first
        seal = first["seal"]
        assert repository._normalize_auto_batch_manifest_seal(seal) == seal
        tampered_seal = {**seal, "source_storage_fingerprint": "f" * 64}
        assert repository._normalize_auto_batch_manifest_seal(tampered_seal) is None
        assert repository._normalize_auto_batch_manifest_seal(
            {**seal, "unexpected": True},
        ) is None

        connection = repository.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current_fingerprint = FifoCostBatchSupplyStore.read_scope_source_fingerprint(
                connection, scope=SCOPE, case_id=case.case_id,
                tenant_fingerprint=tenant_fp,
            )
            assert current_fingerprint == seal["source_storage_fingerprint"]
            connection.rollback()
        finally:
            connection.close()

        _publish_scan(
            repository, tenant_fp, rule, scan_id="manifest-seal-scan-02",
            status="PARTIAL", minute=1,
        )
        connection = repository.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            changed_fingerprint = FifoCostBatchSupplyStore.read_scope_source_fingerprint(
                connection, scope=SCOPE, case_id=case.case_id,
                tenant_fingerprint=tenant_fp,
            )
            assert changed_fingerprint != seal["source_storage_fingerprint"]
            connection.rollback()
        finally:
            connection.close()

        latest = reader.read_current_manifest(case=case)
        assert latest["error"] is False
        assert latest["code"] == "FIFO_BATCH_MANIFEST_LATEST_SCAN_NOT_CURRENT"
        assert latest["manifest"] is None
        assert "seal" not in latest
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_manifest_reader_seals_one_snapshot_when_new_scan_publishes_mid_read(
    tmp_path, monkeypatch,
):
    repository, tenant_fp, rule, case, tenant_token = _setup(tmp_path, monkeypatch)
    try:
        connection = repository.get_connection()
        try:
            assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
        finally:
            connection.close()

        _publish_scan(repository, tenant_fp, rule, scan_id="manifest-snapshot-old")
        connection = repository.get_connection()
        try:
            connection.execute("BEGIN")
            old_fingerprint = FifoCostBatchSupplyStore.read_scope_source_fingerprint(
                connection, scope=SCOPE, case_id=case.case_id,
                tenant_fingerprint=tenant_fp,
            )
        finally:
            connection.close()

        writer_started = Event()
        writer_finished = Event()
        writer_result = {}

        def publish_newer_partial_scan():
            writer_started.set()
            try:
                writer_result["result"] = _publish_scan(
                    repository, tenant_fp, rule,
                    scan_id="manifest-snapshot-new", status="PARTIAL", minute=1,
                )
            except BaseException as exc:  # propagate worker failures to the test thread
                writer_result["exception"] = exc
            finally:
                writer_finished.set()

        original_read = FifoCostBatchSupplyStore.read_membership_decisions

        def read_decisions_then_publish(cls, connection, **kwargs):
            rows = original_read(connection, **kwargs)
            writer = Thread(target=publish_newer_partial_scan, daemon=True)
            writer.start()
            assert writer_started.wait(2), "writer thread did not start"
            assert writer_finished.wait(5), "concurrent scan did not finish"
            assert "exception" not in writer_result, writer_result.get("exception")
            assert writer_result["result"].get("error") is False, writer_result
            return rows

        monkeypatch.setattr(
            FifoCostBatchSupplyStore, "read_membership_decisions",
            classmethod(read_decisions_then_publish),
        )
        result = FifoCostBatchManifestReadService(
            repository, now_provider=lambda: NOW,
        ).read_current_manifest(case=case)

        assert result["error"] is False, result
        assert result["manifest"] is not None
        assert result["manifest"].scan_id == "manifest-snapshot-old"
        assert result["seal"]["source_storage_fingerprint"] == old_fingerprint

        connection = repository.get_connection()
        try:
            connection.execute("BEGIN")
            live_fingerprint = FifoCostBatchSupplyStore.read_scope_source_fingerprint(
                connection, scope=SCOPE, case_id=case.case_id,
                tenant_fingerprint=tenant_fp,
            )
        finally:
            connection.close()
        assert live_fingerprint != old_fingerprint
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_manifest_source_seal_fails_closed_when_a_scoped_table_exceeds_its_bound(
    tmp_path, monkeypatch,
):
    from services import fifo_cost_batch_supply_store as batch_store_module

    repository, tenant_fp, rule, case, tenant_token = _setup(tmp_path, monkeypatch)
    try:
        _publish_scan(repository, tenant_fp, rule, scan_id="manifest-limit-scan-01")
        connection = repository.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            stored = FifoCostBatchSupplyStore.append_observation(
                connection, _observation(suffix="2"),
                tenant_fingerprint=tenant_fp,
                case_id=_case().case_id,
                observation_id="manifest-observation-extra-01",
                recorded_at=NOW_TEXT,
            )
            assert stored["error"] is False, stored
            connection.commit()
        finally:
            connection.close()

        limits = dict(batch_store_module._SOURCE_FINGERPRINT_ROW_LIMITS)
        limits["fifo_cost_batch_supply_observations"] = 1
        monkeypatch.setattr(
            batch_store_module,
            "_SOURCE_FINGERPRINT_ROW_LIMITS", limits,
        )
        connection = repository.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                FifoCostBatchSupplyStore.read_scope_source_fingerprint(
                    connection, scope=SCOPE, case_id=case.case_id,
                    tenant_fingerprint=tenant_fp,
                )
            except ValueError as exc:
                assert str(exc) == "FIFO_BATCH_MANIFEST_SEAL_ROW_LIMIT_REACHED"
            else:
                raise AssertionError("source fingerprint must reject over-limit rows")
            connection.rollback()
        finally:
            connection.close()

        reader = FifoCostBatchManifestReadService(
            repository, now_provider=lambda: NOW,
        )
        result = reader.read_current_manifest(case=case)
        assert result == {
            "error": True,
            "code": "FIFO_BATCH_MANIFEST_STORAGE_UNAVAILABLE",
        }
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_newer_partial_scan_does_not_fall_back_to_older_published_manifest(tmp_path, monkeypatch):
    repository, tenant_fp, rule, case, tenant_token = _setup(tmp_path, monkeypatch)
    try:
        _publish_scan(
            repository, tenant_fp, rule, scan_id="manifest-scan-old", minute=0,
        )
        _publish_scan(
            repository, tenant_fp, rule, scan_id="manifest-scan-new",
            status="PARTIAL", minute=1,
        )
        reader = FifoCostBatchManifestReadService(
            repository, now_provider=lambda: NOW,
        )
        result = reader.read_current_manifest(case=case)

        assert result == {
            "error": False,
            "code": "FIFO_BATCH_MANIFEST_LATEST_SCAN_NOT_CURRENT",
            "manifest": None,
        }
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_equal_time_scan_order_is_ambiguous_and_returns_no_manifest(tmp_path, monkeypatch):
    repository, tenant_fp, rule, case, tenant_token = _setup(tmp_path, monkeypatch)
    try:
        _publish_scan(repository, tenant_fp, rule, scan_id="manifest-scan-tie-a")
        _publish_scan(repository, tenant_fp, rule, scan_id="manifest-scan-tie-b")
        result = FifoCostBatchManifestReadService(
            repository, now_provider=lambda: NOW,
        ).read_current_manifest(case=case)

        assert result == {
            "error": False,
            "code": "FIFO_BATCH_MANIFEST_SCAN_UNAVAILABLE",
            "manifest": None,
        }
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_expired_published_manifest_is_retained_as_stale_evidence(tmp_path, monkeypatch):
    repository, tenant_fp, rule, case, tenant_token = _setup(tmp_path, monkeypatch)
    try:
        _publish_scan(repository, tenant_fp, rule, scan_id="manifest-scan-expired")
        later = datetime(2026, 11, 15, 12, 31, tzinfo=timezone.utc)
        result = FifoCostBatchManifestReadService(
            repository, now_provider=lambda: later,
        ).read_current_manifest(case=case)

        assert result["error"] is False, result
        assert result["manifest"].freshness is ManifestFreshness.STALE
        assert "FIFO_BATCH_SCAN_STALE_EXPIRED" in result["manifest"].issues
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_corrupt_rule_confirmation_does_not_build_a_manifest(tmp_path, monkeypatch):
    repository, tenant_fp, rule, case, tenant_token = _setup(tmp_path, monkeypatch)
    try:
        _publish_scan(repository, tenant_fp, rule, scan_id="manifest-scan-corrupt-rule")
        original_read = FifoCostBatchSupplyStore.read_rule_revisions

        def corrupt_read(cls, connection, **kwargs):
            rows = original_read(
                connection, **kwargs,
            )
            return (dict(rows[0], old_home_confirmed_zero=0),)

        monkeypatch.setattr(
            FifoCostBatchSupplyStore, "read_rule_revisions",
            classmethod(corrupt_read),
        )

        result = FifoCostBatchManifestReadService(
            repository, now_provider=lambda: NOW,
        ).read_current_manifest(case=case)
        assert result == {
            "error": True,
            "code": "FIFO_BATCH_MANIFEST_STORAGE_UNAVAILABLE",
        }
    finally:
        reset_current_tenant_user_id(tenant_token)
