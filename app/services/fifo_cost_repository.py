"""Tenant-local, additive persistence boundary for factual FIFO cost evidence.

The repository deliberately owns only its ``fifo_cost_*`` tables.  It shares
the existing seller SQLite file, but never migrates legacy cost rows or
Planning Workspace schema metadata.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

from services.ozon_account_repository import split_store_tenant_scope
from services.fifo_cost_allocation_service import (
    FifoCostLayer, FifoOpenCostRate, FifoOutflowEvent, FifoRestoreSlice, FifoRestockEvent,
    FifoSaleEvent,
)
from services.fifo_cost_replay_service import FifoCostReplayService, FifoDatedAllocationEvent
from services.fifo_cost_transition_contracts import (
    CostInputMode,
    ReportEvidence,
    SupplyDeclaration,
    SupplyObservation,
    TransitionCase,
    TransitionMetadata,
    TransitionState,
)
from services.fifo_cost_transition_store import FifoCostTransitionStore
from services.tenant_context import get_current_tenant_user_id
from services.tenant_storage import ensure_storage_parent, tenant_storage_path


class FifoCostRepository:
    SCHEMA_VERSION = 13
    MAX_COMMAND_EVENTS = 100
    MAX_REFERENCES_PER_SOURCE = 100
    MAX_EVENT_QUANTITY = 100_000
    MAX_COMMAND_UNITS = 1_000_000
    MAX_PAYLOAD_BYTES = 64 * 1024
    PREVIEW_TTL_SECONDS = 600
    MAX_PREVIEWS = 5000
    _HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
    _IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
    _EVENT_KINDS = frozenset({
        "OPENING_FIFO_ANCHOR", "COST_LAYER_RECEIPT", "INVENTORY_TRANSFER",
        "PHYSICAL_SALE", "SALE_CANCELLATION", "SALEABLE_RETURN_RESTOCK",
        "NON_SALE_OUTFLOW", "CORRECTION",
    })
    _SOURCE_STATUSES = frozenset({
        "COMPLETE", "PARTIAL", "UNAVAILABLE", "STALE", "CONFLICT",
        "NOT_REQUESTED", "OWNER_CONFIRMED", "MODEL_ONLY",
    })
    _PROVENANCE = frozenset({
        "OWNER_CONFIRMED", "OZON_CONFIRMED_FIELD", "DOCUMENT_RECONCILED",
        "LEGACY_DATED_COST", "MODEL_ASSUMPTION",
    })
    _REFERENCE_KINDS = frozenset({"ORDER", "SUPPLY", "ACT", "POSTING", "DOCUMENT", "OTHER"})
    _LOCATIONS = frozenset({"HOME", "TRANSIT", "OZON", "UNKNOWN"})
    _OUTFLOW_REASONS = frozenset({
        "HOME_SHORTAGE", "OZON_DISPOSAL", "SUPPLIER_RETURN", "INVENTORY_WRITE_OFF",
    })
    _REASON_CODES = frozenset({
        "HISTORY_GAP", "ANCHOR_UNCONFIRMED", "INVENTORY_CUTOFF_UNRECONCILED",
        "PHYSICAL_SALE_IDENTITY_UNCONFIRMED", "STOCK_SEMANTICS_UNCONFIRMED",
        "TRANSIT_OVERLAP_UNRESOLVED", "SUPPLY_COST_LINK_MISSING",
        "EVENT_ORDER_UNRESOLVED", "RECONCILIATION_CONFLICT", "STALE_PREVIEW",
        "REVISION_CONFLICT", "BUDGET_EXHAUSTED", "SOURCE_UNAVAILABLE",
        "PERIOD_PROFIT_COST_LEGACY_PROVENANCE_AMBIGUOUS",
        "OWNER_REPORTED_LATE", "COST_ENTRY_CORRECTION", "QUANTITY_CORRECTION",
        "SUPPLY_LINK_CORRECTION", "CANCELLED_FUTURE_CHANGE",
        "HOME_SHORTAGE", "OZON_DISPOSAL", "SUPPLIER_RETURN",
        "INVENTORY_WRITE_OFF", "ACCEPTANCE_SHORTFALL", "INVENTORY_TRANSFER",
    })
    _PREVIEW_LOCK = threading.RLock()
    _ACTIVE_PREVIEWS = {}
    _ACTIVE_RATE_PREVIEWS = {}
    _ACTIVE_RATE_CANCELLATION_PREVIEWS = {}

    _TABLES = (
        "fifo_cost_schema",
        "fifo_cost_streams",
        "fifo_cost_sources",
        "fifo_cost_source_refs",
        "fifo_cost_policy_revisions",
        "fifo_cost_events",
        "fifo_cost_layers",
        "fifo_cost_projections",
        "fifo_cost_allocations",
        "fifo_cost_allocation_lines",
        "fifo_cost_allocation_rate_lines",
        "fifo_cost_idempotency",
        "fifo_cost_commands",
        "fifo_cost_command_events",
        "fifo_cost_rate_changes",
        "fifo_cost_rate_reconciliations",
        "fifo_cost_supply_evidence",
        "fifo_cost_return_basis",
        "fifo_cost_allocation_outflow_lines",
        "fifo_cost_late_entry_drafts",
        "fifo_cost_late_entry_corrections",
        "fifo_cost_rate_cancellations",
        "fifo_cost_transition_cases",
        "fifo_cost_transition_case_revisions",
        "fifo_cost_supply_declarations",
        "fifo_cost_supply_observations",
        "fifo_cost_report_evidence",
        "fifo_cost_transition_previews",
        "fifo_cost_transition_commits",
    )

    _APPEND_ONLY_TABLES = (
        "fifo_cost_sources",
        "fifo_cost_source_refs",
        "fifo_cost_policy_revisions",
        "fifo_cost_events",
        "fifo_cost_layers",
        "fifo_cost_allocations",
        "fifo_cost_allocation_lines",
        "fifo_cost_allocation_rate_lines",
        "fifo_cost_idempotency",
        "fifo_cost_commands",
        "fifo_cost_command_events",
        "fifo_cost_rate_changes",
        "fifo_cost_rate_reconciliations",
        "fifo_cost_supply_evidence",
        "fifo_cost_return_basis",
        "fifo_cost_allocation_outflow_lines",
        "fifo_cost_late_entry_drafts",
        "fifo_cost_late_entry_corrections",
        "fifo_cost_rate_cancellations",
        "fifo_cost_transition_case_revisions",
        "fifo_cost_supply_declarations",
        "fifo_cost_supply_observations",
        "fifo_cost_report_evidence",
        "fifo_cost_transition_previews",
        "fifo_cost_transition_commits",
    )

    def __init__(self, db_path=None, *, now_provider=None):
        self._db_path = Path(db_path) if db_path is not None else None
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    @property
    def db_path(self):
        return self._db_path or Path(tenant_storage_path("ozon_assistant.db"))

    def get_connection(self):
        """Open a tenant-local connection and apply only FIFO-owned migrations."""
        ensure_storage_parent(self.db_path)
        connection = sqlite3.connect(
            self.db_path, timeout=5.0, isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            self._initialize_schema(connection)
        except Exception:
            connection.close()
            raise
        return connection

    def save_transition_case(self, *, case, expected_revision, idempotency_key):
        """Persist an owner draft without initializing or mutating the FIFO stream."""
        if not isinstance(case, TransitionCase):
            return self._error("FIFO_TRANSITION_CASE_INVALID")
        if type(expected_revision) is not int or expected_revision < 0:
            return self._error("FIFO_TRANSITION_REVISION_INVALID")
        if not self._valid_transition_idempotency_key(idempotency_key):
            return self._error("FIFO_TRANSITION_IDEMPOTENCY_KEY_INVALID")
        if case.state not in {
            TransitionState.DRAFT,
            TransitionState.AWAITING_EVIDENCE,
            TransitionState.CANCELLED,
        } or (case.state is TransitionState.CANCELLED and expected_revision == 0):
            return self._error("FIFO_TRANSITION_CASE_NOT_READY")
        scope, _identity = self._transition_metadata_scope(case.metadata)
        if scope.get("error"):
            return scope
        return self._run_transition_write(
            lambda connection: FifoCostTransitionStore.save_case(
                connection, case, scope,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
                recorded_at=self._iso(self._now()),
            )
        )

    def cancel_transition_case(self, *, case, expected_revision, idempotency_key):
        if not isinstance(case, TransitionCase) or case.state is not TransitionState.CANCELLED:
            return self._error("FIFO_TRANSITION_CASE_NOT_READY")
        return self.save_transition_case(
            case=case, expected_revision=expected_revision,
            idempotency_key=idempotency_key,
        )

    def read_transition_case(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
    ):
        identity = self._normalize_transition_read_identity(
            store_id, product_id=product_id, offer_id=offer_id, sku=sku,
        )
        if identity.get("error"):
            return identity
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        if not self._valid_transition_case_id(case_id):
            return self._error("FIFO_TRANSITION_CASE_ID_INVALID")
        connection = None
        try:
            connection = self.get_connection()
            return FifoCostTransitionStore.read_case(
                connection, case_id, scope, identity,
            )
        except (sqlite3.Error, OSError):
            return self._error("FIFO_TRANSITION_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def list_transition_cases(
        self, *, store_id, sku=None,
        states=("DRAFT", "AWAITING_EVIDENCE", "READY_TO_CONFIRM"), limit=100,
    ):
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        try:
            normalized_store = self._safe_identity_part(store_id, "store_id", 128)
            normalized_sku = (
                self._safe_identity_part(sku, "sku", 64) if sku is not None else None
            )
        except ValueError:
            return self._error("FIFO_TRANSITION_SCOPE_INVALID")
        if type(limit) is not int or not 1 <= limit <= 100:
            return self._error("FIFO_TRANSITION_LIMIT_INVALID")
        if not isinstance(states, (tuple, list)) or not states:
            return self._error("FIFO_TRANSITION_STATE_FILTER_INVALID")
        connection = None
        try:
            connection = self.get_connection()
            return FifoCostTransitionStore.list_cases(
                connection, scope, store_id=normalized_store,
                sku=normalized_sku, states=tuple(states), limit=limit,
            )
        except (sqlite3.Error, OSError, ValueError):
            return self._error("FIFO_TRANSITION_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def append_supply_declaration(
        self, *, declaration, expected_case_revision, idempotency_key,
    ):
        if not isinstance(declaration, SupplyDeclaration):
            return self._error("FIFO_TRANSITION_DECLARATION_INVALID")
        if type(expected_case_revision) is not int or expected_case_revision < 1:
            return self._error("FIFO_TRANSITION_REVISION_INVALID")
        if not self._valid_transition_idempotency_key(idempotency_key):
            return self._error("FIFO_TRANSITION_IDEMPOTENCY_KEY_INVALID")
        scope, _identity = self._transition_metadata_scope(declaration.metadata)
        if scope.get("error"):
            return scope
        return self._run_transition_write(
            lambda connection: FifoCostTransitionStore.append_declaration(
                connection, declaration, scope,
                expected_case_revision=expected_case_revision,
                idempotency_key=idempotency_key,
                recorded_at=self._iso(self._now()),
            )
        )

    def append_supply_observation(
        self, *, case_id, observation, expected_case_revision, idempotency_key,
    ):
        if not isinstance(observation, SupplyObservation):
            return self._error("FIFO_TRANSITION_OBSERVATION_INVALID")
        if type(expected_case_revision) is not int or expected_case_revision < 1:
            return self._error("FIFO_TRANSITION_REVISION_INVALID")
        if not self._valid_transition_idempotency_key(idempotency_key):
            return self._error("FIFO_TRANSITION_IDEMPOTENCY_KEY_INVALID")
        scope, _identity = self._transition_metadata_scope(observation.metadata)
        if scope.get("error"):
            return scope
        if not self._valid_transition_case_id(case_id):
            return self._error("FIFO_TRANSITION_CASE_ID_INVALID")
        return self._run_transition_write(
            lambda connection: FifoCostTransitionStore.append_observation(
                connection, case_id, observation, scope,
                expected_case_revision=expected_case_revision,
                idempotency_key=idempotency_key,
                recorded_at=self._iso(self._now()),
            )
        )

    def append_report_evidence(
        self, *, case_id, report, expected_case_revision, idempotency_key,
    ):
        if not isinstance(report, ReportEvidence):
            return self._error("FIFO_TRANSITION_REPORT_INVALID")
        if type(expected_case_revision) is not int or expected_case_revision < 1:
            return self._error("FIFO_TRANSITION_REVISION_INVALID")
        if not self._valid_transition_idempotency_key(idempotency_key):
            return self._error("FIFO_TRANSITION_IDEMPOTENCY_KEY_INVALID")
        scope, _identity = self._transition_metadata_scope(report.metadata)
        if scope.get("error"):
            return scope
        if not self._valid_transition_case_id(case_id):
            return self._error("FIFO_TRANSITION_CASE_ID_INVALID")
        return self._run_transition_write(
            lambda connection: FifoCostTransitionStore.append_report(
                connection, case_id, report, scope,
                expected_case_revision=expected_case_revision,
                idempotency_key=idempotency_key,
                recorded_at=self._iso(self._now()),
            )
        )

    def read_transition_evidence(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
        kind, limit=100, include_encrypted_lookup_reference=False,
    ):
        identity = self._normalize_transition_read_identity(
            store_id, product_id=product_id, offer_id=offer_id, sku=sku,
        )
        if identity.get("error"):
            return identity
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        if not self._valid_transition_case_id(case_id):
            return self._error("FIFO_TRANSITION_CASE_ID_INVALID")
        connection = None
        try:
            connection = self.get_connection()
            return FifoCostTransitionStore.read_evidence(
                connection, case_id, scope, identity, kind=kind, limit=limit,
                include_encrypted_lookup_reference=include_encrypted_lookup_reference,
            )
        except (sqlite3.Error, OSError, ValueError):
            return self._error("FIFO_TRANSITION_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def prepare_transition_preview(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
        expected_case_revision, effective_date, cutoff_bridge, impact_preview,
        tax_policy_fingerprint, idempotency_key, initial_opening_cutover=None,
    ):
        """Seal a complete, scope-bound replay for later atomic confirmation.

        The bridge and impact are rebuilt by the caller immediately before this
        call. The repository independently rebuilds the allocation from its
        immutable ledger and binds it to the case, current source set, tax
        policy, cutoff bridge, and financial-period preview.
        """
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        if (
            not self._valid_transition_case_id(case_id)
            or type(expected_case_revision) is not int
            or expected_case_revision < 1
            or not self._valid_transition_idempotency_key(idempotency_key)
        ):
            return self._error("FIFO_TRANSITION_PREVIEW_INPUT_INVALID")
        try:
            from services.fifo_cost_cutoff_bridge_service import FifoCutoffBridgeResult

            identity = self._normalize_identity(
                store_id, product_id, offer_id, sku, 1,
            )
            if not isinstance(cutoff_bridge, FifoCutoffBridgeResult):
                return self._error("FIFO_CUTOFF_BRIDGE_NOT_VERIFIED")
            if not self._valid_digest(tax_policy_fingerprint):
                return self._error("FIFO_TAX_POLICY_FINGERPRINT_INVALID")
            bridge_error = self._validate_transition_bridge(
                cutoff_bridge, case_id=case_id,
                expected_case_revision=expected_case_revision,
                identity=identity,
                owner_id=split_store_tenant_scope(
                    str(get_current_tenant_user_id() or "").strip(),
                )[0],
            )
            if bridge_error:
                return self._error(bridge_error)
            impact_error = self._validate_transition_impact(
                impact_preview, tax_policy_fingerprint=tax_policy_fingerprint,
            )
            if impact_error:
                return self._error(impact_error)
            if (
                impact_preview.get("complete_through") is not None
                and impact_preview.get("complete_through") != cutoff_bridge.complete_through
            ):
                return self._error("FIFO_TRANSITION_EVIDENCE_MISMATCH")
            now = self._now()
            now_text = self._iso(now)
            connection = self.get_connection()
            try:
                connection.execute("BEGIN IMMEDIATE")
                case_result = FifoCostTransitionStore.read_case(
                    connection, case_id, scope, identity,
                )
                if case_result.get("error"):
                    connection.rollback()
                    return case_result
                if (
                    not (
                        case_result["case_revision"] == expected_case_revision
                        and case_result["state"] in {"DRAFT", "AWAITING_EVIDENCE"}
                    )
                    and not (
                        case_result["case_revision"] == expected_case_revision + 1
                        and case_result["state"] == "READY_TO_CONFIRM"
                        and isinstance(case_result.get("case"), dict)
                        and isinstance(case_result["case"].get("last_preview"), dict)
                        and case_result["case"]["last_preview"].get("idempotency_key")
                        == idempotency_key
                    )
                    or cutoff_bridge.case_revision != expected_case_revision
                ):
                    connection.rollback()
                    return self._error("FIFO_TRANSITION_REVISION_CONFLICT")
                case = case_result["case"]
                cutover_recorded_at = now_text
                last_preview = case.get("last_preview")
                if (
                    case_result["state"] == "READY_TO_CONFIRM"
                    and isinstance(last_preview, dict)
                    and last_preview.get("idempotency_key") == idempotency_key
                ):
                    previous_preview = connection.execute(
                        "SELECT payload_json FROM fifo_cost_transition_previews "
                        "WHERE preview_id=? AND case_id=?",
                        (last_preview.get("preview_id"), case_id),
                    ).fetchone()
                    if previous_preview is None:
                        connection.rollback()
                        return self._error("FIFO_TRANSITION_PREVIEW_CORRUPT")
                    try:
                        previous_payload = json.loads(previous_preview["payload_json"])
                    except (TypeError, ValueError):
                        connection.rollback()
                        return self._error("FIFO_TRANSITION_PREVIEW_CORRUPT")
                    previous_cutover = previous_payload.get("initial_opening_cutover")
                    if previous_cutover is not None:
                        if not isinstance(previous_cutover, dict):
                            connection.rollback()
                            return self._error("FIFO_TRANSITION_PREVIEW_CORRUPT")
                        cutover_recorded_at = previous_cutover.get("recorded_at")
                case_error = self._validate_transition_case_for_apply(
                    case, effective_date=effective_date,
                    complete_through=cutoff_bridge.complete_through,
                )
                if case_error:
                    connection.rollback()
                    return self._error(case_error)
                stream_id = "fifo_" + self._sha256(identity)[:40]
                stream = connection.execute(
                    """SELECT revision, policy_version, state
                       FROM fifo_cost_streams
                       WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                    (stream_id, identity["store_id"], self._sha256(identity)),
                ).fetchone()
                projection = connection.execute(
                    """SELECT revision, state, known_quantity, known_cost_rub,
                              next_unit_cost_rub, queue_complete, cutoff_status,
                              inventory_cutoff, source_set_fingerprint
                       FROM fifo_cost_projections WHERE stream_id=?""",
                    (stream_id,),
                ).fetchone()
                staged_initial_cutover = None
                initial_cutover_staged = False
                if stream is None and projection is None:
                    if initial_opening_cutover is None:
                        connection.rollback()
                        return self._error("FIFO_HISTORY_NOT_INITIALIZED")
                    staged_initial_cutover = self._normalize_transition_initial_cutover(
                        connection, initial_opening_cutover, cutoff_bridge,
                        case, recorded_at=cutover_recorded_at,
                    )
                    if isinstance(staged_initial_cutover, str):
                        connection.rollback()
                        return self._error(staged_initial_cutover)
                    identity_conflict = self._identity_stream_conflict(
                        connection, identity, self._sha256(identity),
                    )
                    if identity_conflict is not None:
                        connection.rollback()
                        return identity_conflict
                    connection.execute("SAVEPOINT transition_initial_preview")
                    self._insert_transition_initial_cutover(
                        connection, identity=identity, bridge=cutoff_bridge,
                        cutover=staged_initial_cutover,
                    )
                    initial_cutover_staged = True
                    stream = connection.execute(
                        """SELECT revision, policy_version, state
                           FROM fifo_cost_streams WHERE stream_id=?""",
                        (stream_id,),
                    ).fetchone()
                    projection = connection.execute(
                        """SELECT revision, state, known_quantity, known_cost_rub,
                                  next_unit_cost_rub, queue_complete, cutoff_status,
                                  inventory_cutoff, source_set_fingerprint
                           FROM fifo_cost_projections WHERE stream_id=?""",
                        (stream_id,),
                    ).fetchone()
                elif stream is None or projection is None:
                    connection.rollback()
                    return self._error("FIFO_HISTORY_INCOMPLETE")
                elif initial_opening_cutover is not None:
                    connection.rollback()
                    return self._error("FIFO_INITIAL_CUTOVER_NOT_APPLICABLE")
                if (
                    stream["state"] not in {"FIFO_READY", "FIFO_PARTIAL"}
                    or projection["revision"] != stream["revision"]
                    or projection["queue_complete"] != 1
                ):
                    connection.rollback()
                    return self._error("FIFO_HISTORY_INCOMPLETE")
                if (
                    projection["cutoff_status"] != "RECONCILED"
                    or projection["inventory_cutoff"] != cutoff_bridge.cutoff_date
                    or cutoff_bridge.complete_through is None
                    or cutoff_bridge.cutoff_date >= cutoff_bridge.complete_through
                ):
                    connection.rollback()
                    return self._error("INVENTORY_CUTOFF_UNRECONCILED")
                active_rates = connection.execute(
                    """SELECT COUNT(*) FROM fifo_cost_rate_changes AS r
                       WHERE r.stream_id=? AND NOT EXISTS (
                           SELECT 1 FROM fifo_cost_rate_cancellations AS c
                           WHERE c.stream_id=r.stream_id
                             AND c.rate_change_id=r.rate_change_id
                       )""",
                    (stream_id,),
                ).fetchone()[0]
                if active_rates:
                    connection.rollback()
                    return self._error("FIFO_REPLAY_RATE_TRANSITION_UNSUPPORTED")
                bridge_error = self._validate_transition_bridge_ledger(
                    connection, stream_id, cutoff_bridge,
                )
                if bridge_error:
                    connection.rollback()
                    return self._error(bridge_error)
                evidence_fingerprint = self._transition_evidence_fingerprint(
                    connection, case_id, case,
                )
                base_source_fingerprint = self._allocation_source_fingerprint(
                    connection, stream_id, stream["revision"],
                    stream["policy_version"], projection["cutoff_status"],
                )
                allocation_revision = connection.execute(
                    "SELECT COALESCE(MAX(revision), 0) FROM fifo_cost_allocations "
                    "WHERE stream_id=?", (stream_id,),
                ).fetchone()[0]
                current_preview = self._preview_allocation_from_connection(
                    connection, stream_id,
                    stream_revision=stream["revision"],
                    allocation_revision=allocation_revision,
                    source_fingerprint=base_source_fingerprint,
                    cutoff_status=projection["cutoff_status"],
                    anchor_cutoff_date=projection["inventory_cutoff"],
                )
                if allocation_revision:
                    normalized_current = self._normalize_allocation_preview(
                        current_preview, "transition-current-0001",
                    ) if current_preview else "FIFO_ALLOCATION_PREVIEW_INCOMPLETE"
                    if isinstance(normalized_current, str):
                        connection.rollback()
                        return self._error(normalized_current)
                    try:
                        self._validate_allocation_lines(
                            connection, stream_id, normalized_current,
                            stream_revision=stream["revision"],
                            allocation_revision=allocation_revision,
                            source_fingerprint=base_source_fingerprint,
                            cutoff_status=projection["cutoff_status"],
                        )
                    except ValueError as exc:
                        connection.rollback()
                        return self._error(str(exc))
                event_counts = {
                    row["event_kind"]: row["count"]
                    for row in connection.execute(
                        """SELECT event_kind, COUNT(*) AS count
                           FROM fifo_cost_events WHERE stream_id=?
                             AND event_kind IN ('SALEABLE_RETURN_RESTOCK', 'NON_SALE_OUTFLOW')
                           GROUP BY event_kind""",
                        (stream_id,),
                    ).fetchall()
                }
                if (
                    impact_preview.get("related_return_count")
                    != event_counts.get("SALEABLE_RETURN_RESTOCK", 0)
                    or impact_preview.get("non_sale_outflow_count")
                    != event_counts.get("NON_SALE_OUTFLOW", 0)
                ):
                    connection.rollback()
                    return self._error("FIFO_TRANSITION_IMPACT_MISMATCH")
                old_unit_cost = self._normalize_money(case.get("old_unit_cost_rub"))
                if old_unit_cost is None:
                    connection.rollback()
                    return self._error("FIFO_TRANSITION_BASELINE_COST_UNAVAILABLE")
                # Keep baseline and candidate on the same hypothetical
                # transition boundary. The baseline changes only the rate
                # value to the old cost, so same-day causal checks remain
                # identical between the two comparisons.
                baseline_rate_date = effective_date
                baseline_rate_id = "transition-baseline_" + self._sha256({
                    "case_id": case_id,
                    "case_revision": expected_case_revision,
                    "unit_cost_rub": old_unit_cost,
                    "cutoff": projection["inventory_cutoff"],
                })[:40]
                baseline_preview = self._preview_allocation_from_connection(
                    connection, stream_id,
                    stream_revision=stream["revision"],
                    allocation_revision=allocation_revision,
                    source_fingerprint=base_source_fingerprint,
                    cutoff_status=projection["cutoff_status"],
                    anchor_cutoff_date=projection["inventory_cutoff"],
                    hypothetical_open_rate=FifoOpenCostRate(
                        baseline_rate_id, old_unit_cost,
                    ),
                    hypothetical_open_rate_effective_date=baseline_rate_date,
                    hypothetical_opening_layer_cost_replacement=(
                        self._normalize_money(case.get("new_unit_cost_rub")),
                        old_unit_cost,
                    ) if initial_cutover_staged else None,
                )
                if (
                    not baseline_preview
                    or baseline_preview.get("complete") is not True
                    or not self._transition_impact_matches_replay(
                        impact_preview, baseline_preview,
                        expected_before_cogs=baseline_preview.get("total_cogs_rub"),
                        check_after=False,
                    )
                ):
                    connection.rollback()
                    return self._error("FIFO_TRANSITION_BASELINE_UNAVAILABLE")

                candidate_rate_id = "rate_transition_" + self._sha256({
                    "case_id": case_id,
                    "case_revision": expected_case_revision,
                    "effective_date": effective_date,
                    "unit_cost_rub": case["new_unit_cost_rub"],
                    "bridge": cutoff_bridge.source_set_fingerprint,
                })[:40]
                cost_mode = case["cost_input_mode"]
                components = case.get("cost_components")
                unit_cost = self._normalize_money(case["new_unit_cost_rub"])
                if unit_cost is None:
                    connection.rollback()
                    return self._error("FIFO_RATE_COST_INPUT_INVALID")
                component_values = {
                    name: (
                        self._normalize_money(components.get(name))
                        if isinstance(components, dict) else None
                    )
                    for name in (
                        "purchase_cost_rub", "delivery_cost_rub", "packaging_cost_rub",
                    )
                }
                if cost_mode == "COMPONENTS" and any(
                    value is None for value in component_values.values()
                ):
                    connection.rollback()
                    return self._error("FIFO_RATE_COMPONENTS_REQUIRED")
                if cost_mode == "TOTAL_LANDED" and any(
                    value is not None for value in component_values.values()
                ):
                    connection.rollback()
                    return self._error("FIFO_RATE_COST_INPUT_INVALID")
                rate_sequence = connection.execute(
                    "SELECT COALESCE(MAX(rate_sequence), 0) + 1 "
                    "FROM fifo_cost_rate_changes WHERE stream_id=?", (stream_id,),
                ).fetchone()[0]
                source_fingerprint = self._sha256({
                    "source": "OWNER_CONFIRMED_FIFO_TRANSITION",
                    "case_id": case_id,
                    "case_revision": expected_case_revision,
                    "case_fingerprint": evidence_fingerprint,
                    "bridge_fingerprint": cutoff_bridge.source_set_fingerprint,
                    "tax_policy_fingerprint": tax_policy_fingerprint,
                    "impact_fingerprint": impact_preview["preview_fingerprint"],
                    "financial_period_mapping_fingerprint": impact_preview.get(
                        "financial_period_mapping_fingerprint",
                    ),
                })
                rate_payload = {
                    "rate_change_id": candidate_rate_id,
                    "rate_sequence": rate_sequence,
                    "effective_date": effective_date,
                    "unit_cost_rub": format(Decimal(unit_cost), ".2f"),
                    "cost_input_mode": cost_mode,
                    **component_values,
                    "owner_old_home_units": case["owner_old_home_units"],
                    "source_fingerprint": source_fingerprint,
                    "idempotency_key": "transition-" + self._sha256({
                        "case_id": case_id, "revision": expected_case_revision,
                    })[:40],
                }
                rate_payload_fingerprint = self._sha256(rate_payload)
                hypothetical_rate = {
                    "rate_change_id": candidate_rate_id,
                    "rate_sequence": rate_sequence,
                    "effective_date": effective_date,
                    "unit_cost_rub": unit_cost,
                    "purchase_cost_rub": component_values["purchase_cost_rub"],
                    "delivery_cost_rub": component_values["delivery_cost_rub"],
                    "packaging_cost_rub": component_values["packaging_cost_rub"],
                    "payload_fingerprint": rate_payload_fingerprint,
                }
                candidate_source_fingerprint = self._allocation_source_fingerprint(
                    connection, stream_id, stream["revision"] + 1,
                    stream["policy_version"], projection["cutoff_status"],
                    hypothetical_rate=hypothetical_rate,
                )
                candidate_replay = self._preview_allocation_from_connection(
                    connection, stream_id,
                    stream_revision=stream["revision"] + 1,
                    allocation_revision=allocation_revision,
                    source_fingerprint=candidate_source_fingerprint,
                    cutoff_status=projection["cutoff_status"],
                    anchor_cutoff_date=projection["inventory_cutoff"],
                    hypothetical_open_rate=FifoOpenCostRate(candidate_rate_id, unit_cost),
                    hypothetical_open_rate_effective_date=effective_date,
                )
                normalized_candidate = self._normalize_allocation_preview(
                    candidate_replay, "transition-candidate-0001",
                ) if candidate_replay else "FIFO_ALLOCATION_PREVIEW_INCOMPLETE"
                if isinstance(normalized_candidate, str):
                    connection.rollback()
                    return self._error(normalized_candidate)
                if candidate_replay["complete"] is not True:
                    connection.rollback()
                    return self._error(candidate_replay.get("reason_code") or "FIFO_REPLAY_INCOMPLETE")
                if not self._transition_impact_matches_replay(
                    impact_preview, candidate_replay,
                    expected_before_cogs=baseline_preview["total_cogs_rub"],
                    expected_after_cogs=candidate_replay["total_cogs_rub"],
                ):
                    connection.rollback()
                    return self._error("FIFO_TRANSITION_IMPACT_MISMATCH")
                self._require_transition_report_evidence(
                    connection, case_id, cutoff_bridge,
                )
                preview_payload = {
                    "schema_version": 1,
                    "case_id": case_id,
                    "case_revision": expected_case_revision,
                    "effective_date": effective_date,
                    "rate": rate_payload,
                    "rate_payload_fingerprint": rate_payload_fingerprint,
                    "base_source_fingerprint": base_source_fingerprint,
                    "base_cogs_rub": current_preview["total_cogs_rub"],
                    "candidate_source_fingerprint": candidate_source_fingerprint,
                    "allocation_preview": candidate_replay,
                    "baseline_preview_fingerprint": baseline_preview[
                        "preview_fingerprint"
                    ],
                    "baseline_cogs_rub": baseline_preview["total_cogs_rub"],
                    "impact_preview": impact_preview,
                    "bridge_fingerprint": cutoff_bridge.source_set_fingerprint,
                    "evidence_set_fingerprint": evidence_fingerprint,
                    "tax_policy_fingerprint": tax_policy_fingerprint,
                    "complete_through": cutoff_bridge.complete_through,
                    "base_fifo_revision": stream["revision"],
                    "base_allocation_revision": allocation_revision,
                    "idempotency_key": idempotency_key,
                    "initial_opening_cutover": staged_initial_cutover,
                }
                if len(self._canonical_json(preview_payload).encode("utf-8")) > 262_144:
                    connection.rollback()
                    return self._error("FIFO_TRANSITION_PREVIEW_TOO_LARGE")
                preview_fingerprint = self._sha256(preview_payload)
                preview_id = "transpreview_" + preview_fingerprint[:40]
                expires_at = self._iso(
                    now + timedelta(seconds=self.PREVIEW_TTL_SECONDS),
                )
                if initial_cutover_staged:
                    connection.execute("ROLLBACK TO SAVEPOINT transition_initial_preview")
                    connection.execute("RELEASE SAVEPOINT transition_initial_preview")
                stored = FifoCostTransitionStore.prepare_case_preview(
                    connection, case_id=case_id, scope=scope, identity=identity,
                    expected_case_revision=expected_case_revision,
                    preview_id=preview_id, preview_payload=preview_payload,
                    preview_fingerprint=preview_fingerprint,
                    fifo_revision=stream["revision"],
                    allocation_revision=allocation_revision,
                    evidence_set_fingerprint=evidence_fingerprint,
                    tax_policy_fingerprint=tax_policy_fingerprint,
                    idempotency_key=idempotency_key,
                    created_at=now_text, expires_at=expires_at,
                )
                if stored.get("error"):
                    connection.rollback()
                    return stored
                connection.commit()
                return {
                    **stored,
                    "code": "FIFO_TRANSITION_PREVIEW_READY",
                    "unit_cost_rub": format(Decimal(unit_cost), ".2f"),
                    "candidate_cogs_rub": candidate_replay["total_cogs_rub"],
                    "complete_through": cutoff_bridge.complete_through,
                    "read_only": True,
                }
            except (ValueError, TypeError, KeyError, InvalidOperation, OverflowError) as exc:
                if connection.in_transaction:
                    connection.rollback()
                code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_TRANSITION_PREVIEW_INVALID"
                return self._error(code)
            except sqlite3.IntegrityError:
                if connection.in_transaction:
                    connection.rollback()
                return self._error("FIFO_TRANSITION_REVISION_CONFLICT")
            except sqlite3.Error:
                if connection.in_transaction:
                    connection.rollback()
                return self._error("FIFO_TRANSITION_STORAGE_UNAVAILABLE")
            finally:
                connection.close()
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_TRANSITION_PREVIEW_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            return self._error("FIFO_TRANSITION_STORAGE_UNAVAILABLE")

    def commit_transition_case(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
        expected_case_revision, preview_id, idempotency_key, cutoff_bridge,
        impact_preview, current_tax_policy_fingerprint,
    ):
        """Atomically apply one transition rate, complete replay, and case audit."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        if (
            not self._valid_transition_case_id(case_id)
            or type(expected_case_revision) is not int
            or expected_case_revision < 1
            or not self._valid_transition_idempotency_key(idempotency_key)
            or not isinstance(preview_id, str)
        ):
            return self._error("FIFO_TRANSITION_COMMIT_INPUT_INVALID")
        try:
            from services.fifo_cost_cutoff_bridge_service import FifoCutoffBridgeResult

            identity = self._normalize_identity(
                store_id, product_id, offer_id, sku, 1,
            )
            if not isinstance(cutoff_bridge, FifoCutoffBridgeResult):
                return self._error("FIFO_CUTOFF_BRIDGE_NOT_VERIFIED")
            impact_policy_fingerprint = (
                impact_preview.get("tax_policy_fingerprint")
                if isinstance(impact_preview, dict) else None
            )
            impact_error = self._validate_transition_impact(
                impact_preview,
                tax_policy_fingerprint=impact_policy_fingerprint,
            )
            if impact_error:
                return self._error(impact_error)
            bridge_error = self._validate_transition_bridge(
                cutoff_bridge, case_id=case_id,
                expected_case_revision=expected_case_revision - 1,
                identity=identity,
                owner_id=split_store_tenant_scope(
                    str(get_current_tenant_user_id() or "").strip(),
                )[0],
            )
            if bridge_error:
                return self._error(bridge_error)
            now = self._now()
            now_text = self._iso(now)
            connection = self.get_connection()
            try:
                connection.execute("BEGIN IMMEDIATE")
                case_result = FifoCostTransitionStore.read_case(
                    connection, case_id, scope, identity,
                )
                if case_result.get("error"):
                    connection.rollback()
                    return case_result
                if cutoff_bridge.case_revision != expected_case_revision - 1:
                    connection.rollback()
                    return self._error("FIFO_TRANSITION_REVISION_CONFLICT")
                preview_row = connection.execute(
                    """SELECT preview_id, case_revision, fifo_revision,
                              allocation_revision, evidence_set_fingerprint,
                              tax_policy_fingerprint, preview_fingerprint,
                              expires_at, payload_json
                       FROM fifo_cost_transition_previews
                       WHERE preview_id=? AND case_id=?""",
                    (preview_id, case_id),
                ).fetchone()
                if preview_row is None or preview_row["case_revision"] != expected_case_revision:
                    connection.rollback()
                    return self._error("FIFO_TRANSITION_PREVIEW_STALE")
                payload = json.loads(preview_row["payload_json"])
                commit_payload_fingerprint = self._sha256({
                    "case_id": case_id,
                    "preview_id": preview_id,
                    "preview_fingerprint": preview_row["preview_fingerprint"],
                    "impact_fingerprint": impact_preview["preview_fingerprint"],
                    "tax_policy_fingerprint": impact_policy_fingerprint,
                    "bridge_fingerprint": cutoff_bridge.source_set_fingerprint,
                })
                prior = connection.execute(
                    """SELECT commit_id, payload_fingerprint, preview_id,
                              case_revision, complete_through, committed_at
                       FROM fifo_cost_transition_commits
                       WHERE case_id=? AND idempotency_key=?""",
                    (case_id, idempotency_key),
                ).fetchone()
                if prior is not None:
                    if (
                        prior["payload_fingerprint"] != commit_payload_fingerprint
                        or prior["preview_id"] != preview_id
                    ):
                        connection.rollback()
                        return self._error("FIFO_TRANSITION_IDEMPOTENCY_CONFLICT")
                    connection.rollback()
                    return {
                        "error": False, "code": "FIFO_TRANSITION_APPLIED",
                        "commit_id": prior["commit_id"],
                        "case_revision": prior["case_revision"],
                        "preview_id": prior["preview_id"],
                        "complete_through": prior["complete_through"],
                        "committed_at": prior["committed_at"], "replayed": True,
                    }
                if (
                    impact_policy_fingerprint != current_tax_policy_fingerprint
                    or payload.get("bridge_fingerprint") != cutoff_bridge.source_set_fingerprint
                    or payload.get("impact_preview", {}).get("preview_fingerprint")
                    != impact_preview.get("preview_fingerprint")
                    or payload.get("tax_policy_fingerprint") != current_tax_policy_fingerprint
                    or preview_row["tax_policy_fingerprint"] != current_tax_policy_fingerprint
                ):
                    connection.rollback()
                    return self._error("FIFO_TRANSITION_PREVIEW_STALE")
                if self._sha256(payload) != preview_row["preview_fingerprint"]:
                    connection.rollback()
                    return self._error("FIFO_TRANSITION_PREVIEW_CORRUPT")
                if preview_row["expires_at"] <= now_text:
                    connection.rollback()
                    return self._error("FIFO_TRANSITION_PREVIEW_EXPIRED")
                if (
                    case_result["case_revision"] != expected_case_revision
                    or case_result["state"] != "READY_TO_CONFIRM"
                ):
                    connection.rollback()
                    return self._error("FIFO_TRANSITION_REVISION_CONFLICT")
                if not self._transition_impact_matches_replay(
                    impact_preview, payload.get("allocation_preview", {}),
                    expected_before_cogs=payload.get("baseline_cogs_rub"),
                    expected_after_cogs=payload.get("allocation_preview", {}).get(
                        "total_cogs_rub",
                    ),
                ):
                    connection.rollback()
                    return self._error("FIFO_TRANSITION_IMPACT_MISMATCH")
                case_payload = case_result["case"]
                evidence_fingerprint = self._transition_evidence_fingerprint(
                    connection, case_id, case_payload,
                )
                if evidence_fingerprint != preview_row["evidence_set_fingerprint"]:
                    connection.rollback()
                    return self._error("FIFO_TRANSITION_PREVIEW_STALE")
                stream_id = "fifo_" + self._sha256(identity)[:40]
                stream = connection.execute(
                    """SELECT revision, policy_version, state FROM fifo_cost_streams
                       WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                    (stream_id, identity["store_id"], self._sha256(identity)),
                ).fetchone()
                projection = connection.execute(
                    """SELECT revision, state, known_quantity, known_cost_rub,
                              next_unit_cost_rub, queue_complete, cutoff_status,
                              inventory_cutoff, source_set_fingerprint, last_event_id
                       FROM fifo_cost_projections WHERE stream_id=?""",
                    (stream_id,),
                ).fetchone()
                if stream is None and projection is None:
                    persisted_cutover = payload.get("initial_opening_cutover")
                    if persisted_cutover is None:
                        connection.rollback()
                        return self._error("FIFO_HISTORY_NOT_INITIALIZED")
                    normalized_cutover = self._normalize_transition_initial_cutover(
                        connection, persisted_cutover, cutoff_bridge,
                        case_payload, recorded_at=persisted_cutover.get("recorded_at"),
                    )
                    if (
                        isinstance(normalized_cutover, str)
                        or normalized_cutover != persisted_cutover
                    ):
                        connection.rollback()
                        return self._error("FIFO_TRANSITION_PREVIEW_STALE")
                    identity_conflict = self._identity_stream_conflict(
                        connection, identity, self._sha256(identity),
                    )
                    if identity_conflict is not None:
                        connection.rollback()
                        return identity_conflict
                    self._insert_transition_initial_cutover(
                        connection, identity=identity, bridge=cutoff_bridge,
                        cutover=normalized_cutover,
                    )
                    stream = connection.execute(
                        """SELECT revision, policy_version, state FROM fifo_cost_streams
                           WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                        (stream_id, identity["store_id"], self._sha256(identity)),
                    ).fetchone()
                    projection = connection.execute(
                        """SELECT revision, state, known_quantity, known_cost_rub,
                                  next_unit_cost_rub, queue_complete, cutoff_status,
                                  inventory_cutoff, source_set_fingerprint, last_event_id
                           FROM fifo_cost_projections WHERE stream_id=?""",
                        (stream_id,),
                    ).fetchone()
                elif stream is None or projection is None:
                    connection.rollback()
                    return self._error("FIFO_HISTORY_INCOMPLETE")
                current_allocation_revision = connection.execute(
                    "SELECT COALESCE(MAX(revision), 0) FROM fifo_cost_allocations "
                    "WHERE stream_id=?", (stream_id,),
                ).fetchone()[0]
                if (
                    stream["revision"] != preview_row["fifo_revision"]
                    or current_allocation_revision != preview_row["allocation_revision"]
                    or projection["revision"] != stream["revision"]
                    or projection["cutoff_status"] != "RECONCILED"
                    or projection["queue_complete"] != 1
                    or projection["inventory_cutoff"] != cutoff_bridge.cutoff_date
                ):
                    connection.rollback()
                    return self._error("FIFO_TRANSITION_PREVIEW_STALE")
                bridge_error = self._validate_transition_bridge_ledger(
                    connection, stream_id, cutoff_bridge,
                )
                if bridge_error:
                    connection.rollback()
                    return self._error(bridge_error)
                current_base_source_fingerprint = self._allocation_source_fingerprint(
                    connection, stream_id, stream["revision"],
                    stream["policy_version"], projection["cutoff_status"],
                )
                if current_base_source_fingerprint != payload["base_source_fingerprint"]:
                    connection.rollback()
                    return self._error("FIFO_TRANSITION_PREVIEW_STALE")
                rate = payload["rate"]
                if (
                    rate["rate_change_id"] != "rate_transition_" + self._sha256({
                        "case_id": case_id,
                        "case_revision": expected_case_revision - 1,
                        "effective_date": payload["effective_date"],
                        "unit_cost_rub": case_payload.get("new_unit_cost_rub"),
                        "bridge": cutoff_bridge.source_set_fingerprint,
                    })[:40]
                    or rate["unit_cost_rub"] != self._normalize_money(
                        case_payload.get("new_unit_cost_rub"),
                    )
                    or rate["owner_old_home_units"] != case_payload.get(
                        "owner_old_home_units",
                    )
                ):
                    connection.rollback()
                    return self._error("FIFO_TRANSITION_CASE_MISMATCH")
                existing_rate_count = connection.execute(
                    """SELECT COUNT(*) FROM fifo_cost_rate_changes AS r
                       WHERE r.stream_id=? AND NOT EXISTS (
                           SELECT 1 FROM fifo_cost_rate_cancellations AS c
                           WHERE c.stream_id=r.stream_id AND c.rate_change_id=r.rate_change_id
                       )""", (stream_id,),
                ).fetchone()[0]
                if existing_rate_count:
                    connection.rollback()
                    return self._error("FIFO_REPLAY_RATE_TRANSITION_UNSUPPORTED")
                self._apply_transition_rate_and_allocation(
                    connection, stream_id=stream_id, identity=identity,
                    stream=stream, projection=projection,
                    payload=payload, now=now, now_text=now_text,
                    idempotency_key=idempotency_key,
                )
                applied = FifoCostTransitionStore.apply_case_preview(
                    connection, case_id=case_id, scope=scope, identity=identity,
                    expected_case_revision=expected_case_revision,
                    preview_id=preview_id, idempotency_key=idempotency_key,
                    payload_fingerprint=commit_payload_fingerprint,
                    complete_through=payload["complete_through"],
                    committed_at=now_text,
                )
                if applied.get("error"):
                    connection.rollback()
                    return applied
                connection.commit()
                return applied
            except (ValueError, TypeError, KeyError, InvalidOperation, OverflowError) as exc:
                if connection.in_transaction:
                    connection.rollback()
                code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_TRANSITION_COMMIT_INVALID"
                return self._error(code)
            except sqlite3.IntegrityError:
                if connection.in_transaction:
                    connection.rollback()
                return self._error("FIFO_TRANSITION_REVISION_CONFLICT")
            except sqlite3.Error:
                if connection.in_transaction:
                    connection.rollback()
                return self._error("FIFO_TRANSITION_STORAGE_UNAVAILABLE")
            finally:
                connection.close()
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_TRANSITION_COMMIT_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            return self._error("FIFO_TRANSITION_STORAGE_UNAVAILABLE")

    def _normalize_transition_initial_cutover(
        self, connection, cutover, bridge, case, *, recorded_at,
    ):
        """Validate an explicit owner-reviewed opening queue against the bridge.

        This is the only permitted way for late-entry confirmation to initialize
        a missing FIFO stream. Quantities are not inferred from turnover totals,
        shipment declarations, or absent stock buckets.
        """
        required = {
            "schema_version", "case_id", "case_revision", "cutoff_date",
            "stock_report_fingerprint", "layers",
            "ozon_units_include_reserved_confirmed",
            "transit_not_in_ozon_confirmed",
        }
        extended = required | {"cutover_fingerprint", "recorded_at"}
        if not isinstance(cutover, dict) or frozenset(cutover) not in {frozenset(required), frozenset(extended)}:
            return "FIFO_INITIAL_CUTOVER_INVALID"
        if (
            cutover.get("schema_version") != 1
            or cutover.get("case_id") != bridge.case_id
            or cutover.get("case_revision") != bridge.case_revision
            or cutover.get("cutoff_date") != bridge.cutoff_date
            or cutover.get("ozon_units_include_reserved_confirmed") is not True
            or cutover.get("transit_not_in_ozon_confirmed") is not True
            or not self._valid_digest(cutover.get("stock_report_fingerprint"))
            or cutover["stock_report_fingerprint"] not in set(
                bridge.provenance_by_basis.get("stock_scope", ()),
            )
            or not isinstance(case, dict)
        ):
            return "FIFO_INITIAL_CUTOVER_NOT_CONFIRMED"
        normalized_at = self._normalize_timestamp(recorded_at)
        if normalized_at is None:
            return "FIFO_CLOCK_INVALID"
        if set(cutover) == set(extended):
            if (
                cutover.get("recorded_at") != normalized_at
                or not self._valid_digest(cutover.get("cutover_fingerprint"))
            ):
                return "FIFO_INITIAL_CUTOVER_INVALID"
        report = connection.execute(
            """SELECT report_type, period_from, period_to, period_provenance,
                      completeness, normalized_fields_json
               FROM fifo_cost_report_evidence
               WHERE case_id=? AND file_sha256=? LIMIT 1""",
            (bridge.case_id, cutover["stock_report_fingerprint"]),
        ).fetchone()
        if (
            report is None
            or report["report_type"] != "STOCK_MANAGEMENT"
            or report["period_from"] != bridge.cutoff_date
            or report["period_to"] != bridge.cutoff_date
            or report["period_provenance"] != "OWNER_CONFIRMED"
            or report["completeness"] != "COMPLETE"
        ):
            return "FIFO_INITIAL_CUTOVER_STOCK_EVIDENCE_UNAVAILABLE"
        try:
            stock_fields = json.loads(report["normalized_fields_json"])
        except (TypeError, ValueError):
            return "FIFO_INITIAL_CUTOVER_STOCK_EVIDENCE_UNAVAILABLE"
        buckets = stock_fields.get("stock_buckets")
        if not isinstance(buckets, dict):
            return "FIFO_INITIAL_CUTOVER_STOCK_EVIDENCE_UNAVAILABLE"
        available = buckets.get("available")
        reserved = buckets.get("reserved")
        if (
            type(available) is not int or available < 0
            or type(reserved) is not int or reserved < 0
        ):
            return "FIFO_INITIAL_CUTOVER_STOCK_SCOPE_UNPROVEN"
        fbs_return_units = stock_fields.get("fbs_return_available_units")
        if (
            type(fbs_return_units) is not int
            or fbs_return_units < 0
            or stock_fields.get("fbs_return_is_subset_of_available") is not True
        ):
            return "FIFO_INITIAL_CUTOVER_RETURN_BASIS_UNAVAILABLE"
        if fbs_return_units != 0:
            return "FIFO_INITIAL_CUTOVER_RETURN_BASIS_UNAVAILABLE"
        confirmed_buckets = dict(bridge.confirmed_stock_buckets)
        if not confirmed_buckets or any(
            buckets.get(name) != quantity
            for name, quantity in confirmed_buckets.items()
        ):
            return "FIFO_INITIAL_CUTOVER_STOCK_SCOPE_UNPROVEN"
        if any(
            buckets.get(name) not in (0, None)
            for name in ("preparing", "checking")
        ):
            return "FIFO_INITIAL_CUTOVER_STOCK_BUCKET_UNRESOLVED"
        if not isinstance(cutover.get("layers"), list):
            return "FIFO_INITIAL_CUTOVER_LAYERS_REQUIRED"
        try:
            from services.fifo_cost_anchor_service import FifoCostAnchorService

            layers, layer_error = FifoCostAnchorService._layers(cutover["layers"])
        except (TypeError, ValueError):
            return "FIFO_INITIAL_CUTOVER_LAYERS_INVALID"
        if layer_error or not layers:
            return layer_error or "FIFO_INITIAL_CUTOVER_LAYERS_REQUIRED"
        totals = {
            name: sum(layer[name] for layer in layers)
            for name in ("ozon_units", "transit_units", "home_units")
        }
        if (
            totals["ozon_units"] != available + reserved
            or totals["transit_units"] != case.get("owner_old_transit_units")
            or totals["home_units"] != case.get("owner_old_home_units")
            or sum(totals.values()) <= 0
        ):
            return "FIFO_INITIAL_CUTOVER_QUANTITY_MISMATCH"
        old_cost = self._normalize_money(case.get("old_unit_cost_rub"))
        if old_cost is None:
            return "FIFO_TRANSITION_BASELINE_COST_UNAVAILABLE"
        new_cost = self._normalize_money(case.get("new_unit_cost_rub"))
        if new_cost is None:
            return "FIFO_RATE_COST_INPUT_INVALID"
        allowed_costs = {old_cost, new_cost}
        layer_costs = [layer["unit_cost_rub"] for layer in layers]
        if any(cost not in allowed_costs for cost in layer_costs):
            return "FIFO_INITIAL_CUTOVER_COST_MISMATCH"
        new_layer_seen = False
        for layer_cost in layer_costs:
            if layer_cost == new_cost:
                new_layer_seen = True
            elif layer_cost == old_cost and new_layer_seen:
                return "FIFO_INITIAL_CUTOVER_LAYER_ORDER_CONFLICT"
        normalized = {
            "schema_version": 1,
            "case_id": bridge.case_id,
            "case_revision": bridge.case_revision,
            "cutoff_date": bridge.cutoff_date,
            "stock_report_fingerprint": cutover["stock_report_fingerprint"],
            "layers": layers,
            "ozon_units_include_reserved_confirmed": True,
            "transit_not_in_ozon_confirmed": True,
            "recorded_at": normalized_at,
        }
        fingerprint = self._sha256({
            key: value for key, value in normalized.items() if key != "recorded_at"
        })
        if set(cutover) == set(extended) and cutover["cutover_fingerprint"] != fingerprint:
            return "FIFO_INITIAL_CUTOVER_FINGERPRINT_INVALID"
        normalized["cutover_fingerprint"] = fingerprint
        return normalized

    def _insert_transition_initial_cutover(
        self, connection, *, identity, bridge, cutover,
    ):
        """Insert a verified owner-confirmed anchor and bridge sales in caller txn."""
        stream_id = "fifo_" + self._sha256(identity)[:40]
        identity_fingerprint = self._sha256(identity)
        if connection.execute(
            "SELECT 1 FROM fifo_cost_streams WHERE stream_id=? LIMIT 1",
            (stream_id,),
        ).fetchone() is not None:
            raise ValueError("FIFO_INITIAL_CUTOVER_ALREADY_EXISTS")
        now_text = cutover["recorded_at"]
        cutover_fp = cutover["cutover_fingerprint"]
        source_material = {
            "source": "OWNER_CONFIRMED_FIFO_CUTOFF",
            "cutover_fingerprint": cutover_fp,
            "bridge_fingerprint": bridge.source_set_fingerprint,
        }
        anchor_source = self._normalize_source({
            "kind": "OWNER_CONFIRMATION",
            "method": "OWNER_CONFIRMED_FIFO_CUTOFF",
            "status": "OWNER_CONFIRMED",
            "completeness": "OWNER_CONFIRMED",
            "provenance": "OWNER_CONFIRMED",
            "coverage_status": "OWNER_CONFIRMED",
            "fingerprint": self._sha256(source_material),
            "captured_at": now_text,
            "inventory_cutoff": bridge.cutoff_date,
            "record_count": len(cutover["layers"]),
            "page_count": 1,
            "references": [
                {"kind": "DOCUMENT", "digest": cutover["stock_report_fingerprint"]},
                {"kind": "OTHER", "digest": cutover_fp},
            ],
        })
        anchor_source_id = "src_" + self._sha256({
            "store_id": identity["store_id"],
            "source_fingerprint": anchor_source["source_fingerprint"],
        })[:40]
        self._ensure_source(connection, {
            "identity": identity, "source": anchor_source,
            "source_id": anchor_source_id,
        })
        connection.execute(
            """INSERT INTO fifo_cost_streams (
                stream_id, store_id, product_id, offer_id, sku,
                identity_fingerprint, policy_version, state, revision,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'FIFO_READY', 1, ?, ?)""",
            (stream_id, identity["store_id"], identity["product_id"],
             identity["offer_id"], identity["sku"], identity_fingerprint,
             identity["policy_version"], now_text, now_text),
        )
        command_id = "cmd_" + self._sha256({
            "case_id": bridge.case_id, "cutover_fingerprint": cutover_fp,
            "bridge_fingerprint": bridge.source_set_fingerprint,
        })[:32]
        event_ids = []
        command_fingerprint = self._sha256({
            "cutover_fingerprint": cutover_fp,
            "bridge_fingerprint": bridge.source_set_fingerprint,
            "layers": cutover["layers"],
            "post_cutoff_events": [
                (item.source_identity_digest, item.quantity, item.physical_effective_date)
                for item in bridge.post_cutoff_events
            ],
        })
        expected_events = sum(
            sum(layer[zone] > 0 for zone in ("ozon_units", "transit_units", "home_units"))
            for layer in cutover["layers"]
        ) + len(bridge.post_cutoff_events)
        if expected_events <= 0 or expected_events > self.MAX_COMMAND_EVENTS:
            raise ValueError("FIFO_COMMAND_EVENT_LIMIT")
        connection.execute(
            """INSERT INTO fifo_cost_commands (
                command_id, stream_id, stream_revision, payload_fingerprint,
                source_fingerprint, event_count, created_at
            ) VALUES (?, ?, 1, ?, ?, ?, ?)""",
            (command_id, stream_id, command_fingerprint,
             bridge.source_set_fingerprint, expected_events, now_text),
        )
        order = 0
        location_by_zone = {"ozon_units": "OZON", "transit_units": "TRANSIT", "home_units": "HOME"}
        for layer in cutover["layers"]:
            for zone in ("ozon_units", "transit_units", "home_units"):
                quantity = layer[zone]
                if not quantity:
                    continue
                order += 1
                event_id = "evt_" + self._sha256({
                    "cutover_fingerprint": cutover_fp,
                    "layer_sequence": layer["sequence"], "zone": zone,
                })[:32]
                layer_id = "layer_" + self._sha256({
                    "cutover_fingerprint": cutover_fp,
                    "layer_sequence": layer["sequence"], "zone": zone,
                })[:32]
                connection.execute(
                    """INSERT INTO fifo_cost_events (
                        event_id, stream_id, event_kind, event_schema_version,
                        effective_at, effective_date, recorded_at, captured_at,
                        source_as_of, inventory_cutoff, quantity, unit_cost_rub,
                        purchase_cost_rub, delivery_cost_rub, packaging_cost_rub,
                        currency, location_from, location_to, source_id,
                        source_fingerprint, provenance, completeness,
                        source_identity_digest, supersedes_event_id, reason_code, created_at
                    ) VALUES (?, ?, 'OPENING_FIFO_ANCHOR', 1, NULL, ?, ?, ?, NULL,
                              ?, ?, ?, NULL, NULL, NULL, 'RUB', NULL, ?, ?, ?,
                              'OWNER_CONFIRMED', 'OWNER_CONFIRMED', NULL, NULL, NULL, ?)""",
                    (event_id, stream_id, bridge.cutoff_date, now_text, now_text,
                     bridge.cutoff_date, quantity, layer["unit_cost_rub"],
                     location_by_zone[zone], anchor_source_id,
                     anchor_source["source_fingerprint"], now_text),
                )
                connection.execute(
                    """INSERT INTO fifo_cost_layers (
                        layer_id, stream_id, event_id, layer_sequence, quantity,
                        unit_cost_rub, currency, effective_at, effective_date,
                        provenance, source_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'RUB', NULL, ?,
                              'OWNER_CONFIRMED', ?, ?)""",
                    (layer_id, stream_id, event_id, order, quantity,
                     layer["unit_cost_rub"], bridge.cutoff_date,
                     anchor_source_id, now_text),
                )
                connection.execute(
                    "INSERT INTO fifo_cost_command_events (command_id, event_id, event_order) VALUES (?, ?, ?)",
                    (command_id, event_id, order),
                )
                event_ids.append(event_id)
        for event in sorted(
            bridge.post_cutoff_events,
            key=lambda row: (row.physical_effective_date, row.source_identity_digest),
        ):
            order += 1
            event_source = self._normalize_source({
                "kind": "OZON_API",
                "method": "OZON_REALIZATION_REPORT",
                "status": "COMPLETE",
                "completeness": "COMPLETE",
                "provenance": "OZON_CONFIRMED_FIELD",
                "coverage_status": "COMPLETE",
                "fingerprint": self._sha256({
                    "bridge_fingerprint": bridge.source_set_fingerprint,
                    "sale_identity_digest": event.source_identity_digest,
                    "physical_effective_date": event.physical_effective_date,
                    "quantity": event.quantity,
                }),
                "captured_at": now_text,
                "inventory_cutoff": bridge.cutoff_date,
                "record_count": 1, "page_count": 1,
                "references": [
                    {"kind": "DOCUMENT", "digest": event.document_fingerprint},
                    {"kind": "OTHER", "digest": event.source_identity_digest},
                ],
            })
            event_source_id = "src_" + self._sha256({
                "store_id": identity["store_id"],
                "source_fingerprint": event_source["source_fingerprint"],
            })[:40]
            self._ensure_source(connection, {
                "identity": identity, "source": event_source,
                "source_id": event_source_id,
            })
            event_id = "evt_" + self._sha256({
                "bridge_fingerprint": bridge.source_set_fingerprint,
                "sale_identity_digest": event.source_identity_digest,
            })[:32]
            connection.execute(
                """INSERT INTO fifo_cost_events (
                    event_id, stream_id, event_kind, event_schema_version,
                    effective_at, effective_date, recorded_at, captured_at,
                    source_as_of, inventory_cutoff, quantity, unit_cost_rub,
                    purchase_cost_rub, delivery_cost_rub, packaging_cost_rub,
                    currency, location_from, location_to, source_id,
                    source_fingerprint, provenance, completeness,
                    source_identity_digest, supersedes_event_id, reason_code, created_at
                ) VALUES (?, ?, 'PHYSICAL_SALE', 1, NULL, ?, ?, ?, NULL, ?, ?,
                          NULL, NULL, NULL, NULL, 'RUB', NULL, NULL, ?, ?,
                'OZON_CONFIRMED_FIELD', 'COMPLETE', ?, NULL, NULL, ?)""",
                (event_id, stream_id, event.physical_effective_date, now_text,
                 now_text, bridge.cutoff_date, event.quantity, event_source_id,
                 event_source["source_fingerprint"], event.source_identity_digest,
                 now_text),
            )
            connection.execute(
                "INSERT INTO fifo_cost_command_events (command_id, event_id, event_order) VALUES (?, ?, ?)",
                (command_id, event_id, order),
            )
            event_ids.append(event_id)
        self._ensure_policy_revision(connection, {
            "identity": identity, "stream_id": stream_id,
        }, self._now())
        total_quantity = sum(
            layer[zone] for layer in cutover["layers"]
            for zone in ("ozon_units", "transit_units", "home_units")
        )
        total_cost = sum(
            (Decimal(layer["unit_cost_rub"]) * sum(
                layer[zone] for zone in ("ozon_units", "transit_units", "home_units")
            ) for layer in cutover["layers"]), Decimal("0.00"),
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        source_set = self._allocation_source_fingerprint(
            connection, stream_id, 1, identity["policy_version"], "RECONCILED",
        )
        connection.execute(
            """INSERT INTO fifo_cost_projections (
                stream_id, revision, state, known_quantity, known_cost_rub,
                next_unit_cost_rub, queue_complete, cutoff_status,
                inventory_cutoff, source_set_fingerprint, last_event_id, updated_at
            ) VALUES (?, 1, 'FIFO_READY', ?, ?, ?, 1, 'RECONCILED', ?, ?, ?, ?)""",
            (stream_id, total_quantity, format(total_cost, ".2f"),
             cutover["layers"][0]["unit_cost_rub"], bridge.cutoff_date,
             source_set, event_ids[-1], now_text),
        )

    @classmethod
    def _validate_transition_bridge(cls, bridge, *, case_id, expected_case_revision,
                                    identity, owner_id):
        scope = getattr(bridge, "scope", None)
        if (
            bridge.status != "READY"
            or bridge.ready_for_fifo_event is not True
            or bridge.preview_only is not True
            or bridge.unresolved_issues
            or bridge.case_id != case_id
            or bridge.case_revision != expected_case_revision
            or scope is None
            or scope.owner_id != owner_id
            or scope.store_id != identity["store_id"]
            or scope.product_id != identity["product_id"]
            or scope.offer_id != identity["offer_id"]
            or scope.sku != identity["sku"]
            or bridge.cutoff_date is None
            or bridge.complete_through is None
            or not cls._valid_digest(bridge.source_set_fingerprint)
        ):
            return "FIFO_CUTOFF_BRIDGE_NOT_READY"
        return None

    @classmethod
    def _validate_transition_case_for_apply(cls, case, *, effective_date, complete_through):
        if not isinstance(effective_date, str) or cls._normalize_date(effective_date) != effective_date:
            return "FIFO_RATE_EFFECTIVE_DATE_INVALID"
        if not isinstance(complete_through, str) or cls._normalize_date(complete_through) != complete_through:
            return "FIFO_TRANSITION_COMPLETE_THROUGH_INVALID"
        if case.get("new_unit_cost_rub") is None:
            return "FIFO_RATE_COST_INPUT_INVALID"
        if type(case.get("owner_old_home_units")) is not int or case["owner_old_home_units"] < 0:
            return "FIFO_RATE_OLD_HOME_QUANTITY_INVALID"
        dispatch_date = case.get("dispatch_date")
        if dispatch_date and effective_date < dispatch_date:
            return "FIFO_RATE_EFFECTIVE_DATE_CONFLICT"
        if effective_date > complete_through:
            return "FIFO_TRANSITION_COMPLETE_THROUGH_INVALID"
        return None

    @classmethod
    def _validate_transition_impact(cls, impact, *, tax_policy_fingerprint):
        if not isinstance(impact, dict) or impact.get("error") is not False:
            return "FIFO_TRANSITION_IMPACT_UNAVAILABLE"
        if (
            impact.get("complete") is not True
            or impact.get("read_only") is not True
            or impact.get("candidate_only") is True
            or impact.get("tax_policy_fingerprint") != tax_policy_fingerprint
            or not cls._valid_digest(tax_policy_fingerprint)
            or not cls._valid_digest(impact.get("preview_fingerprint"))
            or not isinstance(impact.get("periods"), list)
            or not impact["periods"]
        ):
            return "FIFO_TRANSITION_IMPACT_INCOMPLETE"
        material = {
            key: value for key, value in impact.items()
            if key not in {"preview_fingerprint", "code", "error"}
        }
        if cls._sha256(material) != impact["preview_fingerprint"]:
            return "FIFO_TRANSITION_IMPACT_FINGERPRINT_INVALID"
        return None

    @classmethod
    def _transition_impact_matches_replay(
        cls, impact, replay, *, expected_before_cogs=None,
        expected_after_cogs=None, check_after=True,
    ):
        try:
            after = sum(
                (Decimal(str(row["after_sku_cogs_rub"])) for row in impact["periods"]),
                Decimal("0.00"),
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            before = sum(
                (Decimal(str(row["before_sku_cogs_rub"])) for row in impact["periods"]),
                Decimal("0.00"),
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            expected_after = (
                replay.get("total_cogs_rub")
                if expected_after_cogs is None else expected_after_cogs
            )
            before_matches = (
                expected_before_cogs is None
                or format(before, ".2f") == str(expected_before_cogs)
            )
            after_matches = (
                not check_after or format(after, ".2f") == str(expected_after)
            )
            return (
                after_matches
                and before_matches
                and all(row.get("completeness") == "COMPLETE" for row in impact["periods"])
                and before >= Decimal("0.00")
            )
        except (KeyError, TypeError, ValueError, InvalidOperation):
            return False

    @classmethod
    def _validate_transition_bridge_ledger(cls, connection, stream_id, bridge):
        cutoff = bridge.cutoff_date
        rows = connection.execute(
            """SELECT source_identity_digest, quantity, effective_date
               FROM fifo_cost_events WHERE stream_id=? AND event_kind='PHYSICAL_SALE'
               ORDER BY source_identity_digest, effective_date, quantity""",
            (stream_id,),
        ).fetchall()
        expected = sorted(
            (event.source_identity_digest, event.quantity, event.physical_effective_date)
            for event in bridge.post_cutoff_events
        )
        actual = sorted(
            (row["source_identity_digest"], row["quantity"], row["effective_date"])
            for row in rows
        )
        if any(row["effective_date"] <= cutoff for row in rows) or actual != expected:
            return "FIFO_TRANSITION_SALE_BRIDGE_MISMATCH"
        counts = connection.execute(
            """SELECT event_kind, COUNT(*) AS count
               FROM fifo_cost_events WHERE stream_id=?
                 AND event_kind IN ('SALEABLE_RETURN_RESTOCK', 'NON_SALE_OUTFLOW')
               GROUP BY event_kind""",
            (stream_id,),
        ).fetchall()
        ledger_count = sum(row["count"] for row in counts)
        if ledger_count != len(bridge.linked_returns_non_sale_movements):
            return "FIFO_TRANSITION_MOVEMENT_BRIDGE_MISMATCH"
        return None

    @classmethod
    def _transition_evidence_fingerprint(cls, connection, case_id, case_payload):
        case_material = {
            key: value for key, value in case_payload.items()
            if key not in {
                "case_revision", "state", "updated_at", "_command_fingerprint",
                "last_preview", "last_commit", "last_evidence",
            }
        }
        rows = {}
        queries = {
            "declarations": "SELECT declaration_id, declaration_revision, payload_fingerprint, "
                "payload_json, recorded_at FROM fifo_cost_supply_declarations "
                "WHERE case_id=? ORDER BY declaration_id, declaration_revision",
            "observations": "SELECT observation_id, declaration_id, source_fingerprint, "
                "payload_json, captured_at FROM fifo_cost_supply_observations "
                "WHERE case_id=? ORDER BY observation_id",
            "reports": "SELECT report_evidence_id, report_type, period_from, period_to, "
                "period_provenance, captured_at, file_sha256, parser_version, source_kind, "
                "completeness, source_fingerprint, cell_references_json, normalized_fields_json "
                "FROM fifo_cost_report_evidence WHERE case_id=? "
                "ORDER BY report_type, file_sha256, report_evidence_id",
        }
        for key, query in queries.items():
            result = connection.execute(query, (case_id,)).fetchall()
            rows[key] = [dict(row) for row in result]
        if sum(len(value) for value in rows.values()) > 2200:
            raise ValueError("FIFO_TRANSITION_EVIDENCE_LIMIT_REACHED")
        return cls._sha256({"case": case_material, "evidence": rows})

    @staticmethod
    def _require_transition_report_evidence(connection, case_id, bridge):
        stock_fingerprints = set(bridge.provenance_by_basis.get("stock_scope", ()))
        rows = connection.execute(
            """SELECT report_type, file_sha256, completeness
               FROM fifo_cost_report_evidence WHERE case_id=?""",
            (case_id,),
        ).fetchall()
        if not any(
            row["report_type"] == "STOCK_MANAGEMENT"
            and row["file_sha256"] in stock_fingerprints
            and row["completeness"] == "COMPLETE"
            for row in rows
        ):
            raise ValueError("FIFO_TRANSITION_STOCK_EVIDENCE_UNAVAILABLE")
        if not any(
            row["report_type"] == "TURNOVER" and row["completeness"] == "COMPLETE"
            for row in rows
        ):
            raise ValueError("FIFO_TRANSITION_TURNOVER_EVIDENCE_UNAVAILABLE")

    def _apply_transition_rate_and_allocation(
        self, connection, *, stream_id, identity, stream, projection,
        payload, now, now_text, idempotency_key,
    ):
        rate = payload["rate"]
        replay = payload["allocation_preview"]
        normalized = self._normalize_allocation_preview(
            replay, "transition-apply-" + self._sha256({
                "preview": payload["case_id"],
                "fingerprint": payload["rate_payload_fingerprint"],
            })[:32],
        )
        if isinstance(normalized, str):
            raise ValueError(normalized)
        current_source = self._allocation_source_fingerprint(
            connection, stream_id, stream["revision"], stream["policy_version"],
            projection["cutoff_status"],
        )
        if current_source != payload["base_source_fingerprint"]:
            raise ValueError("FIFO_TRANSITION_PREVIEW_STALE")
        rate_id = rate["rate_change_id"]
        source = self._normalize_source({
            "kind": "OWNER_CONFIRMATION",
            "method": "OWNER_CONFIRMED_FIFO_TRANSITION",
            "status": "OWNER_CONFIRMED",
            "completeness": "OWNER_CONFIRMED",
            "provenance": "OWNER_CONFIRMED",
            "coverage_status": "OWNER_CONFIRMED",
            "fingerprint": rate["source_fingerprint"],
            "captured_at": now_text,
            "inventory_cutoff": projection["inventory_cutoff"],
            "references": [{
                "kind": "DOCUMENT",
                "digest": payload["bridge_fingerprint"],
            }],
        })
        source_id = "src_" + self._sha256({
            "store_id": identity["store_id"],
            "source_fingerprint": source["source_fingerprint"],
        })[:40]
        self._ensure_source(connection, {
            "identity": identity, "source": source, "source_id": source_id,
        })
        next_revision = stream["revision"] + 1
        next_rate_sequence = connection.execute(
            "SELECT COALESCE(MAX(rate_sequence), 0) + 1 FROM fifo_cost_rate_changes "
            "WHERE stream_id=?", (stream_id,),
        ).fetchone()[0]
        if next_rate_sequence != rate["rate_sequence"]:
            raise ValueError("FIFO_RATE_REVISION_CONFLICT")
        connection.execute(
            """INSERT INTO fifo_cost_rate_changes (
                rate_change_id, stream_id, stream_revision, rate_sequence,
                effective_date, unit_cost_rub, cost_input_mode,
                purchase_cost_rub, delivery_cost_rub, packaging_cost_rub,
                owner_old_home_units, source_id, source_fingerprint,
                payload_fingerprint, idempotency_key, recorded_at, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rate_id, stream_id, next_revision, rate["rate_sequence"],
             rate["effective_date"], rate["unit_cost_rub"], rate["cost_input_mode"],
             rate["purchase_cost_rub"], rate["delivery_cost_rub"],
             rate["packaging_cost_rub"], rate["owner_old_home_units"], source_id,
             rate["source_fingerprint"], payload["rate_payload_fingerprint"],
             rate["idempotency_key"], now_text, now_text),
        )
        connection.execute(
            "UPDATE fifo_cost_streams SET state='FIFO_PARTIAL', revision=?, updated_at=? "
            "WHERE stream_id=? AND revision=?",
            (next_revision, now_text, stream_id, stream["revision"]),
        )
        connection.execute(
            """UPDATE fifo_cost_projections
               SET revision=?, state='FIFO_PARTIAL', queue_complete=0,
                   source_set_fingerprint=?, updated_at=?
               WHERE stream_id=? AND revision=?""",
            (next_revision, payload["candidate_source_fingerprint"], now_text,
             stream_id, projection["revision"]),
        )
        candidate_source = self._allocation_source_fingerprint(
            connection, stream_id, next_revision, stream["policy_version"],
            projection["cutoff_status"],
        )
        if candidate_source != payload["candidate_source_fingerprint"]:
            raise ValueError("FIFO_TRANSITION_PREVIEW_STALE")
        allocation_revision = connection.execute(
            "SELECT COALESCE(MAX(revision), 0) FROM fifo_cost_allocations "
            "WHERE stream_id=?", (stream_id,),
        ).fetchone()[0]
        if allocation_revision != payload["base_allocation_revision"]:
            raise ValueError("FIFO_REVISION_CONFLICT")
        self._validate_allocation_lines(
            connection, stream_id, normalized,
            stream_revision=next_revision,
            allocation_revision=allocation_revision,
            source_fingerprint=candidate_source,
            cutoff_status=projection["cutoff_status"],
        )
        next_allocation_revision = allocation_revision + 1
        allocation_id = "alloc_" + uuid4().hex
        connection.execute(
            """INSERT INTO fifo_cost_allocations (
                allocation_id, stream_id, revision, stream_revision,
                policy_version, source_set_fingerprint, cutoff_status,
                status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'RECONCILED', 'COMPLETE', ?)""",
            (allocation_id, stream_id, next_allocation_revision, next_revision,
             stream["policy_version"], candidate_source, now_text),
        )
        line_number = 0
        for allocation in normalized["allocations"]:
            for line in allocation["lines"]:
                line_number += 1
                basis_allocation_id = None
                basis_line_number = None
                origin_id = line["origin_sale_event_id"]
                if origin_id is not None:
                    if line["layer_id"] is None:
                        raise ValueError("FIFO_ALLOCATION_BASIS_MISSING")
                    basis = connection.execute(
                        """SELECT l.allocation_id, l.line_number
                           FROM fifo_cost_allocation_lines AS l
                           JOIN fifo_cost_allocations AS a ON a.allocation_id=l.allocation_id
                           WHERE a.stream_id=? AND l.event_id=? AND l.layer_id=?
                           ORDER BY a.revision DESC, l.line_number LIMIT 1""",
                        (stream_id, origin_id, line["layer_id"]),
                    ).fetchone()
                    if basis is None:
                        raise ValueError("FIFO_ALLOCATION_BASIS_MISSING")
                    basis_allocation_id, basis_line_number = basis["allocation_id"], basis["line_number"]
                if line["layer_id"] is not None:
                    connection.execute(
                        """INSERT INTO fifo_cost_allocation_lines (
                            allocation_id, line_number, event_id, layer_id,
                            quantity, unit_cost_rub, total_cost_rub,
                            basis_allocation_id, basis_line_number
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (allocation_id, line_number, allocation["event_id"],
                         line["layer_id"], line["quantity"], line["unit_cost_rub"],
                         line["total_cost_rub"], basis_allocation_id, basis_line_number),
                    )
                else:
                    connection.execute(
                        """INSERT INTO fifo_cost_allocation_rate_lines (
                            allocation_id, line_number, event_id, rate_change_id,
                            quantity, unit_cost_rub, total_cost_rub,
                            basis_allocation_id, basis_line_number
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (allocation_id, line_number, allocation["event_id"],
                         line["rate_change_id"], line["quantity"], line["unit_cost_rub"],
                         line["total_cost_rub"], basis_allocation_id, basis_line_number),
                    )
        outflow_line_number = 0
        for outflow in normalized["outflows"]:
            for line in outflow["lines"]:
                outflow_line_number += 1
                connection.execute(
                    """INSERT INTO fifo_cost_allocation_outflow_lines (
                        allocation_id, line_number, event_id, layer_id,
                        quantity, unit_cost_rub, estimated_value_rub,
                        valuation_method
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (allocation_id, outflow_line_number, outflow["event_id"],
                     line["layer_id"], line["quantity"], line["unit_cost_rub"],
                     line["total_cost_rub"], outflow["valuation_method"]),
                )
        if self._replayed_remaining_layers(
            connection, stream_id, next_allocation_revision,
        ) is None:
            raise ValueError("FIFO_ALLOCATION_REPLAY_UNAVAILABLE")
        remaining = self._replayed_remaining_layers(
            connection, stream_id, next_allocation_revision,
        )
        finite_rows = [row for row in remaining if row["remaining_units"] > 0]
        finite_quantity = sum(row["remaining_units"] for row in finite_rows)
        finite_cost = sum(
            (Decimal(row["unit_cost_rub"]) * row["remaining_units"] for row in finite_rows),
            Decimal("0.00"),
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        next_unit_cost = (
            finite_rows[0]["unit_cost_rub"] if finite_rows else rate["unit_cost_rub"]
        )
        connection.execute(
            """UPDATE fifo_cost_projections
               SET revision=?, state='FIFO_READY', known_quantity=?, known_cost_rub=?,
                   next_unit_cost_rub=?, queue_complete=1,
                   source_set_fingerprint=?, last_event_id=?, updated_at=?
               WHERE stream_id=? AND revision=?""",
            (next_revision, finite_quantity, format(finite_cost, ".2f"),
             next_unit_cost, candidate_source, projection["last_event_id"], now_text,
             stream_id, next_revision),
        )
        connection.execute(
            "UPDATE fifo_cost_streams SET state='FIFO_READY', updated_at=? "
            "WHERE stream_id=? AND revision=?",
            (now_text, stream_id, next_revision),
        )
        if line_number > 250_000:
            raise ValueError("FIFO_REPLAY_WORK_LIMIT")

    def read_cost_history_snapshot(
        self, *, store_id, product_id=None, offer_id=None, sku,
    ):
        """Read one exact tenant/store/SKU history without exposing opaque IDs."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        connection = None
        try:
            identity = self._normalize_identity(
                store_id, product_id, offer_id, sku, 1,
            )
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            connection = self.get_connection()
            identity_conflict = self._identity_stream_conflict(
                connection, identity, identity_fingerprint,
            )
            if identity_conflict is not None:
                return identity_conflict
            stream = connection.execute(
                """SELECT state, revision FROM fifo_cost_streams
                   WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                (stream_id, identity["store_id"], identity_fingerprint),
            ).fetchone()
            if stream is None:
                return {
                    "error": False,
                    "code": "FIFO_HISTORY_NOT_INITIALIZED",
                    "revision": 0,
                    "stream_state": "FIFO_PENDING_ANCHOR",
                    "projection": None,
                    "layers": [],
                    "rates": [],
                    "rate_reconciliations": [],
                    "rate_cancellations": [],
                    "event_counts": {},
                    "movement_count": 0,
                    "latest_allocation": None,
                    "cutoff_date": None,
                }

            projection_row = connection.execute(
                """SELECT revision, state, known_quantity, known_cost_rub,
                          next_unit_cost_rub, queue_complete, cutoff_status,
                          updated_at, inventory_cutoff
                   FROM fifo_cost_projections WHERE stream_id=?""",
                (stream_id,),
            ).fetchone()
            projection = None if projection_row is None else {
                "revision": projection_row["revision"],
                "state": projection_row["state"],
                "known_quantity": projection_row["known_quantity"],
                "known_cost_rub": projection_row["known_cost_rub"],
                "next_unit_cost_rub": projection_row["next_unit_cost_rub"],
                "queue_complete": bool(projection_row["queue_complete"]),
                "cutoff_status": projection_row["cutoff_status"],
                "updated_at": projection_row["updated_at"],
                "inventory_cutoff": projection_row["inventory_cutoff"],
            }
            layer_rows = connection.execute(
                """SELECT l.layer_sequence, l.quantity, l.unit_cost_rub,
                          l.effective_date, l.provenance, e.location_to,
                          s.source_status, s.coverage_status
                   FROM fifo_cost_layers AS l
                   JOIN fifo_cost_events AS e ON e.event_id=l.event_id
                   LEFT JOIN fifo_cost_sources AS s ON s.source_id=l.source_id
                   WHERE l.stream_id=?
                   ORDER BY l.layer_sequence""",
                (stream_id,),
            ).fetchall()
            layers = [{
                "sequence": row["layer_sequence"],
                "recorded_quantity": row["quantity"],
                "unit_cost_rub": row["unit_cost_rub"],
                "effective_date": row["effective_date"],
                "provenance": row["provenance"],
                "location": row["location_to"],
                "source_status": row["source_status"],
                "coverage_status": row["coverage_status"],
            } for row in layer_rows]
            rate_rows = connection.execute(
                """SELECT r.rate_change_id, r.rate_sequence, r.effective_date, r.unit_cost_rub,
                          r.cost_input_mode,
                          r.purchase_cost_rub, r.delivery_cost_rub,
                          r.packaging_cost_rub, r.owner_old_home_units,
                          r.recorded_at, r.captured_at, s.provenance,
                          s.source_status, s.coverage_status
                   FROM fifo_cost_rate_changes AS r
                   LEFT JOIN fifo_cost_sources AS s ON s.source_id=r.source_id
                   WHERE r.stream_id=?
                   ORDER BY r.rate_sequence""",
                (stream_id,),
            ).fetchall()
            cancellation_rows = connection.execute(
                """SELECT c.rate_change_id, r.rate_sequence,
                          c.reason_code, c.recorded_at
                   FROM fifo_cost_rate_cancellations AS c
                   JOIN fifo_cost_rate_changes AS r
                     ON r.rate_change_id=c.rate_change_id
                   WHERE c.stream_id=? ORDER BY r.rate_sequence""",
                (stream_id,),
            ).fetchall()
            cancellations_by_rate = {
                row["rate_change_id"]: row for row in cancellation_rows
            }
            rates = [{
                "sequence": row["rate_sequence"],
                "effective_date": row["effective_date"],
                "unit_cost_rub": row["unit_cost_rub"],
                "cost_input_mode": row["cost_input_mode"],
                "purchase_cost_rub": row["purchase_cost_rub"],
                "delivery_cost_rub": row["delivery_cost_rub"],
                "packaging_cost_rub": row["packaging_cost_rub"],
                "owner_old_home_units": row["owner_old_home_units"],
                "recorded_at": row["recorded_at"],
                "captured_at": row["captured_at"],
                "provenance": row["provenance"],
                "source_status": row["source_status"],
                "coverage_status": row["coverage_status"],
                "cancelled": row["rate_change_id"] in cancellations_by_rate,
                "cancellation_reason_code": (
                    cancellations_by_rate[row["rate_change_id"]]["reason_code"]
                    if row["rate_change_id"] in cancellations_by_rate else None
                ),
                "cancelled_at": (
                    cancellations_by_rate[row["rate_change_id"]]["recorded_at"]
                    if row["rate_change_id"] in cancellations_by_rate else None
                ),
            } for row in rate_rows]
            rate_cancellations = [{
                "rate_sequence": row["rate_sequence"],
                "reason_code": row["reason_code"],
                "recorded_at": row["recorded_at"],
            } for row in cancellation_rows]
            reconciliation_rows = connection.execute(
                """SELECT transition_rate_sequence, reconciled_rate_sequence,
                          reconciled_total_units, older_finite_units,
                          prior_rate_units, fbo_units, reserved_units,
                          transit_units, home_units, captured_at
                   FROM fifo_cost_rate_reconciliations
                   WHERE stream_id=? ORDER BY transition_rate_sequence""",
                (stream_id,),
            ).fetchall()
            rate_reconciliations = [{
                "transition_rate_sequence": row["transition_rate_sequence"],
                "reconciled_rate_sequence": row["reconciled_rate_sequence"],
                "reconciled_total_units": row["reconciled_total_units"],
                "older_finite_units": row["older_finite_units"],
                "prior_rate_units": row["prior_rate_units"],
                "fbo_units": row["fbo_units"],
                "reserved_units": row["reserved_units"],
                "transit_units": row["transit_units"],
                "home_units": row["home_units"],
                "captured_at": row["captured_at"],
            } for row in reconciliation_rows]
            event_rows = connection.execute(
                """SELECT event_kind, COUNT(*) AS event_count
                   FROM fifo_cost_events WHERE stream_id=?
                   GROUP BY event_kind""",
                (stream_id,),
            ).fetchall()
            event_counts = {row["event_kind"]: row["event_count"] for row in event_rows}
            movement_count = sum(
                count for kind, count in event_counts.items()
                if kind not in {"OPENING_FIFO_ANCHOR", "COST_LAYER_RECEIPT"}
            )
            allocation = connection.execute(
                """SELECT revision, stream_revision, status, cutoff_status, created_at
                   FROM fifo_cost_allocations WHERE stream_id=?
                   ORDER BY revision DESC LIMIT 1""",
                (stream_id,),
            ).fetchone()
            latest_allocation = None if allocation is None else {
                "revision": allocation["revision"],
                "stream_revision": allocation["stream_revision"],
                "status": allocation["status"],
                "cutoff_status": allocation["cutoff_status"],
                "stale": allocation["stream_revision"] != stream["revision"],
                "created_at": allocation["created_at"],
            }
            if latest_allocation is not None:
                if (
                    allocation["status"] == "COMPLETE"
                    and allocation["cutoff_status"] == "RECONCILED"
                    and allocation["stream_revision"] == stream["revision"]
                ):
                    latest_allocation["replayed_remaining_layers"] = (
                        self._replayed_remaining_layers(
                            connection, stream_id, allocation["revision"],
                        )
                    )
                else:
                    latest_allocation["replayed_remaining_layers"] = None
            cutoff_date = connection.execute(
                """SELECT MIN(inventory_cutoff) FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='OPENING_FIFO_ANCHOR'""",
                (stream_id,),
            ).fetchone()[0]
            cutoff_date = cutoff_date or (
                projection["inventory_cutoff"] if projection else None
            )
            return {
                "error": False,
                "code": "FIFO_HISTORY_READY",
                "revision": stream["revision"],
                "stream_state": stream["state"],
                "projection": projection,
                "layers": layers,
                "rates": rates,
                "rate_reconciliations": rate_reconciliations,
                "rate_cancellations": rate_cancellations,
                "event_counts": event_counts,
                "movement_count": movement_count,
                "latest_allocation": latest_allocation,
                "cutoff_date": cutoff_date,
            }
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_IDENTITY_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _replayed_remaining_layers(connection, stream_id, allocation_revision):
        allocation = connection.execute(
            """SELECT allocation_id FROM fifo_cost_allocations
               WHERE stream_id=? AND revision=? AND status='COMPLETE'
                 AND cutoff_status='RECONCILED' LIMIT 1""",
            (stream_id, allocation_revision),
        ).fetchone()
        if allocation is None:
            return None
        rows = connection.execute(
            """SELECT l.layer_id, l.layer_sequence, l.quantity,
                      l.unit_cost_rub, l.effective_date, l.provenance,
                      e.location_to
               FROM fifo_cost_layers AS l
               JOIN fifo_cost_events AS e ON e.event_id=l.event_id
               WHERE l.stream_id=? ORDER BY l.layer_sequence LIMIT 100001""",
            (stream_id,),
        ).fetchall()
        if len(rows) > 100_000:
            return None
        remaining = {row["layer_id"]: row["quantity"] for row in rows}
        allocation_id = allocation["allocation_id"]
        consumed = connection.execute(
            """SELECT e.event_kind, l.layer_id, SUM(l.quantity) AS quantity
               FROM fifo_cost_allocation_lines AS l
               JOIN fifo_cost_events AS e ON e.event_id=l.event_id
               WHERE l.allocation_id=? GROUP BY e.event_kind, l.layer_id""",
            (allocation_id,),
        ).fetchall()
        for row in consumed:
            if row["event_kind"] == "PHYSICAL_SALE":
                if row["layer_id"] not in remaining or row["quantity"] is None:
                    return None
                remaining[row["layer_id"]] -= row["quantity"]
        restored = connection.execute(
            """SELECT b.layer_id, SUM(b.quantity) AS quantity
               FROM fifo_cost_return_basis AS b
               JOIN fifo_cost_events AS e ON e.event_id=b.return_event_id
               WHERE e.stream_id=? AND e.event_kind='SALEABLE_RETURN_RESTOCK'
                 AND b.layer_id IS NOT NULL
               GROUP BY b.layer_id""",
            (stream_id,),
        ).fetchall()
        for row in restored:
            if row["layer_id"] not in remaining or row["quantity"] is None:
                return None
            remaining[row["layer_id"]] += row["quantity"]
        outflows = connection.execute(
            """SELECT layer_id, SUM(quantity) AS quantity
               FROM fifo_cost_allocation_outflow_lines
               WHERE allocation_id=? GROUP BY layer_id""",
            (allocation_id,),
        ).fetchall()
        for row in outflows:
            if row["layer_id"] not in remaining or row["quantity"] is None:
                return None
            remaining[row["layer_id"]] -= row["quantity"]
        if any(quantity < 0 for quantity in remaining.values()):
            return None
        return [{
            "sequence": row["layer_sequence"],
            "recorded_quantity": row["quantity"],
            "remaining_units": remaining[row["layer_id"]],
            "unit_cost_rub": row["unit_cost_rub"],
            "effective_date": row["effective_date"],
            "provenance": row["provenance"],
            "location": row["location_to"],
        } for row in rows]

    def read_allocation_guard(self, *, store_id, product_id=None, offer_id=None, sku):
        """Return the current replay CAS token without exposing event payloads."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        connection = None
        try:
            identity = self._normalize_identity(
                store_id, product_id, offer_id, sku, 1,
            )
            fingerprint = self._sha256(identity)
            stream_id = "fifo_" + fingerprint[:40]
            connection = self.get_connection()
            identity_conflict = self._identity_stream_conflict(
                connection, identity, fingerprint,
            )
            if identity_conflict is not None:
                return identity_conflict
            stream = connection.execute(
                """SELECT revision, policy_version, state
                   FROM fifo_cost_streams
                   WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                (stream_id, identity["store_id"], fingerprint),
            ).fetchone()
            if stream is None:
                return self._error("FIFO_HISTORY_NOT_INITIALIZED")
            projection = connection.execute(
                """SELECT cutoff_status, queue_complete
                   FROM fifo_cost_projections WHERE stream_id=?""",
                (stream_id,),
            ).fetchone()
            if projection is None:
                return self._error("FIFO_PROJECTION_UNAVAILABLE")
            allocation_revision = connection.execute(
                """SELECT COALESCE(MAX(revision), 0)
                   FROM fifo_cost_allocations WHERE stream_id=?""",
                (stream_id,),
            ).fetchone()[0]
            event_count = connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_events WHERE stream_id=?",
                (stream_id,),
            ).fetchone()[0]
            if event_count > 100_000:
                return self._error("FIFO_REPLAY_INPUT_LIMIT")
            source_fingerprint = self._allocation_source_fingerprint(
                connection, stream_id, stream["revision"],
                stream["policy_version"], projection["cutoff_status"],
            )
            untrusted_sale_count = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_events AS e
                   LEFT JOIN fifo_cost_sources AS s ON s.source_id=e.source_id
                   WHERE e.stream_id=? AND e.event_kind='PHYSICAL_SALE' AND NOT (
                       e.provenance='OZON_CONFIRMED_FIELD'
                       AND e.completeness='COMPLETE'
                       AND s.source_method='OZON_REALIZATION_REPORT'
                       AND s.source_status='COMPLETE'
                       AND s.coverage_status='COMPLETE'
                   )""",
                (stream_id,),
            ).fetchone()[0]
            anchor_meta = connection.execute(
                """SELECT COUNT(DISTINCT inventory_cutoff), MIN(inventory_cutoff)
                   FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='OPENING_FIFO_ANCHOR'""",
                (stream_id,),
            ).fetchone()
            anchor_cutoff_date = (
                anchor_meta[1] if anchor_meta[0] == 1 else None
            )
            unsupported_event_count = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind NOT IN (
                       'OPENING_FIFO_ANCHOR', 'PHYSICAL_SALE',
                       'SALEABLE_RETURN_RESTOCK', 'NON_SALE_OUTFLOW'
                   )""",
                (stream_id,),
            ).fetchone()[0]
            rate_count = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_rate_changes AS r
                   WHERE r.stream_id=? AND NOT EXISTS (
                       SELECT 1 FROM fifo_cost_rate_cancellations AS c
                       WHERE c.stream_id=r.stream_id
                         AND c.rate_change_id=r.rate_change_id
                   )""",
                (stream_id,),
            ).fetchone()[0]
            rate_cancellation_count = connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_rate_cancellations WHERE stream_id=?",
                (stream_id,),
            ).fetchone()[0]
            cutoff_mismatch_sale_count = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='PHYSICAL_SALE'
                     AND (effective_date IS NULL OR inventory_cutoff IS NULL
                          OR inventory_cutoff<>? OR effective_date<=?)""",
                (stream_id, anchor_cutoff_date or "", anchor_cutoff_date or ""),
            ).fetchone()[0]
            replay = None
            if (
                stream["state"] in {"FIFO_READY", "FIFO_PARTIAL"}
                and projection["cutoff_status"] == "RECONCILED"
                and untrusted_sale_count == 0
                and anchor_cutoff_date is not None
                and unsupported_event_count == 0
                and rate_count <= 1
                and cutoff_mismatch_sale_count == 0
            ):
                replay = self._preview_allocation_from_connection(
                    connection, stream_id,
                    stream_revision=stream["revision"],
                    allocation_revision=allocation_revision,
                    source_fingerprint=source_fingerprint,
                    cutoff_status=projection["cutoff_status"],
                    anchor_cutoff_date=anchor_cutoff_date,
                )
            replay_ready = replay is not None and replay.get("complete") is True
            return {
                "error": False,
                "code": "FIFO_ALLOCATION_GUARD_READY",
                "stream_revision": stream["revision"],
                "allocation_revision": allocation_revision,
                "policy_version": stream["policy_version"],
                "stream_state": stream["state"],
                "cutoff_status": projection["cutoff_status"],
                "queue_complete": bool(projection["queue_complete"]),
                "source_set_fingerprint": source_fingerprint,
                "event_count": event_count,
                "untrusted_sale_count": untrusted_sale_count,
                "anchor_cutoff_date": anchor_cutoff_date,
                "unsupported_event_count": unsupported_event_count,
                "unsupported_rate_transition_count": max(0, rate_count - 1),
                "rate_cancellation_count": rate_cancellation_count,
                "cutoff_mismatch_sale_count": cutoff_mismatch_sale_count,
                "replay_reason_code": (
                    None if replay_ready else
                    replay.get("reason_code") if replay is not None else
                    "FIFO_REPLAY_SOURCE_GATE_UNRESOLVED"
                ),
                "eligible_for_publication": (
                    stream["state"] in {"FIFO_READY", "FIFO_PARTIAL"}
                    and projection["cutoff_status"] == "RECONCILED"
                    and untrusted_sale_count == 0
                    and anchor_cutoff_date is not None
                    and unsupported_event_count == 0
                    and rate_count <= 1
                    and cutoff_mismatch_sale_count == 0
                    and replay_ready
                ),
            }
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_IDENTITY_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def read_physical_sale_event_reference(
        self, *, store_id, product_id=None, offer_id=None, sku,
        source_identity_digest,
    ):
        """Resolve one redacted sale digest to its internal FIFO event reference."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        if not self._valid_digest(source_identity_digest):
            return self._error("FIFO_SALE_IDENTITY_UNCONFIRMED")
        connection = None
        try:
            identity = self._normalize_identity(store_id, product_id, offer_id, sku, 1)
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            connection = self.get_connection()
            rows = connection.execute(
                """SELECT e.event_id, e.quantity, e.effective_date,
                          e.inventory_cutoff, e.source_identity_digest,
                          e.provenance, e.completeness, s.source_method,
                          s.source_status, s.coverage_status
                   FROM fifo_cost_events AS e
                   JOIN fifo_cost_streams AS st ON st.stream_id=e.stream_id
                   LEFT JOIN fifo_cost_sources AS s ON s.source_id=e.source_id
                   WHERE e.stream_id=? AND st.store_id=?
                     AND st.identity_fingerprint=? AND e.event_kind='PHYSICAL_SALE'
                     AND e.source_identity_digest=? LIMIT 2""",
                (stream_id, identity["store_id"], identity_fingerprint,
                 source_identity_digest),
            ).fetchall()
            if len(rows) != 1:
                return self._error(
                    "FIFO_RETURN_ORIGIN_SALE_MISSING" if not rows
                    else "FIFO_RETURN_ORIGIN_SALE_AMBIGUOUS"
                )
            row = rows[0]
            if (
                row["provenance"] != "OZON_CONFIRMED_FIELD"
                or row["completeness"] != "COMPLETE"
                or row["source_method"] != "OZON_REALIZATION_REPORT"
                or row["source_status"] != "COMPLETE"
                or row["coverage_status"] != "COMPLETE"
            ):
                return self._error("FIFO_RETURN_ORIGIN_SALE_UNCONFIRMED")
            return {
                "error": False,
                "code": "FIFO_RETURN_ORIGIN_SALE_READY",
                "event_id": row["event_id"],
                "quantity": row["quantity"],
                "effective_date": row["effective_date"],
                "inventory_cutoff": row["inventory_cutoff"],
            }
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_IDENTITY_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def preview_current_allocation(
        self, *, store_id, product_id=None, offer_id=None, sku,
        hypothetical_outflow=None,
    ):
        """Return a bounded replay preview for the exact current stream revision."""
        guard = self.read_allocation_guard(
            store_id=store_id, product_id=product_id, offer_id=offer_id, sku=sku,
        )
        if guard.get("error") is True:
            return guard
        if guard.get("eligible_for_publication") is not True:
            return self._error(guard.get("replay_reason_code") or "FIFO_ALLOCATION_REPLAY_UNAVAILABLE")
        if hypothetical_outflow is not None:
            if not isinstance(hypothetical_outflow, dict) or set(hypothetical_outflow) != {
                "quantity", "reason_code", "effective_date", "inventory_cutoff",
                "source_identity_digest",
            }:
                return self._error("FIFO_MOVEMENT_EVIDENCE_INVALID")
            if (
                type(hypothetical_outflow["quantity"]) is not int
                or not 1 <= hypothetical_outflow["quantity"] <= self.MAX_EVENT_QUANTITY
                or hypothetical_outflow["reason_code"] not in {
                    "HOME_SHORTAGE", "OZON_DISPOSAL", "SUPPLIER_RETURN",
                    "INVENTORY_WRITE_OFF",
                }
                or self._normalize_date(hypothetical_outflow["effective_date"]) is None
                or hypothetical_outflow["inventory_cutoff"] != guard.get("anchor_cutoff_date")
                or not self._valid_digest(hypothetical_outflow["source_identity_digest"])
            ):
                return self._error("FIFO_MOVEMENT_EVIDENCE_INVALID")
        connection = None
        try:
            identity = self._normalize_identity(store_id, product_id, offer_id, sku, 1)
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            connection = self.get_connection()
            connection.execute("BEGIN")
            stream = connection.execute(
                """SELECT revision, policy_version, state FROM fifo_cost_streams
                   WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                (stream_id, identity["store_id"], identity_fingerprint),
            ).fetchone()
            projection = connection.execute(
                "SELECT cutoff_status FROM fifo_cost_projections WHERE stream_id=?",
                (stream_id,),
            ).fetchone()
            if stream is None or projection is None:
                connection.rollback()
                return self._error("FIFO_HISTORY_NOT_INITIALIZED")
            fingerprint = self._allocation_source_fingerprint(
                connection, stream_id, stream["revision"], stream["policy_version"],
                projection["cutoff_status"],
            )
            allocation_revision = connection.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM fifo_cost_allocations WHERE stream_id=?",
                (stream_id,),
            ).fetchone()[0]
            if (
                stream["revision"] != guard["stream_revision"]
                or fingerprint != guard["source_set_fingerprint"]
                or allocation_revision != guard["allocation_revision"]
            ):
                connection.rollback()
                return self._error("FIFO_REVISION_CONFLICT")
            preview = self._preview_allocation_from_connection(
                connection, stream_id,
                stream_revision=stream["revision"],
                allocation_revision=allocation_revision,
                source_fingerprint=fingerprint,
                cutoff_status=projection["cutoff_status"],
                anchor_cutoff_date=guard["anchor_cutoff_date"],
                hypothetical_outflow=hypothetical_outflow,
            )
            connection.commit()
            if preview is None or preview.get("complete") is not True:
                return self._error(
                    preview.get("reason_code") if isinstance(preview, dict)
                    else "FIFO_ALLOCATION_REPLAY_UNAVAILABLE"
                )
            return preview
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_ALLOCATION_REPLAY_UNAVAILABLE"
            return self._error(code)
        except (sqlite3.Error, OSError):
            if connection is not None and connection.in_transaction:
                connection.rollback()
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def read_period_allocation_summary(
        self, *, store_id, product_id=None, offer_id=None, sku,
        date_from, date_to,
    ):
        """Read one exact SKU's latest complete FIFO COGS allocation by period."""
        start = self._normalize_date(date_from)
        end = self._normalize_date(date_to)
        if start is None or end is None or start > end:
            return self._error("FIFO_PERIOD_INVALID")
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        connection = None
        try:
            identity = self._normalize_identity(
                store_id, product_id, offer_id, sku, 1,
            )
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            connection = self.get_connection()
            connection.execute("BEGIN")
            stream = connection.execute(
                """SELECT revision, policy_version, state
                   FROM fifo_cost_streams
                   WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                (stream_id, identity["store_id"], identity_fingerprint),
            ).fetchone()
            if stream is None or stream["state"] in {"LEGACY", "FIFO_PENDING_ANCHOR"}:
                connection.rollback()
                return {
                    "error": False, "code": "FIFO_COST_MODE_NOT_ACTIVE",
                    "active": False,
                }
            if stream["state"] not in {"FIFO_READY", "FIFO_PARTIAL"}:
                connection.rollback()
                return {
                    "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                    "active": True, "complete": False,
                    "reason_code": "FIFO_STREAM_NOT_READY",
                }
            projection = connection.execute(
                "SELECT cutoff_status FROM fifo_cost_projections WHERE stream_id=?",
                (stream_id,),
            ).fetchone()
            if projection is None or projection["cutoff_status"] != "RECONCILED":
                connection.rollback()
                return {
                    "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                    "active": True, "complete": False,
                    "reason_code": "INVENTORY_CUTOFF_UNRECONCILED",
                }
            anchor = connection.execute(
                """SELECT COUNT(DISTINCT inventory_cutoff), MIN(inventory_cutoff)
                   FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='OPENING_FIFO_ANCHOR'""",
                (stream_id,),
            ).fetchone()
            if anchor[0] != 1 or self._normalize_date(anchor[1]) is None:
                connection.rollback()
                return {
                    "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                    "active": True, "complete": False,
                    "reason_code": "INVENTORY_CUTOFF_UNRECONCILED",
                }
            anchor_cutoff = anchor[1]
            source_fingerprint = self._allocation_source_fingerprint(
                connection, stream_id, stream["revision"],
                stream["policy_version"], projection["cutoff_status"],
            )
            allocation = connection.execute(
                """SELECT allocation_id, revision, stream_revision,
                          source_set_fingerprint, cutoff_status, status
                   FROM fifo_cost_allocations WHERE stream_id=?
                   ORDER BY revision DESC LIMIT 1""",
                (stream_id,),
            ).fetchone()
            sale_rows = connection.execute(
                """SELECT e.event_id, e.effective_date, e.inventory_cutoff,
                          e.quantity, e.source_identity_digest, e.provenance,
                          e.completeness, s.source_method, s.source_status,
                          s.coverage_status
                   FROM fifo_cost_events AS e
                   LEFT JOIN fifo_cost_sources AS s ON s.source_id=e.source_id
                   WHERE e.stream_id=? AND e.event_kind='PHYSICAL_SALE'
                   ORDER BY e.event_id LIMIT 100001""",
                (stream_id,),
            ).fetchall()
            if len(sale_rows) > 100_000:
                connection.rollback()
                return {
                    "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                    "active": True, "complete": False,
                    "reason_code": "FIFO_REPLAY_INPUT_LIMIT",
                }
            if not sale_rows and allocation is None:
                connection.commit()
                return {
                    "error": False, "code": "FIFO_COST_PERIOD_READY",
                    "active": True, "complete": True,
                    "stream_revision": stream["revision"],
                    "allocation_revision": 0,
                    "cutoff_date": anchor_cutoff,
                    "allocations": [],
                    "layers": [],
                    "period_units": 0,
                    "period_cogs_rub": "0.00",
                    "layer_breakdown_complete": True,
                }
            if (
                allocation is None
                or allocation["status"] != "COMPLETE"
                or allocation["cutoff_status"] != "RECONCILED"
                or allocation["stream_revision"] != stream["revision"]
                or allocation["source_set_fingerprint"] != source_fingerprint
            ):
                connection.rollback()
                return {
                    "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                    "active": True, "complete": False,
                    "reason_code": "FIFO_ALLOCATION_STALE_OR_MISSING",
                }

            source_by_id = {}
            for row in sale_rows:
                effective_date = self._normalize_date(row["effective_date"])
                if (
                    effective_date is None or effective_date <= anchor_cutoff
                    or row["inventory_cutoff"] != anchor_cutoff
                    or not self._valid_digest(row["source_identity_digest"])
                    or row["provenance"] != "OZON_CONFIRMED_FIELD"
                    or row["completeness"] != "COMPLETE"
                    or row["source_method"] != "OZON_REALIZATION_REPORT"
                    or row["source_status"] != "COMPLETE"
                    or row["coverage_status"] != "COMPLETE"
                ):
                    connection.rollback()
                    return {
                        "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                        "active": True, "complete": False,
                        "reason_code": "FIFO_ALLOCATION_SOURCE_INVALID",
                    }
                source_by_id[row["event_id"]] = row

            line_rows = connection.execute(
                """SELECT l.event_id, l.layer_id AS basis_id, l.quantity,
                          l.unit_cost_rub, l.total_cost_rub,
                          'LAYER' AS basis_kind, b.layer_sequence,
                          b.effective_date AS basis_effective_date,
                          b.provenance AS basis_provenance,
                          s.source_method AS basis_source_method,
                          s.source_status AS basis_source_status,
                          s.coverage_status AS basis_coverage_status
                   FROM fifo_cost_allocation_lines AS l
                   JOIN fifo_cost_layers AS b ON b.layer_id=l.layer_id
                   LEFT JOIN fifo_cost_sources AS s ON s.source_id=b.source_id
                   WHERE l.allocation_id=?
                   UNION ALL
                   SELECT l.event_id, l.rate_change_id AS basis_id, l.quantity,
                          l.unit_cost_rub, l.total_cost_rub,
                          'RATE' AS basis_kind, b.rate_sequence AS layer_sequence,
                          b.effective_date AS basis_effective_date,
                          s.provenance AS basis_provenance,
                          s.source_method AS basis_source_method,
                          s.source_status AS basis_source_status,
                          s.coverage_status AS basis_coverage_status
                   FROM fifo_cost_allocation_rate_lines AS l
                   JOIN fifo_cost_rate_changes AS b
                     ON b.rate_change_id=l.rate_change_id
                   LEFT JOIN fifo_cost_sources AS s ON s.source_id=b.source_id
                   WHERE l.allocation_id=?
                   ORDER BY event_id, basis_kind, layer_sequence, basis_id""",
                (allocation["allocation_id"], allocation["allocation_id"]),
            ).fetchall()
            by_event = {}
            period_layers = {}
            for line in line_rows:
                quantity = line["quantity"]
                unit_cost = self._normalize_money(line["unit_cost_rub"])
                total_cost = self._normalize_money(line["total_cost_rub"])
                if (
                    line["event_id"] not in source_by_id
                    or type(quantity) is not int or quantity <= 0
                    or unit_cost is None or total_cost is None
                    or (Decimal(unit_cost) * quantity).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP,
                    ) != Decimal(total_cost)
                ):
                    connection.rollback()
                    return {
                        "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                        "active": True, "complete": False,
                        "reason_code": "FIFO_ALLOCATION_LINE_INVALID",
                    }
                if line["basis_kind"] == "LAYER":
                    basis = connection.execute(
                        """SELECT l.unit_cost_rub FROM fifo_cost_layers AS l
                           WHERE l.stream_id=? AND l.layer_id=?""",
                        (stream_id, line["basis_id"]),
                    ).fetchone()
                else:
                    basis = connection.execute(
                        """SELECT r.unit_cost_rub FROM fifo_cost_rate_changes AS r
                           WHERE r.stream_id=? AND r.rate_change_id=?
                             AND NOT EXISTS (
                                 SELECT 1 FROM fifo_cost_rate_cancellations AS c
                                 WHERE c.stream_id=r.stream_id
                                   AND c.rate_change_id=r.rate_change_id
                             )""",
                        (stream_id, line["basis_id"]),
                    ).fetchone()
                if basis is None or self._normalize_money(basis[0]) != unit_cost:
                    connection.rollback()
                    return {
                        "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                        "active": True, "complete": False,
                        "reason_code": "FIFO_ALLOCATION_BASIS_INVALID",
                    }
                group = by_event.setdefault(line["event_id"], {
                    "quantity": 0, "total": Decimal("0.00"),
                })
                group["quantity"] += quantity
                group["total"] += Decimal(total_cost)
                sale = source_by_id[line["event_id"]]
                if start <= sale["effective_date"] <= end:
                    sequence = line["layer_sequence"]
                    effective_date = self._normalize_date(
                        line["basis_effective_date"]
                    )
                    provenance = line["basis_provenance"]
                    source_method = line["basis_source_method"]
                    source_status = line["basis_source_status"]
                    coverage_status = line["basis_coverage_status"]
                    basis_ref = "fifo-basis-" + self._sha256({
                        "schema": 1,
                        "stream_id": stream_id,
                        "basis_kind": line["basis_kind"],
                        "sequence": sequence,
                        "basis_id": line["basis_id"],
                    })[:20]
                    layer = period_layers.setdefault(basis_ref, {
                        "basis_ref": basis_ref,
                        "basis_kind": line["basis_kind"],
                        "sequence": sequence,
                        "effective_date": effective_date,
                        "provenance": provenance,
                        "source_method": source_method,
                        "source_status": source_status,
                        "coverage_status": coverage_status,
                        "quantity": 0,
                        "unit_cost_rub": unit_cost,
                        "total_cogs_rub": Decimal("0.00"),
                    })
                    if (
                        layer["effective_date"] != effective_date
                        or layer["provenance"] != provenance
                        or layer["source_method"] != source_method
                        or layer["source_status"] != source_status
                        or layer["coverage_status"] != coverage_status
                        or layer["unit_cost_rub"] != unit_cost
                    ):
                        connection.rollback()
                        return {
                            "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                            "active": True, "complete": False,
                            "reason_code": "FIFO_ALLOCATION_BASIS_INVALID",
                        }
                    layer["quantity"] += quantity
                    layer["total_cogs_rub"] += Decimal(total_cost)
            if set(by_event) != set(source_by_id):
                connection.rollback()
                return {
                    "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                    "active": True, "complete": False,
                    "reason_code": "FIFO_ALLOCATION_COVERAGE_MISMATCH",
                }

            allocations = []
            period_cogs = Decimal("0.00")
            period_units = 0
            digests = set()
            for event_id, row in source_by_id.items():
                group = by_event[event_id]
                digest = row["source_identity_digest"]
                if (
                    group["quantity"] != row["quantity"]
                    or digest in digests
                ):
                    connection.rollback()
                    return {
                        "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                        "active": True, "complete": False,
                        "reason_code": "FIFO_ALLOCATION_COVERAGE_MISMATCH",
                    }
                digests.add(digest)
                total = group["total"].quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                )
                if start <= row["effective_date"] <= end:
                    period_cogs += total
                    period_units += row["quantity"]
                    allocations.append({
                        "source_identity_digest": digest,
                        "effective_date": row["effective_date"],
                        "quantity": row["quantity"],
                        "total_cogs_rub": format(total, ".2f"),
                    })
            allocations.sort(key=lambda item: (
                item["effective_date"], item["source_identity_digest"],
            ))
            layers = []
            for layer in sorted(
                period_layers.values(),
                key=lambda item: (
                    item["effective_date"] or "",
                    item["sequence"], item["basis_ref"],
                ),
            ):
                amount = layer["total_cogs_rub"].quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                )
                layers.append({
                    **layer,
                    "total_cogs_rub": format(amount, ".2f"),
                })
            layer_units = sum(layer["quantity"] for layer in layers)
            layer_cogs = sum(
                (Decimal(layer["total_cogs_rub"]) for layer in layers),
                Decimal("0.00"),
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if layer_units != period_units or layer_cogs != period_cogs:
                connection.rollback()
                return {
                    "error": False, "code": "FIFO_COST_SCOPE_INCOMPLETE",
                    "active": True, "complete": False,
                    "reason_code": "FIFO_ALLOCATION_LINE_INVALID",
                }
            connection.commit()
            return {
                "error": False, "code": "FIFO_COST_PERIOD_READY",
                "active": True, "complete": True,
                "stream_revision": stream["revision"],
                "allocation_revision": allocation["revision"],
                "cutoff_date": anchor_cutoff,
                "allocations": allocations,
                "layers": layers,
                "period_units": period_units,
                "period_cogs_rub": format(period_cogs, ".2f"),
                "layer_breakdown_complete": True,
            }
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_IDENTITY_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            if connection is not None and connection.in_transaction:
                connection.rollback()
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def read_cost_mode_status(
        self, *, store_id, product_id=None, offer_id=None, sku,
    ):
        """Read the exact-SKU cutover state without resolving any cost value."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        connection = None
        try:
            identity = self._normalize_identity(
                store_id, product_id, offer_id, sku, 1,
            )
            fingerprint = self._sha256(identity)
            stream_id = "fifo_" + fingerprint[:40]
            connection = self.get_connection()
            identity_conflict = self._identity_stream_conflict(
                connection, identity, fingerprint,
            )
            if identity_conflict is not None:
                return identity_conflict
            stream = connection.execute(
                """SELECT revision, state FROM fifo_cost_streams
                   WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                (stream_id, identity["store_id"], fingerprint),
            ).fetchone()
            if stream is None or stream["state"] in {"LEGACY", "FIFO_PENDING_ANCHOR"}:
                return {
                    "error": False, "code": "FIFO_COST_MODE_LEGACY",
                    "active": False,
                }
            projection = connection.execute(
                "SELECT inventory_cutoff FROM fifo_cost_projections WHERE stream_id=?",
                (stream_id,),
            ).fetchone()
            cutoff_date = None if projection is None else projection["inventory_cutoff"]
            if cutoff_date is None:
                cutoff_date = connection.execute(
                    """SELECT MIN(inventory_cutoff) FROM fifo_cost_events
                       WHERE stream_id=? AND event_kind='OPENING_FIFO_ANCHOR'""",
                    (stream_id,),
                ).fetchone()[0]
            return {
                "error": False, "code": "FIFO_COST_MODE_FIFO",
                "active": True,
                "stream_state": stream["state"],
                "stream_revision": stream["revision"],
                "cutoff_date": cutoff_date,
            }
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_IDENTITY_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def append_allocation_revision(
        self, *, store_id, product_id=None, offer_id=None, sku,
        preview, idempotency_key,
    ):
        """Atomically publish a complete immutable projection with source CAS."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        try:
            normalized = self._normalize_allocation_preview(preview, idempotency_key)
        except ValueError as exc:
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_ALLOCATION_PREVIEW_INVALID"
            return self._error(code)
        if isinstance(normalized, str):
            return self._error(normalized)
        connection = None
        try:
            identity = self._normalize_identity(
                store_id, product_id, offer_id, sku, 1,
            )
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            connection = self.get_connection()
            connection.execute("BEGIN IMMEDIATE")
            key = "allocation-" + idempotency_key
            prior = connection.execute(
                """SELECT payload_fingerprint, result_reference
                   FROM fifo_cost_idempotency WHERE stream_id=? AND idempotency_key=?""",
                (stream_id, key),
            ).fetchone()
            if prior is not None:
                if prior["payload_fingerprint"] != normalized["payload_fingerprint"]:
                    connection.rollback()
                    return self._error("FIFO_IDEMPOTENCY_CONFLICT")
                result = json.loads(prior["result_reference"])
                connection.rollback()
                return {"error": False, "code": "FIFO_ALLOCATION_COMMITTED",
                        "idempotent": True, **result}

            stream = connection.execute(
                """SELECT revision, policy_version, state
                   FROM fifo_cost_streams
                   WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                (stream_id, identity["store_id"], identity_fingerprint),
            ).fetchone()
            projection = connection.execute(
                """SELECT cutoff_status FROM fifo_cost_projections
                   WHERE stream_id=?""",
                (stream_id,),
            ).fetchone()
            if stream is None or projection is None:
                connection.rollback()
                return self._error("FIFO_HISTORY_NOT_INITIALIZED")
            if stream["revision"] != normalized["stream_revision"]:
                connection.rollback()
                return self._error("FIFO_REVISION_CONFLICT")
            if (
                stream["state"] not in {"FIFO_READY", "FIFO_PARTIAL"}
                or projection["cutoff_status"] != "RECONCILED"
            ):
                connection.rollback()
                return self._error("INVENTORY_CUTOFF_UNRECONCILED")
            current_fingerprint = self._allocation_source_fingerprint(
                connection, stream_id, stream["revision"],
                stream["policy_version"], projection["cutoff_status"],
            )
            if current_fingerprint != normalized["source_set_fingerprint"]:
                connection.rollback()
                return self._error("FIFO_SOURCE_REVISION_CONFLICT")
            current_allocation_revision = connection.execute(
                """SELECT COALESCE(MAX(revision), 0)
                   FROM fifo_cost_allocations WHERE stream_id=?""",
                (stream_id,),
            ).fetchone()[0]
            if current_allocation_revision != normalized["expected_allocation_revision"]:
                connection.rollback()
                return self._error("FIFO_REVISION_CONFLICT")

            self._validate_allocation_lines(
                connection, stream_id, normalized,
                stream_revision=stream["revision"],
                allocation_revision=current_allocation_revision,
                source_fingerprint=current_fingerprint,
                cutoff_status=projection["cutoff_status"],
            )
            allocation_revision = current_allocation_revision + 1
            allocation_id = "alloc_" + uuid4().hex
            now = self._iso(self._now())
            connection.execute(
                """INSERT INTO fifo_cost_allocations (
                    allocation_id, stream_id, revision, stream_revision,
                    policy_version, source_set_fingerprint, cutoff_status,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'RECONCILED', 'COMPLETE', ?)""",
                (
                    allocation_id, stream_id, allocation_revision,
                    stream["revision"], stream["policy_version"],
                    normalized["source_set_fingerprint"], now,
                ),
            )
            line_number = 0
            for allocation in normalized["allocations"]:
                for line in allocation["lines"]:
                    line_number += 1
                    origin_id = line["origin_sale_event_id"]
                    basis_allocation_id = None
                    basis_line_number = None
                    if origin_id is not None:
                        if line["layer_id"] is None:
                            raise ValueError("FIFO_ALLOCATION_BASIS_MISSING")
                        basis = connection.execute(
                            """SELECT l.allocation_id, l.line_number
                               FROM fifo_cost_allocation_lines AS l
                               JOIN fifo_cost_allocations AS a
                                 ON a.allocation_id=l.allocation_id
                               WHERE a.stream_id=? AND l.event_id=? AND l.layer_id=?
                               ORDER BY a.revision DESC, l.line_number LIMIT 1""",
                            (stream_id, origin_id, line["layer_id"]),
                        ).fetchone()
                        if basis is None:
                            raise ValueError("FIFO_ALLOCATION_BASIS_MISSING")
                        basis_allocation_id = basis["allocation_id"]
                        basis_line_number = basis["line_number"]
                    if line["layer_id"] is not None:
                        connection.execute(
                            """INSERT INTO fifo_cost_allocation_lines (
                                allocation_id, line_number, event_id, layer_id,
                                quantity, unit_cost_rub, total_cost_rub,
                                basis_allocation_id, basis_line_number
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                allocation_id, line_number, allocation["event_id"],
                                line["layer_id"], line["quantity"],
                                line["unit_cost_rub"], line["total_cost_rub"],
                                basis_allocation_id, basis_line_number,
                            ),
                        )
                    else:
                        connection.execute(
                            """INSERT INTO fifo_cost_allocation_rate_lines (
                                allocation_id, line_number, event_id, rate_change_id,
                                quantity, unit_cost_rub, total_cost_rub,
                                basis_allocation_id, basis_line_number
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                allocation_id, line_number, allocation["event_id"],
                                line["rate_change_id"], line["quantity"],
                                line["unit_cost_rub"], line["total_cost_rub"],
                                basis_allocation_id, basis_line_number,
                            ),
                        )
            outflow_line_number = 0
            for outflow in normalized["outflows"]:
                for line in outflow["lines"]:
                    outflow_line_number += 1
                    connection.execute(
                        """INSERT INTO fifo_cost_allocation_outflow_lines (
                            allocation_id, line_number, event_id, layer_id,
                            quantity, unit_cost_rub, estimated_value_rub,
                            valuation_method
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            allocation_id, outflow_line_number, outflow["event_id"],
                            line["layer_id"], line["quantity"], line["unit_cost_rub"],
                            line["total_cost_rub"], outflow["valuation_method"],
                        ),
                    )
            result = {
                "allocation_id": allocation_id,
                "allocation_revision": allocation_revision,
                "stream_revision": stream["revision"],
                "line_count": line_number,
            }
            connection.execute(
                """INSERT INTO fifo_cost_idempotency (
                    stream_id, idempotency_key, payload_fingerprint,
                    result_reference, created_at
                ) VALUES (?, ?, ?, ?, ?)""",
                (
                    stream_id, key, normalized["payload_fingerprint"],
                    self._canonical_json(result), now,
                ),
            )
            connection.commit()
            return {"error": False, "code": "FIFO_ALLOCATION_COMMITTED",
                    "idempotent": False, **result}
        except ValueError as exc:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            code = str(exc) if (
                str(exc).startswith("FIFO_") or str(exc) in self._REASON_CODES
            ) else "FIFO_ALLOCATION_INVALID"
            return self._error(code)
        except sqlite3.IntegrityError:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            return self._error("FIFO_REVISION_CONFLICT")
        except (sqlite3.Error, OSError):
            if connection is not None and connection.in_transaction:
                connection.rollback()
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def record_supply_evidence(
        self, *, store_id, product_id=None, offer_id=None, sku, snapshot,
        expected_revision=None,
    ):
        """Append a reconciled supply-act snapshot without creating inventory."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        connection = None
        try:
            from services.fifo_cost_source_normalizer import (
                FifoCostSourceNormalizer,
                FifoSupplyActEvidence,
                FifoSupplyActSnapshot,
            )

            if not isinstance(snapshot, FifoSupplyActSnapshot):
                return self._error("FIFO_SUPPLY_SNAPSHOT_INVALID")
            if expected_revision is not None and (
                type(expected_revision) is not int or expected_revision < 0
            ):
                return self._error("FIFO_REVISION_CONFLICT")
            identity = self._normalize_identity(store_id, product_id, offer_id, sku, 1)
            if (
                snapshot.status not in {"COMPLETE", "CONFIRMED_ZERO"}
                or snapshot.source_status != "COMPLETE"
            ):
                return self._error("FIFO_SUPPLY_SOURCE_NOT_COMPLETE")
            if (
                snapshot.store_id != identity["store_id"]
                or snapshot.effective_at is not None
                or snapshot.order_ref is None
                or not self._valid_digest(snapshot.order_ref)
                or snapshot.supply_ref is None
                or not self._valid_digest(snapshot.supply_ref)
                or snapshot.evidence_fingerprint is None
                or not self._valid_digest(snapshot.evidence_fingerprint)
                or snapshot.source_fingerprint is None
                or not self._valid_digest(snapshot.source_fingerprint)
                or self._normalize_timestamp(snapshot.captured_at) is None
            ):
                return self._error("FIFO_SUPPLY_SNAPSHOT_INVALID")
            units_by_sku = snapshot.units_by_sku
            if (
                not isinstance(units_by_sku, tuple)
                or len(units_by_sku) != 1
                or not isinstance(units_by_sku[0], tuple)
                or len(units_by_sku[0]) != 2
                or units_by_sku[0][0] != identity["sku"]
                or type(units_by_sku[0][1]) is not int
                or not 0 <= units_by_sku[0][1] <= self.MAX_COMMAND_UNITS
            ):
                return self._error("FIFO_SUPPLY_SKU_IDENTITY_MISMATCH")
            if (
                not snapshot.act_evidence
                or len(snapshot.act_evidence) > self.MAX_PAYLOAD_BYTES // 64
                or not isinstance(snapshot.act_refs, tuple)
                or len(snapshot.act_refs) != len(snapshot.act_evidence)
            ):
                return self._error("FIFO_SUPPLY_ACT_EVIDENCE_INVALID")

            normalized_acts = []
            seen_act_refs = set()
            fact_total = 0
            for item in snapshot.act_evidence:
                if (
                    not isinstance(item, FifoSupplyActEvidence)
                    or not self._valid_digest(item.act_ref)
                    or item.act_ref in seen_act_refs
                    or item.act_type != "ACCEPTANCE"
                    or item.act_state != "ACCEPTED"
                    or type(item.fact_quantity) is not int
                    or not 0 <= item.fact_quantity <= self.MAX_COMMAND_UNITS
                ):
                    return self._error("FIFO_SUPPLY_ACT_EVIDENCE_INVALID")
                seen_act_refs.add(item.act_ref)
                if item.created_date is not None:
                    self._normalize_date(item.created_date)
                quantities = {}
                for field in ("declared_quantity", "approved_quantity"):
                    value = getattr(item, field)
                    if value is not None and (
                        type(value) is not int or not 0 <= value <= self.MAX_COMMAND_UNITS
                    ):
                        return self._error("FIFO_SUPPLY_ACT_EVIDENCE_INVALID")
                    quantities[field] = value
                fact_total += item.fact_quantity
                if fact_total > self.MAX_COMMAND_UNITS:
                    return self._error("FIFO_SUPPLY_QUANTITY_LIMIT")
                normalized_acts.append({
                    "act_ref": item.act_ref,
                    "act_type": item.act_type,
                    "act_state": item.act_state,
                    "created_date": item.created_date,
                    "created_date_kind": "DOCUMENT_CREATED_DATE_ONLY",
                    "declared_quantity": quantities["declared_quantity"],
                    "approved_quantity": quantities["approved_quantity"],
                    "fact_quantity": item.fact_quantity,
                })
            if (
                seen_act_refs != set(snapshot.act_refs)
                or fact_total != units_by_sku[0][1]
                or (snapshot.status == "CONFIRMED_ZERO") != (fact_total == 0)
            ):
                return self._error("FIFO_SUPPLY_ACT_EVIDENCE_MISMATCH")

            canonical_acts = sorted(normalized_acts, key=lambda row: row["act_ref"])
            normalized_fingerprint_payload = {
                "store_id": identity["store_id"],
                "order_ref": snapshot.order_ref,
                "supply_ref": snapshot.supply_ref,
                "act_refs": sorted(snapshot.act_refs),
                "act_evidence": [
                    {key: row[key] for key in (
                        "act_ref", "act_type", "act_state", "created_date",
                        "declared_quantity", "approved_quantity", "fact_quantity",
                    )}
                    for row in canonical_acts
                ],
                "units_by_sku": [[identity["sku"], fact_total]],
                "status": snapshot.status,
            }
            expected_evidence_fingerprint = FifoCostSourceNormalizer._fingerprint(
                normalized_fingerprint_payload,
            )
            expected_source_fingerprint = FifoCostSourceNormalizer._fingerprint({
                **normalized_fingerprint_payload,
                "captured_at": snapshot.captured_at,
            })
            if (
                expected_evidence_fingerprint != snapshot.evidence_fingerprint
                or expected_source_fingerprint != snapshot.source_fingerprint
            ):
                return self._error("FIFO_SUPPLY_EVIDENCE_FINGERPRINT_CONFLICT")

            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            normalized_payload = {
                "status": snapshot.status,
                "store_id": identity["store_id"],
                "sku": identity["sku"],
                "order_ref": snapshot.order_ref,
                "supply_ref": snapshot.supply_ref,
                "act_evidence": canonical_acts,
                "fact_units": fact_total,
                "source_as_of": None,
                "physical_effective_at": None,
                "physical_effective_date": None,
            }
            payload_json = self._canonical_json(normalized_payload)
            if len(payload_json.encode("utf-8")) > self.MAX_PAYLOAD_BYTES:
                return self._error("FIFO_SUPPLY_EVIDENCE_LIMIT")
            source = self._normalize_source({
                "kind": "OZON_API",
                "method": "FIFO_SUPPLY_ACT_SNAPSHOT",
                "status": "COMPLETE",
                "completeness": "COMPLETE",
                "provenance": "OZON_CONFIRMED_FIELD",
                "coverage_status": "COMPLETE",
                "fingerprint": snapshot.source_fingerprint,
                "captured_at": snapshot.captured_at,
                "record_count": len(normalized_acts),
                "page_count": 1,
                "references": [
                    {"kind": "ORDER", "digest": snapshot.order_ref},
                    {"kind": "SUPPLY", "digest": snapshot.supply_ref},
                ],
            })
            source_id = "src_" + self._sha256({
                "store_id": identity["store_id"],
                "source_fingerprint": source["source_fingerprint"],
            })[:40]
            now = self._now()
            connection = self.get_connection()
            connection.execute("BEGIN IMMEDIATE")
            stream = connection.execute(
                """SELECT revision FROM fifo_cost_streams
                   WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                (stream_id, identity["store_id"], identity_fingerprint),
            ).fetchone()
            if stream is None:
                connection.rollback()
                return self._error("FIFO_HISTORY_NOT_INITIALIZED")
            if (
                expected_revision is not None
                and stream["revision"] != expected_revision
            ):
                connection.rollback()
                return self._error("FIFO_REVISION_CONFLICT")
            existing = connection.execute(
                """SELECT evidence_id, source_id, snapshot_sequence, normalized_evidence_json
                   FROM fifo_cost_supply_evidence
                   WHERE stream_id=? AND evidence_fingerprint=?""",
                (stream_id, snapshot.evidence_fingerprint),
            ).fetchone()
            if existing is not None:
                expected_id = "supply_ev_" + self._sha256({
                    "stream_id": stream_id,
                    "evidence_fingerprint": snapshot.evidence_fingerprint,
                })[:40]
                if (
                    existing["evidence_id"] != expected_id
                    or existing["normalized_evidence_json"] != payload_json
                ):
                    connection.rollback()
                    return self._error("FIFO_SUPPLY_EVIDENCE_FINGERPRINT_CONFLICT")
                connection.rollback()
                return {
                    "error": False,
                    "code": "FIFO_SUPPLY_EVIDENCE_RECORDED",
                    "idempotent": True,
                    "evidence_sequence": existing["snapshot_sequence"],
                    "stream_revision": stream["revision"],
                    "accepted_units": fact_total,
                    "act_count": len(normalized_acts),
                }
            snapshot_sequence = connection.execute(
                "SELECT COALESCE(MAX(snapshot_sequence), 0) + 1 "
                "FROM fifo_cost_supply_evidence WHERE stream_id=?",
                (stream_id,),
            ).fetchone()[0]
            self._ensure_source(connection, {
                "identity": identity,
                "source": source,
                "source_id": source_id,
            })
            evidence_id = "supply_ev_" + self._sha256({
                "stream_id": stream_id,
                "evidence_fingerprint": snapshot.evidence_fingerprint,
            })[:40]
            connection.execute(
                """INSERT INTO fifo_cost_supply_evidence (
                    evidence_id, stream_id, snapshot_sequence, stream_revision, source_id,
                    source_fingerprint, evidence_fingerprint, order_digest,
                    supply_digest, source_status, captured_at, source_as_of,
                    physical_effective_at, physical_effective_date,
                    normalized_evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETE', ?, NULL, NULL, NULL, ?, ?)""",
                (
                    evidence_id, stream_id, snapshot_sequence, stream["revision"], source_id,
                    snapshot.source_fingerprint, snapshot.evidence_fingerprint,
                    snapshot.order_ref, snapshot.supply_ref,
                    source["captured_at"], payload_json, self._iso(now),
                ),
            )
            connection.commit()
            return {
                "error": False,
                "code": "FIFO_SUPPLY_EVIDENCE_RECORDED",
                "idempotent": False,
                "evidence_sequence": snapshot_sequence,
                "stream_revision": stream["revision"],
                "accepted_units": fact_total,
                "act_count": len(normalized_acts),
            }
        except (AttributeError, IndexError, TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_SUPPLY_SNAPSHOT_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            if connection is not None:
                try:
                    connection.rollback()
                except sqlite3.Error:
                    pass
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def record_late_entry_draft(
        self, *, store_id, product_id=None, offer_id=None, sku,
        expected_revision, snapshot, owner_effective_date, owner_old_home_units,
        purchase_cost_rub, delivery_cost_rub, packaging_cost_rub,
    ):
        """Append an owner-confirmed late-entry draft, without changing FIFO."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        connection = None
        try:
            from services.fifo_cost_source_normalizer import FifoSupplyActSnapshot

            identity = self._normalize_identity(store_id, product_id, offer_id, sku, 1)
            if (
                type(expected_revision) is not int or expected_revision < 0
                or not isinstance(snapshot, FifoSupplyActSnapshot)
                or snapshot.status != "COMPLETE"
                or snapshot.source_status != "COMPLETE"
                or snapshot.store_id != identity["store_id"]
                or snapshot.captured_at is None
                or snapshot.evidence_fingerprint is None
                or not self._valid_digest(snapshot.evidence_fingerprint)
                or snapshot.source_fingerprint is None
                or not self._valid_digest(snapshot.source_fingerprint)
                or snapshot.order_ref is None
                or not self._valid_digest(snapshot.order_ref)
                or snapshot.supply_ref is None
                or not self._valid_digest(snapshot.supply_ref)
            ):
                return self._error("FIFO_LATE_ENTRY_EVIDENCE_INVALID")
            owner_date = self._normalize_date(owner_effective_date)
            if owner_date is None or owner_date > self._now().date().isoformat():
                return self._error("FIFO_LATE_ENTRY_EFFECTIVE_DATE_INVALID")
            if (
                type(owner_old_home_units) is not int
                or not 0 <= owner_old_home_units <= self.MAX_COMMAND_UNITS
            ):
                return self._error("FIFO_LATE_ENTRY_HOME_QUANTITY_INVALID")
            components = {
                "purchase_cost_rub": self._normalize_money(purchase_cost_rub),
                "delivery_cost_rub": self._normalize_money(delivery_cost_rub),
                "packaging_cost_rub": self._normalize_money(packaging_cost_rub),
            }
            unit_cost = format(
                sum((Decimal(value) for value in components.values()), Decimal("0.00")),
                ".2f",
            )
            if Decimal(unit_cost) > Decimal("1000000000"):
                return self._error("FIFO_MONEY_INPUT_INVALID")
            if (
                not isinstance(snapshot.units_by_sku, tuple)
                or len(snapshot.units_by_sku) != 1
                or snapshot.units_by_sku[0][0] != identity["sku"]
                or type(snapshot.units_by_sku[0][1]) is not int
                or snapshot.units_by_sku[0][1] <= 0
                or snapshot.units_by_sku[0][1] > self.MAX_COMMAND_UNITS
            ):
                return self._error("FIFO_LATE_ENTRY_SKU_OR_QUANTITY_MISMATCH")
            accepted_units = snapshot.units_by_sku[0][1]
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            material = {
                "stream_id": stream_id,
                "expected_revision": expected_revision,
                "source_fingerprint": snapshot.source_fingerprint,
                "evidence_fingerprint": snapshot.evidence_fingerprint,
                "owner_effective_date": owner_date,
                "owner_old_home_units": owner_old_home_units,
                "accepted_units": accepted_units,
                **components,
                "unit_cost_rub": unit_cost,
            }
            payload_fingerprint = self._sha256(material)
            draft_id = "late_" + payload_fingerprint[:40]
            recorded_at = self._iso(self._now())
            connection = self.get_connection()
            connection.execute("BEGIN IMMEDIATE")
            stream = connection.execute(
                """SELECT revision FROM fifo_cost_streams
                   WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                (stream_id, identity["store_id"], identity_fingerprint),
            ).fetchone()
            if stream is None:
                connection.rollback()
                return self._error("FIFO_HISTORY_NOT_INITIALIZED")
            if stream["revision"] != expected_revision:
                connection.rollback()
                return self._error("FIFO_REVISION_CONFLICT")
            evidence = connection.execute(
                """SELECT source_fingerprint, captured_at FROM fifo_cost_supply_evidence
                   WHERE stream_id=? AND evidence_fingerprint=?""",
                (stream_id, snapshot.evidence_fingerprint),
            ).fetchone()
            if (
                evidence is None
                or evidence["source_fingerprint"] != snapshot.source_fingerprint
                or evidence["captured_at"] != self._normalize_timestamp(snapshot.captured_at)
            ):
                connection.rollback()
                return self._error("FIFO_LATE_ENTRY_EVIDENCE_NOT_RECORDED")
            existing = connection.execute(
                """SELECT draft_id FROM fifo_cost_late_entry_drafts
                   WHERE stream_id=? AND payload_fingerprint=?""",
                (stream_id, payload_fingerprint),
            ).fetchone()
            if existing is not None:
                connection.rollback()
                return {
                    "error": False,
                    "code": "FIFO_LATE_ENTRY_DRAFT_RECORDED",
                    "draft_id": existing["draft_id"],
                    "idempotent": True,
                    "expected_revision": expected_revision,
                    "accepted_units": accepted_units,
                    "owner_effective_date": owner_date,
                    "unit_cost_rub": unit_cost,
                }
            connection.execute(
                """INSERT INTO fifo_cost_late_entry_drafts (
                    draft_id, stream_id, expected_revision, evidence_fingerprint,
                    source_fingerprint, order_digest, supply_digest, owner_effective_date,
                    owner_old_home_units, accepted_units, purchase_cost_rub,
                    delivery_cost_rub, packaging_cost_rub, unit_cost_rub,
                    payload_fingerprint, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    draft_id, stream_id, expected_revision,
                    snapshot.evidence_fingerprint, snapshot.source_fingerprint,
                    snapshot.order_ref, snapshot.supply_ref, owner_date,
                    owner_old_home_units, accepted_units,
                    components["purchase_cost_rub"], components["delivery_cost_rub"],
                    components["packaging_cost_rub"], unit_cost,
                    payload_fingerprint, recorded_at,
                ),
            )
            connection.commit()
            return {
                "error": False,
                "code": "FIFO_LATE_ENTRY_DRAFT_RECORDED",
                "draft_id": draft_id,
                "idempotent": False,
                "expected_revision": expected_revision,
                "accepted_units": accepted_units,
                "owner_effective_date": owner_date,
                "unit_cost_rub": unit_cost,
            }
        except ValueError as exc:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_LATE_ENTRY_INVALID"
            return self._error(code)
        except (TypeError, IndexError, InvalidOperation, OverflowError):
            if connection is not None and connection.in_transaction:
                connection.rollback()
            return self._error("FIFO_LATE_ENTRY_INVALID")
        except sqlite3.IntegrityError:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            return self._error("FIFO_REVISION_CONFLICT")
        except (sqlite3.Error, OSError):
            if connection is not None and connection.in_transaction:
                connection.rollback()
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def read_late_entry_drafts(
        self, *, store_id, product_id=None, offer_id=None, sku,
    ):
        """Read immutable late-entry proposals for the exact tenant/SKU stream."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        connection = None
        try:
            identity = self._normalize_identity(store_id, product_id, offer_id, sku, 1)
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            connection = self.get_connection()
            rows = connection.execute(
                """SELECT d.draft_id, d.expected_revision, d.owner_effective_date,
                          d.owner_old_home_units, d.accepted_units, d.purchase_cost_rub,
                          d.delivery_cost_rub, d.packaging_cost_rub, d.unit_cost_rub,
                          d.order_digest, d.supply_digest, d.source_fingerprint,
                          d.evidence_fingerprint, d.payload_fingerprint, d.recorded_at,
                          c.correction_id, c.preview_fingerprint AS correction_fingerprint
                   FROM fifo_cost_late_entry_drafts AS d
                   JOIN fifo_cost_streams AS s ON s.stream_id=d.stream_id
                   LEFT JOIN fifo_cost_late_entry_corrections AS c
                     ON c.stream_id=d.stream_id AND c.draft_id=d.draft_id
                   WHERE d.stream_id=? AND s.store_id=? AND s.identity_fingerprint=?
                   ORDER BY d.recorded_at, d.draft_id""",
                (stream_id, identity["store_id"], identity_fingerprint),
            ).fetchall()
            return {
                "error": False,
                "code": "FIFO_LATE_ENTRY_DRAFTS_READY",
                "drafts": [dict(row) for row in rows],
            }
        except (TypeError, ValueError):
            return self._error("FIFO_IDENTITY_INVALID")
        except (sqlite3.Error, OSError):
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def preview_late_entry_reconstruction(
        self, *, store_id, product_id=None, offer_id=None, sku, draft_id,
    ):
        """Replay a late rate against complete history without writing any rows.

        The draft's accepted act quantity is evidence for the supply link only;
        it is not treated as total purchased stock or added as a finite layer.
        """
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        if (
            not isinstance(draft_id, str)
            or not re.fullmatch(r"late_[0-9a-f]{40}", draft_id)
        ):
            return self._error("FIFO_LATE_ENTRY_DRAFT_NOT_FOUND")
        connection = None
        try:
            identity = self._normalize_identity(store_id, product_id, offer_id, sku, 1)
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            connection = self.get_connection()
            connection.execute("BEGIN")
            stream = connection.execute(
                """SELECT revision, policy_version, state FROM fifo_cost_streams
                   WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                (stream_id, identity["store_id"], identity_fingerprint),
            ).fetchone()
            if stream is None:
                connection.rollback()
                return self._error("FIFO_LATE_ENTRY_DRAFT_NOT_FOUND")
            draft = connection.execute(
                """SELECT draft_id, expected_revision, evidence_fingerprint,
                          source_fingerprint, owner_effective_date,
                          owner_old_home_units, accepted_units, unit_cost_rub,
                          payload_fingerprint
                   FROM fifo_cost_late_entry_drafts
                   WHERE draft_id=? AND stream_id=?""",
                (draft_id, stream_id),
            ).fetchone()
            if draft is None:
                connection.rollback()
                return self._error("FIFO_LATE_ENTRY_DRAFT_NOT_FOUND")
            if draft["expected_revision"] != stream["revision"]:
                connection.rollback()
                return self._late_entry_reconstruction_blocked(
                    "STALE_PREVIEW", stream_revision=stream["revision"],
                )
            evidence = connection.execute(
                """SELECT source_fingerprint, source_status
                   FROM fifo_cost_supply_evidence
                   WHERE stream_id=? AND evidence_fingerprint=?""",
                (stream_id, draft["evidence_fingerprint"]),
            ).fetchone()
            if (
                evidence is None
                or evidence["source_fingerprint"] != draft["source_fingerprint"]
                or evidence["source_status"] != "COMPLETE"
            ):
                connection.rollback()
                return self._late_entry_reconstruction_blocked("SUPPLY_COST_LINK_MISSING")

            projection = connection.execute(
                """SELECT cutoff_status, queue_complete
                   FROM fifo_cost_projections WHERE stream_id=?""",
                (stream_id,),
            ).fetchone()
            if projection is None:
                connection.rollback()
                return self._late_entry_reconstruction_blocked("ANCHOR_UNCONFIRMED")
            if stream["state"] not in {"FIFO_READY", "FIFO_PARTIAL"}:
                connection.rollback()
                return self._late_entry_reconstruction_blocked("ANCHOR_UNCONFIRMED")
            if projection["cutoff_status"] != "RECONCILED":
                connection.rollback()
                return self._late_entry_reconstruction_blocked(
                    "INVENTORY_CUTOFF_UNRECONCILED",
                    required_evidence=(
                        "Подтверждённый исторический остаток на дату перехода по складам Ozon, "
                        "дому и пути",
                        "Полный перечень продаж, возвратов, приёмок, перемещений и списаний "
                        "после среза",
                        "Согласованная граница между остатком и финансовыми продажами",
                    ),
                )
            if projection["queue_complete"] != 1:
                connection.rollback()
                return self._late_entry_reconstruction_blocked("HISTORY_GAP")

            anchor = connection.execute(
                """SELECT COUNT(DISTINCT inventory_cutoff), MIN(inventory_cutoff)
                   FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='OPENING_FIFO_ANCHOR'""",
                (stream_id,),
            ).fetchone()
            if anchor[0] != 1 or self._normalize_date(anchor[1]) is None:
                connection.rollback()
                return self._late_entry_reconstruction_blocked("ANCHOR_UNCONFIRMED")
            anchor_date = anchor[1]
            effective_date = draft["owner_effective_date"]
            if self._normalize_date(effective_date) is None or effective_date <= anchor_date:
                connection.rollback()
                return self._late_entry_reconstruction_blocked("RECONCILIATION_CONFLICT")

            event_count = connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_events WHERE stream_id=?",
                (stream_id,),
            ).fetchone()[0]
            if event_count > 100_000:
                connection.rollback()
                return self._late_entry_reconstruction_blocked("FIFO_REPLAY_INPUT_LIMIT")
            unsupported = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind NOT IN (
                       'OPENING_FIFO_ANCHOR', 'PHYSICAL_SALE',
                       'SALEABLE_RETURN_RESTOCK', 'NON_SALE_OUTFLOW'
                   )""",
                (stream_id,),
            ).fetchone()[0]
            if unsupported:
                connection.rollback()
                return self._late_entry_reconstruction_blocked("HISTORY_GAP")
            unresolved_dates = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind<>'OPENING_FIFO_ANCHOR'
                     AND (effective_date IS NULL OR effective_date<=?)""",
                (stream_id, anchor_date),
            ).fetchone()[0]
            if unresolved_dates:
                connection.rollback()
                return self._late_entry_reconstruction_blocked("EVENT_ORDER_UNRESOLVED")
            cutoff_mismatches = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='PHYSICAL_SALE'
                     AND (inventory_cutoff IS NULL OR inventory_cutoff<>?
                          OR effective_date IS NULL OR effective_date<=?)""",
                (stream_id, anchor_date, anchor_date),
            ).fetchone()[0]
            if cutoff_mismatches:
                connection.rollback()
                return self._late_entry_reconstruction_blocked(
                    "INVENTORY_CUTOFF_UNRECONCILED",
                )
            if connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_rate_changes AS r
                   WHERE r.stream_id=? AND NOT EXISTS (
                       SELECT 1 FROM fifo_cost_rate_cancellations AS c
                       WHERE c.stream_id=r.stream_id
                         AND c.rate_change_id=r.rate_change_id
                   )""",
                (stream_id,),
            ).fetchone()[0]:
                connection.rollback()
                return self._late_entry_reconstruction_blocked(
                    "FIFO_REPLAY_RATE_TRANSITION_UNSUPPORTED",
                )
            untrusted_sales = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_events AS e
                   LEFT JOIN fifo_cost_sources AS s ON s.source_id=e.source_id
                   WHERE e.stream_id=? AND e.event_kind='PHYSICAL_SALE' AND NOT (
                       e.provenance='OZON_CONFIRMED_FIELD'
                       AND e.completeness='COMPLETE'
                       AND s.source_method='OZON_REALIZATION_REPORT'
                       AND s.source_status='COMPLETE'
                       AND s.coverage_status='COMPLETE'
                   )""",
                (stream_id,),
            ).fetchone()[0]
            if untrusted_sales:
                connection.rollback()
                return self._late_entry_reconstruction_blocked(
                    "PHYSICAL_SALE_IDENTITY_UNCONFIRMED",
                )

            source_fingerprint = self._allocation_source_fingerprint(
                connection, stream_id, stream["revision"], stream["policy_version"],
                projection["cutoff_status"],
            )
            allocation_revision = connection.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM fifo_cost_allocations WHERE stream_id=?",
                (stream_id,),
            ).fetchone()[0]
            candidate_rate_id = "late_candidate_" + draft_id[-24:]
            candidate_rate = FifoOpenCostRate(
                candidate_rate_id, draft["unit_cost_rub"],
            )
            common = {
                "stream_revision": stream["revision"],
                "allocation_revision": allocation_revision,
                "source_fingerprint": source_fingerprint,
                "cutoff_status": projection["cutoff_status"],
                "anchor_cutoff_date": anchor_date,
            }
            after = self._preview_allocation_from_connection(
                connection, stream_id, **common,
                hypothetical_open_rate=candidate_rate,
                hypothetical_open_rate_effective_date=effective_date,
            )
            if after is None or after.get("complete") is not True:
                connection.rollback()
                return self._late_entry_reconstruction_blocked(
                    after.get("reason_code") if isinstance(after, dict) else "HISTORY_GAP",
                )

            before = self._preview_allocation_from_connection(
                connection, stream_id, **common,
            )
            sale_event_rows = connection.execute(
                """SELECT event_id, effective_date, source_identity_digest
                   FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='PHYSICAL_SALE'""",
                (stream_id,),
            ).fetchall()
            event_dates = {
                row["event_id"]: row["effective_date"] for row in sale_event_rows
            }
            sale_identity_digests = {
                row["event_id"]: row["source_identity_digest"]
                for row in sale_event_rows
            }
            related_returns = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='SALEABLE_RETURN_RESTOCK'""",
                (stream_id,),
            ).fetchone()[0]
            non_sale_outflows = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='NON_SALE_OUTFLOW'""",
                (stream_id,),
            ).fetchone()[0]

            sales_before = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='PHYSICAL_SALE'
                     AND effective_date<?""",
                (stream_id, effective_date),
            ).fetchone()[0]
            sales_after = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_events
                   WHERE stream_id=? AND event_kind='PHYSICAL_SALE'
                     AND effective_date>?""",
                (stream_id, effective_date),
            ).fetchone()[0]
            candidate_rate_units = sum(
                line["quantity"]
                for allocation in after["allocations"]
                for line in allocation["lines"]
                if line.get("rate_change_id") == candidate_rate_id
            )
            fingerprint = self._sha256({
                "draft_fingerprint": draft["payload_fingerprint"],
                "source_set_fingerprint": source_fingerprint,
                "stream_revision": stream["revision"],
                "allocation_revision": allocation_revision,
                "anchor_date": anchor_date,
                "candidate": after["preview_fingerprint"],
            })
            connection.commit()
            return {
                "error": False,
                "code": "FIFO_LATE_ENTRY_RECONSTRUCTION_READY",
                "draft_id": draft_id,
                "complete": True,
                "preview_fingerprint": fingerprint,
                "stream_revision": stream["revision"],
                "allocation_revision": allocation_revision,
                "source_set_fingerprint": source_fingerprint,
                "anchor_cutoff_date": anchor_date,
                "effective_date": effective_date,
                "recorded_at": self._now().isoformat(),
                "candidate_unit_cost_rub": draft["unit_cost_rub"],
                "owner_old_home_units": draft["owner_old_home_units"],
                "accepted_units_documentary_only": draft["accepted_units"],
                "accepted_units_added_to_stock": 0,
                "sales_before_boundary": sales_before,
                "sales_after_boundary": sales_after,
                "candidate_rate_units": candidate_rate_units,
                "candidate_total_cogs_rub": after["total_cogs_rub"],
                "candidate_allocations": after["allocations"],
                "candidate_outflows": after["outflows"],
                "candidate_non_sale_outflow_value_rub": after[
                    "non_sale_outflow_value_rub"
                ],
                "candidate_restored_units": after["restored_units"],
                "return_cogs_authorization_changed": False,
                "before_complete": bool(before and before.get("complete") is True),
                "before_reason_code": (
                    before.get("reason_code") if isinstance(before, dict) else "HISTORY_GAP"
                ),
                "before_total_cogs_rub": (
                    before.get("total_cogs_rub")
                    if isinstance(before, dict) and before.get("complete") is True
                    else None
                ),
                "before_allocations": (
                    before.get("allocations")
                    if isinstance(before, dict) and before.get("complete") is True
                    else []
                ),
                "before_outflows": (
                    before.get("outflows")
                    if isinstance(before, dict) and before.get("complete") is True
                    else []
                ),
                "before_non_sale_outflow_value_rub": (
                    before.get("non_sale_outflow_value_rub")
                    if isinstance(before, dict) and before.get("complete") is True
                    else None
                ),
                "sale_effective_dates": event_dates,
                "sale_identity_digests_by_event": sale_identity_digests,
                "related_return_count": related_returns,
                "non_sale_outflow_count": non_sale_outflows,
                "period_profit_changed": False,
                "read_only": True,
            }
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_RECONCILIATION_CONFLICT"
            return self._error(code)
        except (sqlite3.Error, OSError):
            if connection is not None and connection.in_transaction:
                connection.rollback()
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def read_late_entry_corrections(
        self, *, store_id, product_id=None, offer_id=None, sku,
    ):
        """Read immutable correction snapshots for one exact tenant/SKU stream."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        connection = None
        try:
            identity = self._normalize_identity(store_id, product_id, offer_id, sku, 1)
            fingerprint = self._sha256(identity)
            stream_id = "fifo_" + fingerprint[:40]
            connection = self.get_connection()
            rows = connection.execute(
                """SELECT c.correction_id, c.stream_revision, c.draft_id,
                          c.effective_date, c.unit_cost_rub, c.reason_code,
                          c.preview_fingerprint, c.reconstruction_fingerprint,
                          c.source_set_fingerprint, c.allocation_revision,
                          c.tax_policy_fingerprint,
                          c.period_source_fingerprints_json, c.impact_json,
                          c.idempotency_key, c.recorded_at
                   FROM fifo_cost_late_entry_corrections AS c
                   JOIN fifo_cost_streams AS s ON s.stream_id=c.stream_id
                   WHERE c.stream_id=? AND s.store_id=?
                     AND s.identity_fingerprint=?
                   ORDER BY c.stream_revision, c.correction_id LIMIT 201""",
                (stream_id, identity["store_id"], fingerprint),
            ).fetchall()
            if len(rows) > 200:
                return self._error("FIFO_LATE_ENTRY_HISTORY_LIMIT")
            result = []
            for row in rows:
                try:
                    impact = json.loads(row["impact_json"])
                    period_sources = json.loads(row["period_source_fingerprints_json"])
                except (TypeError, json.JSONDecodeError):
                    return self._error("FIFO_LATE_ENTRY_HISTORY_INVALID")
                if not isinstance(impact, dict) or not isinstance(period_sources, list):
                    return self._error("FIFO_LATE_ENTRY_HISTORY_INVALID")
                item = dict(row)
                item.pop("impact_json")
                item.pop("period_source_fingerprints_json")
                item["impact"] = impact
                item["period_source_fingerprints"] = period_sources
                result.append(item)
            return {
                "error": False,
                "code": "FIFO_LATE_ENTRY_CORRECTIONS_READY",
                "corrections": result,
            }
        except (TypeError, ValueError):
            return self._error("FIFO_IDENTITY_INVALID")
        except (sqlite3.Error, OSError):
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def preview_cancel_future_rate(
        self, *, store_id, product_id=None, offer_id=None, sku,
        rate_sequence, expected_revision,
    ):
        """Preview cancellation of one unused, future-dated latest rate."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        if type(rate_sequence) is not int or rate_sequence < 1:
            return self._error("FIFO_RATE_SEQUENCE_INVALID")
        if type(expected_revision) is not int or expected_revision < 1:
            return self._error("FIFO_REVISION_CONFLICT")
        connection = None
        try:
            now = self._now()
            identity = self._normalize_identity(store_id, product_id, offer_id, sku, 1)
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            connection = self.get_connection()
            connection.execute("BEGIN")
            stream = connection.execute(
                """SELECT state, revision, policy_version FROM fifo_cost_streams
                   WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                (stream_id, identity["store_id"], identity_fingerprint),
            ).fetchone()
            projection = connection.execute(
                """SELECT revision, state, cutoff_status, source_set_fingerprint
                   FROM fifo_cost_projections WHERE stream_id=?""",
                (stream_id,),
            ).fetchone()
            if stream is None or projection is None:
                connection.rollback()
                return self._error("FIFO_HISTORY_NOT_INITIALIZED")
            if stream["revision"] != expected_revision or projection["revision"] != stream["revision"]:
                connection.rollback()
                return self._error("FIFO_REVISION_CONFLICT")
            rate = connection.execute(
                """SELECT r.rate_change_id, r.rate_sequence, r.effective_date
                   FROM fifo_cost_rate_changes AS r
                   WHERE r.stream_id=? AND r.rate_sequence=?
                     AND NOT EXISTS (
                         SELECT 1 FROM fifo_cost_rate_cancellations AS c
                         WHERE c.stream_id=r.stream_id
                           AND c.rate_change_id=r.rate_change_id
                     )""",
                (stream_id, rate_sequence),
            ).fetchone()
            latest = connection.execute(
                """SELECT COALESCE(MAX(r.rate_sequence), 0)
                   FROM fifo_cost_rate_changes AS r WHERE r.stream_id=?
                     AND NOT EXISTS (
                         SELECT 1 FROM fifo_cost_rate_cancellations AS c
                         WHERE c.stream_id=r.stream_id
                           AND c.rate_change_id=r.rate_change_id
                     )""",
                (stream_id,),
            ).fetchone()[0]
            if rate is None or latest != rate_sequence:
                connection.rollback()
                return self._error("FIFO_RATE_CANCELLATION_NOT_LATEST")
            if rate["effective_date"] <= now.date().isoformat():
                connection.rollback()
                return self._error("FIFO_RATE_CANCELLATION_NOT_FUTURE")
            anchor = connection.execute(
                """SELECT COUNT(*) AS count, COUNT(DISTINCT inventory_cutoff) AS cutoffs,
                          MIN(inventory_cutoff) AS cutoff
                   FROM fifo_cost_events WHERE stream_id=?
                     AND event_kind='OPENING_FIFO_ANCHOR'
                     AND provenance='OWNER_CONFIRMED'
                     AND completeness='OWNER_CONFIRMED'""",
                (stream_id,),
            ).fetchone()
            if anchor["count"] < 1 or anchor["cutoffs"] != 1 or self._normalize_date(anchor["cutoff"]) is None:
                connection.rollback()
                return self._error("FIFO_ANCHOR_UNCONFIRMED")
            future_event_count = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_events WHERE stream_id=?
                   AND event_kind<>'OPENING_FIFO_ANCHOR'
                   AND (effective_date IS NULL OR effective_date>=?)""",
                (stream_id, rate["effective_date"]),
            ).fetchone()[0]
            allocated_rate = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_allocation_rate_lines
                   WHERE rate_change_id=?""",
                (rate["rate_change_id"],),
            ).fetchone()[0]
            if future_event_count or allocated_rate:
                connection.rollback()
                return self._error("FIFO_RATE_FUTURE_EVENT_ALREADY_USED")
            if connection.execute(
                """SELECT 1 FROM fifo_cost_rate_reconciliations
                   WHERE stream_id=? AND transition_rate_sequence=? LIMIT 1""",
                (stream_id, rate_sequence),
            ).fetchone() is not None:
                connection.rollback()
                return self._error("FIFO_RATE_RECONCILIATION_ALREADY_EXISTS")
            source_fingerprint = self._allocation_source_fingerprint(
                connection, stream_id, stream["revision"],
                stream["policy_version"], projection["cutoff_status"],
            )
            material = {
                "stream_id": stream_id,
                "identity_fingerprint": identity_fingerprint,
                "stream_revision": stream["revision"],
                "rate_sequence": rate_sequence,
                "effective_date": rate["effective_date"],
                "source_set_fingerprint": source_fingerprint,
                "anchor_cutoff_date": anchor["cutoff"],
                "reason_code": "CANCELLED_FUTURE_CHANGE",
            }
            preview_fingerprint = self._sha256(material)
            preview_id = "rate_cancel_" + preview_fingerprint
            ticket_key = scope["owner_fingerprint"]
            ticket = {
                **material,
                "preview_fingerprint": preview_fingerprint,
                "preview_id": preview_id,
                "tenant_fingerprint": scope["tenant_fingerprint"],
                "identity": identity,
                "expires_at": now.timestamp() + self.PREVIEW_TTL_SECONDS,
            }
            with self._PREVIEW_LOCK:
                for key in [
                    key for key, item in self._ACTIVE_RATE_CANCELLATION_PREVIEWS.items()
                    if item["expires_at"] <= now.timestamp()
                ]:
                    self._ACTIVE_RATE_CANCELLATION_PREVIEWS.pop(key, None)
                self._ACTIVE_RATE_CANCELLATION_PREVIEWS[ticket_key] = ticket
            connection.commit()
            return {
                "error": False,
                "code": "FIFO_RATE_CANCELLATION_PREVIEW_READY",
                "preview_id": preview_id,
                "active_preview_id": preview_id,
                "preview_fingerprint": preview_fingerprint,
                "stream_revision": stream["revision"],
                "rate_sequence": rate_sequence,
                "effective_date": rate["effective_date"],
                "current_date": now.date().isoformat(),
                "reason_code": "CANCELLED_FUTURE_CHANGE",
                "read_only": True,
                "expires_in_seconds": self.PREVIEW_TTL_SECONDS,
            }
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_RATE_CANCELLATION_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            if connection is not None and connection.in_transaction:
                connection.rollback()
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def commit_cancel_future_rate(
        self, *, preview_id, active_preview_id, idempotency_key,
        store_id, product_id=None, offer_id=None, sku,
    ):
        """Append a cancellation record; never delete or edit the scheduled rate."""
        key = str(idempotency_key or "")
        if not self._IDEMPOTENCY_KEY.fullmatch(key):
            return self._error("FIFO_IDEMPOTENCY_KEY_INVALID")
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        if (
            not isinstance(preview_id, str)
            or preview_id != active_preview_id
            or not re.fullmatch(r"rate_cancel_[0-9a-f]{64}", preview_id)
        ):
            return self._error("FIFO_PREVIEW_STALE")
        connection = None
        try:
            identity = self._normalize_identity(store_id, product_id, offer_id, sku, 1)
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            expected_fingerprint = preview_id.removeprefix("rate_cancel_")
            now = self._now()
            connection = self.get_connection()
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                """SELECT cancellation_id, stream_revision, rate_sequence,
                          effective_date, preview_fingerprint
                   FROM fifo_cost_rate_cancellations
                   WHERE stream_id=? AND idempotency_key=?""",
                (stream_id, key),
            ).fetchone()
            if prior is not None:
                if prior["preview_fingerprint"] != expected_fingerprint:
                    connection.rollback()
                    return self._error("FIFO_IDEMPOTENCY_CONFLICT")
                connection.rollback()
                return {
                    "error": False,
                    "code": "FIFO_RATE_CANCELLATION_COMMITTED",
                    "idempotent": True,
                    "stream_revision": prior["stream_revision"],
                    "rate_sequence": prior["rate_sequence"],
                    "effective_date": prior["effective_date"],
                    "replay_required": True,
                    "projection_complete": False,
                }
            ticket_key = scope["owner_fingerprint"]
            with self._PREVIEW_LOCK:
                ticket = self._ACTIVE_RATE_CANCELLATION_PREVIEWS.get(ticket_key)
                if (
                    ticket is None or ticket["preview_id"] != preview_id
                    or ticket["identity"] != identity
                    or ticket["tenant_fingerprint"] != scope["tenant_fingerprint"]
                    or ticket["preview_fingerprint"] != expected_fingerprint
                    or ticket["expires_at"] <= now.timestamp()
                ):
                    connection.rollback()
                    return self._error("FIFO_PREVIEW_STALE")
            stream = connection.execute(
                """SELECT revision, policy_version FROM fifo_cost_streams
                   WHERE stream_id=? AND store_id=? AND identity_fingerprint=?""",
                (stream_id, identity["store_id"], identity_fingerprint),
            ).fetchone()
            projection = connection.execute(
                """SELECT revision, cutoff_status, source_set_fingerprint
                   FROM fifo_cost_projections WHERE stream_id=?""",
                (stream_id,),
            ).fetchone()
            rate = connection.execute(
                """SELECT r.rate_change_id, r.rate_sequence, r.effective_date
                   FROM fifo_cost_rate_changes AS r
                   WHERE r.stream_id=? AND r.rate_sequence=?
                     AND NOT EXISTS (
                         SELECT 1 FROM fifo_cost_rate_cancellations AS c
                         WHERE c.stream_id=r.stream_id
                           AND c.rate_change_id=r.rate_change_id
                     )""",
                (stream_id, ticket["rate_sequence"]),
            ).fetchone()
            latest = connection.execute(
                """SELECT COALESCE(MAX(r.rate_sequence), 0)
                   FROM fifo_cost_rate_changes AS r WHERE r.stream_id=?
                     AND NOT EXISTS (
                         SELECT 1 FROM fifo_cost_rate_cancellations AS c
                         WHERE c.stream_id=r.stream_id
                           AND c.rate_change_id=r.rate_change_id
                     )""",
                (stream_id,),
            ).fetchone()[0]
            if (
                stream is None or projection is None or rate is None
                or stream["revision"] != ticket["stream_revision"]
                or projection["revision"] != stream["revision"]
                or latest != ticket["rate_sequence"]
                or rate["effective_date"] != ticket["effective_date"]
                or rate["effective_date"] <= now.date().isoformat()
            ):
                connection.rollback()
                return self._error("FIFO_RATE_CANCELLATION_STALE")
            current_source = self._allocation_source_fingerprint(
                connection, stream_id, stream["revision"],
                stream["policy_version"], projection["cutoff_status"],
            )
            if current_source != ticket["source_set_fingerprint"]:
                connection.rollback()
                return self._error("FIFO_RATE_CANCELLATION_STALE")
            future_event_count = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_events WHERE stream_id=?
                   AND event_kind<>'OPENING_FIFO_ANCHOR'
                   AND (effective_date IS NULL OR effective_date>=?)""",
                (stream_id, rate["effective_date"]),
            ).fetchone()[0]
            allocated_rate = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_allocation_rate_lines
                   WHERE rate_change_id=?""",
                (rate["rate_change_id"],),
            ).fetchone()[0]
            if future_event_count or allocated_rate:
                connection.rollback()
                return self._error("FIFO_RATE_FUTURE_EVENT_ALREADY_USED")
            if connection.execute(
                """SELECT 1 FROM fifo_cost_rate_reconciliations
                   WHERE stream_id=? AND transition_rate_sequence=? LIMIT 1""",
                (stream_id, rate["rate_sequence"]),
            ).fetchone() is not None:
                connection.rollback()
                return self._error("FIFO_RATE_RECONCILIATION_ALREADY_EXISTS")
            next_revision = stream["revision"] + 1
            cancellation_id = "rate_cancelled_" + uuid4().hex
            connection.execute(
                """INSERT INTO fifo_cost_rate_cancellations (
                       cancellation_id, stream_id, stream_revision, rate_change_id,
                       rate_sequence, effective_date, reason_code,
                       preview_fingerprint, source_set_fingerprint,
                       idempotency_key, recorded_at
                   ) VALUES (?, ?, ?, ?, ?, ?, 'CANCELLED_FUTURE_CHANGE', ?, ?, ?, ?)""",
                (
                    cancellation_id, stream_id, next_revision, rate["rate_change_id"],
                    rate["rate_sequence"], rate["effective_date"],
                    ticket["preview_fingerprint"], ticket["source_set_fingerprint"],
                    key, self._iso(now),
                ),
            )
            connection.execute(
                "UPDATE fifo_cost_streams SET state='FIFO_PARTIAL', revision=?, updated_at=? "
                "WHERE stream_id=? AND revision=?",
                (next_revision, self._iso(now), stream_id, stream["revision"]),
            )
            connection.execute(
                """UPDATE fifo_cost_projections
                   SET revision=?, state='FIFO_PARTIAL', queue_complete=0,
                       source_set_fingerprint=?, updated_at=?
                   WHERE stream_id=? AND revision=?""",
                (
                    next_revision,
                    self._sha256({
                        "previous": projection["source_set_fingerprint"],
                        "rate_cancellation": ticket["preview_fingerprint"],
                    }),
                    self._iso(now), stream_id, stream["revision"],
                ),
            )
            connection.commit()
            with self._PREVIEW_LOCK:
                current = self._ACTIVE_RATE_CANCELLATION_PREVIEWS.get(ticket_key)
                if current is not None and current["preview_id"] == preview_id:
                    self._ACTIVE_RATE_CANCELLATION_PREVIEWS.pop(ticket_key, None)
            return {
                "error": False,
                "code": "FIFO_RATE_CANCELLATION_COMMITTED",
                "idempotent": False,
                "stream_revision": next_revision,
                "rate_sequence": rate["rate_sequence"],
                "effective_date": rate["effective_date"],
                "reason_code": "CANCELLED_FUTURE_CHANGE",
                "replay_required": True,
                "projection_complete": False,
            }
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_RATE_CANCELLATION_INVALID"
            return self._error(code)
        except sqlite3.IntegrityError:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            return self._error("FIFO_RATE_CANCELLATION_CONFLICT")
        except (sqlite3.Error, OSError):
            if connection is not None and connection.in_transaction:
                connection.rollback()
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _late_entry_reconstruction_blocked(reason, *, stream_revision=None, required_evidence=()):
        return {
            "error": False,
            "code": "FIFO_LATE_ENTRY_RECONSTRUCTION_BLOCKED",
            "complete": False,
            "reason_code": reason or "HISTORY_GAP",
            "stream_revision": stream_revision,
            "required_evidence": list(required_evidence),
            "current_stock_used_as_historical": False,
            "period_profit_changed": False,
            "read_only": True,
        }

    def read_supply_evidence_history(
        self, *, store_id, product_id=None, offer_id=None, sku,
    ):
        """Read redacted, date-provenance-aware supply evidence for one SKU."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        connection = None
        try:
            identity = self._normalize_identity(store_id, product_id, offer_id, sku, 1)
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            connection = self.get_connection()
            rows = connection.execute(
                """SELECT e.snapshot_sequence, e.stream_revision, e.source_status, e.captured_at,
                          e.source_as_of, e.physical_effective_at,
                          e.physical_effective_date, e.normalized_evidence_json
                   FROM fifo_cost_supply_evidence AS e
                   JOIN fifo_cost_streams AS s ON s.stream_id=e.stream_id
                   WHERE e.stream_id=? AND s.store_id=? AND s.identity_fingerprint=?
                   ORDER BY e.snapshot_sequence""",
                (stream_id, identity["store_id"], identity_fingerprint),
            ).fetchall()
            snapshots = []
            for row in rows:
                evidence = json.loads(row["normalized_evidence_json"])
                snapshots.append({
                    "evidence_sequence": row["snapshot_sequence"],
                    "stream_revision": row["stream_revision"],
                    "status": evidence["status"],
                    "source_status": row["source_status"],
                    "captured_at": row["captured_at"],
                    "source_as_of": row["source_as_of"],
                    "physical_effective_at": row["physical_effective_at"],
                    "physical_effective_date": row["physical_effective_date"],
                    "accepted_units": evidence["fact_units"],
                    "order_ref": evidence["order_ref"],
                    "supply_ref": evidence["supply_ref"],
                    "acts": evidence["act_evidence"],
                })
            return {"error": False, "code": "FIFO_SUPPLY_EVIDENCE_READY", "snapshots": snapshots}
        except (TypeError, ValueError):
            return self._error("FIFO_IDENTITY_INVALID")
        except (sqlite3.Error, OSError):
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def preview_command(
        self, *, store_id, product_id=None, offer_id=None, sku,
        policy_version=1, events, source, expected_revision=None,
    ):
        """Create a short-lived, read-only ticket bound to tenant and SKU."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        try:
            identity = self._normalize_identity(
                store_id, product_id, offer_id, sku, policy_version,
            )
            normalized_source = self._normalize_source(source)
            normalized_events = self._normalize_events(events, normalized_source)
            total_units = sum(item["quantity"] for item in normalized_events)
            if total_units > self.MAX_COMMAND_UNITS:
                return self._error("FIFO_STREAM_QUANTITY_LIMIT")
            stable_events = [
                {key: value for key, value in event.items() if key != "event_id"}
                for event in normalized_events
            ]
            source_fingerprint = normalized_source.get("source_fingerprint")
            if not source_fingerprint:
                source_fingerprint = self._sha256({
                    "source": {
                        key: value for key, value in normalized_source.items()
                        if key != "source_fingerprint"
                    },
                    "events": stable_events,
                })
            normalized_source["source_fingerprint"] = source_fingerprint
            source_id = "src_" + self._sha256({
                "store_id": identity["store_id"],
                "source_fingerprint": source_fingerprint,
            })[:40]
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]

            connection = self.get_connection()
            try:
                row = connection.execute(
                    "SELECT revision, state FROM fifo_cost_streams WHERE stream_id=?",
                    (stream_id,),
                ).fetchone()
                current_revision = int(row["revision"]) if row else 0
                current_state = row["state"] if row else "FIFO_PENDING_ANCHOR"
            finally:
                connection.close()

            if any(event["kind"] == "OPENING_FIFO_ANCHOR" for event in normalized_events):
                anchor_error = self._opening_anchor_error(
                    normalized_events,
                    normalized_source,
                    current_revision=current_revision,
                    current_state=current_state,
                )
                if anchor_error:
                    return self._error(anchor_error)

            if expected_revision is not None and (
                type(expected_revision) is not int
                or expected_revision < 0
                or expected_revision != current_revision
            ):
                return self._error("FIFO_REVISION_CONFLICT")

            now = self._now()
            command_id = "cmd_" + uuid4().hex
            normalized = {
                "tenant_fingerprint": scope["tenant_fingerprint"],
                "identity": identity,
                "identity_fingerprint": identity_fingerprint,
                "stream_id": stream_id,
                "source": normalized_source,
                "source_id": source_id,
                "events": normalized_events,
                "expected_revision": current_revision,
                "next_revision": current_revision + 1,
                "current_state": current_state,
                "command_id": command_id,
            }
            payload = {
                key: value for key, value in normalized.items()
                if key not in {"command_id"}
            }
            payload["events"] = stable_events
            payload_fingerprint = self._sha256(payload)
            normalized["payload_fingerprint"] = payload_fingerprint
            if len(self._canonical_json(normalized).encode("utf-8")) > self.MAX_PAYLOAD_BYTES:
                return self._error("FIFO_COMMAND_PAYLOAD_LIMIT")

            preview_id = "preview_" + uuid4().hex
            ticket = {
                "preview_id": preview_id,
                "expires_at": (now.timestamp() + self.PREVIEW_TTL_SECONDS),
                "normalized": normalized,
            }
            preview_scope = scope["owner_fingerprint"]
            with self._PREVIEW_LOCK:
                self._purge_expired_previews(now)
                if (len(self._ACTIVE_PREVIEWS) >= self.MAX_PREVIEWS
                        and preview_scope not in self._ACTIVE_PREVIEWS):
                    return self._error("FIFO_PREVIEW_CAPACITY_EXCEEDED")
                self._ACTIVE_PREVIEWS[preview_scope] = ticket

            return {
                "error": False,
                "code": "FIFO_PREVIEW_READY",
                "preview_id": preview_id,
                "expected_revision": current_revision,
                "next_revision": current_revision + 1,
                "event_count": len(normalized_events),
                "total_units": total_units,
                "source_fingerprint": source_fingerprint,
                "payload_fingerprint": payload_fingerprint,
                "expires_in_seconds": self.PREVIEW_TTL_SECONDS,
                "state": current_state,
            }
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_COMMAND_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            return self._error("FIFO_STORAGE_UNAVAILABLE")

    def commit_command(self, *, preview_id, active_preview_id, idempotency_key):
        """Atomically append a previewed command with revision and idempotency CAS."""
        key = str(idempotency_key or "")
        if not self._IDEMPOTENCY_KEY.fullmatch(key):
            return self._error("FIFO_IDEMPOTENCY_KEY_INVALID")
        try:
            now = self._now()
        except ValueError as exc:
            return self._error(str(exc))
        connection = None
        with self._PREVIEW_LOCK:
            self._purge_expired_previews(now)
            tenant_id = str(get_current_tenant_user_id() or "").strip()
            tenant_fingerprint = self._sha256_text(tenant_id) if tenant_id else ""
            owner_id, _ = split_store_tenant_scope(tenant_id)
            owner_fingerprint = self._sha256_text(owner_id) if owner_id else ""
            ticket = self._ACTIVE_PREVIEWS.get(owner_fingerprint)
            if (ticket is None or not preview_id or preview_id != active_preview_id
                    or ticket["preview_id"] != preview_id):
                return self._error("FIFO_PREVIEW_STALE")
            normalized = ticket["normalized"]
            scope = self._tenant_scope(normalized["identity"]["store_id"])
            if (scope.get("error")
                    or scope["tenant_fingerprint"] != normalized["tenant_fingerprint"]):
                return self._error("FIFO_STORE_SCOPE_MISMATCH")

            try:
                connection = self.get_connection()
                connection.execute("BEGIN IMMEDIATE")
                previous = connection.execute(
                    """SELECT payload_fingerprint, result_reference
                       FROM fifo_cost_idempotency
                       WHERE stream_id=? AND idempotency_key=?""",
                    (normalized["stream_id"], key),
                ).fetchone()
                if previous is not None:
                    if previous["payload_fingerprint"] != normalized["payload_fingerprint"]:
                        connection.rollback()
                        return self._error("FIFO_IDEMPOTENCY_CONFLICT")
                    result = json.loads(previous["result_reference"])
                    connection.rollback()
                    return {
                        "error": False,
                        "code": "FIFO_COMMAND_COMMITTED",
                        "idempotent": True,
                        **result,
                    }

                identity_conflict = self._identity_stream_conflict(
                    connection,
                    normalized["identity"],
                    normalized["identity_fingerprint"],
                )
                if identity_conflict is not None:
                    connection.rollback()
                    return identity_conflict

                stream = connection.execute(
                    "SELECT revision, state FROM fifo_cost_streams WHERE stream_id=?",
                    (normalized["stream_id"],),
                ).fetchone()
                if stream is None:
                    if normalized["expected_revision"] != 0:
                        connection.rollback()
                        return self._error("FIFO_REVISION_CONFLICT")
                    initial_state = "FIFO_PENDING_ANCHOR"
                    identity = normalized["identity"]
                    connection.execute(
                        """INSERT INTO fifo_cost_streams (
                            stream_id, store_id, product_id, offer_id, sku,
                            identity_fingerprint, policy_version, state, revision,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                        (
                            normalized["stream_id"], identity["store_id"],
                            identity["product_id"], identity["offer_id"],
                            identity["sku"], normalized["identity_fingerprint"],
                            identity["policy_version"], initial_state,
                            self._iso(now), self._iso(now),
                        ),
                    )
                    current_revision = 0
                    current_state = initial_state
                else:
                    current_revision = int(stream["revision"])
                    current_state = stream["state"]
                if current_revision != normalized["expected_revision"]:
                    connection.rollback()
                    return self._error("FIFO_REVISION_CONFLICT")

                return_events = [
                    event for event in normalized["events"]
                    if event["kind"] == "SALEABLE_RETURN_RESTOCK"
                ]
                if return_events and len(normalized["events"]) != 1:
                    connection.rollback()
                    return self._error("FIFO_RETURN_COMMAND_MUST_BE_EXCLUSIVE")
                outflow_events = [
                    event for event in normalized["events"]
                    if event["kind"] == "NON_SALE_OUTFLOW"
                ]
                if outflow_events and len(normalized["events"]) != 1:
                    connection.rollback()
                    return self._error("FIFO_MOVEMENT_COMMAND_MUST_BE_EXCLUSIVE")

                has_opening_anchor = any(
                    event["kind"] == "OPENING_FIFO_ANCHOR"
                    for event in normalized["events"]
                )
                if has_opening_anchor:
                    anchor_error = self._opening_anchor_error(
                        normalized["events"],
                        normalized["source"],
                        current_revision=current_revision,
                        current_state=current_state,
                    )
                    if anchor_error:
                        connection.rollback()
                        return self._error(anchor_error)

                self._ensure_source(connection, normalized)
                self._ensure_policy_revision(connection, normalized, now)
                command_id = normalized["command_id"]
                next_revision = current_revision + 1
                connection.execute(
                    """INSERT INTO fifo_cost_commands (
                        command_id, stream_id, stream_revision, payload_fingerprint,
                        source_fingerprint, event_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        command_id, normalized["stream_id"], next_revision,
                        normalized["payload_fingerprint"],
                        normalized["source"]["source_fingerprint"],
                        len(normalized["events"]), self._iso(now),
                    ),
                )
                event_ids = []
                for order, event in enumerate(normalized["events"], start=1):
                    target_kind = self._validate_supersedes_target(
                        connection, normalized["stream_id"], event,
                        normalized["events"][:order - 1],
                    )
                    if event["kind"] == "SALE_CANCELLATION" and target_kind != "PHYSICAL_SALE":
                        raise ValueError("FIFO_EVENT_TARGET_INVALID")
                    if (event["kind"] == "SALEABLE_RETURN_RESTOCK"
                            and target_kind != "PHYSICAL_SALE"):
                        raise ValueError("FIFO_EVENT_TARGET_INVALID")
                    if event["kind"] == "CORRECTION" and not event.get("reason_code"):
                        raise ValueError("FIFO_EVENT_REASON_REQUIRED")
                    return_basis = None
                    if event["kind"] == "SALEABLE_RETURN_RESTOCK":
                        return_basis = self._prepare_return_basis(
                            connection,
                            normalized["stream_id"],
                            event,
                            normalized["source"],
                            expected_stream_revision=current_revision,
                        )
                    event_id = event["event_id"]
                    event_ids.append(event_id)
                    connection.execute(
                        """INSERT INTO fifo_cost_events (
                            event_id, stream_id, event_kind, event_schema_version,
                            effective_at, effective_date, recorded_at,
                            captured_at, source_as_of, inventory_cutoff, quantity,
                            unit_cost_rub, purchase_cost_rub, delivery_cost_rub,
                            packaging_cost_rub, currency, location_from, location_to,
                            source_id, source_fingerprint, provenance, completeness,
                            source_identity_digest, supersedes_event_id, reason_code,
                            created_at
                        ) VALUES (
                            ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RUB',
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                        )""",
                        (
                            event_id, normalized["stream_id"], event["kind"],
                            event["effective_at"], event["effective_date"],
                            self._iso(now), normalized["source"]["captured_at"],
                            normalized["source"]["source_as_of"], event["inventory_cutoff"],
                            event["quantity"], event["unit_cost_rub"],
                            event["purchase_cost_rub"], event["delivery_cost_rub"],
                            event["packaging_cost_rub"], event["location_from"],
                            event["location_to"], normalized["source_id"],
                            normalized["source"]["source_fingerprint"],
                            normalized["source"]["provenance"],
                            normalized["source"]["completeness"],
                            event["source_identity_digest"],
                            event["supersedes_event_id"], event["reason_code"],
                            self._iso(now),
                        ),
                    )
                    if event["kind"] in {"OPENING_FIFO_ANCHOR", "COST_LAYER_RECEIPT"}:
                        layer_sequence = connection.execute(
                            "SELECT COALESCE(MAX(layer_sequence), 0) + 1 "
                            "FROM fifo_cost_layers WHERE stream_id=?",
                            (normalized["stream_id"],),
                        ).fetchone()[0]
                        connection.execute(
                            """INSERT INTO fifo_cost_layers (
                                layer_id, stream_id, event_id, layer_sequence,
                                quantity, unit_cost_rub, currency, effective_at,
                                effective_date, provenance, source_id, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, 'RUB', ?, ?, ?, ?, ?)""",
                            (
                                "layer_" + uuid4().hex, normalized["stream_id"],
                                event_id, layer_sequence, event["quantity"],
                                event["unit_cost_rub"], event["effective_at"],
                                event["effective_date"],
                                normalized["source"]["provenance"],
                                normalized["source_id"], self._iso(now),
                            ),
                        )
                    connection.execute(
                        """INSERT INTO fifo_cost_command_events (
                            command_id, event_id, event_order
                        ) VALUES (?, ?, ?)""",
                        (command_id, event_id, order),
                    )
                    if return_basis is not None:
                        for basis_number, basis in enumerate(return_basis, start=1):
                            connection.execute(
                                """INSERT INTO fifo_cost_return_basis (
                                    return_event_id, basis_line_number, allocation_id,
                                    allocation_line_number, origin_sale_event_id,
                                    layer_id, rate_change_id, quantity, unit_cost_rub,
                                    total_cost_rub
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (
                                    event_id, basis_number, basis["allocation_id"],
                                    basis["allocation_line_number"],
                                    event["supersedes_event_id"], basis["layer_id"],
                                    basis["rate_change_id"], basis["quantity"],
                                    basis["unit_cost_rub"], basis["total_cost_rub"],
                                ),
                            )

                new_state = current_state
                if has_opening_anchor:
                    new_state = "FIFO_READY"
                elif current_revision == 0 and not stream:
                    new_state = "FIFO_PENDING_ANCHOR"
                connection.execute(
                    """UPDATE fifo_cost_streams
                       SET revision=?, state=?, updated_at=? WHERE stream_id=?""",
                    (next_revision, new_state, self._iso(now), normalized["stream_id"]),
                )
                if has_opening_anchor:
                    known_quantity = sum(event["quantity"] for event in normalized["events"])
                    known_cost = sum(
                        Decimal(event["unit_cost_rub"]) * event["quantity"]
                        for event in normalized["events"]
                    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    next_unit_cost = normalized["events"][0]["unit_cost_rub"]
                    connection.execute(
                        """INSERT INTO fifo_cost_projections (
                            stream_id, revision, state, known_quantity,
                            known_cost_rub, next_unit_cost_rub, queue_complete,
                            cutoff_status, inventory_cutoff,
                            source_set_fingerprint, last_event_id,
                            updated_at
                        ) VALUES (?, ?, 'FIFO_READY', ?, ?, ?, 1, ?, ?, ?, ?, ?)
                        ON CONFLICT(stream_id) DO UPDATE SET
                            revision=excluded.revision,
                            state=excluded.state,
                            known_quantity=excluded.known_quantity,
                            known_cost_rub=excluded.known_cost_rub,
                            next_unit_cost_rub=excluded.next_unit_cost_rub,
                            queue_complete=excluded.queue_complete,
                            cutoff_status=excluded.cutoff_status,
                            inventory_cutoff=excluded.inventory_cutoff,
                            source_set_fingerprint=excluded.source_set_fingerprint,
                            last_event_id=excluded.last_event_id,
                            updated_at=excluded.updated_at""",
                        (
                            normalized["stream_id"], next_revision, known_quantity,
                            format(known_cost, ".2f"), next_unit_cost,
                            "INVENTORY_CUTOFF_UNRECONCILED",
                            normalized["events"][0]["inventory_cutoff"],
                            normalized["source"]["source_fingerprint"],
                            event_ids[-1], self._iso(now),
                        ),
                    )
                result = {
                    "command_id": command_id,
                    "stream_id": normalized["stream_id"],
                    "event_ids": event_ids,
                    "revision": next_revision,
                }
                connection.execute(
                    """INSERT INTO fifo_cost_idempotency (
                        stream_id, idempotency_key, payload_fingerprint,
                        result_reference, created_at
                    ) VALUES (?, ?, ?, ?, ?)""",
                    (
                        normalized["stream_id"], key,
                        normalized["payload_fingerprint"],
                        self._canonical_json(result), self._iso(now),
                    ),
                )
                connection.commit()
                return {
                    "error": False,
                    "code": "FIFO_COMMAND_COMMITTED",
                    "idempotent": False,
                    **result,
                }
            except ValueError as exc:
                if connection is not None and connection.in_transaction:
                    connection.rollback()
                code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_COMMAND_INVALID"
                return self._error(code)
            except sqlite3.IntegrityError as exc:
                if connection is not None and connection.in_transaction:
                    connection.rollback()
                detail = str(exc).lower()
                event_kinds = {
                    event["kind"] for event in normalized.get("events", [])
                }
                code = (
                    "FIFO_RETURN_IDENTITY_DUPLICATE"
                    if "SALEABLE_RETURN_RESTOCK" in event_kinds
                    and "source_identity_digest" in detail
                    else "FIFO_MOVEMENT_IDENTITY_DUPLICATE"
                    if "NON_SALE_OUTFLOW" in event_kinds
                    and "source_identity_digest" in detail
                    else "FIFO_EVENT_IDENTITY_CONFLICT"
                    if "PHYSICAL_SALE" in event_kinds
                    and "source_identity_digest" in detail
                    else "FIFO_REVISION_CONFLICT"
                )
                return self._error(code)
            except (sqlite3.Error, OSError):
                if connection is not None and connection.in_transaction:
                    connection.rollback()
                return self._error("FIFO_STORAGE_UNAVAILABLE")
            finally:
                if connection is not None:
                    connection.close()

    def preview_cost_rate_change(
        self, *, store_id, product_id=None, offer_id=None, sku,
        effective_date, purchase_cost_rub=None, delivery_cost_rub=None,
        packaging_cost_rub=None, cost_input_mode=CostInputMode.COMPONENTS,
        unit_cost_rub=None, owner_old_home_units, expected_revision,
        zero_stock_evidence=None, stock_snapshot=None,
        owner_confirms_reconciliation_scope=False,
        late_entry_correction_preview=None,
    ):
        """Preview an owner-reported open rate without adding inventory units."""
        scope = self._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        correction_preview = (
            self._normalize_late_entry_correction(late_entry_correction_preview)
            if late_entry_correction_preview is not None else None
        )
        if isinstance(correction_preview, str):
            return self._error(correction_preview)
        connection = None
        try:
            identity = self._normalize_identity(
                store_id, product_id, offer_id, sku, 1,
            )
            if (
                not isinstance(effective_date, str)
                or len(effective_date) != 10
                or self._normalize_date(effective_date) != effective_date
            ):
                return self._error("FIFO_RATE_EFFECTIVE_DATE_INVALID")
            try:
                mode = CostInputMode(cost_input_mode)
            except (TypeError, ValueError):
                return self._error("FIFO_RATE_COST_INPUT_INVALID")
            components = {
                "purchase_cost_rub": self._normalize_money(purchase_cost_rub),
                "delivery_cost_rub": self._normalize_money(delivery_cost_rub),
                "packaging_cost_rub": self._normalize_money(packaging_cost_rub),
            }
            normalized_unit_cost = self._normalize_money(unit_cost_rub)
            if mode is CostInputMode.COMPONENTS:
                if any(value is None for value in components.values()):
                    return self._error("FIFO_RATE_COMPONENTS_REQUIRED")
                unit_cost = sum(
                    (Decimal(value) for value in components.values()), Decimal("0.00"),
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if (
                    normalized_unit_cost is not None
                    and normalized_unit_cost != format(unit_cost, ".2f")
                ):
                    return self._error("FIFO_RATE_COST_INPUT_INVALID")
            else:
                if normalized_unit_cost is None or any(
                    value is not None for value in components.values()
                ):
                    return self._error("FIFO_RATE_COST_INPUT_INVALID")
                unit_cost = Decimal(normalized_unit_cost)
                if late_entry_correction_preview is not None:
                    return self._error("FIFO_LATE_ENTRY_COST_MODE_UNSUPPORTED")
            if unit_cost > Decimal("1000000000"):
                return self._error("FIFO_MONEY_INPUT_INVALID")
            if type(owner_old_home_units) is not int or not 0 <= owner_old_home_units <= self.MAX_COMMAND_UNITS:
                return self._error("FIFO_RATE_OLD_HOME_QUANTITY_INVALID")
            if type(expected_revision) is not int or expected_revision < 0:
                return self._error("FIFO_REVISION_CONFLICT")
            normalized_zero_stock = None
            if zero_stock_evidence is not None:
                normalized_zero_stock = self._normalize_zero_stock_evidence(
                    zero_stock_evidence, identity,
                )
                if isinstance(normalized_zero_stock, str):
                    return self._error(normalized_zero_stock)
                if owner_old_home_units != 0:
                    return self._error("FIFO_ZERO_ANCHOR_HOME_MUST_BE_ZERO")

            now = self._now()
            identity_fingerprint = self._sha256(identity)
            stream_id = "fifo_" + identity_fingerprint[:40]
            connection = self.get_connection()
            stream = connection.execute(
                "SELECT state, revision, policy_version FROM fifo_cost_streams WHERE stream_id=?",
                (stream_id,),
            ).fetchone()
            projection = connection.execute(
                """SELECT revision, state, known_quantity, known_cost_rub,
                          next_unit_cost_rub, queue_complete, cutoff_status,
                          source_set_fingerprint
                   FROM fifo_cost_projections WHERE stream_id=?""",
                (stream_id,),
            ).fetchone()
            if stream is None:
                if normalized_zero_stock is None or expected_revision != 0:
                    return self._error("FIFO_ANCHOR_REQUIRED")
                stream_snapshot = {
                    "state": "FIFO_PENDING_ANCHOR",
                    "revision": 0,
                    "known_quantity": 0,
                    "known_cost_rub": "0.00",
                    "next_unit_cost_rub": None,
                    "queue_complete": False,
                    "cutoff_status": "INVENTORY_CUTOFF_UNRECONCILED",
                    "source_set_fingerprint": None,
                    "rate_sequence": 1,
                    "prior_rate_unit_cost_rub": None,
                    "zero_stock_anchor": True,
                }
            else:
                if normalized_zero_stock is not None:
                    return self._error("FIFO_ZERO_ANCHOR_STREAM_ALREADY_EXISTS")
                if projection is None:
                    return self._error("FIFO_PROJECTION_MISSING")
                if stream["state"] not in {"FIFO_READY", "FIFO_PARTIAL"}:
                    return self._error("FIFO_STREAM_NOT_READY")
                if type(stream["revision"]) is not int or stream["revision"] != expected_revision:
                    return self._error("FIFO_REVISION_CONFLICT")
                if projection["revision"] != stream["revision"]:
                    if correction_preview is None:
                        return self._error("FIFO_PROJECTION_STALE")
                    if (
                        correction_preview["stream_revision"] != expected_revision
                        or projection["cutoff_status"] != "RECONCILED"
                        or projection["queue_complete"] != 1
                    ):
                        return self._error("FIFO_LATE_ENTRY_PREVIEW_STALE")
                    draft = connection.execute(
                        """SELECT expected_revision, owner_effective_date,
                                  owner_old_home_units, unit_cost_rub,
                                  purchase_cost_rub, delivery_cost_rub,
                                  packaging_cost_rub
                           FROM fifo_cost_late_entry_drafts
                           WHERE draft_id=? AND stream_id=?""",
                        (correction_preview["draft_id"], stream_id),
                    ).fetchone()
                    if (
                        draft is None or draft["expected_revision"] != expected_revision
                        or draft["owner_effective_date"] != effective_date
                        or draft["owner_old_home_units"] != owner_old_home_units
                        or draft["unit_cost_rub"] != format(unit_cost, ".2f")
                        or draft["purchase_cost_rub"] != components["purchase_cost_rub"]
                        or draft["delivery_cost_rub"] != components["delivery_cost_rub"]
                        or draft["packaging_cost_rub"] != components["packaging_cost_rub"]
                    ):
                        return self._error("FIFO_LATE_ENTRY_DRAFT_MISMATCH")
                    current_source_set = self._allocation_source_fingerprint(
                        connection, stream_id, expected_revision,
                        stream["policy_version"], projection["cutoff_status"],
                    )
                    current_allocation_revision = connection.execute(
                        """SELECT COALESCE(MAX(revision), 0)
                           FROM fifo_cost_allocations WHERE stream_id=?""",
                        (stream_id,),
                    ).fetchone()[0]
                    if (
                        current_source_set != correction_preview["source_set_fingerprint"]
                        or current_allocation_revision
                        != correction_preview["allocation_revision"]
                    ):
                        return self._error("FIFO_LATE_ENTRY_SOURCE_STALE")
                    if connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_rate_changes AS r
                   WHERE r.stream_id=? AND NOT EXISTS (
                       SELECT 1 FROM fifo_cost_rate_cancellations AS c
                       WHERE c.stream_id=r.stream_id
                         AND c.rate_change_id=r.rate_change_id
                   )""",
                        (stream_id,),
                    ).fetchone()[0]:
                        return self._error("FIFO_LATE_ENTRY_REPLAY_REQUIRED")
                stream_snapshot = {
                    "state": stream["state"],
                    "revision": stream["revision"],
                    "known_quantity": projection["known_quantity"],
                    "known_cost_rub": projection["known_cost_rub"],
                    "next_unit_cost_rub": projection["next_unit_cost_rub"],
                    "queue_complete": bool(projection["queue_complete"]),
                    "cutoff_status": projection["cutoff_status"],
                    "source_set_fingerprint": projection["source_set_fingerprint"],
                    "zero_stock_anchor": False,
                }
            previous = connection.execute(
                """SELECT r.rate_sequence, r.effective_date, r.unit_cost_rub
                   FROM fifo_cost_rate_changes AS r WHERE r.stream_id=?
                     AND NOT EXISTS (
                         SELECT 1 FROM fifo_cost_rate_cancellations AS c
                         WHERE c.stream_id=r.stream_id
                           AND c.rate_change_id=r.rate_change_id
                     )
                   ORDER BY r.rate_sequence DESC LIMIT 1""",
                (stream_id,),
            ).fetchone()
            if previous is not None and effective_date <= previous["effective_date"]:
                return self._error("FIFO_RATE_DATE_ORDER_UNRESOLVED")
            next_rate_sequence = connection.execute(
                "SELECT COALESCE(MAX(rate_sequence), 0) + 1 "
                "FROM fifo_cost_rate_changes WHERE stream_id=?",
                (stream_id,),
            ).fetchone()[0]
            reconciliation = None
            if previous is not None:
                if stock_snapshot is None:
                    return self._error("FIFO_RATE_RECONCILIATION_REQUIRED")
                if owner_confirms_reconciliation_scope is not True:
                    return self._error("FIFO_RATE_RECONCILIATION_SCOPE_UNCONFIRMED")
                stock = self._normalize_rate_reconciliation_snapshot(
                    stock_snapshot, identity, effective_date,
                    as_of_date=now.date().isoformat(),
                )
                if isinstance(stock, str):
                    return self._error(stock)
                # Until accepted sale/movement replay is available, a current
                # count cannot be used to shrink older layers or explain away
                # inventory disappearance.
                movement_count = connection.execute(
                    """SELECT COUNT(*) FROM fifo_cost_events
                       WHERE stream_id=? AND event_kind NOT IN (
                           'OPENING_FIFO_ANCHOR', 'COST_LAYER_RECEIPT'
                       )""",
                    (stream_id,),
                ).fetchone()[0]
                if movement_count:
                    return self._error("FIFO_RATE_REPLAY_REQUIRED")
                previous_rate_sequence = previous["rate_sequence"]
                prior_reconciliation_count = connection.execute(
                    """SELECT COUNT(*) FROM fifo_cost_rate_reconciliations
                       WHERE stream_id=? AND reconciled_rate_sequence < ?""",
                    (stream_id, previous_rate_sequence),
                ).fetchone()[0]
                expected_prior_reconciliations = connection.execute(
                    """SELECT COUNT(*) FROM fifo_cost_rate_changes AS r
                       WHERE r.stream_id=? AND r.rate_sequence<?
                         AND NOT EXISTS (
                             SELECT 1 FROM fifo_cost_rate_cancellations AS c
                             WHERE c.stream_id=r.stream_id
                               AND c.rate_change_id=r.rate_change_id
                         )""",
                    (stream_id, previous_rate_sequence),
                ).fetchone()[0]
                if prior_reconciliation_count != expected_prior_reconciliations:
                    return self._error("FIFO_RATE_HISTORY_GAP")
                already_reconciled = connection.execute(
                    """SELECT 1 FROM fifo_cost_rate_reconciliations
                       WHERE stream_id=? AND reconciled_rate_sequence=?""",
                    (stream_id, previous_rate_sequence),
                ).fetchone()
                if already_reconciled is not None:
                    return self._error("FIFO_RATE_RECONCILIATION_ALREADY_EXISTS")
                older_units = projection["known_quantity"]
                if type(older_units) is not int or older_units < 0:
                    return self._error("FIFO_PROJECTION_STALE")
                total_units = (
                    stock["fbo_units"] + stock["transit_units"]
                    + owner_old_home_units
                )
                if total_units > self.MAX_COMMAND_UNITS:
                    return self._error("FIFO_STREAM_QUANTITY_LIMIT")
                last_total = connection.execute(
                    """SELECT reconciled_total_units
                       FROM fifo_cost_rate_reconciliations WHERE stream_id=?
                       ORDER BY transition_rate_sequence DESC LIMIT 1""",
                    (stream_id,),
                ).fetchone()
                if last_total is not None and total_units < last_total["reconciled_total_units"]:
                    return self._error("FIFO_RATE_STOCK_DISCREPANCY")
                if total_units < older_units:
                    return self._error("FIFO_RATE_RECONCILIATION_CONFLICT")
                previous_rate_units = total_units - older_units
                if owner_old_home_units > previous_rate_units:
                    return self._error("FIFO_RATE_RECONCILIATION_CONFLICT")
                reconciliation = {
                    "transition_rate_sequence": next_rate_sequence,
                    "reconciled_rate_sequence": previous_rate_sequence,
                    "effective_date": effective_date,
                    "reconciled_total_units": total_units,
                    "older_finite_units": older_units,
                    "prior_rate_units": previous_rate_units,
                    "fbo_units": stock["fbo_units"],
                    "reserved_units": stock["reserved_units"],
                    "transit_units": stock["transit_units"],
                    "home_units": owner_old_home_units,
                    "source_fingerprint": stock["source_fingerprint"],
                    "captured_at": stock["captured_at"],
                    "prior_rate_unit_cost_rub": previous["unit_cost_rub"],
                    "older_finite_cost_rub": projection["known_cost_rub"],
                    "prior_total_units": (
                        last_total["reconciled_total_units"] if last_total else None
                    ),
                }
            latest_layer = connection.execute(
                """SELECT MAX(effective_date) FROM fifo_cost_layers
                   WHERE stream_id=?""",
                (stream_id,),
            ).fetchone()[0]
            latest_effective_date = max(
                date_value for date_value in (
                    previous["effective_date"] if previous is not None else None,
                    latest_layer,
                ) if date_value is not None
            ) if previous is not None or latest_layer is not None else None
            if latest_effective_date is not None and effective_date < latest_effective_date:
                return self._error("FIFO_RATE_DATE_ORDER_UNRESOLVED")
            if latest_layer is not None and effective_date == latest_layer:
                return self._error("FIFO_RATE_DATE_ORDER_UNRESOLVED")
            if previous is None and normalized_zero_stock is None:
                known_old_units = projection["known_quantity"]
                if (
                    type(known_old_units) is not int
                    or known_old_units < 0
                ):
                    return self._error("FIFO_PROJECTION_STALE")
                if owner_old_home_units > known_old_units:
                    return self._error("FIFO_RATE_RECONCILIATION_CONFLICT")
                prior_layer = connection.execute(
                    """SELECT unit_cost_rub FROM fifo_cost_layers WHERE stream_id=?
                       ORDER BY layer_sequence DESC LIMIT 1""",
                    (stream_id,),
                ).fetchone()
                stream_snapshot["prior_rate_unit_cost_rub"] = (
                    prior_layer["unit_cost_rub"] if prior_layer else projection["next_unit_cost_rub"]
                )

            normalized_identity = {
                "store_id": identity["store_id"],
                "product_id": identity["product_id"],
                "offer_id": identity["offer_id"],
                "sku": identity["sku"],
                "policy_version": identity["policy_version"],
            }
            payload = {
                "identity_fingerprint": identity_fingerprint,
                "effective_date": effective_date,
                "cost_input_mode": mode.value,
                **components,
                "unit_cost_rub": format(unit_cost, ".2f"),
                "owner_old_home_units": owner_old_home_units,
                "expected_revision": expected_revision,
                "prior_rate_sequence": previous["rate_sequence"] if previous else 0,
                "zero_stock_fingerprint": (
                    normalized_zero_stock["source_fingerprint"]
                    if normalized_zero_stock else None
                ),
                "rate_reconciliation": reconciliation,
            }
            payload_fingerprint = self._sha256(payload)
            source_fingerprint = self._sha256({
                "source_method": "OWNER_CONFIRMED_NEW_COST_RATE",
                "payload_fingerprint": payload_fingerprint,
                "captured_at": self._iso(now),
            })
            source_references = []
            if normalized_zero_stock is not None:
                source_references.append({
                    "kind": "OTHER",
                    "digest": normalized_zero_stock["source_fingerprint"],
                })
            if reconciliation is not None:
                source_references.append({
                    "kind": "OTHER",
                    "digest": reconciliation["source_fingerprint"],
                })
            source = self._normalize_source({
                "kind": "OWNER_CONFIRMATION",
                "method": "OWNER_CONFIRMED_NEW_COST_RATE",
                "status": "OWNER_CONFIRMED",
                "completeness": "OWNER_CONFIRMED",
                "provenance": "OWNER_CONFIRMED",
                "coverage_status": "OWNER_CONFIRMED",
                "fingerprint": source_fingerprint,
                "captured_at": self._iso(now),
                "references": source_references,
            })
            source_id = "src_" + self._sha256({
                "store_id": identity["store_id"],
                "source_fingerprint": source_fingerprint,
            })[:40]
            stream_snapshot["rate_sequence"] = next_rate_sequence
            if previous is not None:
                stream_snapshot["prior_rate_unit_cost_rub"] = previous["unit_cost_rub"]
            normalized = {
                "tenant_fingerprint": scope["tenant_fingerprint"],
                "owner_fingerprint": scope["owner_fingerprint"],
                "identity": normalized_identity,
                "stream_id": stream_id,
                "identity_fingerprint": identity_fingerprint,
                "payload": payload,
                "payload_fingerprint": payload_fingerprint,
                "source": source,
                "source_id": source_id,
                "zero_stock_source": normalized_zero_stock,
                "stream_snapshot": stream_snapshot,
                "late_entry_correction": correction_preview,
            }
            preview_id = "rate_preview_" + uuid4().hex
            ticket = {
                "preview_id": preview_id,
                "expires_at": now.timestamp() + self.PREVIEW_TTL_SECONDS,
                "normalized": normalized,
            }
            with self._PREVIEW_LOCK:
                self._purge_expired_rate_previews(now)
                if (
                    len(self._ACTIVE_RATE_PREVIEWS) >= self.MAX_PREVIEWS
                    and scope["owner_fingerprint"] not in self._ACTIVE_RATE_PREVIEWS
                ):
                    return self._error("FIFO_PREVIEW_CAPACITY_EXCEEDED")
                self._ACTIVE_RATE_PREVIEWS[scope["owner_fingerprint"]] = ticket
            return {
                "error": False,
                "code": "FIFO_RATE_PREVIEW_READY",
                "preview_id": preview_id,
                "expected_revision": stream_snapshot["revision"],
                "next_revision": stream_snapshot["revision"] + 1,
                "rate_sequence": stream_snapshot["rate_sequence"],
                "effective_date": effective_date,
                "unit_cost_rub": format(unit_cost, ".2f"),
                "cost_input_mode": mode.value,
                **components,
                "owner_old_home_units": owner_old_home_units,
                "finite_units_at_anchor": stream_snapshot["known_quantity"],
                "prior_rate_unit_cost_rub": stream_snapshot["prior_rate_unit_cost_rub"],
                "threshold_status": stream_snapshot["cutoff_status"],
                "inventory_units_added": 0,
                "new_batch_quantity": None,
                "zero_old_inventory_anchor": stream_snapshot["zero_stock_anchor"],
                "late_entry_correction_fingerprint": (
                    correction_preview["preview_fingerprint"]
                    if correction_preview else None
                ),
                "rate_reconciliation": ({
                    "reconciled_rate_sequence": reconciliation["reconciled_rate_sequence"],
                    "reconciled_total_units": reconciliation["reconciled_total_units"],
                    "older_finite_units": reconciliation["older_finite_units"],
                    "prior_rate_units": reconciliation["prior_rate_units"],
                    "prior_rate_unit_cost_rub": reconciliation["prior_rate_unit_cost_rub"],
                    "fbo_units": reconciliation["fbo_units"],
                    "reserved_units": reconciliation["reserved_units"],
                    "transit_units": reconciliation["transit_units"],
                    "home_units": reconciliation["home_units"],
                } if reconciliation else None),
                "expires_in_seconds": self.PREVIEW_TTL_SECONDS,
            }
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_RATE_INPUT_INVALID"
            return self._error(code)
        except (sqlite3.Error, OSError):
            return self._error("FIFO_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    def commit_cost_rate_change(
        self, *, preview_id, active_preview_id, idempotency_key,
        late_entry_correction=None,
    ):
        """Append a cost-rate record atomically, without creating inventory."""
        key = str(idempotency_key or "")
        if not self._IDEMPOTENCY_KEY.fullmatch(key):
            return self._error("FIFO_IDEMPOTENCY_KEY_INVALID")
        normalized_correction = self._normalize_late_entry_correction(
            late_entry_correction,
        ) if late_entry_correction is not None else None
        if isinstance(normalized_correction, str):
            return self._error(normalized_correction)
        try:
            now = self._now()
        except ValueError as exc:
            return self._error(str(exc))
        connection = None
        with self._PREVIEW_LOCK:
            self._purge_expired_rate_previews(now)
            tenant_id = str(get_current_tenant_user_id() or "").strip()
            owner_id, _ = split_store_tenant_scope(tenant_id)
            owner_fingerprint = self._sha256_text(owner_id) if owner_id else ""
            ticket = self._ACTIVE_RATE_PREVIEWS.get(owner_fingerprint)
            if (
                ticket is None or not preview_id or preview_id != active_preview_id
                or ticket["preview_id"] != preview_id
            ):
                return self._error("FIFO_PREVIEW_STALE")
            normalized = ticket["normalized"]
            ticket_correction = normalized.get("late_entry_correction")
            if (
                (normalized_correction is None) != (ticket_correction is None)
                or (
                    normalized_correction is not None
                    and (
                        normalized_correction["preview_fingerprint"]
                        != ticket_correction["preview_fingerprint"]
                        or normalized_correction["draft_id"] != ticket_correction["draft_id"]
                    )
                )
            ):
                return self._error("FIFO_LATE_ENTRY_PREVIEW_STALE")
            scope = self._tenant_scope(normalized["identity"]["store_id"])
            if (
                scope.get("error")
                or scope["tenant_fingerprint"] != normalized["tenant_fingerprint"]
            ):
                return self._error("FIFO_STORE_SCOPE_MISMATCH")
            try:
                connection = self.get_connection()
                connection.execute("BEGIN IMMEDIATE")
                previous = connection.execute(
                    """SELECT rate_change_id, payload_fingerprint, stream_revision, rate_sequence,
                              unit_cost_rub, owner_old_home_units
                       FROM fifo_cost_rate_changes
                       WHERE stream_id=? AND idempotency_key=?""",
                    (normalized["stream_id"], key),
                ).fetchone()
                if previous is not None:
                    if previous["payload_fingerprint"] != normalized["payload_fingerprint"]:
                        connection.rollback()
                        return self._error("FIFO_IDEMPOTENCY_CONFLICT")
                    correction_row = connection.execute(
                        """SELECT correction_id, preview_fingerprint
                           FROM fifo_cost_late_entry_corrections
                           WHERE stream_id=? AND rate_change_id=?""",
                        (normalized["stream_id"], previous["rate_change_id"]),
                    ).fetchone()
                    if normalized_correction is not None and (
                        correction_row is None
                        or correction_row["preview_fingerprint"]
                        != normalized_correction["preview_fingerprint"]
                        or correction_row["correction_id"]
                        != normalized_correction["correction_id"]
                    ):
                        connection.rollback()
                        return self._error("FIFO_IDEMPOTENCY_CONFLICT")
                    result = {
                        "revision": previous["stream_revision"],
                        "rate_sequence": previous["rate_sequence"],
                        "unit_cost_rub": previous["unit_cost_rub"],
                        "owner_old_home_units": previous["owner_old_home_units"],
                    }
                    if correction_row is not None:
                        result["correction_id"] = correction_row["correction_id"]
                    connection.rollback()
                    return {
                        "error": False, "code": "FIFO_RATE_COMMITTED",
                        "idempotent": True, **result,
                    }

                identity_conflict = self._identity_stream_conflict(
                    connection,
                    normalized["identity"],
                    normalized["identity_fingerprint"],
                )
                if identity_conflict is not None:
                    connection.rollback()
                    return identity_conflict

                stream = connection.execute(
                    "SELECT state, revision, policy_version FROM fifo_cost_streams WHERE stream_id=?",
                    (normalized["stream_id"],),
                ).fetchone()
                projection = connection.execute(
                    "SELECT revision, state, known_quantity, known_cost_rub, "
                    "next_unit_cost_rub, source_set_fingerprint, queue_complete, cutoff_status "
                    "FROM fifo_cost_projections WHERE stream_id=?",
                    (normalized["stream_id"],),
                ).fetchone()
                expected_revision = normalized["stream_snapshot"]["revision"]
                zero_anchor = normalized["stream_snapshot"]["zero_stock_anchor"]
                if zero_anchor:
                    if stream is not None or projection is not None or expected_revision != 0:
                        connection.rollback()
                        return self._error("FIFO_REVISION_CONFLICT")
                    identity = normalized["identity"]
                    connection.execute(
                        """INSERT INTO fifo_cost_streams (
                            stream_id, store_id, product_id, offer_id, sku,
                            identity_fingerprint, policy_version, state, revision,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'FIFO_PENDING_ANCHOR', 0, ?, ?)""",
                        (
                            normalized["stream_id"], identity["store_id"],
                            identity["product_id"], identity["offer_id"],
                            identity["sku"], normalized["identity_fingerprint"],
                            identity["policy_version"], self._iso(now), self._iso(now),
                        ),
                    )
                    self._ensure_policy_revision(connection, {
                        "identity": identity,
                        "stream_id": normalized["stream_id"],
                    }, now)
                else:
                    if stream is None or projection is None:
                        connection.rollback()
                        return self._error("FIFO_ANCHOR_REQUIRED")
                    if stream["revision"] != expected_revision:
                        connection.rollback()
                        return self._error("FIFO_REVISION_CONFLICT")
                    if (
                        projection["revision"] != expected_revision
                        and normalized_correction is None
                    ):
                        connection.rollback()
                        return self._error("FIFO_PROJECTION_STALE")
                latest = connection.execute(
                    "SELECT COALESCE(MAX(rate_sequence), 0) FROM fifo_cost_rate_changes "
                    "WHERE stream_id=?", (normalized["stream_id"],),
                ).fetchone()[0]
                if latest != normalized["stream_snapshot"]["rate_sequence"] - 1:
                    connection.rollback()
                    return self._error("FIFO_RATE_REVISION_CONFLICT")

                correction_draft = None
                if normalized_correction is not None:
                    if zero_anchor:
                        connection.rollback()
                        return self._error("FIFO_LATE_ENTRY_ANCHOR_MISMATCH")
                    correction_draft = connection.execute(
                        """SELECT d.draft_id, d.expected_revision,
                                  d.evidence_fingerprint, d.source_fingerprint,
                                  d.owner_effective_date, d.unit_cost_rub,
                                  d.purchase_cost_rub, d.delivery_cost_rub,
                                  d.packaging_cost_rub, d.owner_old_home_units,
                                  d.payload_fingerprint, e.source_status,
                                  e.source_fingerprint AS evidence_source_fingerprint
                           FROM fifo_cost_late_entry_drafts AS d
                           JOIN fifo_cost_supply_evidence AS e
                             ON e.stream_id=d.stream_id
                            AND e.evidence_fingerprint=d.evidence_fingerprint
                           WHERE d.stream_id=? AND d.draft_id=?""",
                        (normalized["stream_id"], normalized_correction["draft_id"]),
                    ).fetchone()
                    if correction_draft is None:
                        connection.rollback()
                        return self._error("FIFO_LATE_ENTRY_DRAFT_NOT_FOUND")
                    if (
                        correction_draft["expected_revision"] != expected_revision
                        or correction_draft["owner_effective_date"]
                        != normalized["payload"]["effective_date"]
                        or correction_draft["unit_cost_rub"]
                        != normalized["payload"]["unit_cost_rub"]
                        or correction_draft["purchase_cost_rub"]
                        != normalized["payload"]["purchase_cost_rub"]
                        or correction_draft["delivery_cost_rub"]
                        != normalized["payload"]["delivery_cost_rub"]
                        or correction_draft["packaging_cost_rub"]
                        != normalized["payload"]["packaging_cost_rub"]
                        or correction_draft["owner_old_home_units"]
                        != normalized["payload"]["owner_old_home_units"]
                        or correction_draft["source_status"] != "COMPLETE"
                        or correction_draft["source_fingerprint"]
                        != correction_draft["evidence_source_fingerprint"]
                        or normalized_correction["stream_revision"] != expected_revision
                        or projection["cutoff_status"] != "RECONCILED"
                        or projection["queue_complete"] != 1
                    ):
                        connection.rollback()
                        return self._error("FIFO_LATE_ENTRY_PREVIEW_STALE")
                    current_allocation_revision = connection.execute(
                        """SELECT COALESCE(MAX(revision), 0)
                           FROM fifo_cost_allocations WHERE stream_id=?""",
                        (normalized["stream_id"],),
                    ).fetchone()[0]
                    current_source_set = self._allocation_source_fingerprint(
                        connection, normalized["stream_id"], expected_revision,
                        stream["policy_version"], projection["cutoff_status"],
                    )
                    if (
                        current_allocation_revision
                        != normalized_correction["allocation_revision"]
                        or current_source_set
                        != normalized_correction["source_set_fingerprint"]
                    ):
                        connection.rollback()
                        return self._error("FIFO_LATE_ENTRY_SOURCE_STALE")
                    existing_rates = connection.execute(
                        """SELECT COUNT(*) FROM fifo_cost_rate_changes AS r
                           WHERE r.stream_id=? AND NOT EXISTS (
                               SELECT 1 FROM fifo_cost_rate_cancellations AS c
                               WHERE c.stream_id=r.stream_id
                                 AND c.rate_change_id=r.rate_change_id
                           )""",
                        (normalized["stream_id"],),
                    ).fetchone()[0]
                    if existing_rates:
                        connection.rollback()
                        return self._error("FIFO_LATE_ENTRY_REPLAY_REQUIRED")
                    existing_correction = connection.execute(
                        """SELECT correction_id FROM fifo_cost_late_entry_corrections
                           WHERE stream_id=? AND draft_id=?""",
                        (normalized["stream_id"], normalized_correction["draft_id"]),
                    ).fetchone()
                    if existing_correction is not None:
                        connection.rollback()
                        return self._error("FIFO_LATE_ENTRY_ALREADY_CORRECTED")

                if zero_anchor:
                    self._ensure_source(connection, {
                        "identity": normalized["identity"],
                        "source": normalized["zero_stock_source"]["source"],
                        "source_id": normalized["zero_stock_source"]["source_id"],
                    })
                self._ensure_source(connection, {
                    "identity": normalized["identity"],
                    "source": normalized["source"],
                    "source_id": normalized["source_id"],
                })
                payload = normalized["payload"]
                next_revision = expected_revision + 1
                rate_change_id = "rate_" + uuid4().hex
                connection.execute(
                    """INSERT INTO fifo_cost_rate_changes (
                        rate_change_id, stream_id, stream_revision, rate_sequence,
                        effective_date, unit_cost_rub, cost_input_mode, purchase_cost_rub,
                        delivery_cost_rub, packaging_cost_rub,
                        owner_old_home_units, source_id, source_fingerprint,
                        payload_fingerprint, idempotency_key, recorded_at,
                        captured_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        rate_change_id, normalized["stream_id"], next_revision,
                        normalized["stream_snapshot"]["rate_sequence"],
                        payload["effective_date"], payload["unit_cost_rub"],
                        payload["cost_input_mode"],
                        payload["purchase_cost_rub"], payload["delivery_cost_rub"],
                        payload["packaging_cost_rub"], payload["owner_old_home_units"],
                        normalized["source_id"], normalized["source"]["source_fingerprint"],
                        normalized["payload_fingerprint"], key,
                        self._iso(now), normalized["source"]["captured_at"],
                    ),
                )
                if normalized_correction is not None:
                    impact_json = normalized_correction["impact_json"]
                    connection.execute(
                        """INSERT INTO fifo_cost_late_entry_corrections (
                            correction_id, stream_id, stream_revision, draft_id,
                            rate_change_id, effective_date, unit_cost_rub,
                            reason_code, preview_fingerprint,
                            reconstruction_fingerprint, source_set_fingerprint,
                            allocation_revision, tax_policy_fingerprint,
                            period_source_fingerprints_json, impact_json,
                            idempotency_key, recorded_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'OWNER_REPORTED_LATE',
                                  ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            normalized_correction["correction_id"],
                            normalized["stream_id"], next_revision,
                            normalized_correction["draft_id"], rate_change_id,
                            normalized["payload"]["effective_date"],
                            normalized["payload"]["unit_cost_rub"],
                            normalized_correction["preview_fingerprint"],
                            normalized_correction["reconstruction_fingerprint"],
                            normalized_correction["source_set_fingerprint"],
                            normalized_correction["allocation_revision"],
                            normalized_correction["tax_policy_fingerprint"],
                            normalized_correction["period_source_fingerprints_json"],
                            impact_json, key, self._iso(now),
                        ),
                    )
                reconciliation = normalized["payload"]["rate_reconciliation"]
                if reconciliation is not None:
                    reconciliation_id = "rate_recon_" + self._sha256({
                        "stream_id": normalized["stream_id"],
                        "transition_rate_sequence": reconciliation[
                            "transition_rate_sequence"
                        ],
                        "source_fingerprint": reconciliation["source_fingerprint"],
                    })[:40]
                    connection.execute(
                        """INSERT INTO fifo_cost_rate_reconciliations (
                            reconciliation_id, stream_id, stream_revision,
                            transition_rate_sequence, reconciled_rate_sequence,
                            effective_date, reconciled_total_units,
                            older_finite_units, prior_rate_units, fbo_units,
                            reserved_units, transit_units, home_units,
                            source_fingerprint, captured_at, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            reconciliation_id, normalized["stream_id"], next_revision,
                            reconciliation["transition_rate_sequence"],
                            reconciliation["reconciled_rate_sequence"],
                            reconciliation["effective_date"],
                            reconciliation["reconciled_total_units"],
                            reconciliation["older_finite_units"],
                            reconciliation["prior_rate_units"],
                            reconciliation["fbo_units"],
                            reconciliation["reserved_units"],
                            reconciliation["transit_units"],
                            reconciliation["home_units"],
                            reconciliation["source_fingerprint"],
                            reconciliation["captured_at"], self._iso(now),
                        ),
                    )
                connection.execute(
                    "UPDATE fifo_cost_streams SET state='FIFO_PARTIAL', revision=?, updated_at=? "
                    "WHERE stream_id=?",
                    (next_revision, self._iso(now), normalized["stream_id"]),
                )
                if zero_anchor:
                    combined_source_set = self._sha256({
                        "zero_stock": normalized["zero_stock_source"]["source_fingerprint"],
                        "rate": normalized["source"]["source_fingerprint"],
                    })
                    connection.execute(
                        """INSERT INTO fifo_cost_projections (
                            stream_id, revision, state, known_quantity, known_cost_rub,
                            next_unit_cost_rub, queue_complete, cutoff_status,
                            inventory_cutoff, source_set_fingerprint,
                            last_event_id, updated_at
                        ) VALUES (?, ?, 'FIFO_PARTIAL', 0, '0.00', ?, 0, ?, ?, ?, NULL, ?)""",
                        (
                            normalized["stream_id"], next_revision,
                            payload["unit_cost_rub"],
                            "INVENTORY_CUTOFF_UNRECONCILED",
                            normalized["zero_stock_source"]["source"]["captured_at"][:10],
                            combined_source_set,
                            self._iso(now),
                        ),
                    )
                else:
                    combined_source_set = self._sha256({
                        "previous": projection["source_set_fingerprint"],
                        "rate": normalized["source"]["source_fingerprint"],
                    })
                    if reconciliation is None:
                        connection.execute(
                            """UPDATE fifo_cost_projections
                               SET revision=?, state='FIFO_PARTIAL', queue_complete=0,
                                   source_set_fingerprint=?, updated_at=?
                               WHERE stream_id=?""",
                            (
                                next_revision, combined_source_set, self._iso(now),
                                normalized["stream_id"],
                            ),
                        )
                    else:
                        prior_rate_cost = Decimal(
                            reconciliation["prior_rate_unit_cost_rub"]
                        )
                        added_cost = (
                            prior_rate_cost * reconciliation["prior_rate_units"]
                        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        reconciled_cost = (
                            Decimal(reconciliation["older_finite_cost_rub"])
                            + added_cost
                        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        old_next_cost = projection["next_unit_cost_rub"]
                        if projection["known_quantity"] > 0:
                            next_unit_cost = old_next_cost
                        elif reconciliation["prior_rate_units"] > 0:
                            next_unit_cost = reconciliation["prior_rate_unit_cost_rub"]
                        else:
                            next_unit_cost = payload["unit_cost_rub"]
                        connection.execute(
                            """UPDATE fifo_cost_projections
                               SET revision=?, state='FIFO_PARTIAL',
                                   known_quantity=?, known_cost_rub=?,
                                   next_unit_cost_rub=?, queue_complete=0,
                                   source_set_fingerprint=?, updated_at=?
                               WHERE stream_id=?""",
                            (
                                next_revision,
                                reconciliation["reconciled_total_units"],
                                format(reconciled_cost, ".2f"), next_unit_cost,
                                combined_source_set, self._iso(now),
                                normalized["stream_id"],
                            ),
                        )
                result = {
                    "revision": next_revision,
                    "rate_sequence": normalized["stream_snapshot"]["rate_sequence"],
                    "unit_cost_rub": payload["unit_cost_rub"],
                    "owner_old_home_units": payload["owner_old_home_units"],
                    **({"reconciled_previous_rate_units": reconciliation["prior_rate_units"]}
                       if reconciliation else {}),
                }
                if normalized_correction is not None:
                    result["correction_id"] = normalized_correction["correction_id"]
                connection.commit()
                return {
                    "error": False, "code": "FIFO_RATE_COMMITTED",
                    "idempotent": False, **result,
                }
            except ValueError as exc:
                if connection is not None and connection.in_transaction:
                    connection.rollback()
                code = str(exc) if str(exc).startswith("FIFO_") else "FIFO_RATE_INPUT_INVALID"
                return self._error(code)
            except sqlite3.IntegrityError:
                if connection is not None and connection.in_transaction:
                    connection.rollback()
                return self._error(
                    "FIFO_LATE_ENTRY_COMMIT_CONFLICT"
                    if normalized_correction is not None
                    else "FIFO_RATE_REVISION_CONFLICT"
                )
            except (sqlite3.Error, OSError):
                if connection is not None and connection.in_transaction:
                    connection.rollback()
                return self._error("FIFO_STORAGE_UNAVAILABLE")
            finally:
                if connection is not None:
                    connection.close()

    def _purge_expired_rate_previews(self, now):
        cutoff = now.timestamp()
        expired = [
            owner for owner, ticket in self._ACTIVE_RATE_PREVIEWS.items()
            if ticket["expires_at"] <= cutoff
        ]
        for owner in expired:
            self._ACTIVE_RATE_PREVIEWS.pop(owner, None)

    def _tenant_scope(self, store_id):
        tenant_id = str(get_current_tenant_user_id() or "").strip()
        if not tenant_id:
            return self._error("FIFO_OWNER_SCOPE_REQUIRED")
        owner_id, scoped_store = split_store_tenant_scope(tenant_id)
        try:
            normalized_store = self._safe_identity_part(store_id, "store_id", 128)
        except ValueError:
            return self._error("FIFO_IDENTITY_INVALID")
        if not owner_id or not scoped_store:
            return self._error("FIFO_STORE_SCOPE_REQUIRED")
        if scoped_store != normalized_store:
            return self._error("FIFO_STORE_SCOPE_MISMATCH")
        return {
            "error": False,
            "owner_fingerprint": self._sha256_text(owner_id),
            "tenant_fingerprint": self._sha256_text(tenant_id),
        }

    def _identity_stream_conflict(self, connection, identity, fingerprint):
        """Fail closed when a store/SKU already has FIFO history under another identity.

        Product and offer metadata can change while the seller SKU stays stable.
        Do not reinterpret such a stream as legacy or create a second queue: the
        caller must resolve the identity explicitly before continuing.
        """
        rows = connection.execute(
            """SELECT identity_fingerprint FROM fifo_cost_streams
               WHERE store_id=? AND sku=? AND policy_version=?
                 AND state<>'LEGACY' AND identity_fingerprint<>?
               LIMIT 2""",
            (
                identity["store_id"], identity["sku"],
                identity["policy_version"], fingerprint,
            ),
        ).fetchall()
        if rows:
            return self._error("FIFO_IDENTITY_CONFLICT")
        return None

    @classmethod
    def _normalize_identity(cls, store_id, product_id, offer_id, sku, policy_version):
        store = cls._safe_identity_part(store_id, "store_id", 128)
        product = cls._optional_identity_part(product_id, "product_id", 128)
        offer = cls._optional_identity_part(offer_id, "offer_id", 128)
        normalized_sku = cls._safe_identity_part(sku, "sku", 64)
        if not product and not offer:
            raise ValueError("FIFO_PRODUCT_IDENTITY_REQUIRED")
        if type(policy_version) is not int or not 1 <= policy_version <= 1000:
            raise ValueError("FIFO_POLICY_VERSION_INVALID")
        return {
            "store_id": store,
            "product_id": product,
            "offer_id": offer,
            "sku": normalized_sku,
            "policy_version": policy_version,
        }

    @staticmethod
    def _safe_identity_part(value, name, max_length):
        if value is None or isinstance(value, bool):
            raise ValueError("FIFO_IDENTITY_INVALID")
        text = str(value).strip()
        if not text or len(text) > max_length or any(ord(char) < 32 for char in text):
            raise ValueError("FIFO_IDENTITY_INVALID")
        return text

    @classmethod
    def _optional_identity_part(cls, value, name, max_length):
        if value is None or str(value).strip() == "":
            return None
        return cls._safe_identity_part(value, name, max_length)

    @classmethod
    def _normalize_rate_reconciliation_snapshot(
        cls, snapshot, identity, effective_date, *, as_of_date=None,
    ):
        """Accept only a complete exact-SKU snapshot on the chosen date."""
        fields = (
            "status", "source_status", "store_id", "product_id", "offer_id",
            "sku", "captured_at", "pagination_complete", "fbo_units",
            "reserved_units", "transit_units", "transit_status",
            "source_fingerprint",
        )
        try:
            evidence = {field: getattr(snapshot, field) for field in fields}
        except (AttributeError, TypeError):
            return "FIFO_RATE_RECONCILIATION_SOURCE_INVALID"
        if (
            evidence["status"] != "COMPLETE"
            or evidence["source_status"] != "COMPLETE"
            or evidence["pagination_complete"] is not True
            or evidence["transit_status"] != "DISJOINT_CONFIRMED"
            or not cls._valid_digest(evidence["source_fingerprint"])
        ):
            return "FIFO_RATE_RECONCILIATION_SOURCE_INCOMPLETE"
        quantities = (
            evidence["fbo_units"], evidence["reserved_units"],
            evidence["transit_units"],
        )
        if any(
            type(value) is not int or value < 0 or value > cls.MAX_COMMAND_UNITS
            for value in quantities
        ):
            return "FIFO_RATE_RECONCILIATION_SOURCE_INVALID"
        if evidence["reserved_units"] > evidence["fbo_units"]:
            return "FIFO_RATE_RECONCILIATION_SOURCE_CONFLICT"
        try:
            store_id = cls._safe_identity_part(evidence["store_id"], "store_id", 128)
            product_id = cls._optional_identity_part(evidence["product_id"], "product_id", 128)
            offer_id = cls._optional_identity_part(evidence["offer_id"], "offer_id", 128)
            sku = cls._safe_identity_part(evidence["sku"], "sku", 64)
            captured_at = cls._normalize_timestamp(evidence["captured_at"])
        except (TypeError, ValueError):
            return "FIFO_RATE_RECONCILIATION_SOURCE_INVALID"
        if (
            store_id != identity["store_id"]
            or product_id != identity["product_id"]
            or offer_id != identity["offer_id"]
            or sku != identity["sku"]
        ):
            return "FIFO_RATE_RECONCILIATION_SCOPE_MISMATCH"
        if (
            captured_at is not None and as_of_date is not None
            and captured_at[:10] > as_of_date
        ):
            return "FIFO_RATE_RECONCILIATION_FUTURE_SNAPSHOT"
        if captured_at is None or captured_at[:10] != effective_date:
            return "FIFO_RATE_RECONCILIATION_DATE_MISMATCH"
        total = evidence["fbo_units"] + evidence["transit_units"]
        if total > cls.MAX_COMMAND_UNITS:
            return "FIFO_STREAM_QUANTITY_LIMIT"
        return {
            "fbo_units": evidence["fbo_units"],
            "reserved_units": evidence["reserved_units"],
            "transit_units": evidence["transit_units"],
            "captured_at": captured_at,
            "source_fingerprint": evidence["source_fingerprint"],
        }

    @classmethod
    def _normalize_zero_stock_evidence(cls, evidence, identity):
        required = {
            "status", "source_status", "store_id", "product_id", "offer_id",
            "sku", "captured_at", "pagination_complete", "fbo_units",
            "reserved_units", "transit_units", "transit_status",
            "source_fingerprint",
        }
        if not isinstance(evidence, dict) or set(evidence) != required:
            return "FIFO_ZERO_ANCHOR_SOURCE_INVALID"
        if (
            evidence["status"] != "CONFIRMED_ZERO"
            or evidence["source_status"] != "COMPLETE"
            or evidence["pagination_complete"] is not True
            or type(evidence["fbo_units"]) is not int or evidence["fbo_units"] != 0
            or type(evidence["reserved_units"]) is not int or evidence["reserved_units"] != 0
            or type(evidence["transit_units"]) is not int or evidence["transit_units"] != 0
            or evidence["transit_status"] != "DISJOINT_CONFIRMED"
            or not cls._valid_digest(evidence["source_fingerprint"])
        ):
            return "FIFO_ZERO_ANCHOR_SOURCE_UNCONFIRMED"
        try:
            store_id = cls._safe_identity_part(evidence["store_id"], "store_id", 128)
            product_id = cls._safe_identity_part(evidence["product_id"], "product_id", 128)
            offer_id = cls._optional_identity_part(evidence["offer_id"], "offer_id", 128)
            sku = cls._safe_identity_part(evidence["sku"], "sku", 64)
            captured_at = cls._normalize_timestamp(evidence["captured_at"])
        except (TypeError, ValueError):
            return "FIFO_ZERO_ANCHOR_SOURCE_INVALID"
        if (
            store_id != identity["store_id"]
            or product_id != identity["product_id"]
            or offer_id != identity["offer_id"]
            or sku != identity["sku"]
            or captured_at is None
        ):
            return "FIFO_ZERO_ANCHOR_SCOPE_MISMATCH"
        source = cls._normalize_source({
            "kind": "OZON_API",
            "method": "FIFO_PRODUCT_STOCKS",
            "status": "COMPLETE",
            "completeness": "COMPLETE",
            "provenance": "OZON_CONFIRMED_FIELD",
            "coverage_status": "COMPLETE",
            "fingerprint": evidence["source_fingerprint"],
            "captured_at": captured_at,
            "record_count": 1,
            "page_count": 1,
            "references": [],
        })
        source_id = "src_" + cls._sha256({
            "store_id": store_id,
            "source_fingerprint": source["source_fingerprint"],
        })[:40]
        return {
            "source": source,
            "source_id": source_id,
            "source_fingerprint": source["source_fingerprint"],
        }

    @classmethod
    def _normalize_source(cls, source):
        if not isinstance(source, dict):
            raise ValueError("FIFO_SOURCE_INVALID")
        allowed = {
            "kind", "method", "status", "completeness", "provenance",
            "coverage_status", "fingerprint", "captured_at", "source_as_of",
            "record_count", "page_count", "inventory_cutoff", "references",
        }
        if set(source) - allowed:
            raise ValueError("FIFO_SOURCE_FIELD_NOT_ALLOWED")
        kind = cls._enum_text(source.get("kind"), "FIFO_SOURCE_KIND_INVALID", 48)
        method = cls._enum_text(source.get("method"), "FIFO_SOURCE_METHOD_INVALID", 80)
        status = source.get("status")
        completeness = source.get("completeness", status)
        provenance = source.get("provenance")
        if status not in cls._SOURCE_STATUSES or completeness not in cls._SOURCE_STATUSES:
            raise ValueError("FIFO_SOURCE_STATUS_INVALID")
        if provenance not in cls._PROVENANCE:
            raise ValueError("FIFO_SOURCE_PROVENANCE_INVALID")
        if status == "MODEL_ONLY" or completeness == "MODEL_ONLY" or provenance == "MODEL_ASSUMPTION":
            raise ValueError("FIFO_MODEL_SOURCE_NOT_PERSISTABLE")
        coverage = source.get("coverage_status", "UNKNOWN")
        if coverage not in {"COMPLETE", "PARTIAL", "UNKNOWN", "OWNER_CONFIRMED", "NOT_APPLICABLE"}:
            raise ValueError("FIFO_SOURCE_COVERAGE_INVALID")
        fingerprint = source.get("fingerprint")
        if fingerprint is not None and not cls._valid_digest(fingerprint):
            raise ValueError("FIFO_SOURCE_FINGERPRINT_INVALID")
        refs = source.get("references", [])
        if not isinstance(refs, list) or len(refs) > cls.MAX_REFERENCES_PER_SOURCE:
            raise ValueError("FIFO_SOURCE_REFERENCE_LIMIT")
        normalized_refs = []
        for ref in refs:
            if not isinstance(ref, dict) or set(ref) != {"kind", "digest"}:
                raise ValueError("FIFO_SOURCE_REFERENCE_INVALID")
            ref_kind = ref["kind"]
            if ref_kind not in cls._REFERENCE_KINDS or not cls._valid_digest(ref["digest"]):
                raise ValueError("FIFO_SOURCE_REFERENCE_INVALID")
            normalized_refs.append({"kind": ref_kind, "digest": ref["digest"]})
        if len({(item["kind"], item["digest"]) for item in normalized_refs}) != len(normalized_refs):
            raise ValueError("FIFO_SOURCE_REFERENCE_DUPLICATE")
        return {
            "source_kind": kind,
            "source_method": method,
            "source_status": status,
            "completeness": completeness,
            "provenance": provenance,
            "coverage_status": coverage,
            "source_fingerprint": fingerprint,
            "captured_at": cls._normalize_timestamp(source.get("captured_at")),
            "source_as_of": cls._normalize_timestamp(source.get("source_as_of")),
            "inventory_cutoff": cls._normalize_cutoff(source.get("inventory_cutoff")),
            "record_count": cls._optional_count(source.get("record_count")),
            "page_count": cls._optional_count(source.get("page_count")),
            "references": sorted(normalized_refs, key=lambda item: (item["kind"], item["digest"])),
        }

    @classmethod
    def _normalize_events(cls, events, source):
        if not isinstance(events, list) or not 1 <= len(events) <= cls.MAX_COMMAND_EVENTS:
            raise ValueError("FIFO_COMMAND_EVENT_LIMIT")
        normalized = []
        for item in events:
            if not isinstance(item, dict):
                raise ValueError("FIFO_EVENT_INVALID")
            allowed = {
                "kind", "quantity", "effective_at", "effective_date",
                "inventory_cutoff", "unit_cost_rub", "purchase_cost_rub",
                "delivery_cost_rub", "packaging_cost_rub", "currency",
                "location_from", "location_to", "source_identity_digest",
                "supersedes_event_id", "reason_code",
            }
            if set(item) - allowed:
                raise ValueError("FIFO_EVENT_FIELD_NOT_ALLOWED")
            kind = item.get("kind")
            if kind not in cls._EVENT_KINDS:
                raise ValueError("FIFO_EVENT_KIND_INVALID")
            quantity = item.get("quantity")
            if type(quantity) is not int or not 1 <= quantity <= cls.MAX_EVENT_QUANTITY:
                raise ValueError("FIFO_EVENT_QUANTITY_INVALID")
            effective_at = cls._normalize_timestamp(item.get("effective_at"))
            effective_date = cls._normalize_date(item.get("effective_date"))
            if effective_at is None and effective_date is None:
                raise ValueError("FIFO_EVENT_EFFECTIVE_TIME_REQUIRED")
            cutoff = cls._normalize_cutoff(
                item.get("inventory_cutoff", source.get("inventory_cutoff")),
            )
            if kind == "NON_SALE_OUTFLOW":
                event_day = effective_date
                if effective_at is not None:
                    event_day = datetime.fromisoformat(
                        effective_at.replace("Z", "+00:00"),
                    ).date().isoformat()
                if item.get("reason_code") not in cls._OUTFLOW_REASONS:
                    raise ValueError("FIFO_OUTFLOW_REASON_INVALID")
                if cutoff is None or event_day is None or event_day <= cutoff:
                    raise ValueError("FIFO_MOVEMENT_EFFECTIVE_DATE_UNAVAILABLE")
            cost_fields = ("purchase_cost_rub", "delivery_cost_rub", "packaging_cost_rub")
            supplied_components = [name in item for name in cost_fields]
            components = {
                name: cls._normalize_money(item.get(name)) if name in item else None
                for name in cost_fields
            }
            if any(supplied_components) and not all(supplied_components):
                raise ValueError("FIFO_COST_COMPONENTS_INCOMPLETE")
            if all(supplied_components) and any(
                components[name] is None for name in cost_fields
            ):
                raise ValueError("FIFO_MONEY_INPUT_INVALID")
            unit_cost = cls._normalize_money(item.get("unit_cost_rub"))
            is_layer = kind in {"OPENING_FIFO_ANCHOR", "COST_LAYER_RECEIPT"}
            if is_layer and unit_cost is None:
                raise ValueError("FIFO_LAYER_COST_REQUIRED")
            if not is_layer and (unit_cost is not None or any(supplied_components)):
                raise ValueError("FIFO_EVENT_COST_NOT_ALLOWED")
            if all(supplied_components):
                component_sum = sum(
                    Decimal(components[name]) for name in cost_fields
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if component_sum != Decimal(unit_cost):
                    raise ValueError("FIFO_COST_COMPONENT_TOTAL_MISMATCH")
            if item.get("currency", "RUB") != "RUB":
                raise ValueError("FIFO_CURRENCY_UNSUPPORTED")
            from_location = item.get("location_from")
            to_location = item.get("location_to")
            if kind == "OPENING_FIFO_ANCHOR":
                if from_location is not None or to_location not in {"HOME", "TRANSIT", "OZON"}:
                    raise ValueError("FIFO_ANCHOR_ZONE_REQUIRED")
                if cutoff is None:
                    raise ValueError("FIFO_ANCHOR_CUTOFF_REQUIRED")
            elif kind == "INVENTORY_TRANSFER":
                if (from_location not in cls._LOCATIONS or to_location not in cls._LOCATIONS
                        or from_location == to_location):
                    raise ValueError("FIFO_TRANSFER_LOCATION_INVALID")
            elif from_location is not None or to_location is not None:
                raise ValueError("FIFO_EVENT_LOCATION_NOT_ALLOWED")
            source_identity_digest = item.get("source_identity_digest")
            if kind == "PHYSICAL_SALE":
                if not cls._valid_digest(source_identity_digest):
                    raise ValueError("FIFO_SALE_IDENTITY_REQUIRED")
            elif source_identity_digest is not None and not cls._valid_digest(source_identity_digest):
                raise ValueError("FIFO_SOURCE_IDENTITY_INVALID")
            if kind == "SALEABLE_RETURN_RESTOCK":
                cls._validate_return_source(source, source_identity_digest, cutoff)
            if kind == "NON_SALE_OUTFLOW":
                if not cls._valid_digest(source_identity_digest):
                    raise ValueError("FIFO_MOVEMENT_IDENTITY_UNCONFIRMED")
                cls._validate_outflow_source(source, source_identity_digest, cutoff)
            supersedes = item.get("supersedes_event_id")
            if kind in {"CORRECTION", "SALE_CANCELLATION", "SALEABLE_RETURN_RESTOCK"}:
                if not isinstance(supersedes, str) or not re.fullmatch(r"evt_[0-9a-f]{32}", supersedes):
                    raise ValueError("FIFO_EVENT_TARGET_REQUIRED")
            elif supersedes is not None:
                raise ValueError("FIFO_EVENT_TARGET_NOT_ALLOWED")
            reason = item.get("reason_code")
            if reason is not None and reason not in cls._REASON_CODES:
                raise ValueError("FIFO_EVENT_REASON_INVALID")
            if kind in {"CORRECTION", "SALE_CANCELLATION", "NON_SALE_OUTFLOW"} and reason is None:
                raise ValueError("FIFO_EVENT_REASON_REQUIRED")
            normalized.append({
                "event_id": "evt_" + uuid4().hex,
                "kind": kind,
                "quantity": quantity,
                "effective_at": effective_at,
                "effective_date": effective_date,
                "inventory_cutoff": cutoff,
                "unit_cost_rub": unit_cost,
                **components,
                "location_from": from_location,
                "location_to": to_location,
                "source_identity_digest": source_identity_digest,
                "supersedes_event_id": supersedes,
                "reason_code": reason,
            })
        return normalized

    @classmethod
    def _validate_return_source(cls, source, return_digest, event_cutoff):
        if not cls._valid_digest(return_digest):
            raise ValueError("FIFO_RETURN_IDENTITY_UNCONFIRMED")
        if (
            source.get("source_kind") != "OWNER_CONFIRMATION"
            or source.get("source_method") != "OWNER_CONFIRMED_SALEABLE_RETURN_RECOVERY"
            or source.get("source_status") != "OWNER_CONFIRMED"
            or source.get("completeness") != "OWNER_CONFIRMED"
            or source.get("provenance") != "OWNER_CONFIRMED"
            or source.get("coverage_status") != "OWNER_CONFIRMED"
            or source.get("captured_at") is None
            or source.get("inventory_cutoff") is None
            or source.get("inventory_cutoff") != event_cutoff
        ):
            raise ValueError("FIFO_RETURN_SALEABLE_RECOVERY_UNCONFIRMED")
        references = source.get("references", [])
        if (
            len(references) != 2
            or any(reference.get("kind") != "OTHER" for reference in references)
            or return_digest not in {reference["digest"] for reference in references}
        ):
            raise ValueError("FIFO_RETURN_SOURCE_REFERENCE_INVALID")

    @classmethod
    def _validate_outflow_source(cls, source, movement_digest, event_cutoff):
        if (
            source.get("source_kind") != "OWNER_CONFIRMATION"
            or source.get("source_method") != "OWNER_CONFIRMED_FIFO_NON_SALE_MOVEMENT"
            or source.get("source_status") != "OWNER_CONFIRMED"
            or source.get("completeness") != "OWNER_CONFIRMED"
            or source.get("provenance") != "OWNER_CONFIRMED"
            or source.get("coverage_status") != "OWNER_CONFIRMED"
            or source.get("captured_at") is None
            or source.get("inventory_cutoff") != event_cutoff
        ):
            raise ValueError("FIFO_MOVEMENT_EVIDENCE_UNCONFIRMED")
        references = source.get("references", [])
        if (
            len(references) != 1
            or references[0].get("kind") != "OTHER"
            or references[0].get("digest") != movement_digest
        ):
            raise ValueError("FIFO_MOVEMENT_SOURCE_REFERENCE_INVALID")

    @staticmethod
    def _opening_anchor_error(events, source, *, current_revision, current_state):
        if any(event["kind"] != "OPENING_FIFO_ANCHOR" for event in events):
            return "FIFO_ANCHOR_COMMAND_MUST_BE_EXCLUSIVE"
        if current_revision != 0 or current_state != "FIFO_PENDING_ANCHOR":
            return "FIFO_ANCHOR_ALREADY_EXISTS"
        if (
            source["source_status"] != "OWNER_CONFIRMED"
            or source["completeness"] != "OWNER_CONFIRMED"
            or source["provenance"] != "OWNER_CONFIRMED"
            or source["coverage_status"] != "OWNER_CONFIRMED"
            or source["source_kind"] != "OWNER_CONFIRMATION"
            or source["source_method"] != "OWNER_CONFIRMED_FIFO_CUTOFF"
        ):
            return "FIFO_ANCHOR_OWNER_CONFIRMATION_REQUIRED"
        if source["inventory_cutoff"] is None:
            return "FIFO_ANCHOR_CUTOFF_REQUIRED"
        if source["captured_at"] is None:
            return "FIFO_ANCHOR_CAPTURE_TIME_REQUIRED"
        if not events or sum(event["quantity"] for event in events) <= 0:
            return "FIFO_ANCHOR_QUANTITY_REQUIRED"
        if any(event["inventory_cutoff"] != source["inventory_cutoff"] for event in events):
            return "FIFO_ANCHOR_CUTOFF_MISMATCH"
        if any(
            event["effective_at"] is not None
            or event["effective_date"] != source["inventory_cutoff"]
            for event in events
        ):
            return "FIFO_ANCHOR_CUTOFF_MISMATCH"
        if any(event["location_to"] not in {"HOME", "TRANSIT", "OZON"} for event in events):
            return "FIFO_ANCHOR_ZONE_REQUIRED"
        return None

    @classmethod
    def _prepare_return_basis(
        cls, connection, stream_id, event, source, *, expected_stream_revision,
    ):
        """Pin a proven return to the exact, current prior sale allocation."""
        allocation = connection.execute(
            """SELECT allocation_id, revision, stream_revision, status, cutoff_status
               FROM fifo_cost_allocations WHERE stream_id=?
               ORDER BY revision DESC LIMIT 1""",
            (stream_id,),
        ).fetchone()
        if (
            allocation is None
            or allocation["status"] != "COMPLETE"
            or allocation["cutoff_status"] != "RECONCILED"
            or allocation["stream_revision"] != expected_stream_revision
        ):
            raise ValueError("FIFO_RETURN_ORIGIN_ALLOCATION_UNAVAILABLE")

        sale = connection.execute(
            """SELECT event_id, quantity, effective_date, inventory_cutoff,
                      source_identity_digest
               FROM fifo_cost_events WHERE stream_id=? AND event_id=?
                 AND event_kind='PHYSICAL_SALE' LIMIT 1""",
            (stream_id, event["supersedes_event_id"]),
        ).fetchone()
        if sale is None or not cls._valid_digest(sale["source_identity_digest"]):
            raise ValueError("FIFO_RETURN_ORIGIN_SALE_MISSING")
        if (
            event["inventory_cutoff"] != sale["inventory_cutoff"]
            or event["effective_date"] is None
            or sale["effective_date"] is None
            or event["effective_date"] <= sale["effective_date"]
        ):
            raise ValueError("FIFO_RETURN_EFFECTIVE_DATE_UNAVAILABLE")
        refs = {reference["digest"] for reference in source["references"]}
        if sale["source_identity_digest"] not in refs:
            raise ValueError("FIFO_RETURN_ORIGIN_SALE_MISMATCH")

        basis_rows = connection.execute(
            """SELECT line_number, layer_id, quantity, unit_cost_rub,
                      total_cost_rub
               FROM fifo_cost_allocation_lines
               WHERE allocation_id=? AND event_id=?
               ORDER BY line_number LIMIT 100001""",
            (allocation["allocation_id"], sale["event_id"]),
        ).fetchall()
        rate_rows = connection.execute(
            """SELECT line_number, rate_change_id, quantity, unit_cost_rub,
                      total_cost_rub
               FROM fifo_cost_allocation_rate_lines
               WHERE allocation_id=? AND event_id=?
               ORDER BY line_number LIMIT 100001""",
            (allocation["allocation_id"], sale["event_id"]),
        ).fetchall()
        if len(basis_rows) + len(rate_rows) > 100_000:
            raise ValueError("FIFO_REPLAY_INPUT_LIMIT")
        if rate_rows:
            raise ValueError("FIFO_RETURN_OPEN_RATE_BASIS_UNSUPPORTED")
        if not basis_rows or sum(row["quantity"] for row in basis_rows) != sale["quantity"]:
            raise ValueError("FIFO_RETURN_ORIGIN_ALLOCATION_INVALID")

        prior = connection.execute(
            """SELECT COALESCE(SUM(quantity), 0) FROM fifo_cost_return_basis
               WHERE origin_sale_event_id=?""",
            (sale["event_id"],),
        ).fetchone()[0]
        if prior + event["quantity"] > sale["quantity"]:
            raise ValueError("FIFO_RETURN_QUANTITY_EXCEEDS_ORIGIN")
        if event["quantity"] != sale["quantity"] and len(basis_rows) != 1:
            raise ValueError("FIFO_RETURN_SPLIT_AMBIGUOUS")
        if event["quantity"] == sale["quantity"] and prior:
            raise ValueError("FIFO_RETURN_QUANTITY_EXCEEDS_ORIGIN")

        remaining = event["quantity"]
        prepared = []
        for row in basis_rows:
            previously_restored = connection.execute(
                """SELECT COALESCE(SUM(quantity), 0)
                   FROM fifo_cost_return_basis
                   WHERE origin_sale_event_id=? AND layer_id=?""",
                (sale["event_id"], row["layer_id"]),
            ).fetchone()[0]
            available = row["quantity"] - previously_restored
            take = min(available, remaining)
            if take > 0:
                unit_cost = cls._normalize_money(row["unit_cost_rub"])
                total_cost = (Decimal(unit_cost) * take).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                )
                prepared.append({
                    "allocation_id": allocation["allocation_id"],
                    "allocation_line_number": row["line_number"],
                    "layer_id": row["layer_id"],
                    "rate_change_id": None,
                    "quantity": take,
                    "unit_cost_rub": unit_cost,
                    "total_cost_rub": format(total_cost, ".2f"),
                })
                remaining -= take
            if remaining == 0:
                break
        if remaining:
            raise ValueError("FIFO_RETURN_ORIGIN_ALLOCATION_INVALID")
        return prepared

    def _ensure_source(self, connection, normalized):
        source = normalized["source"]
        source_id = normalized["source_id"]
        row = connection.execute(
            """SELECT source_id, source_kind, source_method, source_status,
                      provenance, captured_at, source_as_of, coverage_status,
                      record_count, page_count
               FROM fifo_cost_sources WHERE store_id=? AND source_fingerprint=?""",
            (normalized["identity"]["store_id"], source["source_fingerprint"]),
        ).fetchone()
        is_new_source = row is None
        expected = (
            source_id, source["source_kind"], source["source_method"],
            source["source_status"], source["provenance"], source["captured_at"],
            source["source_as_of"], source["coverage_status"],
            source["record_count"], source["page_count"],
        )
        if row is not None:
            if tuple(row) != expected:
                raise ValueError("FIFO_SOURCE_FINGERPRINT_CONFLICT")
            existing_refs = {
                (item["reference_kind"], item["reference_digest"])
                for item in connection.execute(
                    "SELECT reference_kind, reference_digest "
                    "FROM fifo_cost_source_refs WHERE source_id=?",
                    (source_id,),
                ).fetchall()
            }
            requested_refs = {
                (item["kind"], item["digest"]) for item in source["references"]
            }
            if existing_refs != requested_refs:
                raise ValueError("FIFO_SOURCE_FINGERPRINT_CONFLICT")
        else:
            connection.execute(
                """INSERT INTO fifo_cost_sources (
                    source_id, store_id, source_kind, source_method, source_status,
                    provenance, source_fingerprint, captured_at, source_as_of,
                    coverage_status, record_count, page_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source_id, normalized["identity"]["store_id"],
                    source["source_kind"], source["source_method"],
                    source["source_status"], source["provenance"],
                    source["source_fingerprint"], source["captured_at"],
                    source["source_as_of"], source["coverage_status"],
                    source["record_count"], source["page_count"],
                    self._iso(self._now()),
                ),
            )
        for ref in (source["references"] if is_new_source else ()):
            ref_id = "ref_" + self._sha256({
                "source_id": source_id,
                "kind": ref["kind"],
                "digest": ref["digest"],
            })[:40]
            connection.execute(
                """INSERT OR IGNORE INTO fifo_cost_source_refs (
                    source_ref_id, source_id, reference_kind, reference_digest, created_at
                ) VALUES (?, ?, ?, ?, ?)""",
                (ref_id, source_id, ref["kind"], ref["digest"], self._iso(self._now())),
            )

    def _ensure_policy_revision(self, connection, normalized, now):
        identity = normalized["identity"]
        policy = {
            "version": identity["policy_version"],
            "allocation": "FIFO",
            "currency": "RUB",
            "quantity_unit": "SELLABLE_SKU_UNIT",
        }
        policy_json = self._canonical_json(policy)
        fingerprint = self._sha256_text(policy_json)
        row = connection.execute(
            """SELECT policy_json, policy_fingerprint FROM fifo_cost_policy_revisions
               WHERE stream_id=? AND policy_version=?""",
            (normalized["stream_id"], identity["policy_version"]),
        ).fetchone()
        if row is None:
            connection.execute(
                """INSERT INTO fifo_cost_policy_revisions (
                    stream_id, policy_version, policy_json, policy_fingerprint, created_at
                ) VALUES (?, ?, ?, ?, ?)""",
                (
                    normalized["stream_id"], identity["policy_version"],
                    policy_json, fingerprint, self._iso(now),
                ),
            )
        elif tuple(row) != (policy_json, fingerprint):
            raise ValueError("FIFO_POLICY_REVISION_CONFLICT")

    @staticmethod
    def _validate_supersedes_target(connection, stream_id, event, prior_events):
        target_id = event["supersedes_event_id"]
        if not target_id:
            return None
        for previous in prior_events:
            if previous["event_id"] == target_id:
                return previous["kind"]
        row = connection.execute(
            "SELECT event_kind FROM fifo_cost_events WHERE stream_id=? AND event_id=?",
            (stream_id, target_id),
        ).fetchone()
        if row is None:
            raise ValueError("FIFO_EVENT_TARGET_INVALID")
        return row["event_kind"]

    @classmethod
    def _normalize_money(cls, value):
        if value is None:
            return None
        if isinstance(value, bool) or isinstance(value, float):
            raise ValueError("FIFO_MONEY_INPUT_INVALID")
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError("FIFO_MONEY_INPUT_INVALID") from None
        if not amount.is_finite() or amount < 0 or amount > Decimal("1000000000"):
            raise ValueError("FIFO_MONEY_INPUT_INVALID")
        return format(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")

    @classmethod
    def _normalize_timestamp(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("FIFO_TIMESTAMP_INVALID")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("FIFO_TIMESTAMP_INVALID") from None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("FIFO_TIMESTAMP_INVALID")
        return cls._iso(parsed)

    @staticmethod
    def _normalize_date(value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("FIFO_DATE_INVALID")
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            raise ValueError("FIFO_DATE_INVALID") from None

    @classmethod
    def _normalize_cutoff(cls, value):
        if value is None:
            return None
        if isinstance(value, str) and "T" not in value and " " not in value:
            return cls._normalize_date(value)
        return cls._normalize_timestamp(value)

    @staticmethod
    def _optional_count(value):
        if value is None:
            return None
        if type(value) is not int or not 0 <= value <= 10_000_000:
            raise ValueError("FIFO_SOURCE_COUNT_INVALID")
        return value

    @staticmethod
    def _enum_text(value, code, max_length):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9_./-]{1," + str(max_length) + r"}", value):
            raise ValueError(code)
        return value

    @classmethod
    def _normalize_late_entry_correction(cls, value):
        """Validate and freeze a complete, read-only FC22 impact preview."""
        if not isinstance(value, dict) or value.get("error") is not False:
            return "FIFO_LATE_ENTRY_IMPACT_INVALID"
        if (
            value.get("code") != "FIFO_LATE_ENTRY_IMPACT_READY"
            or value.get("complete") is not True
            or value.get("read_only") is not True
        ):
            return "FIFO_LATE_ENTRY_IMPACT_INCOMPLETE"
        for count_field in ("related_return_count", "non_sale_outflow_count"):
            count = value.get(count_field)
            if type(count) is not int or not 0 <= count <= 100_000:
                return "FIFO_LATE_ENTRY_IMPACT_INVALID"
        if (
            value.get("return_cogs_authorization_changed") is not False
            or value.get("non_sale_outflows_included_in_sales_cogs") is not False
        ):
            return "FIFO_LATE_ENTRY_IMPACT_INVALID"
        try:
            outflow_value = cls._normalize_money(
                value.get("non_sale_outflow_estimated_value_rub"),
            )
        except ValueError:
            return "FIFO_LATE_ENTRY_IMPACT_INVALID"
        if (
            outflow_value is None
            or outflow_value != value["non_sale_outflow_estimated_value_rub"]
            or (
                value["non_sale_outflow_count"] == 0
                and outflow_value != "0.00"
            )
        ):
            return "FIFO_LATE_ENTRY_IMPACT_INVALID"
        digest_fields = (
            "preview_fingerprint", "source_set_fingerprint",
            "reconstruction_fingerprint", "tax_policy_fingerprint",
            "financial_period_mapping_fingerprint",
        )
        if any(not cls._valid_digest(value.get(field)) for field in digest_fields):
            return "FIFO_LATE_ENTRY_IMPACT_INVALID"
        draft_id = value.get("draft_id")
        if not isinstance(draft_id, str) or not re.fullmatch(
            r"late_[0-9a-f]{40}", draft_id,
        ):
            return "FIFO_LATE_ENTRY_IMPACT_INVALID"
        stream_revision = value.get("stream_revision")
        allocation_revision = value.get("allocation_revision")
        if (
            type(stream_revision) is not int or stream_revision < 1
            or type(allocation_revision) is not int or allocation_revision < 0
        ):
            return "FIFO_LATE_ENTRY_IMPACT_INVALID"
        material = {
            key: item for key, item in value.items()
            if key not in {"preview_fingerprint", "code", "error"}
        }
        if cls._sha256(material) != value["preview_fingerprint"]:
            return "FIFO_LATE_ENTRY_IMPACT_FINGERPRINT_INVALID"
        periods = value.get("periods")
        if not isinstance(periods, list) or not periods or len(periods) > 200:
            return "FIFO_LATE_ENTRY_IMPACT_INVALID"
        fingerprints = []
        seen_periods = set()
        for row in periods:
            if not isinstance(row, dict):
                return "FIFO_LATE_ENTRY_IMPACT_INVALID"
            period = row.get("period")
            fingerprint = row.get("source_fingerprint")
            if (
                not isinstance(period, str)
                or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period)
                or period in seen_periods
                or not cls._valid_digest(fingerprint)
                or row.get("completeness") != "COMPLETE"
                or row.get("linked_return_count", 0) != 0
            ):
                return "FIFO_LATE_ENTRY_IMPACT_INVALID"
            seen_periods.add(period)
            fingerprints.append({"period": period, "fingerprint": fingerprint})
        try:
            impact_json = cls._canonical_json(value)
            period_fingerprints_json = cls._canonical_json(
                sorted(fingerprints, key=lambda item: item["period"]),
            )
        except (TypeError, ValueError, OverflowError):
            return "FIFO_LATE_ENTRY_IMPACT_INVALID"
        if len(impact_json.encode("utf-8")) > cls.MAX_PAYLOAD_BYTES:
            return "FIFO_LATE_ENTRY_IMPACT_TOO_LARGE"
        correction_id = "latecorr_" + cls._sha256({
            "draft_id": draft_id,
            "preview_fingerprint": value["preview_fingerprint"],
        })[:40]
        return {
            "correction_id": correction_id,
            "draft_id": draft_id,
            "stream_revision": stream_revision,
            "allocation_revision": allocation_revision,
            "source_set_fingerprint": value["source_set_fingerprint"],
            "preview_fingerprint": value["preview_fingerprint"],
            "reconstruction_fingerprint": value["reconstruction_fingerprint"],
            "tax_policy_fingerprint": value["tax_policy_fingerprint"],
            "period_source_fingerprints_json": period_fingerprints_json,
            "impact_json": impact_json,
        }

    @classmethod
    def _valid_digest(cls, value):
        return isinstance(value, str) and cls._HEX_DIGEST.fullmatch(value) is not None

    @staticmethod
    def _canonical_json(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def _sha256(cls, value):
        return cls._sha256_text(cls._canonical_json(value))

    @staticmethod
    def _sha256_text(value):
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()

    def _now(self):
        value = self._now_provider()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("FIFO_CLOCK_INVALID")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _iso(value):
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def _purge_expired_previews(self, now):
        cutoff = now.timestamp()
        expired = [
            scope for scope, ticket in self._ACTIVE_PREVIEWS.items()
            if ticket["expires_at"] <= cutoff
        ]
        for scope in expired:
            self._ACTIVE_PREVIEWS.pop(scope, None)

    def _transition_metadata_scope(self, metadata):
        if not isinstance(metadata, TransitionMetadata):
            return self._error("FIFO_TRANSITION_SCOPE_INVALID"), None
        scope = self._tenant_scope(metadata.scope.store_id)
        if scope.get("error"):
            return scope, None
        tenant_id = str(get_current_tenant_user_id() or "").strip()
        owner_id, scoped_store = split_store_tenant_scope(tenant_id)
        if (owner_id != metadata.scope.owner_id
                or scoped_store != metadata.scope.store_id):
            return self._error("FIFO_TRANSITION_SCOPE_MISMATCH"), None
        try:
            identity = self._normalize_identity(
                metadata.scope.store_id, metadata.scope.product_id,
                metadata.scope.offer_id, metadata.scope.sku, 1,
            )
        except ValueError:
            return self._error("FIFO_TRANSITION_SCOPE_INVALID"), None
        return scope, identity

    def _normalize_transition_read_identity(
        self, store_id, *, product_id=None, offer_id=None, sku,
    ):
        try:
            return self._normalize_identity(
                store_id, product_id, offer_id, sku, 1,
            )
        except ValueError:
            return self._error("FIFO_TRANSITION_SCOPE_INVALID")

    @staticmethod
    def _valid_transition_case_id(value):
        return (
            isinstance(value, str)
            and re.fullmatch(r"[A-Za-z0-9_-]{8,96}", value) is not None
        )

    @staticmethod
    def _valid_transition_idempotency_key(value):
        return (
            isinstance(value, str)
            and re.fullmatch(r"[A-Za-z0-9_-]{8,128}", value) is not None
        )

    def _run_transition_write(self, operation):
        connection = None
        try:
            connection = self.get_connection()
            connection.execute("BEGIN IMMEDIATE")
            result = operation(connection)
            if result.get("error"):
                connection.rollback()
                return result
            connection.commit()
            return result
        except sqlite3.IntegrityError:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            return self._error("FIFO_TRANSITION_EVIDENCE_CONFLICT")
        except (sqlite3.Error, OSError):
            if connection is not None and connection.in_transaction:
                connection.rollback()
            return self._error("FIFO_TRANSITION_STORAGE_UNAVAILABLE")
        except (TypeError, ValueError, OverflowError):
            if connection is not None and connection.in_transaction:
                connection.rollback()
            return self._error("FIFO_TRANSITION_PAYLOAD_INVALID")
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}

    @classmethod
    def _migrate_schema(cls, connection, version):
        """Add allocation source revision metadata without rewriting evidence."""
        if version < 6:
            columns = {
                str(row[1]) for row in
                connection.execute("PRAGMA table_info(fifo_cost_allocations)")
            }
            if "stream_revision" not in columns:
                connection.execute(
                    """ALTER TABLE fifo_cost_allocations
                       ADD COLUMN stream_revision INTEGER NOT NULL DEFAULT 0
                       CHECK(stream_revision >= 0)"""
                )
        if version < 12:
            columns = {
                str(row[1]) for row in
                connection.execute("PRAGMA table_info(fifo_cost_projections)")
            }
            if "inventory_cutoff" not in columns:
                connection.execute(
                    """ALTER TABLE fifo_cost_projections
                       ADD COLUMN inventory_cutoff TEXT"""
                )
            cls._backfill_zero_stock_inventory_cutoffs(connection)
        if version > 0 and version < 13:
            rate_columns = tuple(
                str(row[1]) for row in
                connection.execute("PRAGMA table_info(fifo_cost_rate_changes)")
            )
            if "cost_input_mode" not in rate_columns:
                cls._rebuild_rate_changes_v13(connection, rate_columns)

    @classmethod
    def _rebuild_rate_changes_v13(cls, connection, old_columns):
        """Rebuild v12 rates while preserving every row, FK edge and SQL object."""
        expected_columns = (
            "rate_change_id", "stream_id", "stream_revision", "rate_sequence",
            "effective_date", "unit_cost_rub", "purchase_cost_rub",
            "delivery_cost_rub", "packaging_cost_rub", "owner_old_home_units",
            "source_id", "source_fingerprint", "payload_fingerprint",
            "idempotency_key", "recorded_at", "captured_at",
        )
        if tuple(old_columns) != expected_columns:
            raise sqlite3.DatabaseError("unsupported FIFO rate table shape")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 0:
            raise sqlite3.DatabaseError("FIFO v13 rebuild requires foreign keys disabled")

        preserved_objects = connection.execute(
            """SELECT type, sql FROM sqlite_master
               WHERE tbl_name='fifo_cost_rate_changes'
                 AND type IN ('index', 'trigger') AND sql IS NOT NULL
               ORDER BY type, name"""
        ).fetchall()
        connection.execute(
            """CREATE TABLE fifo_cost_rate_changes_v13 (
                rate_change_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                stream_revision INTEGER NOT NULL CHECK(stream_revision >= 1),
                rate_sequence INTEGER NOT NULL CHECK(rate_sequence >= 1),
                effective_date TEXT NOT NULL,
                unit_cost_rub TEXT NOT NULL,
                cost_input_mode TEXT NOT NULL DEFAULT 'COMPONENTS'
                    CHECK(cost_input_mode IN ('COMPONENTS', 'TOTAL_LANDED')),
                purchase_cost_rub TEXT,
                delivery_cost_rub TEXT,
                packaging_cost_rub TEXT,
                owner_old_home_units INTEGER NOT NULL CHECK(
                    owner_old_home_units >= 0 AND owner_old_home_units <= 1000000
                ),
                source_id TEXT NOT NULL REFERENCES fifo_cost_sources(source_id),
                source_fingerprint TEXT NOT NULL,
                payload_fingerprint TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                UNIQUE(stream_id, rate_sequence),
                UNIQUE(stream_id, idempotency_key),
                CHECK(
                    (cost_input_mode='COMPONENTS'
                     AND purchase_cost_rub IS NOT NULL
                     AND delivery_cost_rub IS NOT NULL
                     AND packaging_cost_rub IS NOT NULL)
                    OR
                    (cost_input_mode='TOTAL_LANDED'
                     AND purchase_cost_rub IS NULL
                     AND delivery_cost_rub IS NULL
                     AND packaging_cost_rub IS NULL)
                )
            )"""
        )
        connection.execute(
            """INSERT INTO fifo_cost_rate_changes_v13 (
                   rate_change_id, stream_id, stream_revision, rate_sequence,
                   effective_date, unit_cost_rub, cost_input_mode,
                   purchase_cost_rub, delivery_cost_rub, packaging_cost_rub,
                   owner_old_home_units, source_id, source_fingerprint,
                   payload_fingerprint, idempotency_key, recorded_at, captured_at
               )
               SELECT rate_change_id, stream_id, stream_revision, rate_sequence,
                      effective_date, unit_cost_rub, 'COMPONENTS',
                      purchase_cost_rub, delivery_cost_rub, packaging_cost_rub,
                      owner_old_home_units, source_id, source_fingerprint,
                      payload_fingerprint, idempotency_key, recorded_at, captured_at
               FROM fifo_cost_rate_changes"""
        )
        connection.execute("DROP TABLE fifo_cost_rate_changes")
        connection.execute(
            "ALTER TABLE fifo_cost_rate_changes_v13 RENAME TO fifo_cost_rate_changes"
        )
        for item in preserved_objects:
            connection.execute(item["sql"])

    @classmethod
    def _backfill_zero_stock_inventory_cutoffs(cls, connection):
        """Recover only a zero-stock cutoff proven by its complete source chain."""
        projections = connection.execute(
            """SELECT p.stream_id, s.store_id, p.source_set_fingerprint
               FROM fifo_cost_projections AS p
               JOIN fifo_cost_streams AS s ON s.stream_id=p.stream_id
               WHERE p.inventory_cutoff IS NULL
                 AND p.source_set_fingerprint IS NOT NULL
                 AND NOT EXISTS (
                     SELECT 1 FROM fifo_cost_events AS e
                     WHERE e.stream_id=p.stream_id
                       AND e.event_kind='OPENING_FIFO_ANCHOR'
                 )"""
        ).fetchall()
        for projection in projections:
            rates = connection.execute(
                """SELECT r.rate_sequence, s.source_fingerprint
                   FROM fifo_cost_rate_changes AS r
                   JOIN fifo_cost_sources AS s ON s.source_id=r.source_id
                   WHERE r.stream_id=? ORDER BY r.rate_sequence LIMIT 257""",
                (projection["stream_id"],),
            ).fetchall()
            if (
                not rates or len(rates) > 256
                or [row["rate_sequence"] for row in rates]
                != list(range(1, len(rates) + 1))
            ):
                continue
            stock_sources = connection.execute(
                """SELECT source_fingerprint, captured_at
                   FROM fifo_cost_sources
                   WHERE store_id=? AND source_method='FIFO_PRODUCT_STOCKS'
                     AND source_status='COMPLETE' AND captured_at IS NOT NULL
                   LIMIT 1001""",
                (projection["store_id"],),
            ).fetchall()
            if len(stock_sources) > 1000:
                continue
            matching_cutoffs = set()
            for stock_source in stock_sources:
                source_set = cls._sha256({
                    "zero_stock": stock_source["source_fingerprint"],
                    "rate": rates[0]["source_fingerprint"],
                })
                for rate in rates[1:]:
                    source_set = cls._sha256({
                        "previous": source_set,
                        "rate": rate["source_fingerprint"],
                    })
                captured_at = stock_source["captured_at"]
                if (
                    source_set == projection["source_set_fingerprint"]
                    and isinstance(captured_at, str)
                    and len(captured_at) >= 10
                ):
                    try:
                        cutoff = date.fromisoformat(captured_at[:10]).isoformat()
                    except ValueError:
                        continue
                    matching_cutoffs.add(cutoff)
            if len(matching_cutoffs) == 1:
                connection.execute(
                    "UPDATE fifo_cost_projections SET inventory_cutoff=? WHERE stream_id=?",
                    (next(iter(matching_cutoffs)), projection["stream_id"]),
                )

    @classmethod
    def _normalize_allocation_preview(cls, preview, idempotency_key):
        if not isinstance(preview, dict):
            return "FIFO_ALLOCATION_PREVIEW_INVALID"
        expected_preview_keys = {
            "error", "complete", "status", "reason_code", "cutoff_status",
            "anchor_cutoff_date", "open_rate_effective_date", "stream_revision",
            "expected_allocation_revision", "source_set_fingerprint",
            "total_cogs_rub", "non_sale_outflow_value_rub",
            "remaining_confirmed_units", "restored_units",
            "allocations", "outflows", "preview_fingerprint",
        }
        if set(preview) != expected_preview_keys:
            return "FIFO_ALLOCATION_PREVIEW_INVALID"
        if not isinstance(idempotency_key, str) or not cls._IDEMPOTENCY_KEY.fullmatch(idempotency_key):
            return "FIFO_IDEMPOTENCY_KEY_INVALID"
        if (
            preview.get("error") is not False
            or preview.get("complete") is not True
            or preview.get("status") != "COMPLETE"
            or preview.get("reason_code") is not None
            or preview.get("cutoff_status") != "RECONCILED"
            or cls._normalize_date(preview.get("anchor_cutoff_date")) is None
            or (
                preview.get("open_rate_effective_date") is not None
                and cls._normalize_date(preview.get("open_rate_effective_date")) is None
            )
        ):
            return "FIFO_ALLOCATION_PREVIEW_INCOMPLETE"
        stream_revision = preview.get("stream_revision")
        allocation_revision = preview.get("expected_allocation_revision")
        source_fingerprint = preview.get("source_set_fingerprint")
        preview_fingerprint = preview.get("preview_fingerprint")
        if type(stream_revision) is not int or stream_revision < 1:
            return "FIFO_REVISION_CONFLICT"
        if type(allocation_revision) is not int or allocation_revision < 0:
            return "FIFO_REVISION_CONFLICT"
        if not cls._valid_digest(source_fingerprint) or not cls._valid_digest(preview_fingerprint):
            return "FIFO_ALLOCATION_PREVIEW_INVALID"
        material = {
            key: value for key, value in preview.items()
            if key not in {"preview_fingerprint", "error"}
        }
        if cls._sha256(material) != preview_fingerprint:
            return "FIFO_ALLOCATION_PREVIEW_INVALID"
        allocations = preview.get("allocations")
        if not isinstance(allocations, list) or len(allocations) > 100_000:
            return "FIFO_REPLAY_INPUT_LIMIT"
        normalized, seen_events = [], set()
        units, lines_total, total = 0, 0, Decimal("0.00")
        for row in allocations:
            if not isinstance(row, dict) or set(row) != {
                "event_id", "quantity", "total_cost_rub", "lines",
            }:
                return "FIFO_ALLOCATION_PREVIEW_INVALID"
            event_id, quantity = row.get("event_id"), row.get("quantity")
            sale_total = cls._normalize_money(row.get("total_cost_rub"))
            lines = row.get("lines")
            if (
                not isinstance(event_id, str) or not event_id or len(event_id) > 160
                or event_id in seen_events or type(quantity) is not int or quantity < 1
                or sale_total is None or not isinstance(lines, list) or not lines
            ):
                return "FIFO_ALLOCATION_PREVIEW_INVALID"
            seen_events.add(event_id)
            normalized_lines, seen_layers = [], set()
            sale_units, sale_cost = 0, Decimal("0.00")
            for line in lines:
                if not isinstance(line, dict) or set(line) != {
                    "layer_id", "rate_change_id", "quantity", "unit_cost_rub",
                    "total_cost_rub", "origin_sale_event_id",
                }:
                    return "FIFO_ALLOCATION_PREVIEW_INVALID"
                layer_id, line_quantity = line.get("layer_id"), line.get("quantity")
                rate_change_id = line.get("rate_change_id")
                unit_cost = cls._normalize_money(line.get("unit_cost_rub"))
                line_total = cls._normalize_money(line.get("total_cost_rub"))
                origin = line.get("origin_sale_event_id")
                basis_key = (
                    ("layer", layer_id) if isinstance(layer_id, str) else
                    ("rate", rate_change_id) if isinstance(rate_change_id, str) else None
                )
                if (
                    (layer_id is None) == (rate_change_id is None)
                    or (layer_id is not None and (
                        not isinstance(layer_id, str) or not layer_id or len(layer_id) > 160
                    ))
                    or (rate_change_id is not None and (
                        not isinstance(rate_change_id, str) or not rate_change_id
                        or len(rate_change_id) > 160
                    ))
                    or basis_key in seen_layers or type(line_quantity) is not int
                    or line_quantity < 1 or unit_cost is None or line_total is None
                    or (origin is not None and (
                        not isinstance(origin, str) or not origin or len(origin) > 160
                    ))
                ):
                    return "FIFO_ALLOCATION_PREVIEW_INVALID"
                seen_layers.add(basis_key)
                calculated = (Decimal(unit_cost) * line_quantity).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                )
                if calculated != Decimal(line_total):
                    return "FIFO_ALLOCATION_TOTAL_MISMATCH"
                normalized_lines.append({
                    "layer_id": layer_id, "rate_change_id": rate_change_id,
                    "quantity": line_quantity,
                    "unit_cost_rub": unit_cost, "total_cost_rub": line_total,
                    "origin_sale_event_id": origin,
                })
                sale_units += line_quantity
                sale_cost += Decimal(line_total)
            if sale_units != quantity or sale_cost != Decimal(sale_total):
                return "FIFO_ALLOCATION_TOTAL_MISMATCH"
            units += quantity
            lines_total += len(normalized_lines)
            total += sale_cost
            if units > cls.MAX_COMMAND_UNITS or lines_total > 250_000:
                return "FIFO_REPLAY_WORK_LIMIT"
            normalized.append({
                "event_id": event_id, "quantity": quantity,
                "total_cost_rub": sale_total, "lines": normalized_lines,
            })
        grand_total = cls._normalize_money(preview.get("total_cogs_rub"))
        if grand_total is None or Decimal(grand_total) != total:
            return "FIFO_ALLOCATION_TOTAL_MISMATCH"
        outflows = preview.get("outflows")
        if not isinstance(outflows, list) or len(outflows) > 100_000:
            return "FIFO_REPLAY_INPUT_LIMIT"
        normalized_outflows, seen_outflows = [], set()
        outflow_units, outflow_lines_total, outflow_value = 0, 0, Decimal("0.00")
        for row in outflows:
            if not isinstance(row, dict) or set(row) != {
                "event_id", "quantity", "reason_code", "estimated_value_rub",
                "valuation_method", "lines",
            }:
                return "FIFO_ALLOCATION_PREVIEW_INVALID"
            event_id, quantity = row.get("event_id"), row.get("quantity")
            reason = row.get("reason_code")
            estimated = cls._normalize_money(row.get("estimated_value_rub"))
            lines = row.get("lines")
            if (
                not isinstance(event_id, str) or not event_id or len(event_id) > 160
                or event_id in seen_events or event_id in seen_outflows
                or type(quantity) is not int or quantity < 1
                or reason not in {"HOME_SHORTAGE", "OZON_DISPOSAL", "SUPPLIER_RETURN", "INVENTORY_WRITE_OFF"}
                or estimated is None or row.get("valuation_method") != "FIFO_FINITE_LAYER_ESTIMATE"
                or not isinstance(lines, list) or not lines
            ):
                return "FIFO_ALLOCATION_PREVIEW_INVALID"
            seen_outflows.add(event_id)
            line_units, line_value = 0, Decimal("0.00")
            normalized_lines = []
            seen_layers = set()
            for line in lines:
                if not isinstance(line, dict) or set(line) != {
                    "layer_id", "rate_change_id", "quantity", "unit_cost_rub",
                    "total_cost_rub", "origin_sale_event_id",
                }:
                    return "FIFO_ALLOCATION_PREVIEW_INVALID"
                layer_id = line.get("layer_id")
                line_quantity = line.get("quantity")
                unit_cost = cls._normalize_money(line.get("unit_cost_rub"))
                line_total = cls._normalize_money(line.get("total_cost_rub"))
                origin = line.get("origin_sale_event_id")
                if (
                    not isinstance(layer_id, str) or not layer_id or len(layer_id) > 160
                    or line.get("rate_change_id") is not None
                    or layer_id in seen_layers or type(line_quantity) is not int
                    or line_quantity < 1 or unit_cost is None or line_total is None
                    or (origin is not None and (
                        not isinstance(origin, str) or not origin or len(origin) > 160
                    ))
                ):
                    return "FIFO_ALLOCATION_PREVIEW_INVALID"
                seen_layers.add(layer_id)
                if (Decimal(unit_cost) * line_quantity).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                ) != Decimal(line_total):
                    return "FIFO_ALLOCATION_TOTAL_MISMATCH"
                line_units += line_quantity
                line_value += Decimal(line_total)
                normalized_lines.append({
                    "layer_id": layer_id, "rate_change_id": None,
                    "quantity": line_quantity, "unit_cost_rub": unit_cost,
                    "total_cost_rub": line_total, "origin_sale_event_id": origin,
                })
            if line_units != quantity or line_value != Decimal(estimated):
                return "FIFO_ALLOCATION_TOTAL_MISMATCH"
            outflow_units += quantity
            outflow_value += line_value
            outflow_lines_total += len(normalized_lines)
            if outflow_units > cls.MAX_COMMAND_UNITS or outflow_lines_total > 250_000:
                return "FIFO_REPLAY_WORK_LIMIT"
            normalized_outflows.append({
                "event_id": event_id, "quantity": quantity,
                "reason_code": reason, "estimated_value_rub": estimated,
                "valuation_method": "FIFO_FINITE_LAYER_ESTIMATE",
                "lines": normalized_lines,
            })
        normalized_outflow_total = cls._normalize_money(
            preview.get("non_sale_outflow_value_rub"),
        )
        if normalized_outflow_total is None or Decimal(normalized_outflow_total) != outflow_value:
            return "FIFO_ALLOCATION_TOTAL_MISMATCH"
        payload = {
            "stream_revision": stream_revision,
            "expected_allocation_revision": allocation_revision,
            "source_set_fingerprint": source_fingerprint,
            "preview_fingerprint": preview_fingerprint,
            "anchor_cutoff_date": preview["anchor_cutoff_date"],
            "open_rate_effective_date": preview["open_rate_effective_date"],
            "allocations": normalized,
            "outflows": normalized_outflows,
            "total_cogs_rub": grand_total,
            "non_sale_outflow_value_rub": normalized_outflow_total,
        }
        return {**payload, "payload_fingerprint": cls._sha256(payload)}

    @classmethod
    def _validate_allocation_lines(
        cls, connection, stream_id, preview, *, stream_revision,
        allocation_revision, source_fingerprint, cutoff_status,
    ):
        allocations = preview["allocations"]
        anchor = connection.execute(
            """SELECT COUNT(DISTINCT inventory_cutoff), MIN(inventory_cutoff)
               FROM fifo_cost_events
               WHERE stream_id=? AND event_kind='OPENING_FIFO_ANCHOR'""",
            (stream_id,),
        ).fetchone()
        if anchor[0] != 1 or not isinstance(anchor[1], str):
            raise ValueError("INVENTORY_CUTOFF_UNRECONCILED")
        anchor_cutoff = cls._normalize_date(anchor[1])
        unsupported_events = connection.execute(
            """SELECT COUNT(*) FROM fifo_cost_events
               WHERE stream_id=? AND event_kind NOT IN (
                   'OPENING_FIFO_ANCHOR', 'PHYSICAL_SALE',
                   'SALEABLE_RETURN_RESTOCK', 'NON_SALE_OUTFLOW'
               )""",
            (stream_id,),
        ).fetchone()[0]
        if unsupported_events:
            raise ValueError("FIFO_REPLAY_UNSUPPORTED_EVENT")
        rate_count = connection.execute(
            """SELECT COUNT(*) FROM fifo_cost_rate_changes AS r
               WHERE r.stream_id=? AND NOT EXISTS (
                   SELECT 1 FROM fifo_cost_rate_cancellations AS c
                   WHERE c.stream_id=r.stream_id
                     AND c.rate_change_id=r.rate_change_id
               )""",
            (stream_id,),
        ).fetchone()[0]
        if rate_count > 1:
            raise ValueError("FIFO_REPLAY_RATE_TRANSITION_UNSUPPORTED")
        source_sales = connection.execute(
            """SELECT event_id, effective_date, inventory_cutoff FROM fifo_cost_events
               WHERE stream_id=? AND event_kind='PHYSICAL_SALE'
               ORDER BY event_id LIMIT 100001""",
            (stream_id,),
        ).fetchall()
        if len(source_sales) > 100_000:
            raise ValueError("FIFO_REPLAY_INPUT_LIMIT")
        if {row["event_id"] for row in source_sales} != {
            row["event_id"] for row in allocations
        }:
            raise ValueError("FIFO_ALLOCATION_COVERAGE_MISMATCH")
        source_sale_by_id = {row["event_id"]: row for row in source_sales}
        for sale in source_sale_by_id.values():
            if (
                sale["effective_date"] is None
                or sale["effective_date"] <= anchor_cutoff
                or sale["inventory_cutoff"] != anchor_cutoff
            ):
                raise ValueError("INVENTORY_CUTOFF_UNRECONCILED")
        for allocation in allocations:
            event = connection.execute(
                """SELECT e.event_kind, e.quantity, e.source_identity_digest,
                          e.provenance, e.completeness, s.source_method,
                          s.source_status, s.coverage_status
                   FROM fifo_cost_events AS e
                   LEFT JOIN fifo_cost_sources AS s ON s.source_id=e.source_id
                   WHERE e.stream_id=? AND e.event_id=?""",
                (stream_id, allocation["event_id"]),
            ).fetchone()
            sale_row = source_sale_by_id[allocation["event_id"]]
            if (
                event is None or event["event_kind"] != "PHYSICAL_SALE"
                or event["source_identity_digest"] is None
                or event["quantity"] != allocation["quantity"]
                or event["provenance"] != "OZON_CONFIRMED_FIELD"
                or event["completeness"] != "COMPLETE"
                or event["source_method"] != "OZON_REALIZATION_REPORT"
                or event["source_status"] != "COMPLETE"
                or event["coverage_status"] != "COMPLETE"
            ):
                raise ValueError("FIFO_ALLOCATION_EVENT_INVALID")
            for line in allocation["lines"]:
                if line["layer_id"] is not None:
                    layer = connection.execute(
                        """SELECT l.unit_cost_rub, l.effective_date,
                                  e.event_kind, e.inventory_cutoff
                           FROM fifo_cost_layers AS l
                           JOIN fifo_cost_events AS e ON e.event_id=l.event_id
                           WHERE l.stream_id=? AND l.layer_id=?""",
                        (stream_id, line["layer_id"]),
                    ).fetchone()
                    if layer is None:
                        raise ValueError("FIFO_ALLOCATION_LAYER_INVALID")
                    if (
                        layer["event_kind"] != "OPENING_FIFO_ANCHOR"
                        or layer["effective_date"] != anchor_cutoff
                        or layer["inventory_cutoff"] != anchor_cutoff
                    ):
                        raise ValueError("FIFO_REPLAY_UNSUPPORTED_EVENT")
                    if cls._normalize_money(layer["unit_cost_rub"]) != line["unit_cost_rub"]:
                        raise ValueError("FIFO_ALLOCATION_RATE_MISMATCH")
                else:
                    rate = connection.execute(
                        """SELECT r.unit_cost_rub, r.effective_date
                           FROM fifo_cost_rate_changes AS r
                           WHERE r.stream_id=? AND r.rate_change_id=?
                             AND NOT EXISTS (
                                 SELECT 1 FROM fifo_cost_rate_cancellations AS c
                                 WHERE c.stream_id=r.stream_id
                                   AND c.rate_change_id=r.rate_change_id
                             )""",
                        (stream_id, line["rate_change_id"]),
                    ).fetchone()
                    if rate is None:
                        raise ValueError("FIFO_ALLOCATION_RATE_INVALID")
                    if cls._normalize_money(rate["unit_cost_rub"]) != line["unit_cost_rub"]:
                        raise ValueError("FIFO_ALLOCATION_RATE_MISMATCH")
                    if rate["effective_date"] >= sale_row["effective_date"]:
                        raise ValueError("FIFO_ALLOCATION_RATE_DATE_CONFLICT")
                if line["origin_sale_event_id"] is not None:
                    basis = connection.execute(
                        """SELECT 1 FROM fifo_cost_events
                           WHERE stream_id=? AND event_id=?
                             AND event_kind='PHYSICAL_SALE' LIMIT 1""",
                        (stream_id, line["origin_sale_event_id"]),
                    ).fetchone()
                    if basis is None:
                        raise ValueError("FIFO_ALLOCATION_BASIS_MISSING")

        expected = cls._preview_allocation_from_connection(
            connection, stream_id,
            stream_revision=stream_revision,
            allocation_revision=allocation_revision,
            source_fingerprint=source_fingerprint,
            cutoff_status=cutoff_status,
            anchor_cutoff_date=anchor_cutoff,
        )
        if expected is None or expected.get("complete") is not True:
            reason = (
                expected.get("reason_code") if expected is not None else None
            ) or "FIFO_ALLOCATION_REPLAY_UNAVAILABLE"
            raise ValueError(reason)
        if (
            preview["anchor_cutoff_date"] != anchor_cutoff
            or preview["open_rate_effective_date"] != expected["open_rate_effective_date"]
            or preview["allocations"] != expected["allocations"]
            or preview["outflows"] != expected["outflows"]
            or preview["total_cogs_rub"] != expected["total_cogs_rub"]
            or preview["non_sale_outflow_value_rub"] != expected["non_sale_outflow_value_rub"]
        ):
            raise ValueError("FIFO_ALLOCATION_REPLAY_MISMATCH")

    @classmethod
    def _preview_allocation_from_connection(
        cls, connection, stream_id, *, stream_revision,
        allocation_revision, source_fingerprint, cutoff_status,
        anchor_cutoff_date, hypothetical_outflow=None,
        hypothetical_open_rate=None,
        hypothetical_open_rate_effective_date=None,
        hypothetical_opening_layer_cost_replacement=None,
    ):
        """Rebuild expected FIFO output from immutable source rows before write."""
        anchor_row = connection.execute(
            """SELECT event_id, provenance, completeness, location_to
               FROM fifo_cost_events
               WHERE stream_id=? AND event_kind='OPENING_FIFO_ANCHOR'
               ORDER BY event_id LIMIT 100001""",
            (stream_id,),
        ).fetchall()
        if not anchor_row or len(anchor_row) > 100_000:
            return None
        anchor_status = (
            "CONFIRMED"
            if all(
                event["provenance"] == "OWNER_CONFIRMED"
                and event["completeness"] == "OWNER_CONFIRMED"
                and event["location_to"] in {"OZON", "TRANSIT", "HOME"}
                for event in anchor_row
            )
            else "UNKNOWN"
        )
        layer_rows = connection.execute(
            """SELECT l.layer_id, l.unit_cost_rub, l.quantity, e.event_kind
               FROM fifo_cost_layers AS l
               JOIN fifo_cost_events AS e ON e.event_id=l.event_id
               WHERE l.stream_id=?
               ORDER BY l.layer_sequence LIMIT 100001""",
            (stream_id,),
        ).fetchall()
        if len(layer_rows) > 100_000:
            return {"complete": False, "reason_code": "FIFO_REPLAY_INPUT_LIMIT"}
        replacement_from = replacement_to = None
        if hypothetical_opening_layer_cost_replacement is not None:
            try:
                replacement_from, replacement_to = hypothetical_opening_layer_cost_replacement
            except (TypeError, ValueError):
                return {"complete": False, "reason_code": "FIFO_REPLAY_INPUT_INVALID"}
            replacement_from = cls._normalize_money(replacement_from)
            replacement_to = cls._normalize_money(replacement_to)
            if replacement_from is None or replacement_to is None:
                return {"complete": False, "reason_code": "FIFO_REPLAY_INPUT_INVALID"}
        layers = []
        for row in layer_rows:
            unit_cost = row["unit_cost_rub"]
            if (
                replacement_from is not None
                and row["event_kind"] == "OPENING_FIFO_ANCHOR"
                and cls._normalize_money(unit_cost) == replacement_from
            ):
                unit_cost = replacement_to
            layers.append(FifoCostLayer(row["layer_id"], unit_cost, row["quantity"]))
        sale_rows = connection.execute(
            """SELECT event_id, effective_at, effective_date, quantity,
                      source_identity_digest
               FROM fifo_cost_events
               WHERE stream_id=? AND event_kind='PHYSICAL_SALE'
               ORDER BY event_id LIMIT 100001""",
            (stream_id,),
        ).fetchall()
        if len(sale_rows) > 100_000:
            return {"complete": False, "reason_code": "FIFO_REPLAY_INPUT_LIMIT"}
        sales = []
        for row in sale_rows:
            sales.append(FifoDatedAllocationEvent(
                event=FifoSaleEvent(row["event_id"], row["quantity"]),
                effective_at=row["effective_at"],
                effective_date=row["effective_date"],
                source_identity_digest=row["source_identity_digest"],
                physical_time_confirmed=True,
                cutoff_bridge_confirmed=(cutoff_status == "RECONCILED"),
            ))
        return_rows = connection.execute(
            """SELECT e.event_id, e.effective_at, e.effective_date, e.quantity,
                      e.source_identity_digest, e.supersedes_event_id,
                      e.inventory_cutoff, e.provenance, e.completeness,
                      s.source_kind, s.source_method, s.source_status,
                      s.coverage_status
               FROM fifo_cost_events AS e
               LEFT JOIN fifo_cost_sources AS s ON s.source_id=e.source_id
               WHERE e.stream_id=? AND e.event_kind='SALEABLE_RETURN_RESTOCK'
               ORDER BY e.event_id LIMIT 100001""",
            (stream_id,),
        ).fetchall()
        if len(return_rows) > 100_000:
            return {"complete": False, "reason_code": "FIFO_REPLAY_INPUT_LIMIT"}
        ref_rows = connection.execute(
            """SELECT e.event_id, r.reference_kind, r.reference_digest
               FROM fifo_cost_events AS e
               LEFT JOIN fifo_cost_source_refs AS r ON r.source_id=e.source_id
               WHERE e.stream_id=? AND e.event_kind='SALEABLE_RETURN_RESTOCK'
               ORDER BY e.event_id, r.reference_kind, r.reference_digest
               LIMIT 200001""",
            (stream_id,),
        ).fetchall()
        if len(ref_rows) > 200_000:
            return {"complete": False, "reason_code": "FIFO_REPLAY_WORK_LIMIT"}
        refs_by_return = {}
        for ref in ref_rows:
            if ref["reference_kind"] is not None:
                refs_by_return.setdefault(ref["event_id"], set()).add(
                    (ref["reference_kind"], ref["reference_digest"]),
                )
        command_rows = connection.execute(
            """SELECT ce.event_id, c.stream_revision
               FROM fifo_cost_command_events AS ce
               JOIN fifo_cost_commands AS c ON c.command_id=ce.command_id
               JOIN fifo_cost_events AS e ON e.event_id=ce.event_id
               WHERE e.stream_id=? AND e.event_kind='SALEABLE_RETURN_RESTOCK'
               ORDER BY ce.event_id LIMIT 100001""",
            (stream_id,),
        ).fetchall()
        if len(command_rows) > 100_000:
            return {"complete": False, "reason_code": "FIFO_REPLAY_INPUT_LIMIT"}
        commands_by_return = {
            row["event_id"]: row["stream_revision"] for row in command_rows
        }
        basis_rows = connection.execute(
            """SELECT b.return_event_id, b.basis_line_number, b.allocation_id,
                      b.allocation_line_number, b.origin_sale_event_id,
                      b.layer_id, b.rate_change_id, b.quantity,
                      b.unit_cost_rub, b.total_cost_rub,
                      a.stream_revision, a.status, a.cutoff_status,
                      l.event_id AS allocated_event_id, l.layer_id AS allocated_layer_id,
                      l.quantity AS allocated_quantity,
                      l.unit_cost_rub AS allocated_unit_cost,
                      l.total_cost_rub AS allocated_total_cost
               FROM fifo_cost_return_basis AS b
               JOIN fifo_cost_allocations AS a ON a.allocation_id=b.allocation_id
               LEFT JOIN fifo_cost_allocation_lines AS l
                 ON l.allocation_id=b.allocation_id
                AND l.line_number=b.allocation_line_number
               JOIN fifo_cost_events AS e ON e.event_id=b.return_event_id
               WHERE e.stream_id=? AND e.event_kind='SALEABLE_RETURN_RESTOCK'
               ORDER BY b.return_event_id, b.basis_line_number LIMIT 250001""",
            (stream_id,),
        ).fetchall()
        if len(basis_rows) > 250_000:
            return {"complete": False, "reason_code": "FIFO_REPLAY_WORK_LIMIT"}
        bases_by_return = {}
        for basis in basis_rows:
            bases_by_return.setdefault(basis["return_event_id"], []).append(basis)
        sale_by_id = {row["event_id"]: row for row in sale_rows}
        for row in return_rows:
            origin = sale_by_id.get(row["supersedes_event_id"])
            if (
                origin is None
                or row["source_kind"] != "OWNER_CONFIRMATION"
                or row["source_method"] != "OWNER_CONFIRMED_SALEABLE_RETURN_RECOVERY"
                or row["source_status"] != "OWNER_CONFIRMED"
                or row["provenance"] != "OWNER_CONFIRMED"
                or row["completeness"] != "OWNER_CONFIRMED"
                or row["coverage_status"] != "OWNER_CONFIRMED"
                or row["inventory_cutoff"] != anchor_cutoff_date
                or not cls._valid_digest(row["source_identity_digest"])
            ):
                return {
                    "complete": False,
                    "reason_code": "FIFO_RETURN_SALEABLE_RECOVERY_UNCONFIRMED",
                }
            expected_refs = {
                ("OTHER", row["source_identity_digest"]),
                ("OTHER", origin["source_identity_digest"]),
            }
            if refs_by_return.get(row["event_id"], set()) != expected_refs:
                return {
                    "complete": False,
                    "reason_code": "FIFO_RETURN_SOURCE_REFERENCE_INVALID",
                }
            command_revision = commands_by_return.get(row["event_id"])
            bases = bases_by_return.get(row["event_id"], [])
            if (
                not bases or command_revision is None
                or sum(base["quantity"] for base in bases) != row["quantity"]
                or any(
                    base["origin_sale_event_id"] != row["supersedes_event_id"]
                    or base["layer_id"] is None or base["rate_change_id"] is not None
                    or base["allocated_event_id"] != row["supersedes_event_id"]
                    or base["allocated_layer_id"] != base["layer_id"]
                    or base["quantity"] > base["allocated_quantity"]
                    or base["unit_cost_rub"] != base["allocated_unit_cost"]
                    or Decimal(base["total_cost_rub"]) != (
                        Decimal(base["unit_cost_rub"]) * base["quantity"]
                    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    or base["stream_revision"] >= command_revision
                    or base["status"] != "COMPLETE"
                    or base["cutoff_status"] != "RECONCILED"
                    for base in bases
                )
            ):
                return {"complete": False, "reason_code": "FIFO_RETURN_ORIGIN_ALLOCATION_INVALID"}
            sales.append(FifoDatedAllocationEvent(
                event=FifoRestockEvent(
                    row["event_id"], row["quantity"], tuple(
                        FifoRestoreSlice(
                            row["supersedes_event_id"], base["layer_id"],
                            base["quantity"],
                        ) for base in bases
                    ),
                ),
                effective_at=row["effective_at"],
                effective_date=row["effective_date"],
                source_identity_digest=row["source_identity_digest"],
                physical_time_confirmed=True,
                cutoff_bridge_confirmed=(cutoff_status == "RECONCILED"),
                saleable_recovery_confirmed=True,
            ))
        outflow_rows = connection.execute(
            """SELECT e.event_id, e.effective_at, e.effective_date, e.quantity,
                      e.source_identity_digest, e.inventory_cutoff, e.reason_code,
                      e.provenance, e.completeness, s.source_kind, s.source_method,
                      s.source_status, s.coverage_status
               FROM fifo_cost_events AS e
               LEFT JOIN fifo_cost_sources AS s ON s.source_id=e.source_id
               WHERE e.stream_id=? AND e.event_kind='NON_SALE_OUTFLOW'
               ORDER BY e.event_id LIMIT 100001""",
            (stream_id,),
        ).fetchall()
        if len(outflow_rows) > 100_000:
            return {"complete": False, "reason_code": "FIFO_REPLAY_INPUT_LIMIT"}
        outflow_refs = connection.execute(
            """SELECT e.event_id, r.reference_kind, r.reference_digest
               FROM fifo_cost_events AS e
               LEFT JOIN fifo_cost_source_refs AS r ON r.source_id=e.source_id
               WHERE e.stream_id=? AND e.event_kind='NON_SALE_OUTFLOW'
               ORDER BY e.event_id, r.reference_kind, r.reference_digest
               LIMIT 100001""",
            (stream_id,),
        ).fetchall()
        if len(outflow_refs) > 100_000:
            return {"complete": False, "reason_code": "FIFO_REPLAY_WORK_LIMIT"}
        refs_by_outflow = {}
        for ref in outflow_refs:
            if ref["reference_kind"] is not None:
                refs_by_outflow.setdefault(ref["event_id"], set()).add(
                    (ref["reference_kind"], ref["reference_digest"]),
                )
        outflow_commands = connection.execute(
            """SELECT ce.event_id, c.stream_revision
               FROM fifo_cost_command_events AS ce
               JOIN fifo_cost_commands AS c ON c.command_id=ce.command_id
               JOIN fifo_cost_events AS e ON e.event_id=ce.event_id
               WHERE e.stream_id=? AND e.event_kind='NON_SALE_OUTFLOW'
               ORDER BY ce.event_id LIMIT 100001""",
            (stream_id,),
        ).fetchall()
        if len(outflow_commands) > 100_000:
            return {"complete": False, "reason_code": "FIFO_REPLAY_INPUT_LIMIT"}
        outflow_command_revisions = {
            row["event_id"]: row["stream_revision"] for row in outflow_commands
        }
        for row in outflow_rows:
            digest = row["source_identity_digest"]
            if (
                row["source_kind"] != "OWNER_CONFIRMATION"
                or row["source_method"] != "OWNER_CONFIRMED_FIFO_NON_SALE_MOVEMENT"
                or row["source_status"] != "OWNER_CONFIRMED"
                or row["provenance"] != "OWNER_CONFIRMED"
                or row["completeness"] != "OWNER_CONFIRMED"
                or row["coverage_status"] != "OWNER_CONFIRMED"
                or row["inventory_cutoff"] != anchor_cutoff_date
                or not cls._valid_digest(digest)
                or row["reason_code"] not in cls._OUTFLOW_REASONS
                or refs_by_outflow.get(row["event_id"], set()) != {("OTHER", digest)}
                or row["event_id"] not in outflow_command_revisions
            ):
                return {
                    "complete": False,
                    "reason_code": "FIFO_MOVEMENT_EVIDENCE_UNCONFIRMED",
                }
            sales.append(FifoDatedAllocationEvent(
                event=FifoOutflowEvent(
                    row["event_id"], row["quantity"], row["reason_code"],
                ),
                effective_at=row["effective_at"],
                effective_date=row["effective_date"],
                source_identity_digest=digest,
                physical_time_confirmed=True,
                cutoff_bridge_confirmed=(cutoff_status == "RECONCILED"),
                movement_reason_confirmed=True,
            ))
        if hypothetical_outflow is not None:
            sales.append(FifoDatedAllocationEvent(
                event=FifoOutflowEvent(
                    "evt_" + hypothetical_outflow["source_identity_digest"][:32],
                    hypothetical_outflow["quantity"],
                    hypothetical_outflow["reason_code"],
                ),
                effective_at=None,
                effective_date=hypothetical_outflow["effective_date"],
                source_identity_digest=hypothetical_outflow["source_identity_digest"],
                physical_time_confirmed=True,
                cutoff_bridge_confirmed=(cutoff_status == "RECONCILED"),
                movement_reason_confirmed=True,
            ))
        rate_rows = connection.execute(
            """SELECT r.rate_change_id, r.effective_date, r.unit_cost_rub
               FROM fifo_cost_rate_changes AS r
               WHERE r.stream_id=? AND NOT EXISTS (
                   SELECT 1 FROM fifo_cost_rate_cancellations AS c
                   WHERE c.stream_id=r.stream_id
                     AND c.rate_change_id=r.rate_change_id
               )
               ORDER BY r.rate_sequence LIMIT 2""",
            (stream_id,),
        ).fetchall()
        if hypothetical_open_rate is not None and rate_rows:
            return {
                "complete": False,
                "reason_code": "FIFO_REPLAY_RATE_TRANSITION_UNSUPPORTED",
            }
        if len(rate_rows) > 1:
            return {
                "complete": False,
                "reason_code": "FIFO_REPLAY_RATE_TRANSITION_UNSUPPORTED",
            }
        open_rate = None
        open_rate_date = None
        if hypothetical_open_rate is not None:
            open_rate = hypothetical_open_rate
            open_rate_date = hypothetical_open_rate_effective_date
        elif rate_rows:
            rate = rate_rows[0]
            open_rate = FifoOpenCostRate(
                rate["rate_change_id"], rate["unit_cost_rub"],
            )
            open_rate_date = rate["effective_date"]
        return FifoCostReplayService().preview(
            layers=layers,
            events=sales,
            stream_revision=stream_revision,
            expected_allocation_revision=allocation_revision,
            source_set_fingerprint=source_fingerprint,
            anchor_cutoff_date=anchor_cutoff_date,
            anchor_status=anchor_status,
            cutoff_status=cutoff_status,
            source_completeness="COMPLETE",
            open_rate=open_rate,
            open_rate_effective_date=open_rate_date,
        )

    @classmethod
    def _allocation_source_fingerprint(
        cls, connection, stream_id, stream_revision, policy_version, cutoff_status,
        *, hypothetical_rate=None,
    ):
        queries = {
            "events": "SELECT event_id, event_kind, effective_at, effective_date, quantity, "
                "unit_cost_rub, source_fingerprint, provenance, completeness, "
                "source_identity_digest, supersedes_event_id, reason_code "
                "FROM fifo_cost_events WHERE stream_id=? ORDER BY event_id",
            "layers": "SELECT layer_id, event_id, layer_sequence, quantity, unit_cost_rub, "
                "effective_at, effective_date, provenance, source_id "
                "FROM fifo_cost_layers WHERE stream_id=? ORDER BY layer_sequence",
            "rates": "SELECT rate_change_id, rate_sequence, effective_date, unit_cost_rub, purchase_cost_rub, "
                "delivery_cost_rub, packaging_cost_rub, payload_fingerprint "
                "FROM fifo_cost_rate_changes WHERE stream_id=? ORDER BY rate_sequence",
            "rate_cancellations": "SELECT cancellation_id, stream_revision, rate_change_id, "
                "rate_sequence, effective_date, reason_code, preview_fingerprint, "
                "source_set_fingerprint, idempotency_key FROM fifo_cost_rate_cancellations "
                "WHERE stream_id=? ORDER BY stream_revision, cancellation_id",
            "reconciliations": "SELECT transition_rate_sequence, reconciled_rate_sequence, "
                "effective_date, reconciled_total_units, older_finite_units, "
                "prior_rate_units, source_fingerprint FROM fifo_cost_rate_reconciliations "
                "WHERE stream_id=? ORDER BY transition_rate_sequence",
            "supplies": "SELECT snapshot_sequence, source_fingerprint, evidence_fingerprint, "
                "source_status, physical_effective_date FROM fifo_cost_supply_evidence "
                "WHERE stream_id=? ORDER BY snapshot_sequence",
            "return_basis": "SELECT b.return_event_id, b.basis_line_number, "
                "b.allocation_id, b.allocation_line_number, b.origin_sale_event_id, "
                "b.layer_id, b.rate_change_id, b.quantity, b.unit_cost_rub, "
                "b.total_cost_rub FROM fifo_cost_return_basis AS b "
                "JOIN fifo_cost_events AS e ON e.event_id=b.return_event_id "
                "WHERE e.stream_id=? ORDER BY b.return_event_id, b.basis_line_number",
        }
        material = {}
        for name, query in queries.items():
            rows = connection.execute(query + " LIMIT 100001", (stream_id,)).fetchall()
            if len(rows) > 100_000:
                raise ValueError("FIFO_REPLAY_INPUT_LIMIT")
            material[name] = [dict(row) for row in rows]
        if hypothetical_rate is not None:
            if not isinstance(hypothetical_rate, dict) or set(hypothetical_rate) != {
                "rate_change_id", "rate_sequence", "effective_date", "unit_cost_rub",
                "purchase_cost_rub", "delivery_cost_rub", "packaging_cost_rub",
                "payload_fingerprint",
            }:
                raise ValueError("FIFO_RATE_INPUT_INVALID")
            existing_rate_ids = {
                row["rate_change_id"] for row in material["rates"]
            }
            existing_sequences = {row["rate_sequence"] for row in material["rates"]}
            if (
                hypothetical_rate["rate_change_id"] in existing_rate_ids
                or hypothetical_rate["rate_sequence"] in existing_sequences
                or type(hypothetical_rate["rate_sequence"]) is not int
                or hypothetical_rate["rate_sequence"] < 1
                or not cls._valid_digest(hypothetical_rate["payload_fingerprint"])
            ):
                raise ValueError("FIFO_RATE_REVISION_CONFLICT")
            material["rates"].append(dict(hypothetical_rate))
            material["rates"].sort(key=lambda row: row["rate_sequence"])
        material.update({
            "stream_revision": stream_revision,
            "policy_version": policy_version,
            "cutoff_status": cutoff_status,
        })
        return cls._sha256(material)


    def _initialize_schema(self, connection):
        """Create the additive FIFO schema atomically and reject unknown versions."""
        version_before_transaction = self._read_schema_version(connection)
        rate_columns = {
            str(row[1]) for row in
            connection.execute("PRAGMA table_info(fifo_cost_rate_changes)")
        }
        needs_rate_rebuild = (
            0 < version_before_transaction < self.SCHEMA_VERSION
            and "cost_input_mode" not in rate_columns
        )
        foreign_keys_disabled = False
        try:
            if needs_rate_rebuild:
                connection.execute("PRAGMA foreign_keys=OFF")
                foreign_keys_disabled = True
                if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 0:
                    raise sqlite3.DatabaseError("could not disable FIFO migration foreign keys")

            connection.execute("BEGIN IMMEDIATE")
            version = self._read_schema_version(connection)
            if version > self.SCHEMA_VERSION:
                raise sqlite3.DatabaseError("unsupported FIFO cost schema version")
            if version not in range(0, self.SCHEMA_VERSION + 1):
                raise sqlite3.DatabaseError("unsupported FIFO cost schema version")

            self._create_tables(connection)
            self._migrate_schema(connection, version)
            self._create_indexes(connection)
            self._create_append_only_guards(connection)

            if version == 0:
                connection.execute(
                    "INSERT INTO fifo_cost_schema(singleton, version) VALUES (1, ?)",
                    (self.SCHEMA_VERSION,),
                )
            elif version < self.SCHEMA_VERSION:
                connection.execute(
                    "UPDATE fifo_cost_schema SET version=? WHERE singleton=1",
                    (self.SCHEMA_VERSION,),
                )
            self._validate_schema_metadata(connection)
            if version < self.SCHEMA_VERSION:
                violations = connection.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise sqlite3.DatabaseError("FIFO schema migration foreign key check failed")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            if foreign_keys_disabled:
                connection.execute("PRAGMA foreign_keys=ON")
                if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                    raise sqlite3.DatabaseError("could not restore FIFO migration foreign keys")

    @staticmethod
    def _read_schema_version(connection):
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fifo_cost_schema'"
        ).fetchone() is not None
        if not exists:
            return 0

        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(fifo_cost_schema)")
        }
        if not {"singleton", "version"} <= columns:
            raise sqlite3.DatabaseError("invalid FIFO cost schema metadata")
        rows = connection.execute(
            "SELECT singleton, version FROM fifo_cost_schema"
        ).fetchall()
        if len(rows) != 1 or rows[0]["singleton"] != 1:
            raise sqlite3.DatabaseError("invalid FIFO cost schema metadata")
        value = rows[0]["version"]
        if type(value) is not int or value < 1:
            raise sqlite3.DatabaseError("invalid FIFO cost schema metadata")
        return value

    @staticmethod
    def _create_tables(connection):
        statements = """
            CREATE TABLE IF NOT EXISTS fifo_cost_schema (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                version INTEGER NOT NULL CHECK(version >= 1)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_streams (
                stream_id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                product_id TEXT,
                offer_id TEXT,
                sku TEXT NOT NULL,
                identity_fingerprint TEXT NOT NULL,
                policy_version INTEGER NOT NULL CHECK(policy_version >= 1),
                state TEXT NOT NULL CHECK(state IN (
                    'LEGACY', 'FIFO_PENDING_ANCHOR', 'FIFO_READY',
                    'FIFO_PARTIAL', 'FIFO_CONFLICT', 'FIFO_SOURCE_BLOCKED'
                )),
                revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK(length(trim(store_id)) > 0),
                CHECK(length(trim(sku)) > 0),
                CHECK(product_id IS NOT NULL OR offer_id IS NOT NULL),
                UNIQUE(store_id, identity_fingerprint, policy_version)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_sources (
                source_id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_method TEXT NOT NULL,
                source_status TEXT NOT NULL CHECK(source_status IN (
                    'COMPLETE', 'PARTIAL', 'UNAVAILABLE', 'STALE', 'CONFLICT',
                    'NOT_REQUESTED', 'OWNER_CONFIRMED', 'MODEL_ONLY'
                )),
                provenance TEXT NOT NULL CHECK(provenance IN (
                    'OWNER_CONFIRMED', 'OZON_CONFIRMED_FIELD',
                    'DOCUMENT_RECONCILED', 'LEGACY_DATED_COST', 'MODEL_ASSUMPTION'
                )),
                source_fingerprint TEXT NOT NULL,
                captured_at TEXT,
                source_as_of TEXT,
                coverage_status TEXT NOT NULL,
                record_count INTEGER CHECK(record_count IS NULL OR record_count >= 0),
                page_count INTEGER CHECK(page_count IS NULL OR page_count >= 0),
                created_at TEXT NOT NULL,
                UNIQUE(store_id, source_fingerprint)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_source_refs (
                source_ref_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES fifo_cost_sources(source_id),
                reference_kind TEXT NOT NULL,
                reference_digest TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(source_id, reference_kind, reference_digest)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_policy_revisions (
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                policy_version INTEGER NOT NULL CHECK(policy_version >= 1),
                policy_json TEXT NOT NULL,
                policy_fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(stream_id, policy_version)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_events (
                event_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                event_kind TEXT NOT NULL CHECK(event_kind IN (
                    'OPENING_FIFO_ANCHOR', 'COST_LAYER_RECEIPT',
                    'INVENTORY_TRANSFER', 'PHYSICAL_SALE', 'SALE_CANCELLATION',
                    'SALEABLE_RETURN_RESTOCK', 'NON_SALE_OUTFLOW', 'CORRECTION'
                )),
                event_schema_version INTEGER NOT NULL CHECK(event_schema_version >= 1),
                effective_at TEXT,
                effective_date TEXT,
                recorded_at TEXT NOT NULL,
                captured_at TEXT,
                source_as_of TEXT,
                inventory_cutoff TEXT,
                quantity INTEGER NOT NULL CHECK(quantity > 0 AND quantity <= 100000),
                unit_cost_rub TEXT,
                purchase_cost_rub TEXT,
                delivery_cost_rub TEXT,
                packaging_cost_rub TEXT,
                currency TEXT NOT NULL DEFAULT 'RUB' CHECK(currency = 'RUB'),
                location_from TEXT,
                location_to TEXT,
                source_id TEXT REFERENCES fifo_cost_sources(source_id),
                source_fingerprint TEXT,
                provenance TEXT NOT NULL CHECK(provenance IN (
                    'OWNER_CONFIRMED', 'OZON_CONFIRMED_FIELD',
                    'DOCUMENT_RECONCILED', 'LEGACY_DATED_COST', 'MODEL_ASSUMPTION'
                )),
                completeness TEXT NOT NULL CHECK(completeness IN (
                    'COMPLETE', 'PARTIAL', 'UNAVAILABLE', 'STALE', 'CONFLICT',
                    'NOT_REQUESTED', 'OWNER_CONFIRMED', 'MODEL_ONLY'
                )),
                source_identity_digest TEXT,
                supersedes_event_id TEXT REFERENCES fifo_cost_events(event_id),
                reason_code TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_layers (
                layer_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                event_id TEXT NOT NULL REFERENCES fifo_cost_events(event_id),
                layer_sequence INTEGER NOT NULL CHECK(layer_sequence >= 1),
                quantity INTEGER NOT NULL CHECK(quantity > 0 AND quantity <= 100000),
                unit_cost_rub TEXT NOT NULL,
                currency TEXT NOT NULL DEFAULT 'RUB' CHECK(currency = 'RUB'),
                effective_at TEXT,
                effective_date TEXT,
                provenance TEXT NOT NULL CHECK(provenance IN (
                    'OWNER_CONFIRMED', 'OZON_CONFIRMED_FIELD',
                    'DOCUMENT_RECONCILED', 'LEGACY_DATED_COST', 'MODEL_ASSUMPTION'
                )),
                source_id TEXT REFERENCES fifo_cost_sources(source_id),
                created_at TEXT NOT NULL,
                UNIQUE(stream_id, layer_sequence)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_projections (
                stream_id TEXT PRIMARY KEY REFERENCES fifo_cost_streams(stream_id),
                revision INTEGER NOT NULL CHECK(revision >= 0),
                state TEXT NOT NULL CHECK(state IN (
                    'LEGACY', 'FIFO_PENDING_ANCHOR', 'FIFO_READY',
                    'FIFO_PARTIAL', 'FIFO_CONFLICT', 'FIFO_SOURCE_BLOCKED'
                )),
                known_quantity INTEGER CHECK(known_quantity IS NULL OR
                    (known_quantity >= 0 AND known_quantity <= 1000000)),
                known_cost_rub TEXT,
                next_unit_cost_rub TEXT,
                queue_complete INTEGER NOT NULL CHECK(queue_complete IN (0, 1)),
                cutoff_status TEXT NOT NULL,
                inventory_cutoff TEXT,
                source_set_fingerprint TEXT,
                last_event_id TEXT REFERENCES fifo_cost_events(event_id),
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_rate_changes (
                rate_change_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                stream_revision INTEGER NOT NULL CHECK(stream_revision >= 1),
                rate_sequence INTEGER NOT NULL CHECK(rate_sequence >= 1),
                effective_date TEXT NOT NULL,
                unit_cost_rub TEXT NOT NULL,
                cost_input_mode TEXT NOT NULL DEFAULT 'COMPONENTS'
                    CHECK(cost_input_mode IN ('COMPONENTS', 'TOTAL_LANDED')),
                purchase_cost_rub TEXT,
                delivery_cost_rub TEXT,
                packaging_cost_rub TEXT,
                owner_old_home_units INTEGER NOT NULL CHECK(
                    owner_old_home_units >= 0 AND owner_old_home_units <= 1000000
                ),
                source_id TEXT NOT NULL REFERENCES fifo_cost_sources(source_id),
                source_fingerprint TEXT NOT NULL,
                payload_fingerprint TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                UNIQUE(stream_id, rate_sequence),
                UNIQUE(stream_id, idempotency_key),
                CHECK(
                    (cost_input_mode='COMPONENTS'
                     AND purchase_cost_rub IS NOT NULL
                     AND delivery_cost_rub IS NOT NULL
                     AND packaging_cost_rub IS NOT NULL)
                    OR
                    (cost_input_mode='TOTAL_LANDED'
                     AND purchase_cost_rub IS NULL
                     AND delivery_cost_rub IS NULL
                     AND packaging_cost_rub IS NULL)
                )
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_rate_reconciliations (
                reconciliation_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                stream_revision INTEGER NOT NULL CHECK(stream_revision >= 2),
                transition_rate_sequence INTEGER NOT NULL CHECK(
                    transition_rate_sequence >= 2
                ),
                reconciled_rate_sequence INTEGER NOT NULL CHECK(
                    reconciled_rate_sequence >= 1
                ),
                effective_date TEXT NOT NULL,
                reconciled_total_units INTEGER NOT NULL CHECK(
                    reconciled_total_units >= 0 AND reconciled_total_units <= 1000000
                ),
                older_finite_units INTEGER NOT NULL CHECK(
                    older_finite_units >= 0 AND older_finite_units <= 1000000
                ),
                prior_rate_units INTEGER NOT NULL CHECK(
                    prior_rate_units >= 0 AND prior_rate_units <= 1000000
                ),
                fbo_units INTEGER NOT NULL CHECK(fbo_units >= 0 AND fbo_units <= 1000000),
                reserved_units INTEGER NOT NULL CHECK(
                    reserved_units >= 0 AND reserved_units <= fbo_units
                ),
                transit_units INTEGER NOT NULL CHECK(
                    transit_units >= 0 AND transit_units <= 1000000
                ),
                home_units INTEGER NOT NULL CHECK(home_units >= 0 AND home_units <= 1000000),
                source_fingerprint TEXT NOT NULL CHECK(length(source_fingerprint) = 64),
                captured_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                CHECK(transition_rate_sequence = reconciled_rate_sequence + 1),
                CHECK(reconciled_total_units = fbo_units + transit_units + home_units),
                CHECK(reconciled_total_units = older_finite_units + prior_rate_units),
                UNIQUE(stream_id, transition_rate_sequence),
                UNIQUE(stream_id, reconciled_rate_sequence)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_supply_evidence (
                evidence_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                snapshot_sequence INTEGER NOT NULL CHECK(snapshot_sequence >= 1),
                stream_revision INTEGER NOT NULL CHECK(stream_revision >= 0),
                source_id TEXT NOT NULL REFERENCES fifo_cost_sources(source_id),
                source_fingerprint TEXT NOT NULL CHECK(length(source_fingerprint) = 64),
                evidence_fingerprint TEXT NOT NULL CHECK(length(evidence_fingerprint) = 64),
                order_digest TEXT NOT NULL CHECK(length(order_digest) = 64),
                supply_digest TEXT NOT NULL CHECK(length(supply_digest) = 64),
                source_status TEXT NOT NULL CHECK(source_status = 'COMPLETE'),
                captured_at TEXT NOT NULL,
                source_as_of TEXT CHECK(source_as_of IS NULL),
                physical_effective_at TEXT CHECK(physical_effective_at IS NULL),
                physical_effective_date TEXT CHECK(physical_effective_date IS NULL),
                normalized_evidence_json TEXT NOT NULL CHECK(
                    length(normalized_evidence_json) <= 65536
                ),
                created_at TEXT NOT NULL,
                UNIQUE(stream_id, evidence_fingerprint),
                UNIQUE(stream_id, snapshot_sequence)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_return_basis (
                return_event_id TEXT NOT NULL REFERENCES fifo_cost_events(event_id),
                basis_line_number INTEGER NOT NULL CHECK(basis_line_number >= 1),
                allocation_id TEXT NOT NULL REFERENCES fifo_cost_allocations(allocation_id),
                allocation_line_number INTEGER NOT NULL CHECK(allocation_line_number >= 1),
                origin_sale_event_id TEXT NOT NULL REFERENCES fifo_cost_events(event_id),
                layer_id TEXT REFERENCES fifo_cost_layers(layer_id),
                rate_change_id TEXT REFERENCES fifo_cost_rate_changes(rate_change_id),
                quantity INTEGER NOT NULL CHECK(quantity > 0 AND quantity <= 100000),
                unit_cost_rub TEXT NOT NULL,
                total_cost_rub TEXT NOT NULL,
                PRIMARY KEY(return_event_id, basis_line_number),
                CHECK((layer_id IS NULL) != (rate_change_id IS NULL))
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_late_entry_drafts (
                draft_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                expected_revision INTEGER NOT NULL CHECK(expected_revision >= 0),
                evidence_fingerprint TEXT NOT NULL CHECK(length(evidence_fingerprint) = 64),
                source_fingerprint TEXT NOT NULL CHECK(length(source_fingerprint) = 64),
                order_digest TEXT NOT NULL CHECK(length(order_digest) = 64),
                supply_digest TEXT NOT NULL CHECK(length(supply_digest) = 64),
                owner_effective_date TEXT NOT NULL,
                owner_old_home_units INTEGER NOT NULL CHECK(
                    owner_old_home_units >= 0 AND owner_old_home_units <= 1000000
                ),
                accepted_units INTEGER NOT NULL CHECK(
                    accepted_units > 0 AND accepted_units <= 1000000
                ),
                purchase_cost_rub TEXT NOT NULL,
                delivery_cost_rub TEXT NOT NULL,
                packaging_cost_rub TEXT NOT NULL,
                unit_cost_rub TEXT NOT NULL,
                payload_fingerprint TEXT NOT NULL CHECK(length(payload_fingerprint) = 64),
                recorded_at TEXT NOT NULL,
                UNIQUE(stream_id, payload_fingerprint),
                FOREIGN KEY(stream_id, evidence_fingerprint)
                    REFERENCES fifo_cost_supply_evidence(stream_id, evidence_fingerprint)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_late_entry_corrections (
                correction_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                stream_revision INTEGER NOT NULL CHECK(stream_revision >= 1),
                draft_id TEXT NOT NULL REFERENCES fifo_cost_late_entry_drafts(draft_id),
                rate_change_id TEXT NOT NULL UNIQUE
                    REFERENCES fifo_cost_rate_changes(rate_change_id),
                effective_date TEXT NOT NULL,
                unit_cost_rub TEXT NOT NULL,
                reason_code TEXT NOT NULL CHECK(reason_code='OWNER_REPORTED_LATE'),
                preview_fingerprint TEXT NOT NULL CHECK(length(preview_fingerprint) = 64),
                reconstruction_fingerprint TEXT NOT NULL
                    CHECK(length(reconstruction_fingerprint) = 64),
                source_set_fingerprint TEXT NOT NULL
                    CHECK(length(source_set_fingerprint) = 64),
                allocation_revision INTEGER NOT NULL CHECK(allocation_revision >= 0),
                tax_policy_fingerprint TEXT NOT NULL
                    CHECK(length(tax_policy_fingerprint) = 64),
                period_source_fingerprints_json TEXT NOT NULL CHECK(
                    length(period_source_fingerprints_json) <= 65536
                ),
                impact_json TEXT NOT NULL CHECK(length(impact_json) <= 65536),
                idempotency_key TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                UNIQUE(stream_id, draft_id),
                UNIQUE(stream_id, idempotency_key)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_rate_cancellations (
                cancellation_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                stream_revision INTEGER NOT NULL CHECK(stream_revision >= 1),
                rate_change_id TEXT NOT NULL REFERENCES fifo_cost_rate_changes(rate_change_id),
                rate_sequence INTEGER NOT NULL CHECK(rate_sequence >= 1),
                effective_date TEXT NOT NULL,
                reason_code TEXT NOT NULL CHECK(reason_code='CANCELLED_FUTURE_CHANGE'),
                preview_fingerprint TEXT NOT NULL CHECK(length(preview_fingerprint) = 64),
                source_set_fingerprint TEXT NOT NULL CHECK(length(source_set_fingerprint) = 64),
                idempotency_key TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                UNIQUE(stream_id, rate_change_id),
                UNIQUE(stream_id, idempotency_key)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_allocations (
                allocation_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                revision INTEGER NOT NULL CHECK(revision >= 1),
                stream_revision INTEGER NOT NULL DEFAULT 0 CHECK(stream_revision >= 0),
                policy_version INTEGER NOT NULL CHECK(policy_version >= 1),
                source_set_fingerprint TEXT NOT NULL,
                cutoff_status TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'COMPLETE', 'PARTIAL', 'CONFLICT', 'SOURCE_BLOCKED'
                )),
                created_at TEXT NOT NULL,
                UNIQUE(stream_id, revision)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_allocation_lines (
                allocation_id TEXT NOT NULL REFERENCES fifo_cost_allocations(allocation_id),
                line_number INTEGER NOT NULL CHECK(line_number >= 1),
                event_id TEXT NOT NULL REFERENCES fifo_cost_events(event_id),
                layer_id TEXT NOT NULL REFERENCES fifo_cost_layers(layer_id),
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                unit_cost_rub TEXT NOT NULL,
                total_cost_rub TEXT NOT NULL,
                basis_allocation_id TEXT,
                basis_line_number INTEGER,
                PRIMARY KEY(allocation_id, line_number),
                CHECK((basis_allocation_id IS NULL) = (basis_line_number IS NULL))
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_allocation_outflow_lines (
                allocation_id TEXT NOT NULL REFERENCES fifo_cost_allocations(allocation_id),
                line_number INTEGER NOT NULL CHECK(line_number >= 1),
                event_id TEXT NOT NULL REFERENCES fifo_cost_events(event_id),
                layer_id TEXT NOT NULL REFERENCES fifo_cost_layers(layer_id),
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                unit_cost_rub TEXT NOT NULL,
                estimated_value_rub TEXT NOT NULL,
                valuation_method TEXT NOT NULL CHECK(
                    valuation_method='FIFO_FINITE_LAYER_ESTIMATE'
                ),
                PRIMARY KEY(allocation_id, line_number)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_allocation_rate_lines (
                allocation_id TEXT NOT NULL REFERENCES fifo_cost_allocations(allocation_id),
                line_number INTEGER NOT NULL CHECK(line_number >= 1),
                event_id TEXT NOT NULL REFERENCES fifo_cost_events(event_id),
                rate_change_id TEXT NOT NULL REFERENCES fifo_cost_rate_changes(rate_change_id),
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                unit_cost_rub TEXT NOT NULL,
                total_cost_rub TEXT NOT NULL,
                basis_allocation_id TEXT,
                basis_line_number INTEGER,
                PRIMARY KEY(allocation_id, line_number),
                CHECK((basis_allocation_id IS NULL) = (basis_line_number IS NULL))
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_idempotency (
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                idempotency_key TEXT NOT NULL,
                payload_fingerprint TEXT NOT NULL,
                result_reference TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(stream_id, idempotency_key)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_commands (
                command_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL REFERENCES fifo_cost_streams(stream_id),
                stream_revision INTEGER NOT NULL CHECK(stream_revision >= 1),
                payload_fingerprint TEXT NOT NULL,
                source_fingerprint TEXT NOT NULL,
                event_count INTEGER NOT NULL CHECK(event_count > 0 AND event_count <= 100),
                created_at TEXT NOT NULL,
                UNIQUE(stream_id, stream_revision)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_command_events (
                command_id TEXT NOT NULL REFERENCES fifo_cost_commands(command_id),
                event_id TEXT NOT NULL REFERENCES fifo_cost_events(event_id),
                event_order INTEGER NOT NULL CHECK(event_order >= 1),
                PRIMARY KEY(command_id, event_order),
                UNIQUE(command_id, event_id)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_transition_cases (
                case_id TEXT PRIMARY KEY,
                schema_version INTEGER NOT NULL CHECK(schema_version = 1),
                owner_fingerprint TEXT NOT NULL CHECK(length(owner_fingerprint) = 64),
                tenant_fingerprint TEXT NOT NULL CHECK(length(tenant_fingerprint) = 64),
                store_id TEXT NOT NULL,
                product_id TEXT,
                offer_id TEXT,
                sku TEXT NOT NULL,
                current_revision INTEGER NOT NULL CHECK(current_revision >= 1),
                current_state TEXT NOT NULL CHECK(current_state IN (
                    'DRAFT', 'AWAITING_EVIDENCE', 'READY_TO_CONFIRM', 'APPLIED', 'CANCELLED'
                )),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK(product_id IS NOT NULL OR offer_id IS NOT NULL),
                UNIQUE(tenant_fingerprint, store_id, case_id)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_transition_case_revisions (
                revision_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES fifo_cost_transition_cases(case_id),
                case_revision INTEGER NOT NULL CHECK(case_revision >= 1),
                schema_version INTEGER NOT NULL CHECK(schema_version = 1),
                state TEXT NOT NULL CHECK(state IN (
                    'DRAFT', 'AWAITING_EVIDENCE', 'READY_TO_CONFIRM', 'APPLIED', 'CANCELLED'
                )),
                payload_json TEXT NOT NULL CHECK(length(payload_json) <= 262144),
                payload_fingerprint TEXT NOT NULL CHECK(length(payload_fingerprint) = 64),
                idempotency_key TEXT NOT NULL CHECK(length(idempotency_key) BETWEEN 1 AND 128),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(case_id, case_revision),
                UNIQUE(case_id, idempotency_key)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_supply_declarations (
                declaration_row_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES fifo_cost_transition_cases(case_id),
                declaration_id TEXT NOT NULL,
                declaration_revision INTEGER NOT NULL CHECK(declaration_revision >= 1),
                reference_kind TEXT NOT NULL CHECK(reference_kind IN ('ORDER', 'SUPPLY')),
                reference_digest TEXT NOT NULL CHECK(length(reference_digest) = 64),
                encrypted_lookup_reference TEXT CHECK(
                    encrypted_lookup_reference IS NULL OR length(encrypted_lookup_reference) <= 4096
                ),
                declared_shipped_units INTEGER CHECK(
                    declared_shipped_units IS NULL OR
                    (declared_shipped_units >= 0 AND declared_shipped_units <= 1000000)
                ),
                dispatch_date TEXT,
                provenance TEXT NOT NULL CHECK(provenance = 'OWNER_INPUT'),
                payload_json TEXT NOT NULL CHECK(length(payload_json) <= 65536),
                payload_fingerprint TEXT NOT NULL CHECK(length(payload_fingerprint) = 64),
                recorded_at TEXT NOT NULL,
                UNIQUE(case_id, declaration_id, declaration_revision)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_supply_observations (
                observation_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES fifo_cost_transition_cases(case_id),
                declaration_id TEXT NOT NULL,
                declaration_revision INTEGER NOT NULL CHECK(declaration_revision >= 1),
                captured_at TEXT NOT NULL,
                source_as_of TEXT,
                raw_status TEXT,
                normalized_status TEXT NOT NULL CHECK(normalized_status IN (
                    'DECLARED', 'AT_DROPOFF', 'IN_TRANSIT', 'RECEIVING',
                    'PARTIALLY_ACCEPTED', 'ACCEPTED', 'CANCELLED', 'UNKNOWN'
                )),
                declared_quantity INTEGER CHECK(
                    declared_quantity IS NULL OR
                    (declared_quantity >= 0 AND declared_quantity <= 1000000)
                ),
                accepted_quantity INTEGER CHECK(
                    accepted_quantity IS NULL OR
                    (accepted_quantity >= 0 AND accepted_quantity <= 1000000)
                ),
                accepted_quantity_kind TEXT CHECK(
                    accepted_quantity_kind IS NULL OR
                    accepted_quantity_kind IN ('CUMULATIVE', 'DOCUMENT_LINES')
                ),
                act_reference_digest TEXT CHECK(
                    act_reference_digest IS NULL OR length(act_reference_digest) = 64
                ),
                act_version_digest TEXT CHECK(
                    act_version_digest IS NULL OR length(act_version_digest) = 64
                ),
                presence TEXT NOT NULL CHECK(presence IN ('PRESENT', 'MISSING')),
                completeness TEXT NOT NULL CHECK(completeness IN ('COMPLETE', 'PARTIAL', 'UNKNOWN')),
                scope_complete INTEGER NOT NULL CHECK(scope_complete IN (0, 1)),
                pagination_complete INTEGER NOT NULL CHECK(pagination_complete IN (0, 1)),
                source_kind TEXT NOT NULL CHECK(source_kind = 'OZON_API'),
                source_fingerprint TEXT NOT NULL CHECK(length(source_fingerprint) = 64),
                payload_json TEXT NOT NULL CHECK(length(payload_json) <= 65536),
                UNIQUE(case_id, declaration_id, observation_id),
                CHECK((accepted_quantity IS NULL) = (accepted_quantity_kind IS NULL)),
                CHECK(presence <> 'MISSING' OR
                      (declared_quantity IS NULL AND accepted_quantity IS NULL))
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_report_evidence (
                report_evidence_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES fifo_cost_transition_cases(case_id),
                report_type TEXT NOT NULL CHECK(report_type IN ('STOCK_MANAGEMENT', 'TURNOVER')),
                period_from TEXT,
                period_to TEXT,
                period_provenance TEXT NOT NULL CHECK(period_provenance IN (
                    'FILENAME_CANDIDATE', 'OWNER_CONFIRMED', 'API_AS_OF', 'UNKNOWN'
                )),
                captured_at TEXT NOT NULL,
                file_sha256 TEXT NOT NULL CHECK(length(file_sha256) = 64),
                parser_version TEXT NOT NULL,
                source_kind TEXT NOT NULL CHECK(source_kind IN ('OWNER_IMPORTED', 'OZON_API')),
                completeness TEXT NOT NULL CHECK(completeness IN ('COMPLETE', 'PARTIAL', 'UNKNOWN')),
                source_fingerprint TEXT NOT NULL CHECK(length(source_fingerprint) = 64),
                cell_references_json TEXT NOT NULL CHECK(length(cell_references_json) <= 262144),
                normalized_fields_json TEXT NOT NULL CHECK(length(normalized_fields_json) <= 262144),
                UNIQUE(case_id, report_type, file_sha256)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_transition_previews (
                preview_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES fifo_cost_transition_cases(case_id),
                case_revision INTEGER NOT NULL CHECK(case_revision >= 1),
                fifo_revision INTEGER NOT NULL CHECK(fifo_revision >= 0),
                allocation_revision INTEGER NOT NULL CHECK(allocation_revision >= 0),
                evidence_set_fingerprint TEXT NOT NULL CHECK(length(evidence_set_fingerprint) = 64),
                tax_policy_fingerprint TEXT NOT NULL CHECK(length(tax_policy_fingerprint) = 64),
                preview_fingerprint TEXT NOT NULL CHECK(length(preview_fingerprint) = 64),
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                payload_json TEXT NOT NULL CHECK(length(payload_json) <= 262144),
                UNIQUE(case_id, preview_fingerprint)
            );

            CREATE TABLE IF NOT EXISTS fifo_cost_transition_commits (
                commit_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES fifo_cost_transition_cases(case_id),
                case_revision INTEGER NOT NULL CHECK(case_revision >= 1),
                preview_id TEXT NOT NULL UNIQUE
                    REFERENCES fifo_cost_transition_previews(preview_id),
                idempotency_key TEXT NOT NULL CHECK(length(idempotency_key) BETWEEN 1 AND 128),
                payload_fingerprint TEXT NOT NULL CHECK(length(payload_fingerprint) = 64),
                complete_through TEXT,
                committed_at TEXT NOT NULL,
                UNIQUE(case_id, idempotency_key)
            );
            """
        for statement in statements.split(";"):
            if statement.strip():
                connection.execute(statement)

    @staticmethod
    def _create_indexes(connection):
        statements = """
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_events_stream_order
                ON fifo_cost_events(stream_id, effective_date, recorded_at, event_id);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_layers_fifo_order
                ON fifo_cost_layers(stream_id, effective_date, layer_sequence, layer_id);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_allocations_stream_revision
                ON fifo_cost_allocations(stream_id, revision);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_commands_stream_revision
                ON fifo_cost_commands(stream_id, stream_revision);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_source_refs_digest
                ON fifo_cost_source_refs(reference_kind, reference_digest);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_rate_changes_order
                ON fifo_cost_rate_changes(stream_id, effective_date, rate_sequence);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_rate_reconciliations_order
                ON fifo_cost_rate_reconciliations(stream_id, transition_rate_sequence);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_supply_evidence_order
                ON fifo_cost_supply_evidence(stream_id, snapshot_sequence);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_late_entry_drafts_order
                ON fifo_cost_late_entry_drafts(stream_id, recorded_at, draft_id);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_rate_cancellations_stream
                ON fifo_cost_rate_cancellations(stream_id, stream_revision);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_transition_case_scope
                ON fifo_cost_transition_cases(
                    tenant_fingerprint, store_id, sku, updated_at, case_id
                );
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_transition_revisions_case
                ON fifo_cost_transition_case_revisions(case_id, case_revision);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_supply_declarations_case
                ON fifo_cost_supply_declarations(case_id, declaration_id, declaration_revision);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_supply_observations_case
                ON fifo_cost_supply_observations(case_id, declaration_id, captured_at);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_report_evidence_case
                ON fifo_cost_report_evidence(case_id, report_type, captured_at);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_transition_previews_expiry
                ON fifo_cost_transition_previews(case_id, expires_at);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_transition_commits_case
                ON fifo_cost_transition_commits(case_id, committed_at);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_fifo_cost_physical_sale_identity
                ON fifo_cost_events(stream_id, source_identity_digest)
                WHERE event_kind='PHYSICAL_SALE' AND source_identity_digest IS NOT NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS idx_fifo_cost_return_identity
                ON fifo_cost_events(stream_id, source_identity_digest)
                WHERE event_kind='SALEABLE_RETURN_RESTOCK' AND source_identity_digest IS NOT NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS idx_fifo_cost_non_sale_movement_identity
                ON fifo_cost_events(stream_id, source_identity_digest)
                WHERE event_kind='NON_SALE_OUTFLOW' AND source_identity_digest IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_return_basis_origin
                ON fifo_cost_return_basis(origin_sale_event_id, layer_id);
            CREATE INDEX IF NOT EXISTS idx_fifo_cost_outflow_allocation_event
                ON fifo_cost_allocation_outflow_lines(allocation_id, event_id);
            """
        for statement in statements.split(";"):
            if statement.strip():
                connection.execute(statement)

    @classmethod
    def _create_append_only_guards(cls, connection):
        for table in cls._APPEND_ONLY_TABLES:
            for operation in ("UPDATE", "DELETE"):
                trigger_name = f"trg_{table}_no_{operation.lower()}"
                connection.execute(
                    f"CREATE TRIGGER IF NOT EXISTS {trigger_name} "
                    f"BEFORE {operation} ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'FIFO evidence is append-only'); END"
                )

    def _validate_schema_metadata(self, connection):
        row = connection.execute(
            "SELECT singleton, version FROM fifo_cost_schema"
        ).fetchone()
        if (row is None or row["singleton"] != 1
                or row["version"] != self.SCHEMA_VERSION):
            raise sqlite3.DatabaseError("invalid FIFO cost schema metadata")
        allocation_columns = {
            str(item[1])
            for item in connection.execute("PRAGMA table_info(fifo_cost_allocations)")
        }
        rate_line_columns = {
            str(item[1])
            for item in connection.execute(
                "PRAGMA table_info(fifo_cost_allocation_rate_lines)"
            )
        }
        late_entry_columns = {
            str(item[1])
            for item in connection.execute(
                "PRAGMA table_info(fifo_cost_late_entry_drafts)"
            )
        }
        correction_columns = {
            str(item[1])
            for item in connection.execute(
                "PRAGMA table_info(fifo_cost_late_entry_corrections)"
            )
        }
        cancellation_columns = {
            str(item[1])
            for item in connection.execute(
                "PRAGMA table_info(fifo_cost_rate_cancellations)"
            )
        }
        rate_columns = {
            str(item[1])
            for item in connection.execute(
                "PRAGMA table_info(fifo_cost_rate_changes)"
            )
        }
        transition_required_columns = {
            "fifo_cost_transition_cases": {
                "case_id", "owner_fingerprint", "tenant_fingerprint", "store_id",
                "sku", "current_revision", "current_state",
            },
            "fifo_cost_transition_case_revisions": {
                "revision_id", "case_id", "case_revision", "payload_json",
                "payload_fingerprint", "idempotency_key",
            },
            "fifo_cost_supply_declarations": {
                "declaration_row_id", "case_id", "declaration_id",
                "declaration_revision", "reference_kind", "reference_digest",
                "encrypted_lookup_reference", "declared_shipped_units",
            },
            "fifo_cost_supply_observations": {
                "observation_id", "case_id", "declaration_id", "captured_at",
                "normalized_status", "presence", "completeness", "source_kind",
                "source_fingerprint",
            },
            "fifo_cost_report_evidence": {
                "report_evidence_id", "case_id", "report_type", "period_from",
                "period_to", "file_sha256", "normalized_fields_json",
            },
            "fifo_cost_transition_previews": {
                "preview_id", "case_id", "case_revision", "preview_fingerprint",
                "expires_at",
            },
            "fifo_cost_transition_commits": {
                "commit_id", "case_id", "case_revision", "preview_id",
                "idempotency_key", "payload_fingerprint", "committed_at",
            },
        }
        actual_transition_columns = {
            table: {
                str(item[1])
                for item in connection.execute(f"PRAGMA table_info({table})")
            }
            for table in transition_required_columns
        }
        legacy_schema_valid = (
            "stream_revision" in allocation_columns
            and {
                "allocation_id", "line_number", "event_id", "rate_change_id",
                "quantity", "unit_cost_rub", "total_cost_rub",
            } <= rate_line_columns
            and {
                "draft_id", "stream_id", "expected_revision", "evidence_fingerprint",
                "owner_effective_date", "accepted_units", "unit_cost_rub",
                "payload_fingerprint", "recorded_at",
            } <= late_entry_columns
            and {
                "correction_id", "stream_id", "stream_revision", "draft_id",
                "rate_change_id", "effective_date", "unit_cost_rub", "reason_code",
                "preview_fingerprint", "reconstruction_fingerprint",
                "source_set_fingerprint", "allocation_revision",
                "tax_policy_fingerprint", "period_source_fingerprints_json",
                "impact_json", "idempotency_key", "recorded_at",
            } <= correction_columns
            and {
                "cancellation_id", "stream_id", "stream_revision", "rate_change_id",
                "rate_sequence", "effective_date", "reason_code", "preview_fingerprint",
                "source_set_fingerprint", "idempotency_key", "recorded_at",
            } <= cancellation_columns
        )
        transition_schema_valid = (
            "cost_input_mode" in rate_columns
            and {
                "purchase_cost_rub", "delivery_cost_rub", "packaging_cost_rub",
            } <= rate_columns
            and all(
                required <= actual_transition_columns[table]
                for table, required in transition_required_columns.items()
            )
        )
        if not legacy_schema_valid or not transition_schema_valid:
            raise sqlite3.DatabaseError("invalid FIFO repository schema")

