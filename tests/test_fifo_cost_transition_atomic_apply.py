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


def _bridge_inputs(case, stock):
    from test_fifo_cost_cutoff_bridge_service import _document as parse_document

    document = parse_document(payload=_document_payload(rows=[
        {
            "posting_number": "posting-before", "finance_sku": SCOPE.sku,
            "quantity": 2, "physical_effective_date": "2026-11-05",
            "row_reference": "A17",
        },
        {
            "posting_number": "posting-after", "finance_sku": SCOPE.sku,
            "quantity": 5, "physical_effective_date": "2026-11-08",
            "row_reference": "A18",
        },
    ]), scope=SCOPE, case_id=CASE_ID)
    proposal = _proposal(case=case, stock=stock, cutoff=CUTOFF)
    return build_cutoff_bridge(
        case=case,
        stock_evidence=stock,
        proposal=proposal,
        physical_sale_document=document,
        owner_confirmation=_confirmation(document),
        requested_complete_through=COMPLETE_THROUGH,
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


def _prepared_repository(tmp_path):
    clock = [datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)]
    repository = FifoCostRepository(
        db_path=tmp_path / "transition-atomic.sqlite",
        now_provider=lambda: clock[0],
    )
    tenant = set_current_tenant_user_id(TENANT)
    stock = _stock_report()
    case = _open_case(repository, stock)
    bridge = _bridge_inputs(case, stock)
    assert bridge.status == "READY"
    impact = _impact("105.00", "92.30")
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
    repository, tenant, _stock, bridge, impact, _cutover, prepared, _clock = _prepared_repository(tmp_path)
    reset_current_tenant_user_id(tenant)
    barrier = Barrier(2)

    def confirm(idempotency_key):
        request_tenant = set_current_tenant_user_id(TENANT)
        try:
            request_repository = FifoCostRepository(
                db_path=tmp_path / "transition-atomic.sqlite",
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

    assert sum(result["error"] is False for result in results) == 1
    assert sum(
        result.get("code") == "FIFO_TRANSITION_REVISION_CONFLICT"
        for result in results
    ) == 1
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

