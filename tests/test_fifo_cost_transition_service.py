from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from threading import Barrier

from cryptography.fernet import Fernet
import pytest

from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_contracts import (
    CostInputMode,
    EvidenceCompleteness,
    EvidenceSourceKind,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
    SupplyTotalMode,
    TransitionCase,
    TransitionMetadata,
    TransitionReasonCode,
    TransitionState,
    UnknownValue,
    source_fingerprint,
)
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.fifo_cost_transition_store import FifoCostTransitionStore
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


def _case(
    *, case_id="case_000001", sku=None, product_id=None, offer_id=None,
    revision=1, created_at="2026-11-08T10:00:00Z", updated_at=None,
):
    scope = ScopeIdentity(
        owner_id="owner-a",
        store_id=IDENTITY["store_id"],
        product_id=product_id or IDENTITY["product_id"],
        offer_id=offer_id or IDENTITY["offer_id"],
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
        created_at=created_at,
        updated_at=updated_at or created_at,
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


def test_case_lifecycle_is_durable_and_does_not_activate_fifo(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"),
    )
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
            _case(revision=2, updated_at="2026-11-08T13:00:00Z"),
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
            FifoCostRepository(
                db_path=repository.db_path,
                now_provider=lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc),
            ),
            now_provider=lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc),
        )
        durable = restarted.get_case(
            case_id="case_000001", **IDENTITY,
        )
        assert durable["error"] is False
        assert durable["case_revision"] == 2
        assert durable["case"]["new_home_quantity"] == 17

        declaration = restarted.declare_supply(
            case_id="case_000001", **IDENTITY,
            reference_kind="SUPPLY", reference_id="987654321",
            declared_shipped_units=148, dispatch_date="2026-11-05",
            expected_case_revision=2, idempotency_key="declare-transition-001",
        )
        assert declaration["error"] is False, declaration
        assert declaration["case_revision"] == 3
        assert restarted.get_case(
            case_id="case_000001", **IDENTITY,
        )["case"]["updated_at"] == "2026-11-08T13:00:00.000000Z"

        cancelled = restarted.cancel_case(
            case_id="case_000001", **IDENTITY, expected_revision=3,
            idempotency_key="cancel-transition-001",
        )
        assert cancelled["error"] is False, cancelled
        assert cancelled["case_revision"] == 4
        assert cancelled["state"] == "CANCELLED"
        repeated_cancel = restarted.cancel_case(
            case_id="case_000001", **IDENTITY, expected_revision=3,
            idempotency_key="cancel-transition-001",
        )
        assert repeated_cancel["error"] is False
        assert repeated_cancel["replayed"] is True
        assert restarted.list_cases(store_id=IDENTITY["store_id"])["count"] == 0
        assert restarted.list_cases(
            store_id=IDENTITY["store_id"], states=("CANCELLED",),
        )["count"] == 1
        durable_history = restarted.read_case_history(
            case_id="case_000001", **IDENTITY, limit=100,
        )
        assert durable_history["error"] is False, durable_history
        assert [item["state"] for item in durable_history["items"]] == [
            "DRAFT", "AWAITING_EVIDENCE", "AWAITING_EVIDENCE", "CANCELLED",
        ]
        assert durable_history["items"][-1]["case_revision"] == 4
        assert "987654321" not in repr(durable_history)
        assert "case_000001" not in repr(durable_history)
        newest_page = restarted.read_case_history(
            case_id="case_000001", **IDENTITY, limit=2,
        )
        assert [item["case_revision"] for item in newest_page["items"]] == [3, 4]
        assert newest_page["has_more"] is True
        older_page = restarted.read_case_history(
            case_id="case_000001", **IDENTITY, limit=2,
            before_revision=newest_page["next_before_revision"],
        )
        assert [item["case_revision"] for item in older_page["items"]] == [1, 2]
        assert older_page["has_more"] is False
        assert restarted.read_case_history(
            case_id="case_000001", **IDENTITY, limit=101,
        )["code"] == "FIFO_TRANSITION_LIMIT_INVALID"
        declaration_evidence = restarted.repository.read_transition_evidence(
            case_id="case_000001", **IDENTITY,
            kind="SUPPLY_DECLARATION", limit=100,
        )
        assert declaration_evidence["error"] is False, declaration_evidence
        assert len(declaration_evidence["items"]) == 1
        assert declaration_evidence["items"][0]["lookup_reference_available"] is True
        assert "encrypted_lookup_reference" not in declaration_evidence["items"][0]

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
            ).fetchone()[0] == 5
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant)


def test_case_supply_total_mode_defaults_legacy_and_survives_payload_roundtrip(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv(
        "OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"),
    )
    tenant = set_current_tenant_user_id(OWNER_SCOPE)
    try:
        repository, service = _service(tmp_path)
        created = service.create_case(
            case=_case(), idempotency_key="batch-mode-create-001",
        )
        assert created["error"] is False
        initial = service.get_case(
            case_id="case_000001", store_id="store-a", sku=IDENTITY["sku"],
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
        )
        assert initial["case"]["supply_total_mode"] == "LEGACY_OWNER_TOTAL"

        auto_case = replace(
            _case(revision=2, updated_at="2026-11-08T13:00:00Z"),
            state=TransitionState.AWAITING_EVIDENCE,
            new_home_quantity=17,
            unknown_values={},
            supply_total_mode=SupplyTotalMode.AUTO_FROM_SUPPLIES,
        )
        updated = service.update_case(
            case=auto_case, expected_revision=1,
            idempotency_key="batch-mode-update-001",
        )
        assert updated["error"] is False
        listed = service.list_cases(store_id="store-a")
        assert listed["cases"][0]["case"]["supply_total_mode"] == "AUTO_FROM_SUPPLIES"

        old_payload = FifoCostTransitionStore.case_payload(_case())
        old_payload.pop("supply_total_mode")
        restored_legacy = service._case_from_payload(old_payload)
        assert restored_legacy.supply_total_mode is SupplyTotalMode.LEGACY_OWNER_TOTAL
        connection = repository.get_connection()
        try:
            assert connection.execute(
                "SELECT supply_total_mode FROM fifo_cost_transition_cases "
                "WHERE case_id='case_000001'"
            ).fetchone()[0] == "AUTO_FROM_SUPPLIES"
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant)


@pytest.mark.parametrize("reported_reserved", [0, None], ids=["reported", "owner-confirmed"])
@pytest.mark.parametrize(
    "supplier_receiving_units", [None, 0, 148],
    ids=["unreported", "owner-confirmed-zero", "owner-confirmed-148"],
)
def test_fr17_public_owner_confirmations_persist_cutoff_and_3_old_plus_100_new(
    tmp_path, monkeypatch, reported_reserved, supplier_receiving_units,
):
    monkeypatch.setenv(
        "OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"),
    )
    tenant = set_current_tenant_user_id(OWNER_SCOPE)
    try:
        repository, service = _service(tmp_path)
        case = replace(
            _case(), owner_old_home_units=3, new_home_quantity=2,
            declared_shipped_units=100, unknown_values={},
        )
        created = service.create_case(case=case, idempotency_key="fr17-case-0001")
        assert created["error"] is False
        stock_report = ReportEvidence(
            metadata=TransitionMetadata(
                scope=case.metadata.scope,
                source_kind=EvidenceSourceKind.OWNER_IMPORTED,
                completeness=EvidenceCompleteness.COMPLETE,
                source_fingerprint=source_fingerprint("fr17-stock-source"),
                store_timezone="Europe/Moscow",
            ),
            report_type=ReportType.STOCK_MANAGEMENT,
            period_from="2026-11-06",
            period_to="2026-11-06",
            period_provenance=PeriodProvenance.OWNER_CONFIRMED,
            captured_at="2026-11-07T18:00:00Z",
            file_sha256=source_fingerprint("fr17-stock-file"),
            parser_version="stock-test-v1",
            cell_references=("A1",),
            normalized_fields={
                "stock_buckets": {
                        "available": 100, "reserved": reported_reserved,
                    "preparing": 0, "checking": 0,
                },
                "fbs_return_available_units": 0,
                "fbs_return_is_subset_of_available": True,
            },
        )
        saved_report = repository.append_report_evidence(
            case_id=case.case_id, report=stock_report,
            expected_case_revision=1, idempotency_key="fr17-report-0001",
        )
        assert saved_report["error"] is False, saved_report

        cutoff = service.record_cutoff_selection(
            case_id=case.case_id, **IDENTITY,
            cutoff_date="2026-11-06",
            stock_report_fingerprint=stock_report.file_sha256,
            supplier_receiving_units=supplier_receiving_units,
            expected_case_revision=saved_report["case_revision"],
            idempotency_key="fr17-cutoff-0001",
        )
        assert cutoff["error"] is False, cutoff
        stored_cutoff = repository.read_transition_bridge_evidence(
            case_id=case.case_id, **IDENTITY,
            evidence_kind="CUTOFF_SELECTION", evidence_id=cutoff["evidence_id"],
            limit=1,
        )["items"][0]
        assert stored_cutoff["completeness"] == "PARTIAL"
        assert stored_cutoff["payload"]["selected_event_count"] is None
        cutoff_confirmed = service.confirm_cutoff_selection(
            case_id=case.case_id, **IDENTITY,
            evidence_id=cutoff["evidence_id"],
            expected_evidence_fingerprint=cutoff["payload_fingerprint"],
            expected_case_revision=cutoff["case_revision"],
            idempotency_key="fr17-cutoff-confirm-0001",
        )
        assert cutoff_confirmed["error"] is False, cutoff_confirmed
        durable_cutoff = service.read_confirmed_cutoff_selection(
            case_id=case.case_id, **IDENTITY,
        )
        assert durable_cutoff["error"] is False, durable_cutoff
        assert durable_cutoff["descriptor"] == {
            "cutoff_date": "2026-11-06",
            "timezone": "Europe/Moscow",
            "precision": "STORE_LOCAL_DATE",
            "boundary": "END_OF_LOCAL_DATE",
        }
        assert durable_cutoff["owner_confirmed_supplier_receiving_units"] == (
            supplier_receiving_units
        )

        layers = [
            {
                "sequence": 1, "unit_cost_rub": "21.00",
                "ozon_units": 0, "transit_units": 0, "home_units": 3,
            },
            {
                "sequence": 2, "unit_cost_rub": "14.65",
                "ozon_units": 100, "transit_units": 0, "home_units": 2,
            },
        ]
        composition = service.record_opening_composition(
            case_id=case.case_id, **IDENTITY,
            cutoff_evidence_id=cutoff["evidence_id"],
            cutoff_evidence_fingerprint=cutoff["payload_fingerprint"],
            stock_report_fingerprint=stock_report.file_sha256,
            layers=layers,
            unknown_new_home_quantity=False,
            new_home_quantity=2,
            new_party_transit_units=7,
            expected_case_revision=cutoff_confirmed["case_revision"],
            idempotency_key="fr17-opening-0001",
        )
        assert composition["error"] is False, composition
        invalid_ozon_units = 200 if reported_reserved == 0 else 99
        rejected_mismatch = service.record_opening_composition(
            case_id=case.case_id, **IDENTITY,
            cutoff_evidence_id=cutoff["evidence_id"],
            cutoff_evidence_fingerprint=cutoff["payload_fingerprint"],
            stock_report_fingerprint=stock_report.file_sha256,
            layers=[layers[0], {**layers[1], "ozon_units": invalid_ozon_units}],
            expected_case_revision=composition["case_revision"],
            idempotency_key="fr17-opening-mismatch-0001",
        )
        assert rejected_mismatch["code"] == "FIFO_INITIAL_CUTOVER_QUANTITY_MISMATCH"
        assert repository.read_transition_case(case_id=case.case_id, **IDENTITY)[
            "case_revision"
        ] == composition["case_revision"]

        confirmed = service.confirm_opening_composition(
            case_id=case.case_id, **IDENTITY,
            evidence_id=composition["evidence_id"],
            expected_evidence_fingerprint=composition["payload_fingerprint"],
            expected_case_revision=composition["case_revision"],
            idempotency_key="fr17-opening-confirm-0001",
        )
        assert confirmed["error"] is False, confirmed
        connection = repository.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_events"
            ).fetchone()[0] == 0
        finally:
            connection.close()

        restarted = FifoCostTransitionService(repository)
        durable_composition = restarted.read_confirmed_opening_composition(
            case_id=case.case_id, **IDENTITY,
        )
        assert durable_composition["error"] is False, durable_composition
        assert durable_composition["layers"] == layers
        assert durable_composition["unknown_new_home_quantity"] is False
        assert durable_composition["total_units"] == 105
        assert durable_composition["new_home_quantity"] == 2
        assert durable_composition["new_party_transit_units"] == 7
        assert durable_composition["owner_confirmed_total_ozon_units"] == 100
        assert durable_composition["owner_confirmed_reserved_units"] == 0
        assert durable_composition["reserved_source"] == (
            "OWNER_CONFIRMED_OPENING_COMPOSITION"
            if reported_reserved is None else "OZON_STOCK_REPORT"
        )
        assert durable_composition["opening_date"] == "2026-11-06"
        assert durable_composition["preview_only"] is True
        assert stock_report.normalized_fields["stock_buckets"]["reserved"] == reported_reserved

        revised = restarted.update_owner_inputs(
            case_id=case.case_id, **IDENTITY,
            expected_revision=confirmed["case_revision"],
            updates={"owner_old_home_units": 4},
            idempotency_key="fr17-owner-basis-revision",
        )
        assert revised["error"] is False, revised
        assert restarted.read_confirmed_cutoff_selection(
            case_id=case.case_id, **IDENTITY,
        )["code"] == "FIFO_CUTOFF_SELECTION_STALE"
        assert restarted.read_confirmed_opening_composition(
            case_id=case.case_id, **IDENTITY,
        )["error"] is True
        connection = repository.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_events"
            ).fetchone()[0] == 0
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


def test_case_list_keyset_reaches_records_beyond_one_hundred(tmp_path):
    tenant = set_current_tenant_user_id(OWNER_SCOPE)
    try:
        _repository, service = _service(tmp_path)
        for index in range(1, 106):
            case_id = f"case_cursor_{index:03d}"
            created_at = (
                f"2026-11-01T00:{index // 60:02d}:{index % 60:02d}Z"
            )
            created = service.create_case(
                case=_case(case_id=case_id, created_at=created_at),
                idempotency_key=f"cursor-create-{index:03d}",
            )
            assert created["error"] is False, created
            cancelled = service.cancel_case(
                case_id=case_id,
                store_id=IDENTITY["store_id"],
                product_id=IDENTITY["product_id"],
                offer_id=IDENTITY["offer_id"],
                sku=IDENTITY["sku"],
                expected_revision=1,
                idempotency_key=f"cursor-cancel-{index:03d}",
            )
            assert cancelled["error"] is False, cancelled

        states = ("DRAFT", "AWAITING_EVIDENCE", "READY_TO_CONFIRM", "APPLIED", "CANCELLED")
        snapshot_cursor = None
        after_cursor = None
        pages = []
        page_sizes = []
        while True:
            result = service.list_cases(
                store_id=IDENTITY["store_id"],
                sku=IDENTITY["sku"],
                states=states,
                limit=20,
                after_cursor=after_cursor,
                snapshot_cursor=snapshot_cursor,
            )
            assert result["error"] is False, result
            snapshot_cursor = result["snapshot_cursor"]
            pages.extend(item["case_id"] for item in result["cases"])
            page_sizes.append(len(result["cases"]))
            if not result["has_more"]:
                break
            after_cursor = result["next_cursor"]

        expected = [f"case_cursor_{index:03d}" for index in range(105, 0, -1)]
        assert pages == expected
        assert page_sizes == [20, 20, 20, 20, 20, 5]
    finally:
        reset_current_tenant_user_id(tenant)


def test_case_list_cursor_keeps_draft_on_same_page_after_update(tmp_path):
    tenant = set_current_tenant_user_id(OWNER_SCOPE)
    try:
        _repository, service = _service(tmp_path)
        for index in range(1, 21):
            case_id = f"case_stable_{index:03d}"
            created = service.create_case(
                case=_case(
                    case_id=case_id,
                    created_at=f"2026-11-02T00:{index:02d}:00Z",
                ),
                idempotency_key=f"stable-create-{index:03d}",
            )
            assert created["error"] is False, created
            cancelled = service.cancel_case(
                case_id=case_id,
                store_id=IDENTITY["store_id"],
                product_id=IDENTITY["product_id"],
                offer_id=IDENTITY["offer_id"],
                sku=IDENTITY["sku"],
                expected_revision=1,
                idempotency_key=f"stable-cancel-{index:03d}",
            )
            assert cancelled["error"] is False, cancelled

        oldest_case_id = "case_stable_oldest"
        created = service.create_case(
            case=_case(
                case_id=oldest_case_id,
                created_at="2026-11-01T00:00:00Z",
            ),
            idempotency_key="stable-create-oldest-001",
        )
        assert created["error"] is False, created
        first_page = service.list_cases(
            store_id=IDENTITY["store_id"], sku=IDENTITY["sku"],
            states=("DRAFT", "AWAITING_EVIDENCE", "READY_TO_CONFIRM", "APPLIED", "CANCELLED"),
            limit=20,
        )
        assert first_page["error"] is False, first_page
        first_ids = [item["case_id"] for item in first_page["cases"]]
        assert oldest_case_id not in first_ids
        assert first_page["has_more"] is True

        updated = service.update_owner_inputs(
            case_id=oldest_case_id,
            store_id=IDENTITY["store_id"],
            product_id=IDENTITY["product_id"],
            offer_id=IDENTITY["offer_id"],
            sku=IDENTITY["sku"],
            expected_revision=1,
            updates={"new_home_quantity": 3},
            idempotency_key="stable-update-oldest-01",
        )
        assert updated["error"] is False, updated
        second_page = service.list_cases(
            store_id=IDENTITY["store_id"], sku=IDENTITY["sku"],
            states=("DRAFT", "AWAITING_EVIDENCE", "READY_TO_CONFIRM", "APPLIED", "CANCELLED"),
            limit=20,
            after_cursor=first_page["next_cursor"],
            snapshot_cursor=first_page["snapshot_cursor"],
        )
        assert second_page["error"] is False, second_page
        second_ids = [item["case_id"] for item in second_page["cases"]]
        assert second_ids == [oldest_case_id]
        assert not set(first_ids).intersection(second_ids)
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


def test_case_list_exact_identity_filters_before_keyset_pagination(tmp_path):
    tenant = set_current_tenant_user_id(OWNER_SCOPE)
    try:
        _repository, service = _service(tmp_path)
        states = (
            "DRAFT", "AWAITING_EVIDENCE", "READY_TO_CONFIRM", "APPLIED", "CANCELLED",
        )
        identities = [
            (IDENTITY["product_id"], IDENTITY["offer_id"], "target", 21),
            ("product-other", "offer-other", "other", 25),
        ]
        created_index = 0
        for product_id, offer_id, prefix, count in identities:
            for index in range(count):
                created_index += 1
                case_id = f"case_exact_{prefix}_{index:03d}"
                created_at = f"2026-11-01T00:{created_index:02d}:00Z"
                created = service.create_case(
                    case=_case(
                        case_id=case_id,
                        product_id=product_id,
                        offer_id=offer_id,
                        created_at=created_at,
                    ),
                    idempotency_key=f"exact-create-{prefix}-{index:03d}",
                )
                assert created["error"] is False, created
                cancelled = service.cancel_case(
                    case_id=case_id,
                    store_id=IDENTITY["store_id"],
                    product_id=product_id,
                    offer_id=offer_id,
                    sku=IDENTITY["sku"],
                    expected_revision=1,
                    idempotency_key=f"exact-cancel-{prefix}-{index:03d}",
                )
                assert cancelled["error"] is False, cancelled

        first = service.list_cases(
            store_id=IDENTITY["store_id"],
            sku=IDENTITY["sku"],
            identity=IDENTITY,
            states=states,
            limit=20,
        )
        assert first["error"] is False, first
        assert first["count"] == 21
        assert first["has_more"] is True
        assert len(first["cases"]) == 20
        assert all(
            item["case"]["metadata"]["scope"]["product_id"] == IDENTITY["product_id"]
            and item["case"]["metadata"]["scope"]["offer_id"] == IDENTITY["offer_id"]
            for item in first["cases"]
        )

        second = service.list_cases(
            store_id=IDENTITY["store_id"],
            sku=IDENTITY["sku"],
            identity=IDENTITY,
            states=states,
            limit=20,
            after_cursor=first["next_cursor"],
            snapshot_cursor=first["snapshot_cursor"],
        )
        assert second["error"] is False, second
        assert second["count"] == 21
        assert second["has_more"] is False
        assert len(second["cases"]) == 1
        assert second["cases"][0]["case_id"] == "case_exact_target_000"
        assert second["cases"][0]["case"]["metadata"]["scope"]["product_id"] == IDENTITY["product_id"]
    finally:
        reset_current_tenant_user_id(tenant)
