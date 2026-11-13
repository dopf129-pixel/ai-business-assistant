from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from test_fifo_cost_cutoff_bridge_service import (
    CASE_ID,
    COMPLETE_THROUGH,
    SCOPE,
    _build as build_cutoff_bridge,
    _confirmation,
    _document_payload,
    _finance_batch,
    _movement_coverage,
    _proposal,
    _stock_report as _base_stock_report,
)
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    TransitionState,
    source_fingerprint,
)
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)
from test_fifo_cost_transition_store import _case


OWNER = SCOPE.owner_id
STORE = SCOPE.store_id
TENANT = make_store_tenant_scope(OWNER, STORE)
TAX_POLICY = "a" * 64
CUTOFF = "2026-11-06"


def _stock_report():
    report = _base_stock_report(cutoff=CUTOFF)
    fields = dict(report.normalized_fields)
    buckets = dict(fields["stock_buckets"])
    buckets.update({"available": 103, "reserved": 0, "preparing": 0, "checking": 0})
    fields["stock_buckets"] = buckets
    fields["fbs_return_available_units"] = 0
    fields["fbs_return_is_subset_of_available"] = True
    return replace(
        report,
        file_sha256=source_fingerprint("atomic-initial-stock-three"),
        normalized_fields=fields,
    )


def _turnover_report():
    case_metadata = _case().metadata
    return ReportEvidence(
        metadata=replace(
            case_metadata,
            scope=SCOPE,
            source_kind=EvidenceSourceKind.OWNER_IMPORTED,
            completeness=EvidenceCompleteness.COMPLETE,
            source_fingerprint=source_fingerprint("atomic-turnover-metadata"),
        ),
        report_type=ReportType.TURNOVER,
        period_from="2026-11-04",
        period_to="2026-11-05",
        period_provenance=PeriodProvenance.OWNER_CONFIRMED,
        captured_at="2026-11-08T12:00:00Z",
        file_sha256=source_fingerprint("atomic-turnover-file"),
        parser_version="atomic-test-v1",
        cell_references=("A1", "A2"),
        normalized_fields={
            "opening": 103, "receipts": 0, "redeemed": 0,
            "withdrawals": 0, "closing": 103,
        },
    )


def _bridge_inputs(case, stock, post_cutoff_sales=None, complete_through=COMPLETE_THROUGH):
    from test_fifo_cost_cutoff_bridge_service import _document as parse_document

    sales = post_cutoff_sales or [{
        "posting_number": "posting-after",
        "finance_sku": SCOPE.sku,
        "quantity": 5,
        "physical_effective_date": "2026-11-08",
    }]
    rows = [{
        "posting_number": "posting-before", "finance_sku": SCOPE.sku,
        "quantity": 2, "physical_effective_date": "2026-11-05",
        "row_reference": "A17",
    }]
    rows.extend({
        **sale,
        "row_reference": f"A{18 + index}",
    } for index, sale in enumerate(sales))
    document = parse_document(
        payload=_document_payload(rows=rows, period_to=complete_through),
        scope=SCOPE, case_id=CASE_ID,
    )
    finance_rows = [
        {"order": {"posting_number": row["posting_number"]}, "item": {
            "sku": SCOPE.sku, "offer_id": SCOPE.offer_id,
            "product_id": SCOPE.product_id,
        }}
        for row in rows
    ]
    proposal = _proposal(case=case, stock=stock, cutoff=CUTOFF)
    return build_cutoff_bridge(
        case=case,
        stock_evidence=stock,
        proposal=proposal,
        finance_batch=_finance_batch(
            response={"error": False, "rows": finance_rows},
            period_to=complete_through,
        ),
        physical_sale_document=document,
        owner_confirmation=_confirmation(document),
        movement_coverage=_movement_coverage(complete_through=complete_through),
        requested_complete_through=complete_through,
    )


def _impact(before, after):
    material = {
        "complete": True,
        "read_only": True,
        "candidate_only": False,
        "tax_policy_fingerprint": TAX_POLICY,
        "complete_through": COMPLETE_THROUGH,
        "related_return_count": 0,
        "non_sale_outflow_count": 0,
        "periods": [{
            "period": "2026-11",
            "completeness": "COMPLETE",
            "before_sku_cogs_rub": before,
            "after_sku_cogs_rub": after,
        }],
    }
    return {
        **material,
        "error": False,
        "code": "FIFO_LATE_ENTRY_IMPACT_READY",
        "preview_fingerprint": FifoCostRepository._sha256(material),
    }


def _open_case(repository, stock):
    case = _case(CASE_ID, sku=SCOPE.sku, owner=OWNER, store=STORE)
    case = replace(case, metadata=replace(case.metadata, scope=SCOPE))
    assert repository.save_transition_case(
        case=case, expected_revision=0, idempotency_key="case-create-atomic-1",
    )["error"] is False
    assert repository.append_report_evidence(
        case_id=CASE_ID, report=stock, expected_case_revision=1,
        idempotency_key="stock-evidence-atomic-1",
    )["case_revision"] == 2
    assert repository.append_report_evidence(
        case_id=CASE_ID, report=_turnover_report(), expected_case_revision=2,
        idempotency_key="turnover-evidence-atomic-1",
    )["case_revision"] == 3
    case_for_bridge = replace(
        case, case_revision=3, state=TransitionState.AWAITING_EVIDENCE,
    )
    return case_for_bridge


def _initial_cutover(stock):
    return {
        "schema_version": 1,
        "case_id": CASE_ID,
        "case_revision": 3,
        "cutoff_date": CUTOFF,
        "stock_report_fingerprint": stock.file_sha256,
        "layers": [
            {
                "sequence": 1, "unit_cost_rub": "21.00",
                "ozon_units": 3, "transit_units": 0, "home_units": 0,
            },
            {
                "sequence": 2, "unit_cost_rub": "14.65",
                "ozon_units": 100, "transit_units": 0, "home_units": 0,
            },
        ],
        "ozon_units_include_reserved_confirmed": True,
        "transit_not_in_ozon_confirmed": True,
    }


def _prepared_repository(
    tmp_path, *, db_path=None, post_cutoff_sales=None,
    complete_through=COMPLETE_THROUGH,
):
    clock = [datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)]
    repository = FifoCostRepository(
        db_path=db_path or tmp_path / "transition-atomic.sqlite",
        now_provider=lambda: clock[0],
    )
    tenant = set_current_tenant_user_id(TENANT)
    stock = _stock_report()
    case = _open_case(repository, stock)
    bridge = _bridge_inputs(
        case, stock, post_cutoff_sales=post_cutoff_sales,
        complete_through=complete_through,
    )
    assert bridge.status == "READY"
    sale_units = sum(
        item["quantity"] for item in (post_cutoff_sales or [{"quantity": 5}])
    )
    baseline_cogs = Decimal(sale_units * 21).quantize(Decimal("0.01"))
    candidate_cogs = (
        Decimal("63.00") + Decimal(max(0, sale_units - 3)) * Decimal("14.65")
    ).quantize(Decimal("0.01"))
    impact = _impact(format(baseline_cogs, ".2f"), format(candidate_cogs, ".2f"))
    impact["complete_through"] = complete_through
    impact["preview_fingerprint"] = FifoCostRepository._sha256({
        key: value for key, value in impact.items()
        if key not in {"error", "code", "preview_fingerprint"}
    })
    cutover = _initial_cutover(stock)
    prepared = repository.prepare_transition_preview(
        case_id=CASE_ID, store_id=STORE, product_id=SCOPE.product_id,
        offer_id=SCOPE.offer_id, sku=SCOPE.sku, expected_case_revision=3,
        effective_date="2026-11-07", cutoff_bridge=bridge,
        impact_preview=impact, tax_policy_fingerprint=TAX_POLICY,
        idempotency_key="prepare-atomic-0001",
        initial_opening_cutover=cutover,
    )
    assert prepared["error"] is False, prepared
    return repository, tenant, stock, bridge, impact, cutover, prepared, clock


def _table_counts(repository):
    connection = repository.get_connection()
    try:
        tables = (
            "fifo_cost_streams", "fifo_cost_events", "fifo_cost_layers",
            "fifo_cost_commands", "fifo_cost_rate_changes",
            "fifo_cost_allocations", "fifo_cost_allocation_lines",
            "fifo_cost_transition_commits",
            "fifo_cost_cutoff_sale_mapping_sets",
            "fifo_cost_cutoff_sale_mappings",
        )
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }
    finally:
        connection.close()


def _commit(
    repository, bridge, impact, prepared, *, current_tax_policy_fingerprint=TAX_POLICY,
    impact_preview=None, idempotency_key="commit-atomic-0001",
):
    return repository.commit_transition_case(
        case_id=CASE_ID, store_id=STORE, product_id=SCOPE.product_id,
        offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        expected_case_revision=prepared["case_revision"],
        preview_id=prepared["preview_id"], idempotency_key=idempotency_key,
        cutoff_bridge=bridge, impact_preview=impact_preview or impact,
        current_tax_policy_fingerprint=current_tax_policy_fingerprint,
    )


class _FaultConnection:
    def __init__(self, connection, *, fail_at, mode):
        self._connection = connection
        self._fail_at = fail_at
        self._mode = mode
        self._writes = 0

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def execute(self, sql, *args):
        is_write = sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE"))
        if not is_write:
            return self._connection.execute(sql, *args)
        self._writes += 1
        if self._mode == "before" and self._writes == self._fail_at:
            raise sqlite3.OperationalError("injected before write")
        cursor = self._connection.execute(sql, *args)
        if self._mode == "after" and self._writes == self._fail_at:
            raise sqlite3.OperationalError("injected after write")
        return cursor


@pytest.mark.parametrize("failure_mode", ["before", "after"])
def test_commit_rolls_back_at_every_write_boundary(tmp_path, failure_mode):
    repository, tenant, _stock, bridge, impact, _cutover, prepared, _clock = _prepared_repository(tmp_path)
    try:
        baseline = _table_counts(repository)
        successful_position = None
        original_get_connection = repository.get_connection
        for fail_at in range(1, 100):
            repository.get_connection = lambda fail_at=fail_at: _FaultConnection(
                original_get_connection(), fail_at=fail_at, mode=failure_mode,
            )
            result = _commit(repository, bridge, impact, prepared)
            repository.get_connection = original_get_connection
            if result["error"] is False:
                successful_position = fail_at
                break
            assert result["code"] in {
                "FIFO_TRANSITION_STORAGE_UNAVAILABLE",
                "FIFO_CUTOFF_SALE_MAPPING_STORAGE_UNAVAILABLE",
            }
            assert _table_counts(repository) == baseline
            case = repository.read_transition_case(
                case_id=CASE_ID, store_id=STORE, product_id=SCOPE.product_id,
                offer_id=SCOPE.offer_id, sku=SCOPE.sku,
            )
            assert case["state"] == "READY_TO_CONFIRM"
        assert successful_position is not None
        assert successful_position > 1
        assert _table_counts(repository)["fifo_cost_transition_commits"] == 1
    finally:
        repository.get_connection = original_get_connection
        reset_current_tenant_user_id(tenant)


def test_new_stock_evidence_after_ready_preview_invalidates_confirmation_without_fifo_writes(
    tmp_path,
):
    repository, tenant, stock, bridge, impact, _cutover, prepared, _clock = _prepared_repository(tmp_path)
    try:
        connection = repository.get_connection()
        try:
            preview_before = tuple(connection.execute(
                """SELECT case_revision, fifo_revision, allocation_revision,
                          evidence_set_fingerprint, tax_policy_fingerprint,
                          preview_fingerprint, expires_at, payload_json
                   FROM fifo_cost_transition_previews WHERE preview_id=?""",
                (prepared["preview_id"],),
            ).fetchone())
        finally:
            connection.close()
        changed_stock = replace(
            stock,
            file_sha256=source_fingerprint("atomic-initial-stock-updated"),
        )
        appended = repository.append_report_evidence(
            case_id=CASE_ID, report=changed_stock,
            expected_case_revision=prepared["case_revision"],
            idempotency_key="stock-evidence-after-preview-1",
        )
        assert appended["error"] is False
        connection = repository.get_connection()
        try:
            preview_after = tuple(connection.execute(
                """SELECT case_revision, fifo_revision, allocation_revision,
                          evidence_set_fingerprint, tax_policy_fingerprint,
                          preview_fingerprint, expires_at, payload_json
                   FROM fifo_cost_transition_previews WHERE preview_id=?""",
                (prepared["preview_id"],),
            ).fetchone())
        finally:
            connection.close()
        assert preview_after == preview_before
        result = _commit(repository, bridge, impact, prepared)
        assert result["error"] is True
        assert result["code"] == "FIFO_TRANSITION_REVISION_CONFLICT"
        assert all(count == 0 for count in _table_counts(repository).values())
        current = repository.read_transition_case(
            case_id=CASE_ID, store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        assert current["state"] == "AWAITING_EVIDENCE"
    finally:
        reset_current_tenant_user_id(tenant)


def test_two_concurrent_confirms_apply_one_fifo_transition(tmp_path):
    repository, tenant, _stock, bridge, impact, _cutover, prepared, clock = _prepared_repository(tmp_path)
    reset_current_tenant_user_id(tenant)
    barrier = Barrier(2)

    def confirm(idempotency_key):
        request_tenant = set_current_tenant_user_id(TENANT)
        try:
            request_repository = FifoCostRepository(
                db_path=tmp_path / "transition-atomic.sqlite",
                now_provider=lambda: clock[0],
            )
            barrier.wait(timeout=5)
            return _commit(
                request_repository, bridge, impact, prepared,
                idempotency_key=idempotency_key,
            )
        finally:
            reset_current_tenant_user_id(request_tenant)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            confirm, ("commit-race-confirm-01", "commit-race-confirm-02"),
        ))

    assert sum(result["error"] is False for result in results) == 1, results
    assert sum(
        result.get("code") == "FIFO_TRANSITION_REVISION_CONFLICT"
        for result in results
    ) == 1, results
    assert _table_counts(repository) == {
        "fifo_cost_streams": 1,
        # Two owner-confirmed opening layers plus one post-cutoff sale.
        "fifo_cost_events": 3,
        "fifo_cost_layers": 2,
        "fifo_cost_commands": 1,
        "fifo_cost_rate_changes": 1,
        "fifo_cost_allocations": 1,
        "fifo_cost_allocation_lines": 2,
        "fifo_cost_transition_commits": 1,
        "fifo_cost_cutoff_sale_mapping_sets": 1,
        "fifo_cost_cutoff_sale_mappings": 2,
    }
    verification_tenant = set_current_tenant_user_id(TENANT)
    try:
        applied = repository.read_transition_case(
            case_id=CASE_ID, store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        assert applied["state"] == "APPLIED"
        assert applied["case_revision"] == prepared["case_revision"] + 1
    finally:
        reset_current_tenant_user_id(verification_tenant)


def test_changed_tax_stock_bridge_and_return_coverage_never_partially_apply(tmp_path):
    repository, tenant, _stock, bridge, impact, _cutover, prepared, _clock = _prepared_repository(tmp_path)
    try:
        changed_stock = replace(
            bridge,
            confirmed_stock_buckets={
                **dict(bridge.confirmed_stock_buckets), "available": 4,
            },
        )
        changed_returns = replace(
            bridge, linked_returns_non_sale_movements=(object(),),
        )
        attempts = (
            (_commit(repository, bridge, impact, prepared,
                     current_tax_policy_fingerprint="b" * 64), "FIFO_TRANSITION_PREVIEW_STALE"),
            (_commit(repository, replace(bridge, source_set_fingerprint="b" * 64), impact, prepared),
             "FIFO_TRANSITION_PREVIEW_STALE"),
            (_commit(repository, changed_stock, impact, prepared),
             "FIFO_TRANSITION_PREVIEW_STALE"),
            (_commit(repository, changed_returns, impact, prepared),
             "FIFO_TRANSITION_MOVEMENT_BRIDGE_MISMATCH"),
        )
        for result, expected_code in attempts:
            assert result["error"] is True
            assert result["code"] == expected_code
            assert all(count == 0 for count in _table_counts(repository).values())
            current = repository.read_transition_case(
                case_id=CASE_ID, store_id=STORE, product_id=SCOPE.product_id,
                offer_id=SCOPE.offer_id, sku=SCOPE.sku,
            )
            assert current["state"] == "READY_TO_CONFIRM"
    finally:
        reset_current_tenant_user_id(tenant)


def test_transition_bridge_ledger_requires_exact_linked_return_event():
    from services.fifo_cost_cutoff_bridge_service import FifoCutoffMovementReference

    base = build_cutoff_bridge()
    sale = base.post_cutoff_events[0]
    movement = FifoCutoffMovementReference(
        movement_kind="RETURN",
        movement_fingerprint=source_fingerprint("atomic-linked-return"),
        source_identity_digest=source_fingerprint("atomic-linked-return-id"),
        linked_sale_identity_digest=sale.source_identity_digest,
        quantity=1,
        effective_date="2026-11-09",
    )
    bridge = replace(
        base, complete_through="2026-11-09",
        linked_returns_non_sale_movements=(movement,),
    )
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("""CREATE TABLE fifo_cost_events (
            event_id TEXT, stream_id TEXT, event_kind TEXT,
            source_identity_digest TEXT, quantity INTEGER, effective_date TEXT,
            supersedes_event_id TEXT, reason_code TEXT
        )""")
        connection.execute(
            """INSERT INTO fifo_cost_events VALUES
               ('sale-event-1', 'stream-1', 'PHYSICAL_SALE', ?, ?, ?, NULL, NULL)""",
            (sale.source_identity_digest, sale.quantity, sale.physical_effective_date),
        )

        assert FifoCostRepository._validate_transition_bridge_ledger(
            connection, "stream-1", bridge,
        ) == "FIFO_TRANSITION_MOVEMENT_BRIDGE_MISMATCH"

        connection.execute(
            """INSERT INTO fifo_cost_events VALUES
               ('return-event-1', 'stream-1', 'SALEABLE_RETURN_RESTOCK', ?, ?, ?,
                'sale-event-1', NULL)""",
            (movement.source_identity_digest, movement.quantity, movement.effective_date),
        )
        assert FifoCostRepository._validate_transition_bridge_ledger(
            connection, "stream-1", bridge,
        ) is None

        connection.execute(
            "UPDATE fifo_cost_events SET quantity=2 WHERE event_id='return-event-1'",
        )
        assert FifoCostRepository._validate_transition_bridge_ledger(
            connection, "stream-1", bridge,
        ) == "FIFO_TRANSITION_MOVEMENT_BRIDGE_MISMATCH"
    finally:
        connection.close()


def test_transition_bridge_ledger_rejects_return_without_proven_causal_order():
    from services.fifo_cost_cutoff_bridge_service import FifoCutoffMovementReference

    base = build_cutoff_bridge()
    sale = base.post_cutoff_events[0]
    movement = FifoCutoffMovementReference(
        movement_kind="RETURN",
        movement_fingerprint=source_fingerprint("atomic-same-day-return"),
        source_identity_digest=source_fingerprint("atomic-same-day-return-id"),
        linked_sale_identity_digest=sale.source_identity_digest,
        quantity=1,
        effective_date=sale.physical_effective_date,
    )
    bridge = replace(base, linked_returns_non_sale_movements=(movement,))
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("""CREATE TABLE fifo_cost_events (
            event_id TEXT, stream_id TEXT, event_kind TEXT,
            source_identity_digest TEXT, quantity INTEGER, effective_date TEXT,
            supersedes_event_id TEXT, reason_code TEXT
        )""")
        connection.execute(
            """INSERT INTO fifo_cost_events VALUES
               ('sale-event-1', 'stream-1', 'PHYSICAL_SALE', ?, ?, ?, NULL, NULL)""",
            (sale.source_identity_digest, sale.quantity, sale.physical_effective_date),
        )
        assert FifoCostRepository._validate_transition_bridge_ledger(
            connection, "stream-1", bridge,
        ) == "FIFO_TRANSITION_MOVEMENT_ORDER_UNRESOLVED"
    finally:
        connection.close()


def test_ordinary_fifo_rate_change_remains_available_after_one_late_transition(tmp_path):
    from services.fifo_cost_rate_service import FifoCostRateService
    from services.fifo_cost_source_normalizer import FifoStockSnapshot

    repository, tenant, _stock, bridge, impact, _cutover, prepared, clock = (
        _prepared_repository(tmp_path, complete_through="2026-11-10")
    )
    try:
        applied = _commit(repository, bridge, impact, prepared)
        assert applied["error"] is False, applied
        history = repository.read_cost_history_snapshot(
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        assert history["error"] is False
        assert len(history["rates"]) == 1

        repository._now_provider = lambda: datetime(
            2026, 11, 10, 12, tzinfo=timezone.utc,
        )
        stock = FifoStockSnapshot(
            status="COMPLETE", source_status="COMPLETE",
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
            captured_at="2026-11-10T12:00:00Z", source_as_of=None,
            pagination_complete=True, pages_read=1, total_items=1,
            fbo_units=98, reserved_units=0, available_units=98,
            transit_units=0, transit_status="DISJOINT_CONFIRMED",
            source_fingerprint="e" * 64, issue_codes=(), anchor_eligible=False,
        )
        rate_service = FifoCostRateService(repository)
        next_preview = rate_service.preview_new_cost(
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
            effective_date="2026-11-10", unit_cost_rub="9.50",
            cost_input_mode="TOTAL_LANDED", old_home_units=0,
            expected_revision=history["revision"], stock_snapshot=stock,
            owner_confirms_reconciliation_scope=True,
        )
        assert next_preview["error"] is False, next_preview
        committed = rate_service.confirm_new_cost(
            preview_id=next_preview["preview_id"],
            active_preview_id=next_preview["preview_id"],
            idempotency_key="post-late-ordinary-rate-001",
        )
        assert committed["error"] is False, committed
        updated = repository.read_cost_history_snapshot(
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        assert [item["unit_cost_rub"] for item in updated["rates"]] == [
            "14.65", "9.50",
        ]
    finally:
        reset_current_tenant_user_id(tenant)


def test_fr09_replays_three_rates_from_prefix_and_publishes_atomically(
    tmp_path, monkeypatch,
):
    from services.fifo_cost_rate_service import FifoCostRateService
    from services.fifo_cost_source_normalizer import FifoStockSnapshot

    sales = [
        {"posting_number": "mr01-sale", "finance_sku": SCOPE.sku,
         "quantity": 5, "physical_effective_date": "2026-11-08"},
        {"posting_number": "mr02-sale", "finance_sku": SCOPE.sku,
         "quantity": 110, "physical_effective_date": "2026-11-10"},
        {"posting_number": "mr03-sale", "finance_sku": SCOPE.sku,
         "quantity": 10, "physical_effective_date": "2026-11-12"},
    ]
    repository, tenant, _stock, bridge, impact, _cutover, prepared, _clock = (
        _prepared_repository(
            tmp_path, post_cutoff_sales=sales, complete_through="2026-11-12",
        )
    )
    try:
        applied = _commit(repository, bridge, impact, prepared)
        assert applied["error"] is False, applied
        history = repository.read_cost_history_snapshot(
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        assert history["error"] is False
        assert history["latest_allocation"]["replayed_remaining_layers"] is not None

        rate_service = FifoCostRateService(repository)
        stock_r2 = FifoStockSnapshot(
            status="COMPLETE", source_status="COMPLETE",
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
            captured_at="2026-11-09T12:00:00Z", source_as_of=None,
            pagination_complete=True, pages_read=1, total_items=1,
            fbo_units=108, reserved_units=0, available_units=108,
            transit_units=0, transit_status="DISJOINT_CONFIRMED",
            source_fingerprint="b" * 64, issue_codes=(), anchor_eligible=False,
        )
        r2_preview = rate_service.preview_new_cost(
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
            effective_date="2026-11-09", unit_cost_rub="16.00",
            cost_input_mode="TOTAL_LANDED", old_home_units=0,
            expected_revision=history["revision"], stock_snapshot=stock_r2,
            owner_confirms_reconciliation_scope=True,
        )
        assert r2_preview["error"] is False, r2_preview
        assert r2_preview["rate_reconciliation"]["older_finite_units"] == 98
        assert r2_preview["rate_reconciliation"]["prior_rate_units"] == 10
        before_failed_commit = repository.read_cost_history_snapshot(
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        persist_allocation = repository._persist_allocation_revision_rows

        def persist_then_fail(*args, **kwargs):
            persist_allocation(*args, **kwargs)
            raise ValueError("FIFO_RATE_BALANCE_MISMATCH")

        with monkeypatch.context() as patcher:
            patcher.setattr(
                repository, "_persist_allocation_revision_rows", persist_then_fail,
            )
            failed_commit = rate_service.confirm_new_cost(
                preview_id=r2_preview["preview_id"],
                active_preview_id=r2_preview["preview_id"],
                idempotency_key="mr-public-rate-two-001",
            )
        assert failed_commit == {
            "error": True, "code": "FIFO_RATE_BALANCE_MISMATCH",
        }
        after_failed_commit = repository.read_cost_history_snapshot(
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        assert after_failed_commit["revision"] == before_failed_commit["revision"]
        assert after_failed_commit["rates"] == before_failed_commit["rates"]
        assert after_failed_commit["rate_reconciliations"] == before_failed_commit[
            "rate_reconciliations"
        ]
        assert after_failed_commit["projection"] == before_failed_commit["projection"]
        assert after_failed_commit["latest_allocation"]["revision"] == (
            before_failed_commit["latest_allocation"]["revision"]
        )

        r2_commit = rate_service.confirm_new_cost(
            preview_id=r2_preview["preview_id"],
            active_preview_id=r2_preview["preview_id"],
            idempotency_key="mr-public-rate-two-001",
        )
        assert r2_commit["error"] is False, r2_commit
        after_r2 = FifoCostRepository(
            db_path=tmp_path / "transition-atomic.sqlite",
        ).read_cost_history_snapshot(
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        assert after_r2["projection"]["queue_complete"] is True
        assert after_r2["latest_allocation"]["stale"] is False
        assert after_r2["latest_allocation"]["stream_revision"] == after_r2["revision"]
        assert after_r2["latest_allocation"]["replayed_rate_balances"][-1][
            "remaining_units"
        ] is None

        stock_r3 = replace(
            stock_r2, captured_at="2026-11-11T12:00:00Z",
            fbo_units=7, available_units=7, source_fingerprint="c" * 64,
        )
        r3_preview = rate_service.preview_new_cost(
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
            effective_date="2026-11-11", unit_cost_rub="18.00",
            cost_input_mode="TOTAL_LANDED", old_home_units=0,
            expected_revision=after_r2["revision"], stock_snapshot=stock_r3,
            owner_confirms_reconciliation_scope=True,
        )
        assert r3_preview["error"] is False, r3_preview
        assert r3_preview["rate_reconciliation"]["older_finite_units"] == 0
        assert r3_preview["rate_reconciliation"]["prior_rate_units"] == 7
        r3_commit = rate_service.confirm_new_cost(
            preview_id=r3_preview["preview_id"],
            active_preview_id=r3_preview["preview_id"],
            idempotency_key="mr-public-rate-three-001",
        )
        assert r3_commit["error"] is False, r3_commit

        final_repository = FifoCostRepository(
            db_path=tmp_path / "transition-atomic.sqlite",
        )
        final_history = final_repository.read_cost_history_snapshot(
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        assert [row["unit_cost_rub"] for row in final_history["rates"]] == [
            "14.65", "16.00", "18.00",
        ]
        assert [
            (row["older_finite_units"], row["prior_rate_units"])
            for row in final_history["rate_reconciliations"]
        ] == [(98, 10), (0, 7)]
        assert final_history["projection"]["queue_complete"] is True
        assert final_history["latest_allocation"]["stale"] is False
        assert final_history["latest_allocation"]["stream_revision"] == final_history["revision"]
        assert [row["remaining_units"] for row in final_history[
            "latest_allocation"]["replayed_rate_balances"]] == [0, 0, None]

        connection = final_repository.get_connection()
        try:
            stream_id = connection.execute(
                "SELECT stream_id FROM fifo_cost_streams WHERE store_id=?",
                (STORE,),
            ).fetchone()[0]
            allocation_id = connection.execute(
                "SELECT allocation_id FROM fifo_cost_allocations "
                "WHERE stream_id=? ORDER BY revision DESC LIMIT 1",
                (stream_id,),
            ).fetchone()[0]
            cogs_by_day = connection.execute(
                """SELECT e.effective_date, lines.total_cost_rub
                   FROM (
                       SELECT allocation_id, event_id, total_cost_rub
                       FROM fifo_cost_allocation_lines
                       UNION ALL
                       SELECT allocation_id, event_id, total_cost_rub
                       FROM fifo_cost_allocation_rate_lines
                   ) AS lines
                   JOIN fifo_cost_events AS e ON e.event_id=lines.event_id
                   WHERE lines.allocation_id=? AND e.event_kind='PHYSICAL_SALE'
                   ORDER BY e.effective_date, e.event_id, lines.total_cost_rub""",
                (allocation_id,),
            ).fetchall()
        finally:
            connection.close()
        by_day = {}
        for effective_date, amount in cogs_by_day:
            by_day[effective_date] = by_day.get(
                effective_date, Decimal("0.00"),
            ) + Decimal(amount)
        assert [
            (day, format(amount, ".2f")) for day, amount in by_day.items()
        ] == [
            ("2026-11-08", "92.30"),
            ("2026-11-10", "1614.20"),
            ("2026-11-12", "166.00"),
        ]
        assert sum(Decimal(row[1]) for row in cogs_by_day) == Decimal("1872.50")
    finally:
        reset_current_tenant_user_id(tenant)


def test_fr09_rejects_stock_drop_without_a_complete_movement_bridge(tmp_path):
    from services.fifo_cost_rate_service import FifoCostRateService
    from services.fifo_cost_source_normalizer import FifoStockSnapshot

    repository, tenant, _stock, bridge, impact, _cutover, prepared, _clock = (
        _prepared_repository(tmp_path, complete_through="2026-11-12")
    )
    try:
        applied = _commit(repository, bridge, impact, prepared)
        assert applied["error"] is False, applied
        history = repository.read_cost_history_snapshot(
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        rate_service = FifoCostRateService(repository)
        stock = FifoStockSnapshot(
            status="COMPLETE", source_status="COMPLETE",
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
            captured_at="2026-11-09T12:00:00Z", source_as_of=None,
            pagination_complete=True, pages_read=1, total_items=1,
            fbo_units=108, reserved_units=0, available_units=108,
            transit_units=0, transit_status="DISJOINT_CONFIRMED",
            source_fingerprint="d" * 64, issue_codes=(), anchor_eligible=False,
        )
        r2 = rate_service.preview_new_cost(
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
            effective_date="2026-11-09", unit_cost_rub="16.00",
            cost_input_mode="TOTAL_LANDED", old_home_units=0,
            expected_revision=history["revision"], stock_snapshot=stock,
            owner_confirms_reconciliation_scope=True,
        )
        assert r2["error"] is False, r2
        r2_commit = rate_service.confirm_new_cost(
            preview_id=r2["preview_id"], active_preview_id=r2["preview_id"],
            idempotency_key="mr-unexplained-rate-two-001",
        )
        assert r2_commit["error"] is False, r2_commit
        after_r2 = repository.read_cost_history_snapshot(
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )

        lower_stock = replace(
            stock, captured_at="2026-11-11T12:00:00Z",
            fbo_units=7, available_units=7, source_fingerprint="e" * 64,
        )
        r3 = rate_service.preview_new_cost(
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
            effective_date="2026-11-11", unit_cost_rub="18.00",
            cost_input_mode="TOTAL_LANDED", old_home_units=0,
            expected_revision=after_r2["revision"], stock_snapshot=lower_stock,
            owner_confirms_reconciliation_scope=True,
        )
        assert r3 == {
            "error": True, "code": "FIFO_RATE_STOCK_DISCREPANCY",
        }
        unchanged = repository.read_cost_history_snapshot(
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        assert unchanged["revision"] == after_r2["revision"]
        assert len(unchanged["rates"]) == 2
    finally:
        reset_current_tenant_user_id(tenant)


def test_uninitialized_fifo_preview_is_read_only_and_atomic_cutover_applies_once(
    tmp_path,
):
    repository, tenant, stock, bridge, impact, cutover, prepared, clock = _prepared_repository(tmp_path)
    try:
        assert prepared["candidate_cogs_rub"] == "92.30"
        assert all(count == 0 for count in _table_counts(repository).values())
        retry = repository.prepare_transition_preview(
            case_id=CASE_ID, store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku, expected_case_revision=3,
            effective_date="2026-11-07", cutoff_bridge=bridge,
            impact_preview=impact, tax_policy_fingerprint=TAX_POLICY,
            idempotency_key="prepare-atomic-0001",
            initial_opening_cutover=cutover,
        )
        assert retry["error"] is False
        assert retry["preview_id"] == prepared["preview_id"]
        assert retry["replayed"] is True
        changed_impact = _impact("105.00", "92.30")
        changed_impact["periods"][0]["period"] = "2026-10"
        material = {
            key: value for key, value in changed_impact.items()
            if key not in {"error", "code", "preview_fingerprint"}
        }
        changed_impact["preview_fingerprint"] = FifoCostRepository._sha256(material)
        conflict = repository.prepare_transition_preview(
            case_id=CASE_ID, store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku, expected_case_revision=3,
            effective_date="2026-11-07", cutoff_bridge=bridge,
            impact_preview=changed_impact, tax_policy_fingerprint=TAX_POLICY,
            idempotency_key="prepare-atomic-0001",
            initial_opening_cutover=cutover,
        )
        assert conflict["code"] == "FIFO_TRANSITION_IDEMPOTENCY_CONFLICT"

        result = _commit(repository, bridge, impact, prepared)
        assert result["error"] is False, result
        assert result["replayed"] is False
        applied = repository.read_transition_case(
            case_id=CASE_ID, store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        assert applied["state"] == "APPLIED"
        applied_case = replace(
            _case(CASE_ID, sku=SCOPE.sku, owner=OWNER, store=STORE),
            metadata=replace(
                _case(CASE_ID, sku=SCOPE.sku, owner=OWNER, store=STORE).metadata,
                scope=SCOPE,
            ),
            case_revision=applied["case_revision"],
            state=TransitionState.APPLIED,
            updated_at="2026-11-08T12:00:00Z",
        )
        attempted_overwrite = replace(
            applied_case, case_revision=applied["case_revision"] + 1,
            state=TransitionState.AWAITING_EVIDENCE,
            new_unit_cost_rub="15.00",
            updated_at="2026-11-08T12:01:00Z",
        )
        rejected_overwrite = repository.save_transition_case(
            case=attempted_overwrite,
            expected_revision=applied["case_revision"],
            idempotency_key="applied-case-overwrite-01",
        )
        assert rejected_overwrite["code"] == "FIFO_TRANSITION_CASE_NOT_READY"
        correction = replace(
            applied_case, case_id="transition-correction-0001", case_revision=1,
            state=TransitionState.DRAFT,
            created_at="2026-11-08T12:02:00Z",
            updated_at="2026-11-08T12:02:00Z",
            supersedes_case_id=CASE_ID,
        )
        correction_saved = repository.save_transition_case(
            case=correction, expected_revision=0,
            idempotency_key="applied-case-correction-01",
        )
        assert correction_saved["error"] is False, correction_saved
        assert repository.read_transition_case(
            case_id=CASE_ID, store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )["state"] == "APPLIED"
        assert _table_counts(repository)["fifo_cost_allocations"] == 1
        assert _table_counts(repository)["fifo_cost_rate_changes"] == 1
        mapping = repository.read_cutoff_sale_mapping_set(
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        assert mapping["error"] is False
        assert mapping["complete"] is True
        assert mapping["mapping_revision"] == 1
        assert mapping["cutoff_date"] == CUTOFF
        assert mapping["complete_through"] == COMPLETE_THROUGH
        assert sorted(
            (row["partition"], row["quantity"], row["physical_effective_date"])
            for row in mapping["mappings"]
        ) == [
            ("POST_CUTOFF", 5, "2026-11-08"),
            ("PRE_CUTOFF", 2, "2026-11-05"),
        ]
        connection = repository.get_connection()
        try:
            for table in (
                "fifo_cost_cutoff_sale_mapping_sets",
                "fifo_cost_cutoff_sale_mappings",
            ):
                for operation in ("UPDATE", "DELETE"):
                    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                        if operation == "UPDATE":
                            column = (
                                "created_at" if table.endswith("_sets")
                                else "quantity"
                            )
                            connection.execute(
                                f"UPDATE {table} SET {column}={column}"
                            )
                        else:
                            connection.execute(f"DELETE FROM {table}")
        finally:
            connection.close()
        snapshot = repository.read_cost_history_snapshot(
            store_id=STORE, product_id=SCOPE.product_id,
            offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        assert snapshot["projection"]["known_quantity"] == 98
        assert snapshot["projection"]["known_cost_rub"] == "1435.70"
        assert snapshot["projection"]["next_unit_cost_rub"] == "14.65"
        remaining_layers = snapshot["latest_allocation"]["replayed_remaining_layers"]
        assert sum(layer["remaining_units"] for layer in remaining_layers) == 98
        assert sum(
            Decimal(layer["unit_cost_rub"]) * layer["remaining_units"]
            for layer in remaining_layers
        ) == Decimal("1435.70")

        clock[0] += timedelta(hours=2)
        replay = _commit(
            repository, bridge, impact, prepared,
            current_tax_policy_fingerprint="b" * 64,
        )
        assert replay["error"] is False
        assert replay["replayed"] is True
        assert replay["commit_id"] == result["commit_id"]
        assert _table_counts(repository)["fifo_cost_allocations"] == 1
        assert _table_counts(repository)["fifo_cost_transition_commits"] == 1

        changed_payload = _commit(
            repository, bridge, impact, prepared,
            impact_preview=_impact("105.00", "91.00"),
        )
        assert changed_payload["error"] is True
        assert changed_payload["code"] == "FIFO_TRANSITION_IDEMPOTENCY_CONFLICT"
        assert _table_counts(repository)["fifo_cost_allocations"] == 1
        assert _table_counts(repository)["fifo_cost_transition_commits"] == 1
    finally:
        reset_current_tenant_user_id(tenant)


@pytest.mark.parametrize(
    "field,value",
    [
        ("fbs_return_is_subset_of_available", None),
        ("fbs_return_available_units", None),
        ("fbs_return_available_units", 1),
    ],
)
def test_initial_cutover_fails_closed_when_return_overlap_is_unproven(
    tmp_path, field, value,
):
    repository = FifoCostRepository(db_path=tmp_path / "return-overlap.sqlite")
    tenant = set_current_tenant_user_id(TENANT)
    try:
        stock = _stock_report()
        fields = dict(stock.normalized_fields)
        fields[field] = value
        altered = replace(stock, file_sha256=source_fingerprint(f"stock-{field}-{value}"), normalized_fields=fields)
        case = _open_case(repository, altered)
        bridge = _bridge_inputs(case, altered)
        connection = repository.get_connection()
        try:
            result = repository._normalize_transition_initial_cutover(
                connection, _initial_cutover(altered), bridge,
                {
                    "old_unit_cost_rub": case.old_unit_cost_rub,
                    "new_unit_cost_rub": case.new_unit_cost_rub,
                    "owner_old_home_units": case.owner_old_home_units,
                    "owner_old_transit_units": case.owner_old_transit_units,
                },
                recorded_at="2026-11-08T12:00:00+00:00",
            )
        finally:
            connection.close()
        assert result == "FIFO_INITIAL_CUTOVER_RETURN_BASIS_UNAVAILABLE"
    finally:
        reset_current_tenant_user_id(tenant)


@pytest.mark.parametrize(
    "layers,expected_code",
    [
        (
            [
                {"sequence": 1, "unit_cost_rub": "22.00", "ozon_units": 3,
                 "transit_units": 0, "home_units": 0},
                {"sequence": 2, "unit_cost_rub": "14.65", "ozon_units": 100,
                 "transit_units": 0, "home_units": 0},
            ],
            "FIFO_INITIAL_CUTOVER_COST_MISMATCH",
        ),
        (
            [
                {"sequence": 1, "unit_cost_rub": "14.65", "ozon_units": 100,
                 "transit_units": 0, "home_units": 0},
                {"sequence": 2, "unit_cost_rub": "21.00", "ozon_units": 3,
                 "transit_units": 0, "home_units": 0},
            ],
            "FIFO_INITIAL_CUTOVER_LAYER_ORDER_CONFLICT",
        ),
    ],
)
def test_initial_cutover_rejects_unrelated_or_reversed_cost_layers(
    tmp_path, layers, expected_code,
):
    repository = FifoCostRepository(db_path=tmp_path / "layer-costs.sqlite")
    tenant = set_current_tenant_user_id(TENANT)
    try:
        stock = _stock_report()
        case = _open_case(repository, stock)
        bridge = _bridge_inputs(case, stock)
        cutover = _initial_cutover(stock)
        cutover["layers"] = layers
        connection = repository.get_connection()
        try:
            result = repository._normalize_transition_initial_cutover(
                connection, cutover, bridge,
                {
                    "old_unit_cost_rub": case.old_unit_cost_rub,
                    "new_unit_cost_rub": case.new_unit_cost_rub,
                    "owner_old_home_units": case.owner_old_home_units,
                    "owner_old_transit_units": case.owner_old_transit_units,
                },
                recorded_at="2026-11-08T12:00:00+00:00",
            )
        finally:
            connection.close()
        assert result == expected_code
    finally:
        reset_current_tenant_user_id(tenant)

